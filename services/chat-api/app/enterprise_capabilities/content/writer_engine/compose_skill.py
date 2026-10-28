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


from .compose_parts.strategy import ComposeStrategyMixin
from .compose_parts.evidence import ComposeEvidenceMixin
from .compose_parts.body import ComposeBodyMixin

class ToolWriterEngineComposeSkill(ComposeStrategyMixin, ComposeEvidenceMixin, ComposeBodyMixin, BaseSkill):
    name = "tool_writer_engine_compose"
    description = "Unified bottom-layer writing engine driven by profile preset."

    def __init__(self) -> None:
        self._pipeline = WriterEnginePipeline()
        self._argument_selector = ArgumentPackSelector()
        self._mode_resolver = ExecutionModeResolver()
        self._subject_resolver = SubjectResolutionResolver()

    async def run_stream(self, context: SkillContext) -> AsyncIterator[Dict[str, Any]]:
        output_spec = dict(context.output_spec or {})
        payload = dict(context.payload or {})
        raw_user_query = self._extract_user_query(context)

        strategy = self._build_strategy(output_spec)
        strategy = self._attach_section_arguments(strategy)
        strategy = self._ensure_runtime_contract(strategy, output_spec)
        strategy["_operation_scope"] = str(
            output_spec.get("current_task_node_id") or output_spec.get("request_id") or "writer"
        ).strip()
        # Keep debug output aligned with the finalized runtime contract.
        output_spec["required_blocks"] = list(
            ((strategy.get("structure_contract") or {}).get("required_blocks") or [])
        )
        route = self._decide_execution_mode(strategy=strategy, output_spec=output_spec, user_query=raw_user_query)
        resolved_mode = str(route.get("mode") or "direct_compose")
        strategy["mode"] = (
            "sectional_compose"
            if resolved_mode in {"sectional_compose", "document_scale_compose"}
            else "direct_compose"
        )
        # Merge delivery-level flags (e.g. agreement mode) from the upstream compose_strategy
        # OR detect agreement type directly from output_spec (graph orchestrator path).
        delivery_compose = payload.get("compose_strategy") if isinstance(payload.get("compose_strategy"), dict) else {}
        delivery_mode = str(delivery_compose.get("mode") or "").strip().lower()
        if delivery_mode != "agreement_clauses":
            # Fallback: detect agreement from output_spec deliverable_type / task_contract
            # (graph orchestrator does NOT call build_delivery_profile, so compose_strategy is empty)
            _gc = output_spec.get("goal_contract") if isinstance(output_spec.get("goal_contract"), dict) else {}
            _tc = output_spec.get("task_contract") if isinstance(output_spec.get("task_contract"), dict) else {}
            _dtype = str(
                _gc.get("deliverable_type")
                or _tc.get("deliverable_mode")
                or _tc.get("selected_mode")
                or ""
            ).strip().lower()
            if _dtype in {"agreement", "contract", "protocol", "mou", "nda", "terms"}:
                delivery_mode = "agreement_clauses"
            elif _dtype in {"translation", "translate"}:
                delivery_mode = "translation"
        if delivery_mode == "translation":
            strategy["mode"] = "translation"
            strategy["skip_toc"] = True
            strategy["skip_visuals"] = True
            strategy["visual_policy"] = {
                "min_visuals_per_report": 0,
                "max_visuals_per_report": 0,
                "min_infographics_per_report": 0,
                "max_infographics_per_report": 0,
                "include_infographics": False,
            }
            # Auto-infer output format from uploaded source file type
            import os
            _docs = output_spec.get("documents") if isinstance(output_spec.get("documents"), dict) else {}
            _parsed = [dict(x) for x in list(_docs.get("parsed_documents") or []) if isinstance(x, dict)]
            for _pd in _parsed[:1]:
                _fn = str(_pd.get("filename") or "").strip().lower()
                _ext = os.path.splitext(_fn)[1]
                if _ext in {".docx", ".doc"}:
                    output_spec.setdefault("formats", [])
                    if "docx" not in output_spec["formats"]:
                        output_spec["formats"].append("docx")
                elif _ext in {".xlsx", ".xlsm", ".xls"}:
                    output_spec.setdefault("formats", [])
                    if "xlsx" not in output_spec["formats"]:
                        output_spec["formats"].append("xlsx")
                elif _ext == ".pdf":
                    output_spec.setdefault("formats", [])
                    if "pdf" not in output_spec["formats"]:
                        output_spec["formats"].append("pdf")
            if isinstance(context.output_spec, dict):
                context.output_spec["formats"] = list(output_spec.get("formats") or [])
        if delivery_mode == "agreement_clauses":
            strategy["mode"] = delivery_mode
            strategy["skip_toc"] = True
            strategy["skip_visuals"] = True
            strategy["numbering_style"] = str(delivery_compose.get("numbering_style") or "clause")
            strategy["section_count"] = int(delivery_compose.get("section_count") or strategy.get("section_count") or 8)
            strategy["outline_depth"] = int(delivery_compose.get("outline_depth") or 1)
            # Disable visuals for agreements
            strategy["visual_policy"] = {
                "min_visuals_per_report": 0,
                "max_visuals_per_report": 0,
                "min_infographics_per_report": 0,
                "max_infographics_per_report": 0,
                "include_infographics": False,
            }
        payload["compose_strategy"] = strategy
        logging.warning(
            "[writer_engine] agreement_detect | delivery_mode=%s strategy_mode=%s skip_toc=%s skip_visuals=%s numbering=%s gc_type=%s tc_mode=%s",
            delivery_mode,
            strategy.get("mode", ""),
            strategy.get("skip_toc", ""),
            strategy.get("skip_visuals", ""),
            strategy.get("numbering_style", ""),
            (output_spec.get("goal_contract") or {}).get("deliverable_type", ""),
            (output_spec.get("task_contract") or {}).get("deliverable_mode", ""),
        )

        preset = output_spec.get("profile_preset") if isinstance(output_spec.get("profile_preset"), dict) else {}
        compose_policy = preset.get("compose_policy") if isinstance(preset.get("compose_policy"), dict) else {}
        gp = dict(resolve_compose_policy(output_spec) or {})
        gp.update({k: v for k, v in compose_policy.items() if v is not None})
        output_spec["generation_policy"] = gp

        try:
            log_print(
                "[writer_engine] mode=%s preset=%s source=%s section_count=%s required_blocks=%s score=%s reasons=%s"
                % (
                    str(strategy.get("mode") or ""),
                    str(preset.get("preset_id") or ""),
                    str(preset.get("source") or ""),
                    int(strategy.get("section_count") or 0),
                    json.dumps(list(output_spec.get("required_blocks") or []), ensure_ascii=False),
                    int(route.get("score") or 0),
                    json.dumps(list(route.get("reasons") or []), ensure_ascii=False),
                ),
                flush=True,
            )
        except Exception:
            pass
        try:
            assembly = compose_policy.get("assembly_profile") if isinstance(compose_policy.get("assembly_profile"), dict) else {}
            log_print(
                "[writer_engine] assembly source=%s length=%s scan=%s visuals=%s hook=%s tags=%s signals=%s"
                % (
                    str(assembly.get("source") or ""),
                    str(assembly.get("length_band") or ""),
                    str(assembly.get("scannability") or ""),
                    str(assembly.get("visual_density") or ""),
                    str(assembly.get("hook_strength") or ""),
                    str(assembly.get("tagging_mode") or ""),
                    ",".join([str(x) for x in list(assembly.get("signals") or [])[:8]]),
                ),
                flush=True,
            )
        except Exception:
            pass
        try:
            compose_profile = dict(output_spec.get("compose_profile") or {})
            profile_preset = dict(output_spec.get("profile_preset") or {})
            prompt_contract = dict(output_spec.get("prompt_contract") or {})
            strategy_view = dict(strategy or {})

            preset_summary = {
                "preset_id": profile_preset.get("preset_id"),
                "source": profile_preset.get("source"),
                "publish_channel": (profile_preset.get("compose_policy") or {}).get("publish_channel"),
                "content_form": (profile_preset.get("compose_policy") or {}).get("content_form"),
                "required_blocks": (profile_preset.get("structure_contract") or {}).get("required_blocks"),
                "section_count": (profile_preset.get("structure_contract") or {}).get("section_count"),
                "citation_required": (profile_preset.get("evidence_policy") or {}).get("citation_required"),
                "deliverable": (profile_preset.get("output_contract") or {}).get("deliverable"),
            }
            prompt_summary = {
                "keys": sorted(list(prompt_contract.keys())),
                "must_include_count": len(list(prompt_contract.get("must_include") or [])),
                "forbidden_count": len(list(prompt_contract.get("forbidden_patterns") or [])),
                "has_identity": bool(str(prompt_contract.get("identity") or "").strip()),
                "has_style_ref_pos": bool(str((prompt_contract.get("style_reference") or {}).get("positive") or "").strip()),
                "style_markdown_len": len(str(prompt_contract.get("style_markdown") or "")),
                "style_markdown_compact_len": len(str(prompt_contract.get("style_markdown_compact") or "")),
            }
            strategy_summary = {
                "section_count": strategy_view.get("section_count"),
                "outline_depth": strategy_view.get("outline_depth"),
                "word_budget": strategy_view.get("word_budget"),
                "visual_policy": strategy_view.get("visual_policy"),
                "required_blocks": (strategy_view.get("structure_contract") or {}).get("required_blocks"),
                "deliverable": (strategy_view.get("output_contract") or {}).get("deliverable"),
            }

            log_print(
                "[writer_engine] compose profile | intent=%s audience=%s confidence=%s"
                % (
                    str(compose_profile.get("intent_statement") or "")[:120],
                    str(compose_profile.get("audience_model") or "")[:120],
                    str(compose_profile.get("confidence") or ""),
                ),
                flush=True,
            )
            log_print(
                "[writer_engine] preset summary | id=%s source=%s channel=%s form=%s sections=%s deliverable=%s citations=%s"
                % (
                    str(preset_summary.get("preset_id") or ""),
                    str(preset_summary.get("source") or ""),
                    str(preset_summary.get("publish_channel") or ""),
                    str(preset_summary.get("content_form") or ""),
                    int(preset_summary.get("section_count") or 0),
                    str(preset_summary.get("deliverable") or ""),
                    str(bool(preset_summary.get("citation_required"))),
                ),
                flush=True,
            )
            log_print(
                "[writer_engine] prompt contract | keys=%s must_include=%s forbidden=%s has_identity=%s has_style_ref=%s"
                % (
                    len(list(prompt_summary.get("keys") or [])),
                    int(prompt_summary.get("must_include_count") or 0),
                    int(prompt_summary.get("forbidden_count") or 0),
                    str(bool(prompt_summary.get("has_identity"))),
                    str(bool(prompt_summary.get("has_style_ref_pos"))),
                ),
                flush=True,
            )
            log_print(
                "[writer_engine] strategy summary | sections=%s depth=%s target_words=%s required_blocks=%s deliverable=%s"
                % (
                    int(strategy_summary.get("section_count") or 0),
                    int(strategy_summary.get("outline_depth") or 0),
                    int(((strategy_summary.get("word_budget") or {}).get("total_target") or 0)),
                    len(list(strategy_summary.get("required_blocks") or [])),
                    str(strategy_summary.get("deliverable") or ""),
                ),
                flush=True,
            )
        except Exception:
            pass

        tool_observations = list(payload.get("tool_observations") or [])
        tool_observations = self._build_document_tool_observations(
            output_spec=output_spec,
            base_observations=tool_observations,
        )
        if isinstance(context.output_spec, dict):
            context.output_spec["tool_observations"] = list(tool_observations or [])

        has_generated_visuals = self._has_planned_generated_visuals(strategy=strategy, output_spec=output_spec)
        if not has_generated_visuals and str(strategy.get("mode") or "").strip().lower() not in {"translation", "agreement_clauses"}:
            strategy["skip_visuals"] = True
            strategy["visual_policy"] = {
                "min_visuals_per_report": 0,
                "max_visuals_per_report": 0,
                "min_infographics_per_report": 0,
                "max_infographics_per_report": 0,
                "include_infographics": False,
            }
        subject_context = self._build_subject_context(output_spec)
        node_meta_for_subject = (
            output_spec.get("current_task_node_meta")
            if isinstance(output_spec.get("current_task_node_meta"), dict)
            else {}
        )
        subject_source_contract = (
            node_meta_for_subject.get("subject_source")
            if isinstance(node_meta_for_subject.get("subject_source"), dict)
            else None
        )
        upstream_artifacts_for_subject: Dict[str, Any] = {}
        if isinstance(output_spec.get("input_artifacts"), dict):
            upstream_artifacts_for_subject.update(dict(output_spec.get("input_artifacts") or {}))
        predecessor_for_subject = (
            output_spec.get("predecessor_artifacts")
            if isinstance(output_spec.get("predecessor_artifacts"), dict)
            else {}
        )
        for _pred_node_id, _pred_artifact in predecessor_for_subject.items():
            if not isinstance(_pred_artifact, dict):
                continue
            for _k, _v in _pred_artifact.items():
                if str(_k).startswith("_"):
                    continue
                upstream_artifacts_for_subject.setdefault(str(_k), _v)
        subject_resolution = await self._subject_resolver.resolve(
            user_query=raw_user_query,
            tool_observations=tool_observations,
            document_context=subject_context,
            subject_source=subject_source_contract,
            upstream_artifacts=upstream_artifacts_for_subject or None,
        )
        output_spec["subject_resolution"] = subject_resolution.model_dump()
        body_user_goal = self._build_body_user_goal(output_spec, raw_user_query)
        # Append cross-node data-flow context so the compose LLM sees the
        # same three layers every browser node sees: user's original ask,
        # the actual key-values upstream left behind, and (if compose is a
        # middle-of-graph node) what downstream consumers expect. When
        # upstream values are empty/placeholder, this block tells the LLM
        # honestly so it doesn't generate boilerplate on top of nothing.
        body_user_goal = self._augment_body_goal_with_data_flow(
            body_user_goal=body_user_goal,
            raw_user_query=raw_user_query,
            upstream_artifacts=upstream_artifacts_for_subject,
            node_meta=node_meta_for_subject,
        )
        language = "zh" if re.search(r"[\u4e00-\u9fff]", raw_user_query or body_user_goal or "") else "en"
        title_hint = self._build_title_hint(
            output_spec=output_spec,
            canonical_subject=str(subject_resolution.canonical_subject or ""),
            language=language,
            user_query=raw_user_query,
        )
        if title_hint:
            strategy["title_hint"] = title_hint
            # Surface title_hint via the shared nested profile_preset.metadata
            # dict. The subagent runtime shallow-copies output_spec for each
            # node, so a top-level mutation (e.g. output_spec["title_hint"])
            # does NOT reach the export node that triggers docx render. But
            # nested dicts (profile_preset, its metadata) are still shared
            # references — mutating them propagates to all subagents and back
            # to the parent's output_spec. This is the channel by which the
            # docx renderer (running in N_S_EXPORT) gets the LLM-derived
            # title that the writer (running in N_S1) just computed.
            preset_for_title = output_spec.get("profile_preset") if isinstance(output_spec.get("profile_preset"), dict) else None
            if isinstance(preset_for_title, dict):
                meta = preset_for_title.get("metadata")
                if not isinstance(meta, dict):
                    meta = {}
                    preset_for_title["metadata"] = meta
                meta["title_hint"] = title_hint
            try:
                log_print(
                    "[writer_engine] title hint selected | title=%s explicit=%s"
                    % (
                        json.dumps(title_hint, ensure_ascii=False),
                        bool(str((output_spec or {}).get("explicit_title_block") or "").strip()),
                    ),
                    flush=True,
                )
            except Exception:
                pass
        try:
            log_print(
                "[writer_engine] subject resolution | status=%s canonical=%s candidates=%s rationale=%s"
                % (
                    str(subject_resolution.status or ""),
                    str(subject_resolution.canonical_subject or "")[:120],
                    len(list(subject_resolution.candidate_subjects or [])),
                    str(subject_resolution.rationale or "")[:160],
                ),
                flush=True,
            )
        except Exception:
            pass
        selected_style_markdowns = payload.get("selected_style_markdowns") or []
        style_resolution = resolve_writer_style_prompt(
            output_spec=output_spec,
            payload=payload,
            selected_style_markdowns=selected_style_markdowns,
        )
        style_mode = str(style_resolution.get("mode") or "legacy").strip()
        style_parts = [
            self._sanitize_body_style_markdown(str(x or "").strip())
            for x in list(style_resolution.get("parts") or [])
            if str(x or "").strip()
        ]
        style_parts = [item for item in style_parts if item]
        selected_style_md = "\n\n".join(style_parts)
        if style_mode != "contract":
            selected_style_md = selected_style_md[:12000]
        try:
            log_print(
                "[writer_engine] style prompt | mode=%s selected_style_parts=%s merged_style_len=%s preview=%s"
                % (
                    style_mode,
                    len(style_parts),
                    len(selected_style_md),
                    json.dumps(selected_style_md[:160], ensure_ascii=False),
                ),
                flush=True,
            )
        except Exception:
            pass
        evidence_bundle = payload.get("evidence_bundle") if isinstance(payload.get("evidence_bundle"), dict) else {}
        evidence_bundle = normalize_evidence_bundle(evidence_bundle)
        evidence_bundle = self._build_document_evidence_bundle(output_spec=output_spec, base_bundle=evidence_bundle)
        evidence_bundle = self._build_multimodal_evidence_bundle(output_spec=output_spec, base_bundle=evidence_bundle)
        evidence_bundle = self._build_graph_artifact_evidence_bundle(output_spec=output_spec, base_bundle=evidence_bundle)
        evidence_bundle = normalize_evidence_bundle(evidence_bundle)
        # Agreement mode: inject uploaded document as full template/draft so the
        # outline planner and section writer can use it as the baseline structure.
        _strategy_mode = str(strategy.get("mode") or "").strip().lower()
        if _strategy_mode == "agreement_clauses":
            evidence_bundle = self._inject_agreement_template(output_spec=output_spec, bundle=evidence_bundle)
        elif _strategy_mode == "translation":
            evidence_bundle = self._inject_translation_source(output_spec=output_spec, bundle=evidence_bundle)
        task_ir_context = output_spec.get("task_ir") if isinstance(output_spec.get("task_ir"), dict) else {}
        content_task_context = output_spec.get("content_task_spec") if isinstance(output_spec.get("content_task_spec"), dict) else {}
        evidence_bundle = await enrich_evidence_with_user_request_facts(
            llm=getattr(self._pipeline, "_llm", None),
            evidence_bundle=evidence_bundle,
            user_request=raw_user_query,
            task_context={
                "task_ir_constraints": task_ir_context.get("constraints") if isinstance(task_ir_context, dict) else {},
                "content_task_spec": {
                    key: content_task_context.get(key)
                    for key in ("constraints", "schema", "research_requirements")
                    if key in content_task_context
                },
            },
        )
        evidence_bundle = normalize_evidence_bundle(evidence_bundle)
        payload["evidence_bundle"] = dict(evidence_bundle or {})
        if isinstance(context.output_spec, dict):
            context.output_spec["evidence_bundle"] = dict(evidence_bundle or {})
        writer_evidence_packet = WriterEvidencePacketBuilder().build(
            evidence_bundle=evidence_bundle,
            tool_observations=tool_observations,
            output_spec=output_spec,
            user_query=raw_user_query,
        )
        packet_runtime = persist_writer_evidence_packet(
            packet=writer_evidence_packet,
            evidence_bundle=evidence_bundle,
            tool_observations=tool_observations,
            mode="active_packet_replaces_projection_and_raw",
        )
        output_spec["writer_evidence_packet_runtime"] = dict(packet_runtime or {})
        if isinstance(context.output_spec, dict):
            context.output_spec["writer_evidence_packet_runtime"] = dict(packet_runtime or {})
        try:
            log_print(
                "[writer_engine] evidence inputs | tool_observations=%s evidence_results=%s confirmed_facts=%s user_request_facts=%s"
                % (
                    len([x for x in list(tool_observations or []) if isinstance(x, dict)]),
                    len([x for x in list((evidence_bundle or {}).get("results") or []) if isinstance(x, dict)]),
                    len([x for x in list((evidence_bundle or {}).get("confirmed_facts") or []) if str(x or "").strip()]),
                    len([x for x in list((evidence_bundle or {}).get("user_request_facts") or []) if isinstance(x, dict)]),
                ),
                flush=True,
            )
            graph_count = int((evidence_bundle or {}).get("graph_artifact_evidence_count") or 0)
            if graph_count:
                log_print(
                    "[writer_engine] graph artifact evidence | count=%d"
                    % graph_count,
                    flush=True,
                )
        except Exception:
            pass

        strict_blocker = self._resolve_strict_grounding_blocker(
            output_spec=output_spec,
            user_query=raw_user_query,
            tool_observations=tool_observations,
            evidence_bundle=evidence_bundle,
        )
        if strict_blocker:
            try:
                log_print("[writer_engine] strict grounding blocked generation | evidence=0", flush=True)
            except Exception:
                pass
            yield {"type": "answer", "content": strict_blocker + "\n\n"}
            return

        # Extract channel and audience for context-aware subject resolution
        preset_summary = output_spec.get("preset_summary") if isinstance(output_spec.get("preset_summary"), dict) else {}
        compose_profile = output_spec.get("compose_profile") if isinstance(output_spec.get("compose_profile"), dict) else {}
        channel = str(preset_summary.get("publish_channel") or "")
        audience = str(compose_profile.get("audience_model") or "")

        # Read execution_kind and schema.category out of content_task_spec
        # so the gate can short-circuit for browser / code / file tasks.
        _cts = output_spec.get("content_task_spec") if isinstance(output_spec.get("content_task_spec"), dict) else {}
        _ek = str((_cts or {}).get("execution_kind") or "").strip().lower()
        _schema = (_cts or {}).get("schema") if isinstance((_cts or {}).get("schema"), dict) else {}
        _sc = str((_schema or {}).get("category") or "").strip().lower()
        if _strategy_mode == "translation" and not _ek:
            _ek = "file"
        subject_gate = self._resolve_subject_generation_gate(
            user_query=raw_user_query,
            subject_resolution=output_spec.get("subject_resolution") or {},
            tool_observations=tool_observations,
            evidence_bundle=evidence_bundle,
            channel=channel,
            audience=audience,
            execution_kind=_ek,
            schema_category=_sc,
        )
        output_spec["subject_resolution_gate"] = dict(subject_gate or {})
        if isinstance(context.output_spec, dict):
            context.output_spec["subject_resolution_gate"] = dict(subject_gate or {})
        gate_action = str(subject_gate.get("action") or "proceed").strip().lower()
        if gate_action == "clarify":
            try:
                log_print(
                    "[writer_engine] subject gate | action=clarify evidence_strength=%s"
                    % int(subject_gate.get("evidence_strength") or 0),
                    flush=True,
                )
            except Exception:
                pass
            message = str(subject_gate.get("message") or "").strip()
            if message:
                yield {"type": "answer", "content": message + "\n\n"}
                return
        if gate_action == "disambiguate":
            body_user_goal = str(subject_gate.get("body_user_goal") or body_user_goal).strip() or body_user_goal
            output_spec["subject_resolution_gate_mode"] = "disambiguation"
            if isinstance(context.output_spec, dict):
                context.output_spec["subject_resolution_gate_mode"] = "disambiguation"
            try:
                log_print(
                    "[writer_engine] subject gate | action=disambiguate evidence_strength=%s"
                    % int(subject_gate.get("evidence_strength") or 0),
                    flush=True,
                )
            except Exception:
                pass
        compose_user_id = str(output_spec.get("user_id") or "anonymous")

        mode = str(strategy.get("mode") or "")
        output_spec["deferred_visuals_disabled"] = bool(strategy.get("skip_visuals"))
        if isinstance(context.output_spec, dict):
            context.output_spec["deferred_visuals_disabled"] = bool(strategy.get("skip_visuals"))
        # Record which writer path actually ran. The downstream document-level
        # retry gate reads this — sectional paths (where per-section eval+regen
        # already runs inside the writer loop) should NOT re-trigger a full
        # document retry; doc-level retry only makes sense for single-shot
        # The direct path has no inline section repair mechanism.
        # no inline repair mechanism.
        output_spec["__writer_path"] = (
            "sectional" if mode == "sectional_compose"
            else ("translation" if mode == "translation" else "single_shot")
        )
        if isinstance(context.output_spec, dict):
            context.output_spec["__writer_path"] = str(output_spec["__writer_path"])
        if mode == "translation":
            stream = self._pipeline.generate_translation(
                user_query=raw_user_query or body_user_goal,
                language=language,
                evidence_bundle=evidence_bundle,
                user_id=compose_user_id,
            )
        elif mode == "direct_compose":
            stream = self._pipeline.generate_direct(
                user_query=body_user_goal,
                language=language,
                strategy=strategy,
                tool_observations=tool_observations,
                selected_style_md=selected_style_md,
                evidence_bundle=evidence_bundle,
                writer_evidence_packet=writer_evidence_packet.model_dump(),
                user_id=compose_user_id,
            )
        else:
            stream = self._pipeline.generate(
                user_query=body_user_goal,
                language=language,
                strategy=strategy,
                tool_observations=tool_observations,
                selected_style_md=selected_style_md,
                evidence_bundle=evidence_bundle,
                writer_evidence_packet=writer_evidence_packet.model_dump(),
                user_id=compose_user_id,
            )
        buffered_answer_parts: List[str] = []
        async for evt in stream:
            if isinstance(evt, dict) and str(evt.get("type") or "") == "answer":
                buffered_answer_parts.append(self._strip_outer_markdown_fence(str(evt.get("content") or "")))
                continue
            if isinstance(evt, dict) and str(evt.get("type") or "") == "activity":
                # V3 work visibility comes from the graph node operation. Do
                # not translate writer-engine timeline prose into V3 items.
                if bool(payload.get("preserve_activity_events")):
                    yield evt
                continue
            yield evt

        final_content = "\n\n".join([part.strip() for part in buffered_answer_parts if str(part or "").strip()]).strip()
        # Translation mode: bypass all post-processing (fact grounding, image planning, etc.)
        # The translated content must be preserved exactly as produced by the translator.
        if mode == "translation":
            if final_content:
                yield {"type": "answer", "content": final_content + "\n\n"}
            return
        multimodal = output_spec.get("multimodal") if isinstance(output_spec.get("multimodal"), dict) else {}
        uploaded_assets = self._collect_uploaded_assets_for_compose(output_spec)
        existing_layout_hints = [dict(x) for x in list(multimodal.get("image_layout_hints") or []) if isinstance(x, dict)]
        compose_policy = strategy.get("compose_policy") if isinstance(strategy.get("compose_policy"), dict) else {}
        visual_preferences = (
            compose_policy.get("visual_preferences")
            if isinstance(compose_policy.get("visual_preferences"), dict)
            else {}
        )
        uploaded_image_insert_mode = str(
            visual_preferences.get("uploaded_image_insert_mode") or "auto"
        ).strip().lower()
        if uploaded_image_insert_mode not in {"auto", "reference_only", "preserve"}:
            uploaded_image_insert_mode = "auto"
        if final_content and uploaded_assets and uploaded_image_insert_mode != "reference_only":
            log_print(
                "[tool_writer_engine_compose][image_assets] "
                f"uploaded_assets={len(uploaded_assets)} existing_hints={len(existing_layout_hints)} "
                f"insert_mode={uploaded_image_insert_mode}",
                flush=True,
            )
            planner_result = await get_image_planner_service().plan_document_images(
                markdown=final_content,
                user_goal=body_user_goal,
                uploaded_assets=uploaded_assets,
                language=language,
            )
            layout_hints = merge_image_layout_hints(
                existing_layout_hints,
                list(planner_result.get("layout_hints") or []),
            )
            if layout_hints:
                final_content = await inject_images_inline(markdown=final_content, image_layout_hints=layout_hints)
                final_content = normalize_image_markdown(final_content)
                log_print(
                    "[tool_writer_engine_compose][image_insert] "
                    f"layout_hints={len(layout_hints)} markdown_images={final_content.count('![')}",
                    flush=True,
                )
        elif final_content and uploaded_assets:
            log_print(
                "[tool_writer_engine_compose][image_assets_skip] "
                f"uploaded_assets={len(uploaded_assets)} insert_mode={uploaded_image_insert_mode}",
                flush=True,
            )
        if final_content:
            yield {"type": "answer", "content": final_content + "\n\n"}
