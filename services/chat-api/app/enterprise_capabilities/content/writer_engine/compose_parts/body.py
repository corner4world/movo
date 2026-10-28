from __future__ import annotations
from app.infrastructure.observability.config import log_print

import json
import logging
import re
from typing import Any, AsyncIterator, Dict, List, Tuple

import yaml
from app.llm.types import Message, Role

from app.enterprise_capabilities.content.body_projection import (
    canonicalize_required_blocks,
    strip_visual_or_production_clauses,
    strip_visual_placeholder_directives,
)
from app.enterprise_capabilities.content.structure_roles import contains_cjk
from app.enterprise_capabilities.content.writer_engine.skill_contract import BaseSkill, SkillContext
from app.services.image_assets import build_embedded_document_image_assets
from app.services.image_markdown import inject_images_inline, merge_image_layout_hints, normalize_image_markdown
from app.services.image_planner import get_image_planner_service
from app.enterprise_capabilities.content.writer_engine.pipeline import WriterEnginePipeline
from app.enterprise_capabilities.content.argument_pack import ArgumentPackSelector
from app.enterprise_capabilities.content.planning import build_body_plan
from app.enterprise_capabilities.evidence.foundation.external_web_raw import strip_external_web_raw
from app.enterprise_capabilities.evidence.foundation import normalize_evidence_bundle
from app.enterprise_capabilities.evidence.foundation.writer_packet import WriterEvidencePacketBuilder, persist_writer_evidence_packet
from app.enterprise_capabilities.evidence.foundation.fair_selection import round_robin_take
from app.enterprise_capabilities.evidence.foundation.graph_artifact_projector import project_graph_artifact_result
from app.enterprise_capabilities.evidence.foundation.user_request_fact_extractor import enrich_evidence_with_user_request_facts
from app.enterprise_capabilities.content.execution_mode import ExecutionModeResolver
from app.enterprise_capabilities.content.compose_access import resolve_compose_policy
from app.enterprise_capabilities.content.style_contract_renderer import resolve_writer_style_prompt
from app.enterprise_capabilities.content.structure_roles import normalize_section_roles
from app.enterprise_capabilities.content.subject_resolution import CandidateAnalyzer, SubjectResolutionResolver


from .strategy import ComposeStrategyMixin

