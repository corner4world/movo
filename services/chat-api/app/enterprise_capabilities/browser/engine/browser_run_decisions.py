from __future__ import annotations

from . import desktop_agent_executor as api


async def handle_terminal_decision(s):
    if s.decision.tool == "browser_done":
        # A write can be confirmed only after a later observation. Sync
        # that delayed receipt before consulting the task-level ledger;
        # otherwise the effect tracker and context disagree forever.
        s.done_refreshed_receipts = await s.effect_tracker.refresh_pending(
            after=s.current_obs,
            supplemental_evidence=s.form_transaction.outcome_evidence(s.current_obs),
        )
        for s.refreshed_receipt in s.done_refreshed_receipts:
            s.business_actions.record(s.refreshed_receipt)
            api.notify_effect_receipt(s.planner, s.refreshed_receipt)
            await s.persist_confirmed_effect(s.refreshed_receipt, s.current_obs)
            s.form_transaction.after_effect(s.refreshed_receipt, s.current_obs)
            s.receipt_application = api.apply_effect_receipt(
                context=s.task_context,
                tracks_context_state=s.context_tracks_state,
                receipt=s.refreshed_receipt,
                observation=s.current_obs,
            )
            if s.receipt_application.error:
                api.logger.warning(
                    "browser context delayed effect hook failed",
                    extra={
                        "event": "browser.context_delayed_effect_hook_failed",
                        "error": s.receipt_application.error,
                    },
                )
            api.logger.info(
                "browser pending effect refreshed before done",
                extra={
                    "event": "browser.effect_refreshed_before_done",
                    "contract_key": s.refreshed_receipt.contract_key,
                    "status": s.refreshed_receipt.status,
                    "action": s.refreshed_receipt.action_name,
                    "completes_goal": s.refreshed_receipt.completes_goal,
                    "goal_completed": s.receipt_application.goal_completed,
                },
            )
            if s.refreshed_receipt.status == "confirmed_failure":
                s._topology = (getattr(s.inputs, "output_spec", None) or {}).get("graph_topology") or []
                for s.failure_event in api.build_effect_business_failure_events(
                    receipt=s.refreshed_receipt,
                    objective=str(s.node.goal or ""),
                    steps=len(s.history),
                    lang=s.lang,
                    result_data=api.project_verified_operation_result(
                        receipt=s.refreshed_receipt,
                        context=s.task_context,
                        form_state=s.form_transaction.export_state(),
                        observation=s.current_obs,
                    ),
                    subagent_id=s.subagent_id,
                    node_id=s.node.node_id,
                    emit_answer=not bool(s._topology),
                ):
                    yield s.failure_event
                s.terminal = True
                return
            if s.receipt_application.goal_completed:
                s.summary, s.completion_meta = api.build_effect_completion(
                    receipt=s.refreshed_receipt,
                    objective=str(s.node.goal or ""),
                    steps=len(s.history),
                    lang=s.lang,
                    result_data=api.project_verified_operation_result(
                        receipt=s.refreshed_receipt,
                        context=s.task_context,
                        form_state=s.form_transaction.export_state(),
                        observation=s.current_obs,
                    ),
                )
                s._topology = (getattr(s.inputs, "output_spec", None) or {}).get("graph_topology") or []
                if not s._topology:
                    yield {"type": "answer", "content": s.summary}, {}
                s.schedule_workflow_capture()
                yield {"type": "subagent_done", "content": {
                    "subagent_id": s.subagent_id,
                    "node_id": s.node.node_id,
                    "status": "succeeded",
                }}, s.completion_meta
                s.terminal = True
                return
        # Stateful contexts may reject browser_done until their
        # task-specific completion conditions have been verified.
        if s.context_tracks_state and not s.task_context.ready_to_done():
            s.blocked_hint = s.task_context.done_blocked_hint(s.current_obs)
            s.history.append(s.blocked_hint)
            yield {"type": "activity", "content": {
                "kind": "warning",
                "message": str(s.blocked_hint.error or s.blocked_hint.result_digest or "browser_done blocked"),
            }}, {}
            api.logger.info(
                "browser context done blocked",
                extra={
                    "event": "browser.context_done_blocked",
                    "context": type(s.task_context).__name__,
                    "phase": str(getattr(s.task_context, "phase", "")),
                },
            )
            s.recovery = s.done_block_recovery.blocked(
                fingerprint=(
                    f"{type(s.task_context).__name__}:"
                    f"{getattr(s.task_context, 'phase', '')}:"
                    f"{s.blocked_hint.error or s.blocked_hint.result_digest or ''}"
                ),
            )
            if s.recovery.terminal:
                s.reason = (
                    "浏览器多次尝试结束，但任务上下文在刷新页面后仍缺少必要证据；"
                    "已安全停止，避免继续重复操作。"
                    if s.lang == "zh" else
                    "The browser repeatedly tried to finish, but required context evidence "
                    "remained missing after fresh observations; stopped safely to avoid a loop."
                )
                yield {"type": "activity", "content": {
                    "kind": "error", "message": s.reason,
                }}, {}
                yield {"type": "subagent_done", "content": {
                    "subagent_id": s.subagent_id,
                    "node_id": s.node.node_id,
                    "status": "failed_terminal",
                }}, {"browser_receipt": s.browser_failure_receipt(
                    error=s.reason,
                    status="context_evidence_incomplete",
                )}
                s.terminal = True
                return
            s.pending_resolved_decision = s.recovery.retry
            s.continue_step = True
            return
        # ─── check-before-done gate ────────────────────────
        # Any conclusion (positive or negative) after a state-
        # changing action MUST be backed by a fresh page read.
        # Walk history: if the most recent mutation (click/fill/
        # select/press/upload) happened after the most recent
        # observation tool (observe/read_text/navigate/scroll/
        # screenshot/tab_new/back/forward), the LLM is calling
        # done on a stale snapshot. Reject and force a re-read.
        # Zero keyword matching — pure structural invariant.
        s._post_action_check = api.post_action_observation_check(s.history)
        if s._post_action_check.required:
            s._hint = (
                "⛔ Do not call browser_done without observing again after an action."
                "\nYour latest action (fill/click/select/press/upload) has no subsequent"
                " snapshot-producing step such as browser_observe, browser_read_text,"
                " browser_navigate, or browser_scroll. The current observation is from"
                " **before the action**, so any success, failure, or bug conclusion would rely on stale information."
                "\nNext, use browser_observe (or read_text / scroll) to obtain the actual post-action page state before deciding whether to call browser_done."
                "\nNote: browser_wait_for does not count as re-observation because it returns no DOM snapshot."
                if s.lang == "zh" else
                "⛔ browser_done not allowed without a post-action observation."
                "\nYour most recent mutation (fill/click/select/press/upload) has"
                " no following snapshot-producing step (browser_observe / read_text /"
                " navigate / scroll / screenshot). The current observation reflects"
                " the page BEFORE the mutation; any conclusion you draw (success/"
                "failure/bug) is based on stale information."
                "\nYour next step MUST be a fresh read (browser_observe / read_text /"
                " scroll) so you see the post-action state, THEN decide whether to"
                " browser_done."
                "\nNote: browser_wait_for does NOT count — it does not return a DOM"
                " snapshot."
            )
            s.history.append(api.StepRecord(
                observation=s.current_obs,
                decision=api.Decision(
                    tool="__check_required__", args={},
                    rationale="system: mutation without post-action observation",
                ),
                ok=False, error=s._hint, result_digest="",
            ))
            yield {"type": "activity", "content": {
                "kind": "warning",
                "message": (
                    "未在动作后重观察，已拦截 browser_done —— 请先 observe"
                    if s.lang == "zh" else
                    "browser_done blocked: no post-action observation — observe first"
                ),
            }}, {}
            api.logger.info("browser done blocked for missing check", extra={"event": "browser.done_blocked_need_check", "last_mutation_step": s._post_action_check.last_mutation_index, "last_observation_step": s._post_action_check.last_fresh_index})
            # Auto-observe injection. Without this, observed
            # behaviour is: LLM calls done → blocked → next turn
            # LLM calls done AGAIN (ignoring the hint) → blocked
            # → ... → step budget exhausted (we saw 9 consecutive
            # done attempts in one run). Inject a real observe
            # ourselves right now so the gate condition flips
            # (last_obs > last_mut) — LLM's next done attempt
            # will pass through, AND the resulting report carries
            # the post-action snapshot the gate was protecting.
            # Net cost: same one wasted step the LLM was going
            # to burn anyway, but now it produces useful
            # observation data instead of a no-op.
            try:
                s._auto_obs_args: api.Dict[str, api.Any] = {}
                if (
                    s.task_context.active
                    and getattr(s.task_context, "round", 0) == 1
                    and getattr(s.task_context, "round1_op_idx", 0) in (2, 3)
                ):
                    s._auto_obs_args["with_hover_reveal"] = True
                s._auto_obs_dec = api.Decision(
                    tool="browser_observe", args=s._auto_obs_args,
                    rationale="system: auto-observe after done-blocked (post-mutation guard)",
                )
                s._auto_res, s._auto_ok, s._auto_err = await s.executor._dispatch(s._auto_obs_dec)
                s._fresh = api._update_obs(s.current_obs, "browser_observe", s._auto_res)
                s.history.append(api.StepRecord(
                    observation=s._fresh,
                    decision=s._auto_obs_dec,
                    ok=s._auto_ok,
                    error=s._auto_err,
                    result_digest=api._digest("browser_observe", s._auto_res),
                ))
                s.current_obs = s._fresh
                api.logger.info("auto observe after done-blocked", extra={"event": "browser.done_blocked_auto_observe", "ok": bool(s._auto_ok), "url": getattr(s._fresh, "url", "")})
            except Exception as exc:
                api.logger.warning("auto observe after done-blocked failed", extra={"event": "browser.done_blocked_auto_observe_failed", "error": str(exc)})
            s.continue_step = True
            return
        # ─────────────────────────────────────────────────────
        s.refreshed_effects = await s.effect_tracker.refresh_pending(
            after=s.current_obs,
            supplemental_evidence=s.form_transaction.outcome_evidence(s.current_obs),
        )
        s.exhausted_effect = next((
            item for item in s.refreshed_effects
            if bool((item.fingerprint or {}).get("verification_exhausted"))
        ), None)
        if s.exhausted_effect is not None:
            s.verification = api.build_effect_verification_decision(
                s.exhausted_effect,
                lang=s.lang,
            )
            async for s.event in s.suspend_for_human_assistance(
                question=str(s.verification.args.get("question") or ""),
                next_step=s.step + 1,
                category=api.FORM_EFFECT_VERIFY_CATEGORY,
                handoff=dict(s.verification.args.get("handoff") or {}),
            ):
                yield s.event
            s.terminal = True
            return
        s.pending_effects = s.effect_tracker.pending_receipts()
        if s.pending_effects:
            s.pending_hint = (
                "The commit occurred, but its business result is still unverified. Inspect the result page or look up the business object; do not resubmit or finish yet."
                if s.lang == "zh" else
                "The commit occurred, but its business result is still unverified. "
                "Inspect or look up the resulting object; do not resubmit or finish yet."
            )
            s.history.append(api.StepRecord(
                observation=s.current_obs,
                decision=s.decision,
                ok=False,
                error=s.pending_hint,
                result_digest=api.json.dumps(
                    [item.model_dump(mode="json") for item in s.pending_effects],
                    ensure_ascii=False,
                )[:6000],
            ))
            yield {"type": "activity", "content": {
                "kind": "analyze", "message": s.pending_hint,
            }}, {}
            api.logger.info(
                "browser done blocked by pending effect",
                extra={
                    "event": "browser.done_blocked_pending_effect",
                    "contracts": [item.contract_key for item in s.pending_effects],
                },
            )
            s.continue_step = True
            return
        s.effect_completion = api.assess_effect_completion(
            s.action_capability_id,
            s.effect_tracker.receipts(),
            lang=s.lang,
        )
        if not s.effect_completion.allowed:
            if (
                not s.effect_tracker.receipts()
                and s.assistance_kind in {"form_fill", "form_media", "form_commit"}
                and str(s.resume_signal.get("human_outcome") or "").strip().lower() == "completed"
            ):
                s.confirmation = api.build_task_completion_confirmation_decision(
                    reason=(
                        "人工操作后 Agent 判断任务可以结束，但系统没有人工提交动作的回执"
                    ),
                    evidence=("browser_done reached without an agent-side effect receipt",),
                    lang=s.lang,
                )
                async for s.event in s.suspend_for_human_assistance(
                    question=str(s.confirmation.args.get("question") or ""),
                    next_step=s.step + 1,
                    category=api.FORM_TASK_COMPLETION_CATEGORY,
                    handoff=dict(s.confirmation.args.get("handoff") or {}),
                ):
                    yield s.event
                s.terminal = True
                return
            s.history.append(api.StepRecord(
                observation=s.current_obs,
                decision=s.decision,
                ok=False,
                error=api.assess_effect_completion(
                    s.action_capability_id,
                    s.effect_tracker.receipts(),
                    lang="en",
                ).reason,
                result_digest=api.json.dumps(s.effect_tracker.receipts(), ensure_ascii=False)[:6000],
            ))
            yield {"type": "activity", "content": {
                "kind": "warning",
                "message": s.effect_completion.reason,
            }}, {}
            api.logger.info(
                "browser done blocked without confirmed side effect",
                extra={
                    "event": "browser.done_blocked_unconfirmed_effect",
                    "capability": s.action_capability_id,
                },
            )
            s.continue_step = True
            return
        s.summary = str(s.decision.args.get("summary") or "")
        # Structured data returned by the LLM (e.g. scraped news
        # items, form submission receipts, etc.). Written to the
        # node artifact so downstream nodes can read it via
        # predecessor_artifacts / input_artifacts in their payload.
        s.data = s.decision.args.get("data")
        if not isinstance(s.data, dict):
            s.data = {}
        # ─── action-contract gate ───────────────────────────
        # The planner labels each browser step with a concrete
        # capability (browser.read / submit / modify / …); every
        # capability declares a structural produce shape. Reject
        # browser_done whose data doesn't match the declared
        # shape and loop back — LLM sees the reason in the next
        # turn's history and either scans more or calls fail.
        s.cap_id = str((s.node.meta or {}).get("capability_id") or "").strip().lower()
        s.contract = api.action_contract_validate_data(s.cap_id, s.data)
        # Diagnostic: log every contract outcome so you can trace
        # whether the action taxonomy is actually firing in prod.
        api.logger.debug(
            "browser done contract checked",
            extra={"event": "browser.contract_check", "capability": s.cap_id or "<untyped>", "ok": s.contract.ok, "data_keys": list(s.data.keys())[:6] if isinstance(s.data, dict) else [], "reason": (s.contract.reason or "")[:180]},
        )
        if not s.contract.ok:
            s.missing_preview = ", ".join(s.contract.missing[:6])
            s.reason = s.contract.reason or "contract violation"
            api.logger.warning(
                "browser done rejected by contract",
                extra={"event": "browser.done_contract_rejected", "capability": s.cap_id or "<untyped>", "reason": s.reason, "missing": s.missing_preview},
            )
            s.history.append(api.StepRecord(
                observation=s.current_obs,
                decision=s.decision,
                ok=False,
                error=(
                    f"browser_done rejected by contract ({s.cap_id}): {s.reason}. "
                    f"Missing/empty: {s.missing_preview}. "
                    "Either keep scanning the page to capture the real values, "
                    "or call browser_fail explaining which piece is unavailable."
                ),
                result_digest="",
            ))
            s.consecutive_failures += 1
            yield {"type": "activity", "content": {
                "kind": "warning",
                "message": (
                    f"browser_done 被合同拒绝（{s.cap_id}）：{s.reason}"
                    if s.lang == "zh"
                    else f"browser_done rejected by contract ({s.cap_id}): {s.reason}"
                ),
            }}, {}
            if s.consecutive_failures >= api.MAX_CONSECUTIVE_FAILURES:
                s.recovery = s.terminal_recovery_plan(
                    source=api.OUTPUT_CONTRACT_EXHAUSTED,
                    error=s.reason,
                )
                if s.recovery_assistance_available(s.recovery):
                    async for s.event in s.suspend_for_recovery(
                        s.recovery,
                        next_step=s.step + 1,
                    ):
                        yield s.event
                    s.terminal = True
                    return
                yield {"type": "activity", "content": {
                    "kind": "error",
                    "message": (
                        f"⚠ 无法满足本步契约（{s.cap_id}）：{s.reason}"
                        if s.lang == "zh"
                        else f"⚠ Could not satisfy step contract ({s.cap_id}): {s.reason}"
                    ),
                }}, {}
                yield {"type": "subagent_done", "content": {
                    "subagent_id": s.subagent_id, "node_id": s.node.node_id,
                    "status": "failed_terminal",
                }}, {"browser_receipt": {
                    **s.browser_failure_receipt(error=s.reason, status="failed_contract"),
                    "capability_id": s.cap_id,
                    "reason": s.reason,
                }}
                s.terminal = True
                return
            s.continue_step = True
            return  # back to the planner loop, LLM sees the rejection
        if s.context_tracks_state:
            s.summary, s.data = s.task_context.finalize(s.summary, s.data)
        s.answer_content = api.render_browser_result(
            summary=s.summary,
            data=s.data,
            lang=s.lang,
        ) or ("任务完成" if s.lang == "zh" else "Task completed")
        s._topology = (getattr(s.inputs, "output_spec", None) or {}).get("graph_topology") or []
        if not s._topology:
            yield {"type": "answer", "content": s.answer_content}, {}
        s.effect_receipts = s.effect_tracker.receipts()
        s.meta: api.Dict[str, api.Any] = {"browser_receipt": {
            "status": "ok",
            "summary": s.summary,
            "steps": len(s.history),
            **({"effect_receipts": s.effect_receipts} if s.effect_receipts else {}),
        }}
        # Flatten structured data into meta so it becomes part of
        # the node artifact. Existing browser_receipt field is kept
        # untouched for backward compatibility.
        for s.k, s.v in s.data.items():
            if s.k == "browser_receipt":
                continue  # don't let LLM overwrite our receipt
            s.meta[s.k] = s.v
        s.meta["browser_result"] = api.build_browser_result(
            objective=str(s.node.goal or ""),
            summary=s.summary,
            data=s.data,
        )
        s.schedule_workflow_capture()
        yield {"type": "subagent_done", "content": {
            "subagent_id": s.subagent_id, "node_id": s.node.node_id, "status": "succeeded",
        }}, s.meta
        s.terminal = True
        return

    if s.decision.tool == "browser_ask_user":
        s.q = str(s.decision.args.get("question") or "")
        s.ask_category = str(s.decision.args.get("category") or "browser")
        s.ask_handoff = s.decision.args.get("handoff")
        if not isinstance(s.ask_handoff, dict):
            s.ask_handoff = None
        s.automatic_assistance: api.BrowserHumanAssistance | None = None
        if s.decision.rationale == "deterministic recovery after read-budget exhaustion":
            s.automatic_assistance = api.browser_human_assistance(
                source=api.READ_BUDGET,
                observation=s.current_obs,
                lang=s.lang,
            )
            if not s.automatic_assistance_available(s.automatic_assistance):
                s.reason = (
                    "当前页面在人工协助后仍无法找到可靠的下一步"
                    if s.lang == "zh" else
                    "The page still has no reliable next step after human assistance"
                )
                yield {"type": "activity", "content": {
                    "kind": "error",
                    "message": s.reason,
                }}, {}
                yield {"type": "subagent_done", "content": {
                    "subagent_id": s.subagent_id,
                    "node_id": s.node.node_id,
                    "status": "failed_terminal",
                }}, {"browser_receipt": s.browser_failure_receipt(error=s.reason)}
                s.terminal = True
                return
            s.q = s.automatic_assistance.question
        s.ask_domain = api._domain(s.current_obs.url) or ""
        s.ask_scope = api.site_scope(s.current_obs.url) or s.ask_domain
        # URL says login. Three cases, in order:
        #   1) Domain not authenticated yet → real login intervention
        #      (let the next iteration enter the login wait loop).
        #   2) Authenticated, URL-only match (no DOM form) → stale
        #      substring hit (e.g. /login-history); fall through to
        #      the normal ask_user suspend below.
        #   3) Authenticated AND DOM confirms a login form → genuine
        #      re-auth OR LLM mis-navigation. Try safe-URL recovery
        #      first; on exhausted budget downgrade to real login
        #      (clear the authenticated flag + surface intervention).
        s.explicit_auth_request = s.ask_category in {
            "login", "authentication", "runtime_authentication",
        }
        if s.explicit_auth_request or api._login_detected_from_obs(s.current_obs):
            s.is_authenticated = bool(s.ask_scope) and s.ask_scope in s.authenticated_domains
            if not s.is_authenticated:
                s.auth_category = (
                    "registration"
                    if str((s.current_obs.auth or {}).get("state") or "") == "registration_required"
                    else "login"
                )
                async for s.event in s.suspend_for_authentication(
                    category=s.auth_category,
                    source="ask_user",
                    next_step=s.step + 1,
                    question=s.q,
                ):
                    yield s.event
                s.terminal = True
                return
            if s.last_dom_login_flag:
                s.attempts = s.login_recovery_failures.get(s.ask_scope, 0)
                if s.attempts < api.MAX_LOGIN_RECOVERY_ATTEMPTS:
                    s.login_recovery_failures[s.ask_scope] = s.attempts + 1
                    s.safe_url = (
                        s.last_safe_url_by_domain.get(s.ask_scope)
                        or (s.last_navigate_target if s.last_navigate_target and not api._is_login_like_url(s.last_navigate_target) else "")
                        or (f"https://{s.ask_domain}/" if s.ask_domain else "")
                    )
                    s.remaining = api.MAX_LOGIN_RECOVERY_ATTEMPTS - s.attempts - 1
                    yield {"type": "activity", "content": {
                        "kind": "analyze",
                        "message": (
                            f"已登录的 {s.ask_domain} 出现登录表单，尝试恢复回 {s.safe_url}（剩余 {s.remaining} 次）"
                            if s.lang == "zh"
                            else f"Login form on authenticated {s.ask_domain}; recovering to {s.safe_url} (remaining {s.remaining})"
                        ),
                    }}, {}
                    if s.safe_url:
                        try:
                            s.re_result = await s.executor._dispatch(api.Decision(
                                tool="browser_navigate",
                                args={"url": s.safe_url},
                                rationale="safe-URL recovery on authenticated domain (ask_user branch)"))
                            s.re_data = s.re_result[0]
                            if isinstance(s.re_data, dict):
                                s.new_obs = api._obs_from_payload(s.re_data.get("observation") or s.re_data)
                                if s.new_obs:
                                    s.current_obs = s.new_obs
                                s.last_dom_login_flag = bool(api._login_detected(s.re_data))
                                if not s.last_dom_login_flag and not api._is_login_like_url(s.current_obs.url):
                                    yield {"type": "intervention_cleared", "content": {
                                        "category": "login",
                                        "url": s.current_obs.url,
                                        "domain": s.ask_domain,
                                        "reason": "authenticated_domain_recovery_succeeded",
                                    }}, {}
                        except Exception:
                            pass
                    s.continue_step = True
                    return
                # Budget exhausted — real session expiry. Downgrade
                # the domain and surface a real login intervention.
                s.authenticated_domains.discard(s.ask_scope)
                s.login_recovery_failures.pop(s.ask_scope, None)
                yield {"type": "activity", "content": {
                    "kind": "analyze",
                    "message": (
                        f"{s.ask_domain} 恢复重试已用尽，判定为真实登录过期，走正常重新登录"
                        if s.lang == "zh"
                        else f"Recovery budget for {s.ask_domain} exhausted; treating as real session expiry"
                    ),
                }}, {}
                async for s.event in s.suspend_for_authentication(
                    category="login",
                    source="ask_user_recovery_exhausted",
                    next_step=s.step + 1,
                    question=s.q,
                ):
                    yield s.event
                s.terminal = True
                return
            # Authenticated + URL-only match, no DOM login form:
            # fall through to normal ask_user suspend below.
        async for s.event in s.suspend_for_human_assistance(
            question=s.q,
            next_step=s.step + 1,
            assistance=s.automatic_assistance,
            category=s.ask_category,
            handoff=s.ask_handoff,
        ):
            yield s.event
        s.terminal = True
        return

    if s.decision.tool == "browser_fail":
        s.reason = str(s.decision.args.get("reason") or "")
        s.recovery = s.terminal_recovery_plan(
            source=api.recovery_source_for_browser_fail(s.decision.args),
            error=s.reason,
        )
        if s.recovery_assistance_available(s.recovery):
            async for s.event in s.suspend_for_recovery(
                s.recovery,
                next_step=s.step + 1,
            ):
                yield s.event
            s.terminal = True
            return
        yield {"type": "activity", "content": {
            "kind": "error",
            "message": (
                f"⚠️ 无法继续：{s.reason}" if s.lang == "zh"
                else f"⚠️ Cannot continue: {s.reason}"
            ),
        }}, {}
        yield {"type": "subagent_done", "content": {
            "subagent_id": s.subagent_id, "node_id": s.node.node_id, "status": "failed_terminal",
        }}, {"browser_receipt": s.browser_failure_receipt(error=s.reason)}
        s.terminal = True
        return

    # Hard-cap repetitive read-only tools on the same URL. The
    # planner LLM tends to loop on read_text/screenshot/observe
    # without making progress — detect the pattern and force it
