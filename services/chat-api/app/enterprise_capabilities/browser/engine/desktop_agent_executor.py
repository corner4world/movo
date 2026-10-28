"""Execute a browser task via the connected desktop Local Agent.

Selected by the runtime dispatcher when ``agent_registry.get(user_id)``
reports an active WebSocket connection. Uses the same planner as the
generic ``browser_task`` skill but emits events in the subagent runtime's
``(event_dict, meta_dict)`` shape so the graph orchestrator can treat
the output through the standard runtime event contract.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timedelta
from typing import Any, AsyncIterator, Dict, List, Set, Tuple
from urllib.parse import urlparse

from app.browser.local_bridge import AgentNotConnected, LocalBridge
from app.browser.loop_policy import BROWSER_MAX_READS_PER_STATE, BROWSER_MAX_STEPS
from app.browser.tools import is_browser_tool, is_control_tool
from app.enterprise_capabilities.runtime.execution_contracts import CapabilityTask
from app.enterprise_capabilities.runtime.execution_contracts import CapabilityInputs
from app.enterprise_capabilities.browser.engine.action_contracts import (
    blocks_whole_node_replay as action_contract_blocks_whole_node_replay,
    describe_for_agent as action_contract_describe_for_agent,
    validate_data as action_contract_validate_data,
)
from app.services.skill_assets.publish_channels import publish_channel_registry
from app.services.skill_assets.composite_task import format_site_hints_for_goal
from app.services.site_profiles import site_profile_service
from app.enterprise_capabilities.browser.engine.agent_loop.protocol import (
    Decision, Observation, StepRecord,
)
from app.enterprise_capabilities.browser.engine.contexts import factory as context_factory
from app.enterprise_capabilities.browser.engine.contexts.action_transition import BrowserActionTransition
from app.enterprise_capabilities.browser.engine.context_action_transitions import context_action_transitions
from app.enterprise_capabilities.browser.engine.contexts.done_recovery import DoneBlockRecovery
from app.enterprise_capabilities.browser.engine.drivers import (
    apply_driver_resume_signal,
    notify_driver_rejection,
    notify_effect_receipt,
    notify_step_completed,
    prepare_driver_dispatch,
    select_driver,
)
from app.enterprise_capabilities.browser.engine.form_input import BrowserInputContext
from app.enterprise_capabilities.browser.engine.form_input.fill_retry import FillRetryPolicy, is_fill_reconciliation
from app.enterprise_capabilities.browser.engine.form_input.step_reconciliation import reconcile_input_step
from app.enterprise_capabilities.browser.engine.obstruction_evidence import obstruction_evidence, OBSTRUCTION_GUIDANCE
from app.enterprise_capabilities.browser.engine.passive_wait_recovery import recover_passive_wait
from app.enterprise_capabilities.browser.engine.form_input.target_preflight import (
    validate_fill_target,
)
from app.enterprise_capabilities.browser.engine.post_action_observation import (
    observation_retry_required,
    reconcile_post_action_observation,
)
from app.enterprise_capabilities.browser.engine.click_outcome import (
    ClickOutcome,
    ClickOutcomePolicy,
    effect_verification_eligible,
)
from app.enterprise_capabilities.browser.engine.interaction_target_recovery import (
    InteractionTargetRecovery,
    bind_coordinate_action,
    is_stale_interaction_target_error,
)
from app.enterprise_capabilities.browser.engine.transition_stabilizer import stabilize_transition_observation
from app.enterprise_capabilities.browser.engine.stagnation_budget import StagnationBudget
from app.browser.tool_deadlines import timeout_for_tool
from app.enterprise_capabilities.browser.engine.skill_fast_path import execute_skill_fast_path, prepare_skill_fast_path
from app.enterprise_capabilities.browser.engine.result_presenter import render_browser_result
from app.enterprise_capabilities.browser.engine.result_artifact import build_browser_result
from app.enterprise_capabilities.browser.engine.execution_budget import (
    BrowserExecutionBudget,
    BrowserExecutionBudgetExpired,
    build_budget_continuation,
    interrupted_effect_requires_handoff,
    unknown_effect_verification_question,
)
from app.enterprise_capabilities.browser.engine.operation_result_projection import (
    project_verified_operation_result,
)
from app.enterprise_capabilities.browser.engine.effect_receipt_flow import (
    applied_effect_task_outcome,
    apply_effect_receipt,
    build_effect_completion,
    build_effect_failure,
)
from app.enterprise_capabilities.browser.engine.effect_business_failure import build_effect_business_failure_events
from app.enterprise_capabilities.browser.engine.action_history import BrowserActionHistory
from app.enterprise_capabilities.browser.engine.alternative_target_recovery import (
    AlternativeTargetRecovery,
)
from app.enterprise_capabilities.browser.engine.completed_target_recovery import (
    CompletedTargetRecovery,
)
from app.enterprise_capabilities.browser.engine.target_history_policy import TargetHistoryState
from app.enterprise_capabilities.browser.engine.business_action import BusinessActionLedger
from app.enterprise_capabilities.browser.engine.observation_freshness import (
    complete_observation,
    invalidate_observation,
    requires_fresh_observation,
)
from app.enterprise_capabilities.browser.engine.initial_observation import acquire_initial_observation
from app.enterprise_capabilities.browser.engine.initial_entry_navigation import initial_entry_url
from app.enterprise_capabilities.browser.engine.entry_preflight import assess_entry_preflight
from app.enterprise_capabilities.browser.engine.progress_signature import browser_progress_signature
from app.enterprise_capabilities.browser.engine.loop_observation_policy import (
    READ_ONLY_TOOLS,
    is_technical_recovery_observation,
    observe_count_for_current_interaction_state,
    post_action_observation_check,
    read_count_for_current_state,
)
from app.enterprise_capabilities.browser.engine.loop_recovery import recovery_decision_after_guard_failure
from app.enterprise_capabilities.browser.engine.exploration_stagnation import assess_exploration_stagnation
from app.enterprise_capabilities.browser.engine.human_assistance_policy import (
    BrowserHumanAssistance,
    EXPLORATION_STAGNATION,
    NAVIGATION_STAGNATION,
    NAVIGATION_TARGET_BLOCKED,
    READ_BUDGET,
    browser_human_assistance,
)
from app.enterprise_capabilities.browser.engine.media_upload_assistance import (
    augment_form_assistance_handoff,
    build_media_upload_handoff,
    completed_media_candidate_ids,
    is_media_delivery_handoff_error,
    media_upload_assistance_decision,
)
from app.enterprise_capabilities.browser.engine.form_human_assistance import (
    FORM_COMMIT_CATEGORY,
    FORM_EFFECT_VERIFY_CATEGORY,
    FORM_TASK_COMPLETION_CATEGORY,
    build_effect_verification_decision,
    build_task_completion_confirmation_decision,
    manual_commit_receipt,
    manual_effect_receipt,
    resume_contract,
    resume_outcome,
)
from app.enterprise_capabilities.browser.engine.human_commit_reconciliation import (
    assess_human_commit_reconciliation,
)
from app.enterprise_capabilities.browser.engine.recovery_router import (
    INTERACTION_BLOCKED,
    LOOP_EXHAUSTED,
    MODEL_FAILURE,
    OUTPUT_CONTRACT_EXHAUSTED,
    RESUME_RECONCILIATION_UNAVAILABLE,
    BrowserRecoveryPlan,
    recovery_source_for_browser_fail,
    route_browser_recovery,
)
from app.enterprise_capabilities.browser.engine.navigation_provenance import assess_navigation_provenance
from app.enterprise_capabilities.browser.engine.visual_observation_guard import (
    redundant_visual_observation,
)
from app.enterprise_capabilities.browser.engine.auth_state import (
    AuthTransitionTracker,
    assessment_from_payload,
    site_scope,
)
from app.enterprise_capabilities.browser.engine.auth_intervention import (
    BrowserAuthIntervention,
    authentication_resume_is_blocked,
    suspend_browser_authentication,
)
from app.enterprise_capabilities.browser.engine.intervention_suspension import (
    browser_resume_context,
    suspend_browser_intervention,
)
from app.enterprise_capabilities.browser.engine.checkpoint import BrowserCheckpointSession
from app.enterprise_capabilities.browser.engine.wait_for_cache import (
    WaitForClickTarget,
    can_reuse_click_target,
    confirmed_click_target,
)
from app.enterprise_capabilities.browser.engine.workflow_cache import browser_workflow_cache
from app.enterprise_capabilities.browser.engine.workflow_cache.identity import site_id_for_node
from app.enterprise_capabilities.browser.engine.workflow_cache.learning_trace import WorkflowLearningTrace
from app.enterprise_capabilities.browser.engine.workflow_cache.admission import terminal_effect_allows_cache
from app.enterprise_capabilities.browser.engine.recording import human_recording_store
from app.enterprise_capabilities.browser.engine.entry_candidates import extract_candidate_entries
from app.enterprise_capabilities.browser.engine.business_site_scope import (
    resolve_business_site_scope,
    scope_node,
)
from app.enterprise_capabilities.browser.engine.action_resolution import resolve_wait_for_action
from app.enterprise_capabilities.browser.engine.wait_action_policy import should_resolve_wait_action
from app.enterprise_capabilities.browser.engine.human_recording_handoff import begin_recorded_human_handoff
from app.enterprise_capabilities.browser.engine.effect_verification import (
    enforce_commit_preconditions,
    EffectReceipt,
    EffectTracker,
    FormTransactionTracker,
    PreparedEffect,
    SemanticActionRejected,
    assess_effect_completion,
    resolve_effect_target,
)
from app.enterprise_capabilities.browser.engine.run_request import resolve_run_original_request


logger = logging.getLogger(__name__)


# Complex multi-page tasks need room for re-observation, navigation and
# bounded recovery. The stagnation and repeated-read guards below stop a
# single action pattern from monopolising the overall step budget.
MAX_STEPS = BROWSER_MAX_STEPS
MAX_CONSECUTIVE_FAILURES = 3
# Per-domain safe-URL recovery budget. When a login signal fires on an
# already-authenticated domain we bounce once to the last safe URL instead
# of re-entering the login flow. If the same domain keeps surfacing a
# DOM-level login form this many times in a row, we assume the session
# genuinely expired, drop the domain from the authenticated set, and fall
# through to the real login intervention. Intentionally small — one false
# positive bounce is cheap; letting a truly expired session spin is not.
MAX_LOGIN_RECOVERY_ATTEMPTS = 2
SPA_EMPTY_OBSERVE_RETRIES = 2
SPA_EMPTY_OBSERVE_WAIT_SECONDS = 1.2

# Landing-page URLs that the xiaohongshu creator SPA often returns
# before hydration. Any navigate to one of these during a publish flow
# gets rewritten to the resolved publish_url so the planner doesn't
# stall on the empty shell.
_XHS_LANDING_URLS: frozenset[str] = frozenset(
    {
        "https://creator.xiaohongshu.com",
        "https://creator.xiaohongshu.com/login",
        "https://creator.xiaohongshu.com/new/home",
    }
)

# Matches an explicit publish-page URL the user embedded in their goal
# (for example, a request to open the platform's video publishing URL).
# Such a URL overrides the yaml default for this task only.
_XHS_USER_PUBLISH_URL_RE = re.compile(
    r"https?://creator\.xiaohongshu\.com/publish/[^\s'\"<>)，。；]+",
    re.IGNORECASE,
)


def _detect_language(inputs: CapabilityInputs) -> str:
    explicit = str(getattr(inputs, "language", "") or "").strip().lower().replace("_", "-")
    if explicit.startswith("zh"):
        return "zh"
    if explicit.startswith("en"):
        return "en"
    for msg in reversed(list(inputs.messages or [])):
        text = str(getattr(msg, "content", "") or "")
        if re.search(r"[\u4e00-\u9fff]", text):
            return "zh"
    for msg in reversed(list(inputs.raw_messages or [])):
        text = str((msg or {}).get("content") or "") if isinstance(msg, dict) else ""
        if re.search(r"[\u4e00-\u9fff]", text):
            return "zh"
    if re.search(r"[\u4e00-\u9fff]", str(inputs.intent or "")):
        return "zh"
    return "en"


def _effect_timeline_message(status: str, reason: str, *, lang: str) -> str:
    if lang != "zh":
        return f"Operation result: {status} ({reason})"
    status_label = {
        "confirmed_success": "已确认成功",
        "confirmed_failure": "已确认失败",
        "pending_verification": "等待复核",
        "unknown": "结果待确认",
    }.get(str(status or ""), "结果待确认")
    reason_text = str(reason or "").strip()
    # Internal English diagnostics belong in logs, not a Chinese Timeline.
    suffix = f"（{reason_text}）" if re.search(r"[\u4e00-\u9fff]", reason_text) else ""
    return f"操作结果：{status_label}{suffix}"


def _extract_goal(node: CapabilityTask, inputs: CapabilityInputs) -> str:
    goal = str(getattr(node, "goal", "") or "").strip()
    if goal:
        return goal
    for msg in reversed(list(inputs.messages or [])):
        role = str(getattr(msg, "role", "") or "").lower()
        if role in ("user", "human"):
            text = str(getattr(msg, "content", "") or "").strip()
            if text:
                return text
    return ""


def _domain(url: str) -> str | None:
    try:
        host = urlparse(str(url)).hostname
        return host or None
    except Exception:
        return None


def _build_enterprise_sites_map(profiles: List[Dict[str, Any]]) -> Dict[str, str]:
    """Turn the user-visible site profiles into the flat {name: line} shape
    consumed by the browser planner.

    Each site collapses into one line that surfaces everything the LLM
    needs to navigate without guessing: host, entry URL, auth method,
    and a clipped hints blurb. This is *unconditional* context — the
    LLM should know where the user's intranet systems live regardless
    of whether a composite skill was also selected for this turn.
    """
    out: Dict[str, str] = {}
    for p in profiles or []:
        if not isinstance(p, dict):
            continue
        name = str(p.get("name") or "").strip()
        if not name:
            continue
        host = str(p.get("domain") or "").strip()
        entry_url = str(p.get("entry_url") or "").strip()
        auth = str(p.get("auth_method") or "").strip()
        hints = str(p.get("hints") or "").strip()
        parts: List[str] = []
        if host:
            parts.append(host)
        if entry_url and entry_url != host:
            parts.append(f"Entry URL: {entry_url}")
        if auth:
            parts.append(f"Authentication: {auth}")
        if hints:
            flat = " ".join(line.strip() for line in hints.splitlines() if line.strip())
            if flat:
                parts.append(f"Notes: {flat[:220]}")
        out[name] = " | ".join(parts) or name
    return out


def _digest(tool: str, result: Any) -> str:
    if not isinstance(result, dict):
        return ""
    if tool == "browser_observe":
        return f"{result.get('url','')} [{len(result.get('elements') or [])} els]"
    if tool == "browser_navigate":
        return str(result.get("url") or "")
    if tool == "browser_execute_plan":
        failed = next(
            (
                item for item in list(result.get("receipts") or [])
                if isinstance(item, dict) and item.get("status") == "failed"
            ),
            {},
        )
        failure = ""
        if failed:
            failure = (
                f"; failed_tool={str(failed.get('tool') or '')[:80]}"
                f"; action_error={str(failed.get('error') or '')[:200]}"
            )
        return (
            f"action-plan={str(result.get('status') or 'unknown')}; "
            f"completed={int(result.get('completed_actions') or 0)}; "
            f"reason={str(result.get('reason') or '')[:160]}{failure}"
        )
    if tool == "browser_wait_for":
        # Surface matched_ref / clickable_ref in history digest so subsequent
        # LLM turns see "my last wait_for gave me ref=X" instead of a blank
        # success — otherwise the model loops on the same text because it
        # can't remember that a ref came back.
        m = result.get("matched_ref") or ""
        c = result.get("clickable_ref") or ""
        f = result.get("fillable_ref") or ""
        txt = str(result.get("matched_text") or "")[:60]
        if c or f or m:
            parts = []
            if c:
                parts.append(f"click-ref={c}")
            if f:
                parts.append(f"fill-ref={f}")
            if m and m != c:
                parts.append(f"ref={m}")
            if txt:
                parts.append(f"text={txt!r}")
            return "matched: " + ", ".join(parts)
        if result.get("model_required"):
            candidates = list(result.get("candidates") or [])[:6]
            compact = [
                {
                    "ref": item.get("ref"),
                    "role": item.get("role"),
                    "name": item.get("name") or item.get("text"),
                }
                for item in candidates
                if isinstance(item, dict)
            ]
            return (
                f"model_required: {result.get('reason') or 'local_rule_unresolved'}; "
                f"candidates={json.dumps(compact, ensure_ascii=False)}"
            )
        return ""
    if tool == "browser_read_text":
        # LLM explicitly asked to read page text — it needs the content,
        # not an 80-char teaser. Keep up to ~6000 chars so the planner can
        # actually extract the displayed values on its next turn. (Agent
        # side caps at 50KB; we trim down to a prompt-safe length here.)
        return str(result.get("text") or "")[:6000]
    if tool == "browser_fill":
        receipt = result.get("fill_receipt")
        if isinstance(receipt, dict):
            return (
                f"fill={str(receipt.get('status') or 'unknown')}; "
                f"verification={str(receipt.get('verification') or 'unknown')}"
            )
    return ""


def _obs_from_payload(payload: Any) -> Observation | None:
    if not isinstance(payload, dict):
        return None
    nested = payload.get("observation")
    if isinstance(nested, dict):
        merged = dict(nested)
        if payload.get("screenshot") and not merged.get("screenshot"):
            merged["screenshot"] = payload.get("screenshot")
        if payload.get("screenshot_metadata") and not merged.get("screenshot_metadata"):
            merged["screenshot_metadata"] = payload.get("screenshot_metadata")
        return _obs_from_payload(merged)
    # The Tauri agent (agent/src/browser/observer.ts) sends `pageText` for
    # every observe / navigate response; older clients that don't yet
    # populate it fall back to empty string, which matches the dataclass
    # default and keeps the planner prompt shape stable.
    page_text = str(
        payload.get("pageText")
        or payload.get("page_text")
        or payload.get("page_text_snippet")
        or ""
    )
    return complete_observation(Observation(
        url=str(payload.get("url") or ""),
        title=str(payload.get("title") or ""),
        elements=list(payload.get("elements") or []),
        revision=str(payload.get("revision") or ""),
        screenshot=payload.get("screenshot"),
        clean_dom=payload.get("cleanDom") or payload.get("clean_dom"),
        dom_diff=payload.get("domDiff") or payload.get("dom_diff") or payload.get("axDelta") or payload.get("ax_delta"),
        page_text=page_text,
        auth=payload.get("auth") if isinstance(payload.get("auth"), dict) else None,
        frame_count=max(1, int(payload.get("frameCount") or payload.get("frame_count") or 1)),
        interaction=payload.get("interaction") if isinstance(payload.get("interaction"), dict) else None,
        effects=list(payload.get("effects") or []),
        diagnostics=payload.get("diagnostics") if isinstance(payload.get("diagnostics"), dict) else None,
        viewport=payload.get("viewport") if isinstance(payload.get("viewport"), dict) else None,
        screenshot_metadata=(
            payload.get("screenshot_metadata")
            if isinstance(payload.get("screenshot_metadata"), dict)
            else None
        ),
    ))


def _update_obs(current: Observation, tool: str, result: Any) -> Observation:
    if not isinstance(result, dict):
        return current
    if tool in {"browser_observe", "browser_execute_plan"}:
        return _obs_from_payload(result) or current
    if tool == "browser_navigate":
        # The agent (see agent/src/tools/browser_tools.ts::browser_navigate)
        # nests the full PageObservation under ``result.observation`` — that's
        # the only place ``pageText`` / ``elements`` live after a navigate.
        # The top level only carries url/title/screenshot/loginDetected.
        nested = result.get("observation")
        if isinstance(nested, dict):
            fresh = _obs_from_payload(nested)
            if fresh is not None:
                return fresh
        # A navigate response without a nested snapshot has no valid refs for
        # the destination. Keep only location and force a fresh observation.
        return invalidate_observation(
            current,
            url=str(result.get("url") or ""),
            title=str(result.get("title") or ""),
        )
    # State-changing tools (click/fill/press/select/scroll) ship a fresh
    # observation under result.observation so the planner sees the post-
    # action page state on its next turn.
    fresh = _obs_from_payload(result.get("observation"))
    if fresh is not None:
        return fresh
    if requires_fresh_observation(tool):
        return invalidate_observation(current)
    return current


def _extract_screenshot(result: Any) -> str | None:
    if not isinstance(result, dict):
        return None
    s = result.get("screenshot")
    if isinstance(s, str) and s:
        return s
    obs = result.get("observation")
    if isinstance(obs, dict):
        s2 = obs.get("screenshot")
        if isinstance(s2, str) and s2:
            return s2
    return None


def _login_detected(result: Any) -> bool:
    return assessment_from_payload(result).get("state") in {
        "required", "registration_required", "authenticating", "failed",
    }


def _format_upstream_artifacts(node: CapabilityTask, inputs: CapabilityInputs, lang: str) -> str:
    """Render predecessor node artifacts as a text block appended to the
    browser task goal. Lets the planner LLM see what upstream produced.

    Returns empty string when there are no upstream artifacts (single-task
    or first node in a graph) — keeps single-task behavior unchanged.
    """
    graph_artifacts = (inputs.output_spec or {}).get("graph_artifacts") or {}
    if not isinstance(graph_artifacts, dict) or not graph_artifacts:
        return ""
    deps = list(node.depends_on or [])
    if not deps:
        return ""
    pieces: List[str] = []
    for dep_id in deps:
        art = graph_artifacts.get(dep_id)
        if not isinstance(art, dict):
            continue
        # Strip internal bookkeeping keys and heavy blobs.
        cleaned = {}
        for k, v in art.items():
            if k.startswith("_"):
                continue
            if k in ("browser_receipt", "skill_state", "skill_finalize", "answer"):
                continue
            if isinstance(v, str) and len(v) > 8000:
                v = v[:8000] + "...<truncated>"
            cleaned[k] = v
        if cleaned:
            pieces.append(f"# {dep_id}\n{json.dumps(cleaned, ensure_ascii=False, indent=2)}")
    if not pieces:
        return ""
    header = ("UPSTREAM ARTIFACTS (inputs from prior nodes):" if str(lang).startswith("zh")
              else "UPSTREAM ARTIFACTS (inputs from prior nodes):")
    return header + "\n" + "\n\n".join(pieces)


def _format_candidate_entries(
    candidates: List[Dict[str, str]], lang: str,
) -> str:
    if not candidates:
        return ""
    lines: List[str] = []
    for idx, c in enumerate(candidates, 1):
        url = c.get("url") or ""
        src = c.get("source") or ""
        name = c.get("name") or ""
        if src == "user_request":
            tag = "from user request"
        elif src == "site_scope":
            tag = "from task site scope"
        else:
            tag = f"from site profile '{name}'"
        lines.append(f"  {idx}. {url}  ({tag})")
    header = "CANDIDATE ENTRY URLS (from user request + site profiles):"
    rule = (
        "⛔ Do not call browser_ask_user for a URL. First choose one of the candidates above and browser_navigate to it."
        "\nWith multiple candidates, follow the semantic roles and order in the user request (for example, query on A and upload to B means use A for reading and B for uploading)."
    )
    return f"{header}\n" + "\n".join(lines) + "\n" + rule


def _extract_original_user_request(inputs: CapabilityInputs) -> str:
    """Return the immutable request bound to this graph run.

    Old runs may not have the persisted field, so the compatibility fallback
    uses the latest user message. It must never use the conversation's first
    user message because that may belong to an earlier task in the session.
    """
    return resolve_run_original_request(
        output_spec=inputs.output_spec,
        messages=inputs.raw_messages or inputs.messages or [],
    )


def _upstream_is_empty(node: CapabilityTask, upstream_block: str) -> bool:
    """A node declared upstream deps but the rendered block is empty —
    means predecessors didn't emit any concrete data beyond the stripped
    bookkeeping fields. The caller prepends an explicit warning so the
    LLM doesn't quietly assume the work is already done.
    """
    return bool(node.depends_on) and not upstream_block.strip()


def _format_downstream_expectations(node: CapabilityTask, lang: str) -> str:
    """Render downstream consumers from ``node.meta.downstream_consumers``.

    Gives the LLM a structural view of "what will consume my output and
    what shape does it expect". Empty string when no consumers are
    recorded (terminal node or single-node graph).
    """
    meta = node.meta if isinstance(node.meta, dict) else {}
    consumers = meta.get("downstream_consumers")
    if not isinstance(consumers, list) or not consumers:
        return ""
    lines: List[str] = []
    for c in consumers:
        if not isinstance(c, dict):
            continue
        node_id = str(c.get("node_id") or "").strip()
        objective = str(c.get("objective") or "").strip()
        required_inputs = [str(x).strip() for x in (c.get("required_inputs") or []) if str(x).strip()]
        agent = str(c.get("assigned_agent") or "").strip()
        header_parts: List[str] = []
        if node_id:
            header_parts.append(f"`{node_id}`")
        if agent:
            header_parts.append(f"({agent})")
        header = "- " + (" ".join(header_parts) if header_parts else "consumer")
        lines.append(header)
        if objective:
            lines.append(f"  goal: {objective}")
        if required_inputs:
            keys = ", ".join(required_inputs[:8])
            lines.append(f"  expects artifact keys from you: {keys}")
    if not lines:
        return ""
    header_text = "DOWNSTREAM CONSUMERS (shape your browser_done.data to serve them):"
    return header_text + "\n" + "\n".join(lines)


_LOGIN_URL_RE = re.compile(r"login|signin|sign-in|auth|sso|cas|oauth|登录|登入", re.I)


def _is_login_like_url(url: str) -> bool:
    return bool(_LOGIN_URL_RE.search(str(url or "")))


def _login_detected_from_obs(obs: "Observation") -> bool:
    state = str((obs.auth or {}).get("state") or "")
    return state in {"required", "registration_required", "authenticating", "failed"} or (
        not state and _is_login_like_url(obs.url or "")
    )


def _looks_like_empty_spa_observation(obs: "Observation") -> bool:
    url = str(obs.url or "").strip()
    if not url or _is_login_like_url(url):
        return False
    title = str(obs.title or "").strip().lower()
    # Generic JS app shells often have a proper title but no interactive
    # elements during the first paint / hydration window.
    return len(list(obs.elements or [])) == 0 and bool(title)


def _is_xiaohongshu_publish_goal(goal: str) -> bool:
    text = str(goal or "").lower()
    return (
        "creator.xiaohongshu.com" in text
        and any(token in text for token in ("新建图文笔记", "新建笔记", "图文笔记", "article_markdown", "保存为草稿", "保存草稿"))
    )


def _resolve_xiaohongshu_publish_url(goal: str) -> str:
    """Return the target publish URL for a xiaohongshu publish run.

    Priority:
      1. Explicit URL embedded in the user's goal (e.g. the user said
         "go to https://creator.xiaohongshu.com/publish/publish?target=video")
      2. The yaml-configured default (``publish_channels.yaml``)
      3. Empty string — caller should interpret this as "no default, don't
         rewrite", letting the planner's own navigate call stand.
    """
    match = _XHS_USER_PUBLISH_URL_RE.search(goal or "")
    if match:
        candidate = match.group(0).strip().rstrip("/")
        # Reject landing URLs accidentally matched as "user-specified".
        if candidate not in _XHS_LANDING_URLS:
            return match.group(0).strip()
    return publish_channel_registry.publish_url_for("xiaohongshu")


class DesktopAgentBrowserExecutor:
    def __init__(
        self,
        user_id: str,
        session_id: str = "default",
        *,
        checkpoint_session: BrowserCheckpointSession | None = None,
    ) -> None:
        self.user_id = user_id
        self.session_id = session_id or "default"
        self.bridge = LocalBridge(user_id, self.session_id)
        self.checkpoint_session = checkpoint_session

    async def _retry_empty_spa_observation(
        self,
        *,
        current_obs: Observation,
        lang: str,
        step: int,
    ) -> tuple[Observation, bool, str | None]:
        """Give JS-heavy SPA pages a short hydration window before the
        planner reacts to a zero-element observation.

        Returns the possibly refreshed observation, whether it stabilized,
        and an optional screenshot from the last retry observation.
        """
        if not _looks_like_empty_spa_observation(current_obs):
            return current_obs, False, None

        import asyncio as _asyncio

        latest = current_obs
        latest_screenshot: str | None = None
        for attempt in range(1, SPA_EMPTY_OBSERVE_RETRIES + 1):
            logger.debug(
                "empty SPA observation retry",
                extra={"event": "browser.empty_spa_retry", "attempt": attempt, "max_attempts": SPA_EMPTY_OBSERVE_RETRIES, "url": latest.url, "title": latest.title[:120]},
            )
            await _asyncio.sleep(SPA_EMPTY_OBSERVE_WAIT_SECONDS)
            re_result, re_ok, _re_err = await self._dispatch(Decision(
                tool="browser_observe",
                args={},
                rationale="retry observe after short hydration wait on empty SPA page",
            ))
            if not re_ok or not isinstance(re_result, dict):
                continue
            refreshed = _obs_from_payload(re_result)
            latest_screenshot = _extract_screenshot(re_result)
            if refreshed is not None:
                latest = refreshed
            if latest.elements:
                logger.info(
                    "empty SPA observation stabilized",
                    extra={"event": "browser.empty_spa_stabilized", "step": step, "url": latest.url, "elements": len(list(latest.elements or []))},
                )
                return latest, True, latest_screenshot
        return latest, False, latest_screenshot

    async def execute(self, *, node: CapabilityTask, inputs: CapabilityInputs) -> AsyncIterator[Tuple[Dict[str, Any], Dict[str, Any]]]:
        from .browser_run_flow import run_browser_execution
        async for event in run_browser_execution(self, node=node, inputs=inputs):
            yield event

    async def _dispatch(self, decision: Decision):
        args = dict(decision.args or {})
        args["__observation_mode"] = "accessibility"
        # `domain` is a meta field — which pool context the call runs against —
        # not a tool arg. Pull it out of args and promote it to the frame's
        # top-level ``domain`` so the agent can key the right browser context.
        # Precedence: explicit LLM-declared domain > host derived from url >
        # agent-side lastDomain fallback (see BrowserPool.getLastActivePage).
        declared = args.pop("domain", None)
        domain = str(declared).strip() if isinstance(declared, str) else None
        if not domain and decision.tool in ("browser_navigate", "browser_tab_new"):
            domain = _domain(str(args.get("url") or ""))
        try:
            result = await self.bridge.execute(
                decision.tool,
                args,
                domain=domain,
                timeout=timeout_for_tool(decision.tool),
            )
            ok = bool(result.get("ok"))
            err = result.get("error") if not ok else None
            payload = result.get("result")
            if (
                ok
                and decision.tool == "browser_execute_plan"
                and isinstance(payload, dict)
                and str(payload.get("status") or "") != "completed"
            ):
                ok = False
                err = str(payload.get("reason") or "action plan stopped")
            return payload, ok, err
        except AgentNotConnected:
            return None, False, "agent-disconnected"
        except Exception as exc:
            return None, False, f"dispatch-error: {exc}"