class ComposeBodyMixin:
    @staticmethod
    def _resolve_subject_generation_gate(
        *,
        user_query: str,
        subject_resolution: Dict[str, Any],
        tool_observations: List[Dict[str, Any]],
        evidence_bundle: Dict[str, Any],
        channel: str = "",
        audience: str = "",
        execution_kind: str = "",
        schema_category: str = "",
    ) -> Dict[str, Any]:
        # Execution-type tasks (browser automation, code,
        # file transforms) deliver results that are inherently "about" a
        # target the user already specified (a URL, a file, a system).
        # The subject-resolution gate is designed for topic writing — it
        # treats the URL's "https" token as an ambiguous subject label
        # and demands the user clarify, which produces nonsense tails
        # like "can't uniquely identify 'https'" on execution reports.
        # Hard-disable the gate for non-content execution kinds.
        ek = str(execution_kind or "").strip().lower()
        if ek and ek != "content":
            return {"action": "proceed", "evidence_strength": 0, "gate_skipped": f"execution_kind={ek}"}
        status = str(subject_resolution.get("status") or "").strip().lower()
        selection_confidence = max(0.0, min(1.0, float(subject_resolution.get("selection_confidence") or 0.0)))
        canonical_subject = strip_visual_or_production_clauses(
            str(subject_resolution.get("canonical_subject") or "")
        ).strip()
        candidate_subjects = []
        for item in list(subject_resolution.get("candidate_subjects") or []):
            token = strip_visual_or_production_clauses(str(item or "")).strip()
            if token and token not in candidate_subjects:
                candidate_subjects.append(token)
        supporting_facts = [
            strip_visual_or_production_clauses(str(item or "")).strip()
            for item in list(subject_resolution.get("supporting_facts") or [])
            if strip_visual_or_production_clauses(str(item or "")).strip()
        ]
        observation_count = len([item for item in list(tool_observations or []) if isinstance(item, dict)])
        evidence_results = len([item for item in list((evidence_bundle or {}).get("results") or []) if isinstance(item, dict)])
        confirmed_facts = len(
            [item for item in list((evidence_bundle or {}).get("confirmed_facts") or []) if str(item or "").strip()]
        )
        evidence_strength = observation_count + evidence_results + confirmed_facts + len(supporting_facts)
        if canonical_subject and (
            status == "resolved_single_subject"
            or selection_confidence >= 0.55
        ):
            return {"action": "proceed", "evidence_strength": evidence_strength}

        if len(candidate_subjects) >= 2 and CandidateAnalyzer.are_synonymous(candidate_subjects):
            return {"action": "proceed", "evidence_strength": evidence_strength}

        subject_label = ComposeBodyMixin._extract_ambiguous_subject_label(
            user_query=user_query,
            fallback=candidate_subjects[0] if candidate_subjects else "",
        )
        if len(candidate_subjects) >= 2 and evidence_strength >= max(2, len(candidate_subjects[:3])):
            return {
                "action": "disambiguate",
                "evidence_strength": evidence_strength,
                "body_user_goal": ComposeBodyMixin._build_disambiguation_goal(
                    subject_label=subject_label,
                    candidate_subjects=candidate_subjects,
                ),
            }
        return {
            "action": "clarify",
            "evidence_strength": evidence_strength,
            "message": ComposeBodyMixin._build_subject_clarification_message(
                user_query=user_query,
                subject_label=subject_label,
                candidate_subjects=candidate_subjects,
            ),
        }

    @staticmethod
    def _resolve_strict_grounding_blocker(
        *,
        output_spec: Dict[str, Any],
        user_query: str,
        tool_observations: List[Dict[str, Any]],
        evidence_bundle: Dict[str, Any],
    ) -> str:
        effective = output_spec.get("effective_policy") if isinstance(output_spec.get("effective_policy"), dict) else {}
        compose = effective.get("compose_policy") if isinstance(effective.get("compose_policy"), dict) else {}
        research = effective.get("research_policy") if isinstance(effective.get("research_policy"), dict) else {}
        strictness = str(compose.get("grounding_strictness") or "").strip().lower()
        if strictness != "strict":
            return ""
        must_tools = [str(x).strip() for x in list(research.get("must_use_tools") or []) if str(x).strip()]
        preferred_tools = [str(x).strip() for x in list(research.get("preferred_tools") or []) if str(x).strip()]
        scope = str(research.get("research_scope") or "").strip().lower()
        requires_search = bool(scope in {"internal_kb", "public_web", "mixed"} or must_tools or preferred_tools)
        if not requires_search:
            return ""
        evidence_count = 0
        evidence_count += len([x for x in list(tool_observations or []) if isinstance(x, dict)])
        evidence_count += len([x for x in list((evidence_bundle or {}).get("results") or []) if isinstance(x, dict)])
        evidence_count += len([x for x in list((evidence_bundle or {}).get("confirmed_facts") or []) if str(x or "").strip()])
        if evidence_count > 0:
            return ""
        is_zh = bool(re.search(r"[\u4e00-\u9fff]", str(user_query or "")))
        if is_zh:
            return "未检索到足够可依据的资料。由于你要求必须基于检索结果且不要编造，我不能在缺少可靠资料的情况下继续生成正文。"
        return "I could not find enough grounded evidence. Because you asked me to rely on search results and not invent facts, I cannot continue drafting without reliable source material."

    @staticmethod
    def _extract_ambiguous_subject_label(*, user_query: str, fallback: str = "") -> str:
        text = str(user_query or "").strip()
        for pattern in [r"“([^”]{1,40})”", r"\"([^\"]{1,40})\""]:
            m = re.search(pattern, text)
            if m:
                return str(m.group(1) or "").strip()
        token = re.findall(r"[A-Za-z][A-Za-z0-9._\-]{1,24}", text)
        if token:
            return str(token[0] or "").strip()
        if fallback:
            return str(fallback or "").strip()
        return "the subject"

    @staticmethod
    def _build_disambiguation_goal(*, subject_label: str, candidate_subjects: List[str]) -> str:
        label = str(subject_label or "the subject").strip()
        candidates = [str(item or "").strip() for item in list(candidate_subjects or []) if str(item or "").strip()]
        candidate_text = "; ".join(candidates[:4]) if candidates else "the most relevant candidate subjects"
        return (
            f"Do not present '{label}' as a uniquely identified subject. First explain that it has several common meanings in this context. "
            f"Focus on these candidates: {candidate_text}. Summarize each candidate's core concept, use cases, and distinguishing clues. "
            "Finally tell readers what context is needed to go deeper. Keep the whole piece in a disambiguating style; do not pretend the subject has been uniquely identified."
        )

    @staticmethod
    def _build_subject_clarification_message(
        *,
        user_query: str,
        subject_label: str,
        candidate_subjects: List[str],
    ) -> str:
        zh = contains_cjk(user_query)
        label = str(subject_label or ("该主题" if zh else "the subject")).strip()
        candidates = [str(item or "").strip() for item in list(candidate_subjects or []) if str(item or "").strip()]
        if zh:
            lines = [f"当前还不能唯一确定你说的“{label}”具体指哪一个对象。"]
            if candidates:
                lines.append("我目前识别到的候选有：")
                for idx, item in enumerate(candidates[:4], start=1):
                    lines.append(f"{idx}. {item}")
            lines.append("请补充一句上下文，或直接告诉我你指的是哪一个，我再按原要求继续生成。")
            return "\n".join(lines)
        lines = [f"I can't uniquely identify what '{label}' refers to yet."]
        if candidates:
            lines.append("Current likely candidates:")
            for idx, item in enumerate(candidates[:4], start=1):
                lines.append(f"{idx}. {item}")
        lines.append("Please add one line of context or tell me which one you mean, and I'll continue with the original writing request.")
        return "\n".join(lines)

    @staticmethod
    def _extract_user_query(context: SkillContext) -> str:
        inherited = ""
        if isinstance(context.output_spec, dict):
            inherited = str(context.output_spec.get("inherited_user_request") or "").strip()
        if inherited:
            return inherited
        for msg in reversed(context.messages or []):
            if msg.role == Role.USER and isinstance(msg.content, str):
                return msg.content.strip()
        return ""

    @staticmethod
    def _augment_body_goal_with_data_flow(
        *,
        body_user_goal: str,
        raw_user_query: str,
        upstream_artifacts: Dict[str, Any],
        node_meta: Dict[str, Any],
    ) -> str:
        """Append the cross-node data-flow context block to ``body_user_goal``.

        The compose LLM already has ``body_user_goal`` describing "how to
        write". This augmentation tells it "what came in from upstream and
        what's waiting downstream" so content can be grounded in real data
        rather than templated from thin air.

        Empty-upstream flag: when this node declared upstream deps but
        every value is empty/falsy, we *explicitly* say so — a compose
        LLM should surface "insufficient upstream data" rather than
        fabricate placeholder sections.
        """
        lines: List[str] = []

        trimmed_query = str(raw_user_query or "").strip()
        # Only include the user's original request when the body_user_goal
        # above didn't already quote it verbatim — avoids doubling the
        # same text into the prompt.
        if trimmed_query and trimmed_query not in (body_user_goal or ""):
            lines.append(f"[User's final goal (original request shared by all nodes)]\n{trimmed_query}")

        upstream_pairs: List[Tuple[str, Any]] = []
        if isinstance(upstream_artifacts, dict):
            for k, v in upstream_artifacts.items():
                key = str(k or "").strip()
                if not key or key.startswith("_"):
                    continue
                if key in ("browser_receipt", "skill_state", "skill_finalize", "answer", "graph_node_id"):
                    continue
                upstream_pairs.append((key, v))

        def _value_looks_empty(val: Any) -> bool:
            if val is None:
                return True
            if isinstance(val, str):
                s = val.strip().lower()
                return s in ("", "null", "none", "n/a", "undefined", "待确认", "tbd")
            if isinstance(val, (list, dict)):
                return not val
            return False

        if upstream_pairs:
            cleaned_upstream_pairs: List[Tuple[str, Any]] = []
            stripped_external_raw_count = 0
            for key, val in upstream_pairs:
                cleaned_val, removed_count = strip_external_web_raw(val)
                stripped_external_raw_count += removed_count
                if _value_looks_empty(cleaned_val):
                    continue
                cleaned_upstream_pairs.append((key, cleaned_val))

            all_empty = not cleaned_upstream_pairs or all(_value_looks_empty(v) for _k, v in cleaned_upstream_pairs)
            if all_empty:
                lines.append(
                    "[Upstream node output]\n"
                    "The upstream node declared these artifact keys, but **all values are empty**. "
                    "Do not write from empty data. State clearly in the body that upstream data collection failed and specific figures cannot be provided; make this visible to the user when needed.\n"
                    + "\n".join(f"  - {k}: (empty)" for k, _ in upstream_pairs[:10])
                )
            else:
                rendered: List[str] = []
                for key, val in cleaned_upstream_pairs[:12]:
                    try:
                        val_json = json.dumps(val, ensure_ascii=False)
                    except Exception:
                        val_json = str(val)
                    if len(val_json) > 1200:
                        val_json = val_json[:1200] + "...<truncated>"
                    rendered.append(f"  - {key}: {val_json}")
                if stripped_external_raw_count:
                    rendered.append(f"  - external_search_raw_filtered: {stripped_external_raw_count}")
                lines.append(
                    "[Upstream node output (concrete values to ground the writing)]\n"
                    + "\n".join(rendered)
                )

        consumers = node_meta.get("downstream_consumers") if isinstance(node_meta, dict) else None
        if isinstance(consumers, list) and consumers:
            consumer_lines: List[str] = []
            for c in consumers:
                if not isinstance(c, dict):
                    continue
                node_id = str(c.get("node_id") or "").strip()
                obj = str(c.get("objective") or "").strip()
                reqs = [str(x) for x in (c.get("required_inputs") or []) if str(x).strip()]
                bits: List[str] = []
                if node_id:
                    bits.append(f"`{node_id}`")
                if obj:
                    bits.append(f"Goal: {obj}")
                if reqs:
                    bits.append(f"Required artifacts: {', '.join(reqs[:6])}")
                if bits:
                    consumer_lines.append("  - " + " | ".join(bits))
            if consumer_lines:
                lines.append(
                    "[What downstream nodes need] (shape your output so they can use it directly)\n"
                    + "\n".join(consumer_lines)
                )

        if not lines:
            return body_user_goal
        return (body_user_goal or "") + "\n\n" + "\n\n".join(lines)

    @staticmethod
    def _build_body_user_goal(output_spec: Dict[str, Any], fallback: str) -> str:
        subject_resolution = output_spec.get("subject_resolution") if isinstance(output_spec.get("subject_resolution"), dict) else {}
        subject_hint = strip_visual_or_production_clauses(str(subject_resolution.get("article_goal_hint") or ""))
        canonical_subject = strip_visual_or_production_clauses(str(subject_resolution.get("canonical_subject") or ""))
        supporting_facts = [
            strip_visual_or_production_clauses(str(x))
            for x in list(subject_resolution.get("supporting_facts") or [])
            if strip_visual_or_production_clauses(str(x))
        ][:3]
        content_task_spec = output_spec.get("content_task_spec") if isinstance(output_spec.get("content_task_spec"), dict) else {}
        writing_mode = ComposeStrategyMixin._normalize_writing_mode(content_task_spec.get("writing_mode"))
        goal = dict(content_task_spec.get("goal") or {})
        publish_narrative = dict(content_task_spec.get("publish_narrative") or {})
        outcome = strip_visual_or_production_clauses(str(goal.get("outcome") or ""))
        preset = output_spec.get("profile_preset") if isinstance(output_spec.get("profile_preset"), dict) else {}
        structure = dict(preset.get("structure_contract") or {})
        compose = dict(preset.get("compose_policy") or {})
        output_contract = dict(preset.get("output_contract") or {})
        required_blocks = [str(x).strip() for x in list(structure.get("required_blocks") or output_spec.get("required_blocks") or []) if str(x).strip()]
        reader_problem = strip_visual_or_production_clauses(str(publish_narrative.get("reader_problem") or ""))
        narrative_goal = strip_visual_or_production_clauses(str(publish_narrative.get("narrative_goal") or ""))
        opening_intent = strip_visual_or_production_clauses(str(publish_narrative.get("opening_intent") or ""))
        closing_intent = strip_visual_or_production_clauses(str(publish_narrative.get("closing_intent") or ""))
        content_form = str(compose.get("content_form") or output_contract.get("deliverable") or "").strip().lower()
        base = ComposeStrategyMixin._body_base_instruction(output_spec, content_form)
        if reader_problem or narrative_goal:
            parts = [base]
            if writing_mode == "evidence_bound":
                parts.append("Write only from confirmed facts; clearly mark insufficient evidence as pending confirmation or a suggestion")
            elif writing_mode == "hybrid":
                parts.append("Keep the body fact-led; limited suggestions are allowed, but never present inferences as established facts")
            if canonical_subject:
                parts.append(f"Keep the entire piece focused on '{canonical_subject}'")
            if supporting_facts:
                parts.append(f"Anchor the writing in these facts first: {'; '.join(supporting_facts)}")
            if reader_problem:
                parts.append(f"Develop the piece around this real problem: {reader_problem}")
            if narrative_goal:
                parts.append(f"Article goal: {narrative_goal}")
            if opening_intent:
                parts.append(f"Opening requirement: {opening_intent}")
            if closing_intent:
                parts.append(f"Closing requirement: {closing_intent}")
            if required_blocks:
                parts.append(f"Cover these content blocks in the body: {'; '.join(required_blocks[:8])}")
            return ". ".join([p for p in parts if p]).strip(". ") + "."
        if canonical_subject and required_blocks:
            base_parts = [f"Complete this document about '{canonical_subject}'"]
            if writing_mode == "evidence_bound":
                base_parts.append("Write only from confirmed facts; clearly mark insufficient evidence as pending confirmation or a suggestion")
            if supporting_facts:
                base_parts.append(f"Anchor the writing in these facts first: {'; '.join(supporting_facts)}")
            base_parts.append(f"Cover these content blocks in the body: {'; '.join(required_blocks[:8])}")
            return ". ".join(base_parts).strip(". ") + "."
        if canonical_subject:
            if supporting_facts:
                return f"Complete this document about '{canonical_subject}' and anchor it in these facts first: {'; '.join(supporting_facts)}."
            return f"Complete this document about '{canonical_subject}', ensuring all sections and arguments serve this central subject."
        if subject_hint and required_blocks:
            return f"{subject_hint}. Cover these content blocks in the body: {'; '.join(required_blocks[:8])}."
        if subject_hint:
            return subject_hint
        if outcome and required_blocks:
            return f"{outcome}. Cover these content blocks in the body: {'; '.join(required_blocks[:8])}."
        if outcome:
            return outcome
        compose_profile = output_spec.get("compose_profile") if isinstance(output_spec.get("compose_profile"), dict) else {}
        intent_statement = strip_visual_or_production_clauses(str(compose_profile.get("intent_statement") or ""))
        if intent_statement and required_blocks:
            return f"{intent_statement}. Cover these content blocks in the body: {'; '.join(required_blocks[:8])}."
        if intent_statement:
            return intent_statement
        return strip_visual_or_production_clauses(fallback)

    @staticmethod
    def _build_title_hint(
        *,
        output_spec: Dict[str, Any],
        canonical_subject: str,
        language: str,
        user_query: str = "",
    ) -> str:
        explicit_title = strip_visual_or_production_clauses(
            str((output_spec or {}).get("explicit_title_block") or "")
        ).strip()
        if explicit_title:
            return explicit_title
        subject = ComposeBodyMixin._localize_subject_for_title(
            output_spec=output_spec,
            canonical_subject=canonical_subject,
            language=language,
            user_query=user_query,
        )
        if not subject:
            return ""
        content_task_spec = output_spec.get("content_task_spec") if isinstance(output_spec.get("content_task_spec"), dict) else {}
        writing_mode = ComposeStrategyMixin._normalize_writing_mode(content_task_spec.get("writing_mode"))
        if writing_mode == "creative":
            return ""
        preset = output_spec.get("profile_preset") if isinstance(output_spec.get("profile_preset"), dict) else {}
        compose = preset.get("compose_policy") if isinstance(preset.get("compose_policy"), dict) else {}
        output_contract = preset.get("output_contract") if isinstance(preset.get("output_contract"), dict) else {}
        deliverable = str(
            output_contract.get("deliverable")
            or compose.get("content_form")
            or output_spec.get("content_form")
            or "document"
        ).strip().lower()
        if deliverable in {"article", "post"}:
            label = "文章" if language == "zh" else "Article"
        elif deliverable in {"brief"}:
            label = "简报" if language == "zh" else "Brief"
        elif deliverable in {"plan"}:
            label = "方案" if language == "zh" else "Plan"
        else:
            label = "文档" if language == "zh" else "Document"
        if label in subject:
            return subject
        return f"{subject} {label}".strip()

    @staticmethod
    def _localize_subject_for_title(
        *,
        output_spec: Dict[str, Any],
        canonical_subject: str,
        language: str,
        user_query: str = "",
    ) -> str:
        subject = strip_visual_or_production_clauses(str(canonical_subject or "")).strip()
        if not subject:
            return ""
        if language != "zh" or contains_cjk(subject):
            return subject

        multimodal = output_spec.get("multimodal") if isinstance(output_spec.get("multimodal"), dict) else {}
        image_facts = multimodal.get("image_facts") if isinstance(multimodal.get("image_facts"), dict) else {}
        candidates: List[str] = []
        for token in list(image_facts.get("subject_candidates") or []) + list(image_facts.get("entities") or []):
            value = str(token or "").strip()
            if value and contains_cjk(value) and value not in candidates:
                candidates.append(value)
        strong_candidates = [item for item in candidates if any(marker in item for marker in ("系统", "平台", "工作台", "体系"))]
        if strong_candidates:
            return strong_candidates[0]
        for token in list(image_facts.get("page_titles") or []) + list(image_facts.get("ui_terms") or []):
            value = str(token or "").strip()
            if value and contains_cjk(value) and value not in candidates:
                candidates.append(value)
        if candidates:
            return candidates[0]
        return subject

    @staticmethod
    def _strip_visual_style_axes(style_markdown: str) -> str:
        text = str(style_markdown or "").strip()
        if not text:
            return ""
        blocked_prefixes = (
            "- visual_type_mix:",
            "- required_visual_total:",
            "- visual_roles:",
        )
        kept = []
        for raw in text.splitlines():
            line = str(raw or "")
            stripped = line.strip().lower()
            if any(stripped.startswith(prefix) for prefix in blocked_prefixes):
                continue
            kept.append(line)
        return "\n".join(kept).strip()

    @staticmethod
    def _sanitize_body_style_markdown(style_markdown: str) -> str:
        text = str(style_markdown or "").strip()
        if not text:
            return ""

        if text.startswith("---"):
            lines = text.splitlines()
            end = None
            for idx in range(1, len(lines)):
                if lines[idx].strip() == "---":
                    end = idx
                    break
            if end is not None:
                front = "\n".join(lines[1:end])
                body = "\n".join(lines[end + 1 :]).lstrip()
                try:
                    meta = yaml.safe_load(front) or {}
                except Exception:
                    meta = {}
                if isinstance(meta, dict):
                    style_contract = meta.get("style_contract")
                    if isinstance(style_contract, dict):
                        style_contract = dict(style_contract)
                        style_contract.pop("visual_policy", None)
                        meta["style_contract"] = style_contract
                    meta.pop("visual_policy", None)
                front_clean = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).strip() if isinstance(meta, dict) and meta else ""
                text = (f"---\n{front_clean}\n---\n\n{body}" if front_clean else body).strip()

        lines = text.splitlines()
        kept: list[str] = []
        skip_section = False
        in_visual_block = False
        for raw in lines:
            line = str(raw or "")
            stripped = line.strip()
            lowered = stripped.lower()

            if lowered.startswith("[visual:"):
                in_visual_block = True
                continue
            if lowered == "[/visual]":
                in_visual_block = False
                continue
            if in_visual_block:
                continue

            if re.match(r"^#{1,6}\s+", stripped):
                title = re.sub(r"^#{1,6}\s+", "", stripped).strip().lower()
                if title in {"visual spec format", "visual specs", "image guidance", "image generation"}:
                    skip_section = True
                    continue
                skip_section = False
            if skip_section:
                continue
            if any(token in lowered for token in ["visual_spec_format:", "include_infographic_blocks:", "image_render_enabled:"]):
                continue
            kept.append(line)
        text = strip_visual_placeholder_directives("\n".join(kept).strip())
        return ComposeBodyMixin._strip_visual_style_axes(text)
