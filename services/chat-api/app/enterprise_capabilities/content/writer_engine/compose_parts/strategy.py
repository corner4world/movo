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



class ComposeStrategyMixin:
    @staticmethod
    def _strip_outer_markdown_fence(text: str) -> str:
        raw = str(text or "").strip()
        if not raw:
            return raw
        m = re.match(r"^\s*```(?:md|markdown)?\s*\n([\s\S]*?)\n```\s*$", raw, flags=re.IGNORECASE)
        if not m:
            return raw
        inner = str(m.group(1) or "").strip()
        return inner

    @staticmethod
    def _truncate_text(value: Any, limit: int = 1800) -> str:
        raw = str(value or "")
        if len(raw) <= limit:
            return raw
        return raw[:limit] + "...<truncated>"

    @staticmethod
    def _normalize_writing_mode(value: Any) -> str:
        token = str(value or "").strip().lower()
        if token in {"creative", "hybrid", "evidence_bound"}:
            return token
        return "hybrid"

    @staticmethod
    def _target_words_from_quality(quality_gates: Dict[str, Any]) -> int:
        target = int(quality_gates.get("target_words") or 0)
        min_words = int(quality_gates.get("min_words") or 0)
        max_words = int(quality_gates.get("max_words") or 0)
        if target > 0:
            return target
        if min_words > 0 and max_words >= min_words:
            return (min_words + max_words) // 2
        return max_words or min_words or 0

    @staticmethod
    def _is_report_like_deliverable(output_spec: Dict[str, Any], strategy: Dict[str, Any]) -> bool:
        preset = output_spec.get("profile_preset") if isinstance(output_spec.get("profile_preset"), dict) else {}
        compose = preset.get("compose_policy") if isinstance(preset.get("compose_policy"), dict) else {}
        output_contract = preset.get("output_contract") if isinstance(preset.get("output_contract"), dict) else {}
        content_task_spec = output_spec.get("content_task_spec") if isinstance(output_spec.get("content_task_spec"), dict) else {}
        schema = content_task_spec.get("schema") if isinstance(content_task_spec.get("schema"), dict) else {}
        goal = content_task_spec.get("goal") if isinstance(content_task_spec.get("goal"), dict) else {}
        strategy_compose = strategy.get("compose_policy") if isinstance(strategy.get("compose_policy"), dict) else {}
        strategy_output = strategy.get("output_contract") if isinstance(strategy.get("output_contract"), dict) else {}
        tokens = {
            str(compose.get("content_form") or "").strip().lower(),
            str(output_contract.get("deliverable") or "").strip().lower(),
            str(strategy_compose.get("content_form") or "").strip().lower(),
            str(strategy_output.get("deliverable") or "").strip().lower(),
            str(schema.get("category") or "").strip().lower(),
            str(goal.get("primary_action") or "").strip().lower(),
            str(output_spec.get("_dynamic_deliverable_signature") or "").strip().lower(),
        }
        report_like = {
            "report",
            "document",
            "document_scale",
            "prd",
            "plan",
            "proposal",
            "solution",
            "方案",
            "whitepaper",
            "handbook",
            "analysis_report",
            "research_report",
            "product_requirements_document",
            "compose_report",
            "document_scale",
        }
        return bool(tokens.intersection(report_like))

    @staticmethod
    def _has_planned_generated_visuals(strategy: Dict[str, Any], output_spec: Dict[str, Any]) -> bool:
        content_task_spec = output_spec.get("content_task_spec") if isinstance(output_spec.get("content_task_spec"), dict) else {}
        visual_plan = content_task_spec.get("visual_plan") if isinstance(content_task_spec.get("visual_plan"), dict) else {}
        if int(visual_plan.get("min_assets") or 0) > 0:
            return True
        visual_policy = strategy.get("visual_policy") if isinstance(strategy.get("visual_policy"), dict) else {}
        if int(visual_policy.get("min_visuals_per_report") or 0) > 0:
            return True
        if int(visual_policy.get("min_infographics_per_report") or 0) > 0:
            return True
        return False

    @staticmethod
    def _body_document_shape(output_spec: Dict[str, Any], content_form: str = "") -> str:
        content_task_spec = output_spec.get("content_task_spec") if isinstance(output_spec.get("content_task_spec"), dict) else {}
        schema = content_task_spec.get("schema") if isinstance(content_task_spec.get("schema"), dict) else {}
        goal = content_task_spec.get("goal") if isinstance(content_task_spec.get("goal"), dict) else {}
        task_ir = output_spec.get("task_ir") if isinstance(output_spec.get("task_ir"), dict) else {}
        text = " ".join(
            [
                str(content_form or ""),
                str(output_spec.get("_dynamic_deliverable_signature") or ""),
                str(schema.get("name") or ""),
                str(schema.get("type") or ""),
                str(schema.get("category") or ""),
                str(goal.get("primary_action") or ""),
                str(goal.get("outcome") or ""),
                str(task_ir.get("deliverable_mode") or ""),
                str(output_spec.get("_timeline_user_text") or ""),
            ]
        ).strip().lower()
        if any(token in text for token in ("manual", "handbook", "instruction", "说明书", "手册", "largemodelusermanual")):
            return "manual"
        if any(token in text for token in ("guide", "tutorial", "指南", "教程")):
            return "guide"
        if any(token in text for token in ("faq", "常见问题")):
            return "faq"
        if any(token in text for token in ("sop", "standard operating procedure", "操作规程", "标准作业")):
            return "sop"
        if any(token in text for token in ("prd", "product_requirements_document")):
            return "prd"
        return str(content_form or "").strip().lower()

    @classmethod
    def _body_base_instruction(cls, output_spec: Dict[str, Any], content_form: str) -> str:
        shape = cls._body_document_shape(output_spec, content_form=content_form)
        if shape == "manual":
            return "Write a manual that readers can follow directly, covering audience, core concepts, preparation, steps, precautions, and FAQs; do not turn it into a background analysis report"
        if shape == "guide":
            return "Write a practical guide focused on procedures, examples, checklists, and precautions; do not turn it into a research report"
        if shape == "faq":
            return "Write a question-and-answer FAQ addressing real user questions one by one; avoid report-style background analysis"
        if shape == "sop":
            return "Write a standard operating procedure covering scope, responsibilities, steps, checkpoints, and exception handling"
        if shape == "prd":
            return "Write a product requirements document covering goals, user scenarios, functional and nonfunctional requirements, and acceptance criteria"
        if shape in {"report", "document_scale"}:
            return "Write a complete formal report suitable for collaboration and review"
        if shape == "plan":
            return "Write an actionable, implementable plan document"
        if shape in {"document", "brief", "memo"}:
            return "Write a structured document for the final reader; get straight to the topic and avoid report-style background buildup"
        return "Write a publishable article for the final reader"

    @staticmethod
    def _merge_uploaded_assets(existing_assets: List[Dict[str, Any]], new_assets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        seen = set()
        for asset in [*list(existing_assets or []), *list(new_assets or [])]:
            if not isinstance(asset, dict):
                continue
            key = (
                str(asset.get("asset_id") or "").strip(),
                str(asset.get("object_path") or "").strip(),
                str(asset.get("path") or asset.get("signed_url") or "").strip(),
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(dict(asset))
        return merged

    @classmethod
    def _collect_uploaded_assets_for_compose(cls, output_spec: Dict[str, Any]) -> List[Dict[str, Any]]:
        multimodal = output_spec.get("multimodal") if isinstance(output_spec.get("multimodal"), dict) else {}
        assets = [dict(x) for x in list(multimodal.get("uploaded_assets") or []) if isinstance(x, dict)]

        parsed_documents: List[Dict[str, Any]] = []
        documents = output_spec.get("documents") if isinstance(output_spec.get("documents"), dict) else {}
        parsed_documents.extend(
            dict(x) for x in list(documents.get("parsed_documents") or []) if isinstance(x, dict)
        )
        for artifact_bucket_key in ("input_artifacts", "predecessor_artifacts"):
            artifact_bucket = output_spec.get(artifact_bucket_key)
            if not isinstance(artifact_bucket, dict):
                continue
            for artifact in artifact_bucket.values():
                if not isinstance(artifact, dict):
                    continue
                parsed_documents.extend(
                    dict(x) for x in list(artifact.get("parsed_documents") or []) if isinstance(x, dict)
                )
                nested_documents = artifact.get("documents") if isinstance(artifact.get("documents"), dict) else {}
                parsed_documents.extend(
                    dict(x) for x in list(nested_documents.get("parsed_documents") or []) if isinstance(x, dict)
                )

        embedded_assets: List[Dict[str, Any]] = []
        seen_docs = set()
        for doc in parsed_documents:
            doc_key = (
                str(doc.get("asset_id") or "").strip(),
                str(doc.get("filename") or "").strip(),
                len(list(doc.get("embedded_images") or [])),
            )
            if doc_key in seen_docs:
                continue
            seen_docs.add(doc_key)
            embedded_assets.extend(
                build_embedded_document_image_assets(
                    embedded_images=[dict(x) for x in list(doc.get("embedded_images") or []) if isinstance(x, dict)],
                    source_document_id=str(doc.get("asset_id") or doc.get("filename") or "").strip(),
                )
            )
        return cls._merge_uploaded_assets(assets, embedded_assets)

    @staticmethod
    def _build_strategy(output_spec: Dict[str, Any]) -> Dict[str, Any]:
        preset = output_spec.get("profile_preset") if isinstance(output_spec.get("profile_preset"), dict) else {}
        _is_dynamic_preset = str((preset or {}).get("source") or "").strip().lower() == "dynamic"
        prompt_contract = output_spec.get("prompt_contract") if isinstance(output_spec.get("prompt_contract"), dict) else {}
        production_contract = output_spec.get("production_contract") if isinstance(output_spec.get("production_contract"), dict) else {}
        content_plan = output_spec.get("content_plan") if isinstance(output_spec.get("content_plan"), dict) else {}
        argument_pack = output_spec.get("argument_pack") if isinstance(output_spec.get("argument_pack"), dict) else {}
        visual_semantics = output_spec.get("visual_semantics") if isinstance(output_spec.get("visual_semantics"), dict) else {}
        content_task_spec = output_spec.get("content_task_spec") if isinstance(output_spec.get("content_task_spec"), dict) else {}
        structure = preset.get("structure_contract") if isinstance(preset.get("structure_contract"), dict) else {}
        evidence = preset.get("evidence_policy") if isinstance(preset.get("evidence_policy"), dict) else {}
        visual = preset.get("visual_contract") if isinstance(preset.get("visual_contract"), dict) else {}
        gates = preset.get("quality_gates") if isinstance(preset.get("quality_gates"), dict) else {}
        compose = preset.get("compose_policy") if isinstance(preset.get("compose_policy"), dict) else {}
        # Carry top-level output_spec.compose_policy into strategy when preset is empty
        # OR when the top-level overrides carry signals the preset doesn't have
        # (evidence_strength_hint and pinned section/length constraints).
        # Preset values stay authoritative when both are present.
        top_compose = output_spec.get("compose_policy") if isinstance(output_spec.get("compose_policy"), dict) else {}
        if isinstance(top_compose, dict):
            merged_compose = dict(top_compose)
            for k, v in (compose or {}).items():
                if v not in (None, "", [], {}):
                    merged_compose[k] = v
            compose = merged_compose

        required_blocks = list(structure.get("required_blocks") or output_spec.get("required_blocks") or [])
        explicit_count = int(structure.get("section_count") or 0)
        # Prefer concrete block list cardinality to avoid stale section_count drift.
        section_count = len(required_blocks) if required_blocks else (explicit_count if explicit_count > 0 else 8)
        section_count = max(1, min(section_count, 18))
        body_plan = build_body_plan(structure=structure, content_plan=content_plan)
        visual_plan = dict(content_task_spec.get("visual_plan") or {})
        min_images = max(0, int(visual_plan.get("min_assets") or 0))
        max_images = max(min_images, int(visual_plan.get("max_assets") or 0))
        if max_images < min_images:
            max_images = min_images
        min_words = int(gates.get("min_words") or 0)
        max_words = int(gates.get("max_words") or 0)
        target_words = int(gates.get("target_words") or 0)
        if target_words <= 0:
            if min_words > 0 and max_words >= min_words:
                target_words = (min_words + max_words) // 2
            elif max_words > 0:
                target_words = max_words
            elif _is_dynamic_preset:
                # Dynamic preset with no word signal: conservative short-form
                # default rather than 2600 (which is article-shaped).
                target_words = 800
            else:
                target_words = 2600
        section_min = int(gates.get("section_min_words") or 220)
        section_max = int(gates.get("section_max_words") or 650)
        if section_max < section_min:
            section_max = section_min

        # For dynamic presets (unknown deliverable types — resume, email,
        # manual), default to "none" instead of "hierarchical": short
        # structured docs should not get 1./2./3. numbering by accident.
        _numbering_default = "none" if _is_dynamic_preset else "hierarchical"
        _numbering_style = str(structure.get("numbering_style") or _numbering_default).strip().lower()
        if _numbering_style not in {"hierarchical", "flat", "clause", "none"}:
            _numbering_style = _numbering_default
        strategy = {
            "section_count": section_count,
            "outline_depth": int(structure.get("outline_depth") or 2),
            "numbering_style": _numbering_style,
            "word_budget": {
                "total_target": target_words,
                "section_min": section_min,
                "section_max": section_max,
            },
            "visual_policy": {
                "min_visuals_per_report": min_images,
                "max_visuals_per_report": max_images,
                "min_infographics_per_report": min_images,
                "max_infographics_per_report": max_images,
                "include_infographics": bool(min_images > 0 or list(visual_plan.get("assets") or [])),
            },
            "compose_policy": dict(compose),
            "structure_contract": dict(structure),
            "evidence_policy": dict(evidence),
            "visual_contract": dict(visual),
            "quality_gates": dict(gates),
            "output_contract": dict(preset.get("output_contract") or {}),
            "forbidden_patterns": list(preset.get("forbidden_patterns") or []),
            "prompt_contract": dict(prompt_contract),
            "production_contract": dict(production_contract),
            "content_plan": dict(content_plan),
            "body_plan": dict(body_plan),
            "content_task_spec": dict(content_task_spec),
            "writing_mode": ComposeStrategyMixin._normalize_writing_mode(content_task_spec.get("writing_mode")),
            "argument_pack": dict(argument_pack),
            "visual_semantics": dict(visual_semantics),
        }
        # Doc-level eval feedback (set by task_satisfaction_eval on retry):
        # mirror onto strategy so the writer engine's generate methods can
        # read it via the same field regardless of which entry path runs.
        _doc_feedback = str(output_spec.get("__doc_level_eval_feedback") or "").strip()
        if _doc_feedback:
            strategy["doc_level_feedback"] = _doc_feedback
        try:
            log_print(
                "[tool_writer_engine_compose][strategy] dynamic=%s section_count=%s "
                "numbering=%s target_words=%s min/max=%s/%s min_imgs=%s "
                "content_form=%s blocks=%s"
                % (
                    _is_dynamic_preset,
                    section_count,
                    _numbering_style,
                    target_words,
                    min_words,
                    max_words,
                    min_images,
                    str(compose.get("content_form") or ""),
                    json.dumps(list(structure.get("required_blocks") or []), ensure_ascii=False),
                ),
                flush=True,
            )
        except Exception:
            pass
        return strategy

    def _decide_execution_mode(self, *, strategy: Dict[str, Any], output_spec: Dict[str, Any], user_query: str) -> Dict[str, Any]:
        decision = self._mode_resolver.resolve(
            compose_policy=strategy.get("compose_policy") if isinstance(strategy.get("compose_policy"), dict) else {},
            structure_contract=strategy.get("structure_contract") if isinstance(strategy.get("structure_contract"), dict) else {},
            quality_gates=strategy.get("quality_gates") if isinstance(strategy.get("quality_gates"), dict) else {},
            evidence_policy=strategy.get("evidence_policy") if isinstance(strategy.get("evidence_policy"), dict) else {},
            prompt_contract=strategy.get("prompt_contract") if isinstance(strategy.get("prompt_contract"), dict) else {},
            user_query=user_query,
        )
        return decision.model_dump()

    def _attach_section_arguments(self, strategy: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(strategy or {})
        body_plan = out.get("body_plan") if isinstance(out.get("body_plan"), dict) else {}
        argument_pack = out.get("argument_pack") if isinstance(out.get("argument_pack"), dict) else {}
        sections = [item for item in list(body_plan.get("sections") or []) if isinstance(item, dict)]
        if not sections or not argument_pack:
            return out
        enriched = []
        for sec in sections:
            item = dict(sec)
            item["argument_items"] = self._argument_selector.select_for_section(
                argument_pack=argument_pack,
                title=str(item.get("title") or ""),
                objective=str(item.get("purpose") or item.get("objective") or ""),
                evidence_focus=[str(x) for x in list(item.get("evidence_focus") or []) if str(x).strip()],
            )
            enriched.append(item)
        updated_plan = dict(body_plan)
        updated_plan["sections"] = enriched
        out["body_plan"] = updated_plan
        return out

    @staticmethod
    def _ensure_runtime_contract(strategy: Dict[str, Any], output_spec: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(strategy or {})
        compose = out.get("compose_policy") if isinstance(out.get("compose_policy"), dict) else {}
        structure = out.get("structure_contract") if isinstance(out.get("structure_contract"), dict) else {}
        evidence = out.get("evidence_policy") if isinstance(out.get("evidence_policy"), dict) else {}
        quality = out.get("quality_gates") if isinstance(out.get("quality_gates"), dict) else {}
        output = out.get("output_contract") if isinstance(out.get("output_contract"), dict) else {}
        gp = resolve_compose_policy(output_spec)
        effective_policy = output_spec.get("effective_policy") if isinstance(output_spec.get("effective_policy"), dict) else {}
        effective_compose = (
            effective_policy.get("compose_policy") if isinstance(effective_policy.get("compose_policy"), dict) else {}
        )
        effective_sections = [str(x).strip() for x in (effective_compose.get("required_sections") or []) if str(x).strip()]
        compose_sections = [str(x).strip() for x in (compose.get("required_sections") or []) if str(x).strip()]
        required_blocks = [str(x).strip() for x in (structure.get("required_blocks") or []) if str(x).strip()]
        output_blocks = [str(x).strip() for x in (output_spec.get("required_blocks") or []) if str(x).strip()]
        if not output_blocks:
            output_blocks = [str(x).strip() for x in (gp.get("required_sections") or []) if str(x).strip()]

        # Authoritative source ranking for required_blocks:
        #   - For dynamic-source presets, the SYNTH's structure_contract wins.
        #     Upstream `compose.required_sections` is often a single sentence
        #     describing the deliverable (e.g.
        #     a sentence requesting a professional resume) — meant as a
        #     deliverable descriptor, not as a section list. Letting it win
        #     collapses synth's 6-7 resume blocks into a single bogus section.
        #   - For non-dynamic (builtin presets / catalog), compose policy stays
        #     authoritative as before.
        _preset_for_order = output_spec.get("profile_preset") if isinstance(output_spec.get("profile_preset"), dict) else {}
        _is_dynamic_preset = str((_preset_for_order or {}).get("source") or "").strip().lower() == "dynamic"
        if _is_dynamic_preset and required_blocks:
            # Keep synth's structure_contract.required_blocks; ignore upstream noise.
            pass
        elif compose_sections:
            required_blocks = compose_sections
        elif effective_sections:
            required_blocks = effective_sections
        else:
            if len(output_blocks) > len(required_blocks):
                required_blocks = output_blocks
            if not required_blocks:
                required_blocks = output_blocks
        if not required_blocks:
            required_blocks = ["核心内容"]
        # Dynamic-source presets carry user-facing order from the synthesiser
        # (resume → header→summary→experience→…). canonicalize_required_blocks's
        # weight map is article-shaped and would shuffle those into alphabetical
        # order. Preserve order in dynamic mode.
        required_blocks = canonicalize_required_blocks(required_blocks, preserve_order=_is_dynamic_preset)
        structure["required_blocks"] = required_blocks
        section_roles = [str(x).strip() for x in list(structure.get("section_roles") or []) if str(x).strip()]
        if not section_roles:
            structure_blocks = [item for item in list(structure.get("blocks") or []) if isinstance(item, dict)]
            section_roles = normalize_section_roles([str(item.get("role") or "") for item in structure_blocks])
        if not section_roles:
            body_plan = out.get("body_plan") if isinstance(out.get("body_plan"), dict) else {}
            body_sections = [item for item in list(body_plan.get("sections") or []) if isinstance(item, dict)]
            section_roles = normalize_section_roles([str(item.get("role") or "") for item in body_sections])
        if not section_roles:
            content_plan = out.get("content_plan") if isinstance(out.get("content_plan"), dict) else {}
            content_sections = [item for item in list(content_plan.get("sections") or []) if isinstance(item, dict)]
            section_roles = normalize_section_roles([str(item.get("role") or "") for item in content_sections])
        if section_roles:
            structure["section_roles"] = section_roles[:8]
        structure.setdefault("section_count", max(1, len(required_blocks)))
        schema_planning_mode = str(structure.get("planning_mode") or "").strip()
        if schema_planning_mode and not str(structure.get("schema_planning_mode") or "").strip():
            structure["schema_planning_mode"] = schema_planning_mode
        structure.pop("planning_mode", None)

        compose["tone"] = str(compose.get("tone") or gp.get("tone") or "professional").strip()
        compose["content_form"] = str(compose.get("content_form") or gp.get("content_form") or "article").strip()
        writing_mode = ComposeStrategyMixin._normalize_writing_mode(
            out.get("writing_mode")
            or output_spec.get("writing_mode")
            or ((out.get("content_task_spec") or {}).get("writing_mode") if isinstance(out.get("content_task_spec"), dict) else "")
        )
        compose["writing_mode"] = writing_mode
        write_mode = str(compose.get("write_mode") or gp.get("write_mode") or "auto").strip().lower()
        if write_mode == "structured":
            write_mode = "sectional"
        if write_mode not in {"direct", "compact_block", "sectional", "document_scale", "auto"}:
            write_mode = "auto"
        compose["write_mode"] = write_mode
        normalized_content_form = str(compose.get("content_form") or "").strip().lower()
        if "citation_required" not in evidence:
            tc = output_spec.get("task_contract") if isinstance(output_spec.get("task_contract"), dict) else {}
            evidence["citation_required"] = bool(str(tc.get("evidence_mode") or "").strip().lower() == "required")
        if writing_mode == "evidence_bound":
            evidence["citation_required"] = True
        # Dynamic preset: trust quality_gates set upstream by normalize_minimal_spec
        # (which already gave synth's word range priority). Falling back to
        # gp/1200/2600 here was the second-tier leak that re-inflated short
        # forms (resume) even after minimal_spec preserved 350-700.
        if _is_dynamic_preset and quality.get("min_words") and quality.get("max_words"):
            min_words = int(quality["min_words"])
            max_words = int(quality["max_words"])
        elif _is_dynamic_preset:
            min_words = int(quality.get("min_words") or gp.get("min_words") or 400)
            max_words = int(quality.get("max_words") or gp.get("max_words") or 1200)
        else:
            min_words = int(quality.get("min_words") or gp.get("min_words") or 1200)
            max_words = int(quality.get("max_words") or gp.get("max_words") or 2600)
        if max_words < min_words:
            max_words = min_words + 600
        quality["min_words"] = min_words
        quality["max_words"] = max_words
        output["format"] = str(output.get("format") or "markdown").strip()
        deliverable = str(output.get("deliverable") or normalized_content_form or "").strip().lower()
        if normalized_content_form in {"report", "document", "document_scale", "prd", "brief"} or deliverable in {
            "report",
            "document",
            "document_scale",
            "prd",
            "brief",
        }:
            output["deliverable"] = "report" if normalized_content_form in {"report", "document", "document_scale", "prd"} else "brief"
        elif normalized_content_form == "plan" or deliverable == "plan":
            output["deliverable"] = "plan"
        else:
            output["deliverable"] = deliverable or "article"

        out["compose_policy"] = compose
        out["structure_contract"] = structure
        out["evidence_policy"] = evidence
        out["quality_gates"] = quality
        out["output_contract"] = output
        out["writing_mode"] = writing_mode

        # FIX: required_blocks must dictate absolute minimum section_count
        base_count = int(out.get("section_count") or 0)
        req_len = len(required_blocks)
        # Evidence-aware floor: when upstream supplied an explicit
        # evidence_strength_hint and it's thin, don't
        # pad a "report" up to 6 sections — let req_len drive section_count.
        evidence_hint_raw = compose.get("evidence_strength_hint")
        evidence_hint = int(evidence_hint_raw) if evidence_hint_raw is not None else -1
        thin_evidence = 0 <= evidence_hint < 4
        # Dynamic preset: synth's section_count / required_blocks is authoritative.
        # Forcing report->6 / brief->5 here was the third leak that turned a
        # 5-block resume contract into a 6-block report-shaped output.
        if _is_dynamic_preset:
            floor = 1
            out["section_count"] = max(floor, min(24, max(base_count, req_len)))
            return out
        if normalized_content_form == "report" and not thin_evidence:
            base_count = max(base_count, 6)
        elif normalized_content_form in {"brief", "document", "document_scale", "prd"} and not thin_evidence:
            base_count = max(base_count, 5)
        floor = 1 if thin_evidence else 4
        out["section_count"] = max(floor, min(24, max(base_count, req_len)))
        return out
