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



class ComposeEvidenceMixin:
    @staticmethod
    def _build_subject_context(output_spec: Dict[str, Any]) -> Dict[str, Any]:
        preset = output_spec.get("profile_preset") if isinstance(output_spec.get("profile_preset"), dict) else {}
        structure = preset.get("structure_contract") if isinstance(preset.get("structure_contract"), dict) else {}
        compose = preset.get("compose_policy") if isinstance(preset.get("compose_policy"), dict) else {}
        content_task_spec = output_spec.get("content_task_spec") if isinstance(output_spec.get("content_task_spec"), dict) else {}
        goal = content_task_spec.get("goal") if isinstance(content_task_spec.get("goal"), dict) else {}
        multimodal = output_spec.get("multimodal") if isinstance(output_spec.get("multimodal"), dict) else {}
        return {
            "content_form": str(compose.get("content_form") or "").strip(),
            "writing_mode": str(content_task_spec.get("writing_mode") or "").strip(),
            "required_sections": [str(x).strip() for x in list(structure.get("required_blocks") or output_spec.get("required_blocks") or []) if str(x).strip()][:8],
            "goal_outcome": str(goal.get("outcome") or "").strip(),
            "multimodal": multimodal,
        }

    @staticmethod
    def _build_multimodal_evidence_bundle(
        *,
        output_spec: Dict[str, Any],
        base_bundle: Dict[str, Any],
    ) -> Dict[str, Any]:
        bundle = dict(base_bundle or {}) if isinstance(base_bundle, dict) else {}
        multimodal = output_spec.get("multimodal") if isinstance(output_spec.get("multimodal"), dict) else {}
        if not multimodal:
            return bundle

        image_facts = multimodal.get("image_facts") if isinstance(multimodal.get("image_facts"), dict) else {}
        uploaded_assets = [dict(x) for x in list(multimodal.get("uploaded_assets") or []) if isinstance(x, dict)]
        subject_resolution = output_spec.get("subject_resolution") if isinstance(output_spec.get("subject_resolution"), dict) else {}
        results = [dict(x) for x in list(bundle.get("results") or []) if isinstance(x, dict)]
        topic = str(bundle.get("topic") or "").strip()
        entities = [str(x).strip() for x in list(bundle.get("entities") or []) if str(x).strip()]
        flow_steps = [str(x).strip() for x in list(bundle.get("flow_steps") or []) if str(x).strip()]
        requirements = [str(x).strip() for x in list(bundle.get("requirements") or []) if str(x).strip()]
        confirmed_facts = [str(x).strip() for x in list(bundle.get("confirmed_facts") or []) if str(x).strip()]
        open_questions = [str(x).strip() for x in list(bundle.get("open_questions") or []) if str(x).strip()]
        subject_candidates = [
            str(x).strip()
            for x in list(image_facts.get("subject_candidates") or image_facts.get("entities") or [])
            if str(x).strip()
        ]
        for item in list(image_facts.get("cross_image_facts") or [])[:12]:
            value = str(item or "").strip()
            if value and value not in confirmed_facts:
                confirmed_facts.append(value)
        for item in list(image_facts.get("uncertain") or [])[:12]:
            value = str(item or "").strip()
            if value and value not in open_questions:
                open_questions.append(value)

        for token in subject_candidates[:12]:
            value = str(token or "").strip()
            if value and value not in entities:
                entities.append(value)

        for item in list(image_facts.get("images") or [])[:8]:
            if not isinstance(item, dict):
                continue
            page_area = str(item.get("page_area") or "").strip()
            flow = str(item.get("flow_relationship") or "").strip()
            fields = [str(x).strip() for x in list(item.get("visible_fields") or [])[:5] if str(x).strip()]
            controls = [str(x).strip() for x in list(item.get("controls") or [])[:4] if str(x).strip()]
            if page_area and page_area not in requirements:
                requirements.append(page_area)
            if flow and flow not in flow_steps:
                flow_steps.append(flow)
            summary_parts = [part for part in [page_area, flow, " / ".join(fields), " / ".join(controls)] if part]
            if summary_parts:
                results.append(
                    {
                        "title": page_area or f"image_fact_{len(results)+1}",
                        "summary": "；".join(summary_parts),
                        "source": "multimodal_image_fact",
                        "structured_payload": {
                            key: value
                            for key, value in item.items()
                            if key
                            in {
                                "page_area",
                                "visible_fields",
                                "status_tags",
                                "flow_relationship",
                                "controls",
                            }
                        },
                    }
                )
            for fact in summary_parts[:3]:
                if fact and fact not in confirmed_facts:
                    confirmed_facts.append(fact)

        for asset in uploaded_assets[:8]:
            summary = str(asset.get("summary") or "").strip()
            if not summary:
                continue
            results.append(
                {
                    "title": str(asset.get("page_area") or asset.get("filename") or asset.get("asset_id") or "uploaded_image").strip(),
                    "summary": summary,
                    "source": "uploaded_image_asset",
                    "url": str(asset.get("signed_url") or asset.get("path") or "").strip(),
                }
            )

        if not topic:
            topic = str(subject_resolution.get("canonical_subject") or "").strip()
        if not topic and subject_candidates:
            topic = subject_candidates[0]
        if not topic:
            topic = str(multimodal.get("vision_summary") or "").strip()[:120]
        bundle["topic"] = topic
        bundle["entities"] = entities[:16]
        bundle["flow_steps"] = flow_steps[:16]
        bundle["requirements"] = requirements[:20]
        bundle["confirmed_facts"] = confirmed_facts[:20]
        bundle["open_questions"] = open_questions[:12]
        bundle["results"] = results[:24]
        return bundle

    @staticmethod
    def _build_document_tool_observations(
        *,
        output_spec: Dict[str, Any],
        base_observations: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        observations = [dict(x) for x in list(base_observations or []) if isinstance(x, dict)]
        documents = output_spec.get("documents") if isinstance(output_spec.get("documents"), dict) else {}
        parsed_documents = [dict(x) for x in list(documents.get("parsed_documents") or []) if isinstance(x, dict)]
        if not parsed_documents:
            return observations

        for item in parsed_documents[:10]:
            if str(item.get("parse_status") or "").strip() != "parsed":
                continue
            profile = dict(item.get("profile") or {})
            title = str(profile.get("title") or item.get("filename") or item.get("asset_id") or "uploaded_document").strip()
            source_url = str(item.get("source_url") or "").strip()
            summary = str(
                profile.get("active_context_brief")
                or profile.get("summary")
                or item.get("inline_markdown")
                or item.get("markdown")
                or ""
            ).strip()
            key_points = [str(x).strip() for x in list(profile.get("key_points") or []) if str(x).strip()]
            if key_points:
                summary = "\n".join([summary] + key_points[:4]) if summary else "；".join(key_points[:4])
            if not summary:
                continue
            observation = {
                "tool": "uploaded_document",
                "query": title,
                "summary": summary[:2000],
                "sources": [{"title": title, "url": source_url}] if source_url else [],
                "artifacts": [{"type": "document", "url": source_url, "caption": title}] if source_url else [],
            }
            observations.append(observation)
        return observations[:24]

    @staticmethod
    def _document_markdown_evidence_items(markdown: str, *, source_url: str, title: str, limit: int = 8) -> List[Dict[str, Any]]:
        text = str(markdown or "").strip()
        if not text:
            return []
        chunks: List[Dict[str, Any]] = []
        heading = title
        current: List[str] = []
        for raw_line in text.splitlines():
            line = str(raw_line or "").rstrip()
            if line.startswith("## "):
                if current:
                    body = "\n".join(current).strip()
                    if body:
                        chunks.append({"title": heading, "summary": body[:2000], "url": source_url, "source": "uploaded_document_markdown"})
                heading = line[3:].strip() or title
                current = []
                continue
            if line:
                current.append(line)
        if current:
            body = "\n".join(current).strip()
            if body:
                chunks.append({"title": heading, "summary": body[:2000], "url": source_url, "source": "uploaded_document_markdown"})
        return chunks[:limit]

    @classmethod
    def _build_document_evidence_bundle(
        cls,
        *,
        output_spec: Dict[str, Any],
        base_bundle: Dict[str, Any],
    ) -> Dict[str, Any]:
        bundle = dict(base_bundle or {}) if isinstance(base_bundle, dict) else {}
        documents = output_spec.get("documents") if isinstance(output_spec.get("documents"), dict) else {}
        parsed_documents = [dict(x) for x in list(documents.get("parsed_documents") or []) if isinstance(x, dict)]
        if not parsed_documents:
            return bundle

        results = [dict(x) for x in list(bundle.get("results") or []) if isinstance(x, dict)]
        topic = str(bundle.get("topic") or "").strip()
        entities = [str(x).strip() for x in list(bundle.get("entities") or []) if str(x).strip()]
        flow_steps = [str(x).strip() for x in list(bundle.get("flow_steps") or []) if str(x).strip()]
        requirements = [str(x).strip() for x in list(bundle.get("requirements") or []) if str(x).strip()]
        confirmed_facts = [str(x).strip() for x in list(bundle.get("confirmed_facts") or []) if str(x).strip()]
        open_questions = [str(x).strip() for x in list(bundle.get("open_questions") or []) if str(x).strip()]
        document_result_groups: List[List[Dict[str, Any]]] = []
        document_fact_groups: List[List[str]] = []

        for item in parsed_documents[:10]:
            if str(item.get("parse_status") or "").strip() != "parsed":
                continue
            profile = dict(item.get("profile") or {})
            title = str(profile.get("title") or item.get("filename") or item.get("asset_id") or "uploaded_document").strip()
            source_url = str(item.get("source_url") or "").strip()
            summary = str(profile.get("summary") or profile.get("active_context_brief") or "").strip()
            document_results: List[Dict[str, Any]] = []
            document_facts: List[str] = []
            if summary:
                document_results.append(
                    {
                        "title": title,
                        "summary": summary[:2000],
                        "url": source_url,
                        "source": "uploaded_document_profile",
                    }
                )
                document_facts.append(summary)

            for token in list(profile.get("subject_candidates") or [])[:6]:
                value = str(token or "").strip()
                if value and value not in entities:
                    entities.append(value)
            for token in list(profile.get("section_outline") or [])[:8]:
                value = str(token or "").strip()
                if value and value not in requirements:
                    requirements.append(value)
            for token in list(profile.get("key_points") or [])[:10]:
                value = str(token or "").strip()
                if value and value not in document_facts:
                    document_facts.append(value)

            for brief in list(item.get("chunk_briefs") or [])[:8]:
                if not isinstance(brief, dict):
                    continue
                brief_summary = str(brief.get("summary") or "").strip()
                brief_title = ""
                signals = [str(x).strip() for x in list(brief.get("section_signals") or []) if str(x).strip()]
                if signals:
                    brief_title = " / ".join(signals[:2])
                if brief_summary:
                    document_results.append(
                        {
                            "title": brief_title or title,
                            "summary": brief_summary[:2000],
                            "url": source_url,
                            "source": "uploaded_document_chunk",
                        }
                    )
                for token in signals[:4]:
                    if token and token not in flow_steps:
                        flow_steps.append(token)
                for token in list(brief.get("key_points") or [])[:6]:
                    value = str(token or "").strip()
                    if value and value not in document_facts:
                        document_facts.append(value)

            markdown = str(item.get("markdown") or "").strip()
            for result in cls._document_markdown_evidence_items(markdown, source_url=source_url, title=title, limit=10):
                document_results.append(result)
            if document_results:
                document_result_groups.append(document_results)
            if document_facts:
                document_fact_groups.append(document_facts)

        results.extend(round_robin_take(document_result_groups, limit=max(0, 64 - len(results))))
        selected_document_facts = round_robin_take(document_fact_groups, limit=max(0, 48 - len(confirmed_facts)))
        for fact in selected_document_facts:
            if fact not in confirmed_facts:
                confirmed_facts.append(fact)

        if not topic:
            topic = str(documents.get("active_document_context") or output_spec.get("active_document_context") or "").strip()[:160]
        bundle["topic"] = topic
        bundle["entities"] = entities[:20]
        bundle["flow_steps"] = flow_steps[:20]
        bundle["requirements"] = requirements[:20]
        bundle["confirmed_facts"] = confirmed_facts[:48]
        bundle["open_questions"] = open_questions[:12]
        bundle["results"] = results[:64]
        return bundle

    @staticmethod
    def _compact_structured_evidence(value: Any, *, limit: int = 2400) -> str:
        if value is None:
            return ""
        try:
            text = json.dumps(value, ensure_ascii=False, default=str, indent=2)
        except Exception:
            text = str(value)
        text = text.strip()
        if len(text) <= limit:
            return text
        return text[:limit].rstrip() + "\n...<truncated>"

    @classmethod
    def _build_graph_artifact_evidence_bundle(
        cls,
        *,
        output_spec: Dict[str, Any],
        base_bundle: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Promote graph node artifacts into the normal evidence bundle.

        Graph execution already passes upstream node outputs through
        ``predecessor_artifacts`` / ``input_artifacts``. The writer evidence
        contract, however, is ``evidence_bundle``. This bridge keeps graph
        outputs inside the existing grounding path instead of inventing a
        separate writer/reviewer flow.
        """
        bundle = dict(base_bundle or {}) if isinstance(base_bundle, dict) else {}
        artifact_buckets: List[Tuple[str, Dict[str, Any]]] = []
        for bucket_name in ("predecessor_artifacts", "input_artifacts", "graph_artifacts"):
            bucket = output_spec.get(bucket_name) if isinstance(output_spec.get(bucket_name), dict) else {}
            if bucket:
                artifact_buckets.append((bucket_name, bucket))
        if not artifact_buckets:
            return bundle

        results = [dict(x) for x in list(bundle.get("results") or []) if isinstance(x, dict)]
        confirmed_facts = [str(x).strip() for x in list(bundle.get("confirmed_facts") or []) if str(x).strip()]
        entities = [str(x).strip() for x in list(bundle.get("entities") or []) if str(x).strip()]
        requirements = [str(x).strip() for x in list(bundle.get("requirements") or []) if str(x).strip()]

        seen_results = {
            (str(item.get("source") or ""), str(item.get("title") or ""))
            for item in results
            if isinstance(item, dict)
        }
        seen_node_keys: set[str] = set()
        added = 0
        for bucket_name, bucket in artifact_buckets:
            for node_id, artifact in bucket.items():
                if not isinstance(artifact, dict):
                    continue
                node_key = str(node_id or "").strip() or "graph_node"
                if node_key in seen_node_keys:
                    continue
                result = project_graph_artifact_result(
                    node_id=node_key,
                    artifact_bucket=bucket_name,
                    artifact=artifact,
                )
                if not result:
                    continue
                title = str(result.get("title") or "")
                source = str(result.get("source") or "")
                dedupe_key = (source, title)
                if dedupe_key in seen_results:
                    continue
                seen_results.add(dedupe_key)
                seen_node_keys.add(node_key)
                summary = str(result.get("summary") or "").strip()
                if not summary:
                    continue
                results.append(result)
                if summary not in confirmed_facts:
                    confirmed_facts.append(summary)
                for name_key in ("name", "title"):
                    value = artifact.get(name_key)
                    if isinstance(value, str) and value.strip() and value.strip() not in entities:
                        entities.append(value.strip())
                added += 1
                if added >= 24:
                    break
            if added >= 24:
                break

        if added <= 0:
            return bundle

        if "Use graph node artifacts as grounded evidence for generated answers." not in requirements:
            requirements.append("Use graph node artifacts as grounded evidence for generated answers.")
        bundle["results"] = results[:48]
        bundle["confirmed_facts"] = confirmed_facts[:48]
        bundle["entities"] = entities[:24]
        bundle["requirements"] = requirements[:24]
        bundle["graph_artifact_evidence_count"] = added
        return bundle

    @staticmethod
    def _inject_agreement_template(*, output_spec: Dict[str, Any], bundle: Dict[str, Any]) -> Dict[str, Any]:
        """For agreement mode, inject the full uploaded document markdown as a
        template/draft so that the outline planner extracts clause structure from
        it and the section writer uses it as baseline content to modify."""
        bundle = dict(bundle or {})
        documents = output_spec.get("documents") if isinstance(output_spec.get("documents"), dict) else {}
        parsed_documents = [dict(x) for x in list(documents.get("parsed_documents") or []) if isinstance(x, dict)]
        if not parsed_documents:
            return bundle
        # Use the first successfully parsed document as the agreement template.
        for item in parsed_documents[:3]:
            if str(item.get("parse_status") or "").strip() != "parsed":
                continue
            markdown = str(item.get("markdown") or "").strip()
            if not markdown:
                continue
            title = str(
                (item.get("profile") or {}).get("title")
                or item.get("filename")
                or "uploaded_agreement"
            ).strip()
            # Insert as a high-priority "template" result at the front of the bundle.
            language = str(output_spec.get("language") or "zh").lower()
            template_label = "Agreement Draft" if language.startswith("en") else "协议底稿"
            template_result = {
                "title": f"[{template_label}] {title}",
                "summary": markdown[:8000],
                "url": str(item.get("source_url") or "").strip(),
                "source": "agreement_template",
            }
            results = list(bundle.get("results") or [])
            results.insert(0, template_result)
            bundle["results"] = results[:40]
            bundle["agreement_template_markdown"] = markdown[:12000]
            break
        return bundle

    TRANSLATABLE_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".txt", ".md"}

    @staticmethod
    def _inject_translation_source(*, output_spec: Dict[str, Any], bundle: Dict[str, Any]) -> Dict[str, Any]:
        """For translation mode, inject the uploaded document's full markdown
        as the translation source material."""
        import os
        bundle = dict(bundle or {})
        documents = output_spec.get("documents") if isinstance(output_spec.get("documents"), dict) else {}
        parsed_documents = [dict(x) for x in list(documents.get("parsed_documents") or []) if isinstance(x, dict)]
        if not parsed_documents:
            return bundle
        for item in parsed_documents[:3]:
            markdown = str(item.get("markdown") or "").strip()
            filename = str(item.get("filename") or "").strip()
            ext = os.path.splitext(filename.lower())[1] if filename else ""
            parse_status = str(item.get("parse_status") or "").strip()
            source_object_path = str(item.get("object_path") or "").strip()
            source_url = str(item.get("source_url") or item.get("signed_url") or item.get("url") or "").strip()
            binary_translatable = ext in {".docx", ".xlsx"}
            # Text translation for PDF/TXT/MD requires extracted Markdown; DOCX/XLSX can
            # fall back to the original binary download URL for in-place translation.
            if binary_translatable:
                if not source_object_path and not source_url:
                    continue
            else:
                if parse_status != "parsed" or not markdown:
                    continue
            if not filename:
                continue
            bundle["translation_source_markdown"] = markdown
            bundle["translation_source_filename"] = filename
            bundle["translation_source_ext"] = ext
            # Keep the OSS object_path and signed URL to fetch original .docx bytes.
            bundle["translation_source_object_path"] = source_object_path
            bundle["translation_source_url"] = source_url
            bundle["translation_source_content_type"] = str(item.get("content_type") or "").strip()
            break
        return bundle
