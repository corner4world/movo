from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional
from app.llm.types import Message, Role
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_fixed
from app.enterprise_capabilities.content.body_projection import body_only_contract_context
from app.enterprise_capabilities.evidence.foundation.writer_packet import (
    WriterEvidencePacket,
    render_section_writer_evidence_packet,
)
from app.enterprise_capabilities.content.structure_roles import resolve_language
from app.enterprise_capabilities.content.writer_engine.unified_compose.writer_prompt_budget import (
    fit_writer_prompt,
)
from app.utils.report_file_manager import report_file_manager
from .models import (
    ComposeDeps,
    DocumentState,
    SectionContractAssessment,
    SectionContractRewriteOutput,
    SectionPromptNormalizationOutput,
    SectionSummary,
    SectionSummaryBundle,
)
from .prompt_formatting import (
    _compact_scalar,
    _format_writer_constraints_markdown,
    _markdown_bullets,
    _markdown_section,
    _project_writer_constraints,
    _render_claim_contract_markdown,
    _render_fact_contract_markdown,
    _split_identity_block,
)
from .shared import _truncate_text
from .visual import VisualAugmenter


class SectionWriter:
    def __init__(self, deps: ComposeDeps, prompt_registry: Any):
        self.deps = deps
        self.prompts = prompt_registry

    @staticmethod
    def _has_contract_requirements(
        *,
        must_cover_facts: List[Dict[str, Any]],
        allowed_claim_types: List[str],
        disallowed_claim_types: List[str],
        open_questions: List[str],
    ) -> bool:
        return bool(must_cover_facts or allowed_claim_types or disallowed_claim_types or open_questions)

    async def _assess_section_contract(
        self,
        *,
        section_markdown: str,
        title: str,
        objective: str,
        language: str,
        must_cover_facts: List[Dict[str, Any]],
        allowed_claim_types: List[str],
        disallowed_claim_types: List[str],
        open_questions: List[str],
    ) -> SectionContractAssessment | None:
        if not self._has_contract_requirements(
            must_cover_facts=must_cover_facts,
            allowed_claim_types=allowed_claim_types,
            disallowed_claim_types=disallowed_claim_types,
            open_questions=open_questions,
        ):
            return None
        system = (
            "You audit a generated markdown section against a section claim contract.\n"
            "Check only these rules:\n"
            "1) Must Cover Facts must appear as supported content in the section when they are relevant.\n"
            "2) Disallowed claim types must not appear as asserted facts.\n"
            "3) Open Questions must not be presented as confirmed facts in the main narrative.\n"
            "4) Unsupported assertions are claims that go beyond Must Cover Facts, evidence focus, or clearly supported context.\n"
            "Return strict structured output.\n"
        )
        payload = {
            "language": language,
            "section_title": title,
            "objective": objective,
            "section_markdown": str(section_markdown or "")[:6000],
            "must_cover_facts": list(must_cover_facts or [])[:12],
            "allowed_claim_types": list(allowed_claim_types or [])[:8],
            "disallowed_claim_types": list(disallowed_claim_types or [])[:8],
            "open_questions": list(open_questions or [])[:8],
        }
        try:
            model = self.deps.llm.with_structured_output(SectionContractAssessment, method="function_calling")
            result = await model.ainvoke(
                [
                    Message(role=Role.SYSTEM, content=system),
                    Message(role=Role.USER, content=json.dumps(payload, ensure_ascii=False, default=str)),
                ]
            )
            return result if isinstance(result, SectionContractAssessment) else SectionContractAssessment.model_validate(result)
        except Exception as exc:
            self.deps.log(
                "section_contract_assess_failed",
                {"title": str(title or "")[:120], "error": str(exc)[:260], "error_type": type(exc).__name__},
            )
            return None

    async def _rewrite_section_to_contract(
        self,
        *,
        section_markdown: str,
        title: str,
        objective: str,
        language: str,
        must_cover_facts: List[Dict[str, Any]],
        allowed_claim_types: List[str],
        disallowed_claim_types: List[str],
        open_questions: List[str],
        assessment: SectionContractAssessment,
    ) -> str:
        system = (
            "You rewrite a markdown section to satisfy a section claim contract.\n"
            "Preserve the section heading and reader-facing structure.\n"
            "Do not output explanations or JSON.\n"
            "Requirements:\n"
            "- cover missing required facts when they can be stated from the provided contract\n"
            "- remove or soften disallowed and unsupported assertions\n"
            "- move unresolved items into a short trailing uncertainty note instead of main factual narrative\n"
            "- keep the prose publishable\n"
        )
        payload = {
            "language": language,
            "section_title": title,
            "objective": objective,
            "original_markdown": str(section_markdown or "")[:7000],
            "must_cover_facts": list(must_cover_facts or [])[:12],
            "allowed_claim_types": list(allowed_claim_types or [])[:8],
            "disallowed_claim_types": list(disallowed_claim_types or [])[:8],
            "open_questions": list(open_questions or [])[:8],
            "violations": {
                "missing_facts": list(assessment.missing_facts or [])[:8],
                "disallowed_claims": list(assessment.disallowed_claims or [])[:8],
                "unsupported_assertions": list(assessment.unsupported_assertions or [])[:8],
                "leaked_open_questions": list(assessment.leaked_open_questions or [])[:8],
                "notes": list(assessment.notes or [])[:8],
            },
        }
        try:
            model = self.deps.llm.with_structured_output(SectionContractRewriteOutput, method="function_calling")
            result = await model.ainvoke(
                [
                    Message(role=Role.SYSTEM, content=system),
                    Message(role=Role.USER, content=json.dumps(payload, ensure_ascii=False, default=str)),
                ]
            )
            parsed = result if isinstance(result, SectionContractRewriteOutput) else SectionContractRewriteOutput.model_validate(result)
            return str(parsed.markdown_content or "").strip()
        except Exception as exc:
            self.deps.log(
                "section_contract_rewrite_failed",
                {"title": str(title or "")[:120], "error": str(exc)[:260], "error_type": type(exc).__name__},
            )
            return str(section_markdown or "")

    async def _enforce_section_contract(
        self,
        *,
        section_markdown: str,
        title: str,
        objective: str,
        language: str,
        must_cover_facts: List[Dict[str, Any]],
        allowed_claim_types: List[str],
        disallowed_claim_types: List[str],
        open_questions: List[str],
    ) -> str:
        assessment = await self._assess_section_contract(
            section_markdown=section_markdown,
            title=title,
            objective=objective,
            language=language,
            must_cover_facts=must_cover_facts,
            allowed_claim_types=allowed_claim_types,
            disallowed_claim_types=disallowed_claim_types,
            open_questions=open_questions,
        )
        if assessment is None or assessment.ok or not assessment.rewrite_needed:
            return section_markdown
        self.deps.log(
            "section_contract_rewrite_scheduled",
            {
                "title": str(title or "")[:120],
                "missing_facts": len(list(assessment.missing_facts or [])),
                "disallowed_claims": len(list(assessment.disallowed_claims or [])),
                "unsupported_assertions": len(list(assessment.unsupported_assertions or [])),
                "leaked_open_questions": len(list(assessment.leaked_open_questions or [])),
            },
        )
        rewritten = await self._rewrite_section_to_contract(
            section_markdown=section_markdown,
            title=title,
            objective=objective,
            language=language,
            must_cover_facts=must_cover_facts,
            allowed_claim_types=allowed_claim_types,
            disallowed_claim_types=disallowed_claim_types,
            open_questions=open_questions,
            assessment=assessment,
        )
        rewritten = str(rewritten or "").strip() or str(section_markdown or "").strip()
        final_assessment = await self._assess_section_contract(
            section_markdown=rewritten,
            title=title,
            objective=objective,
            language=language,
            must_cover_facts=must_cover_facts,
            allowed_claim_types=allowed_claim_types,
            disallowed_claim_types=disallowed_claim_types,
            open_questions=open_questions,
        )
        if final_assessment is not None and not final_assessment.ok:
            self.deps.log(
                "section_contract_rewrite_incomplete",
                {
                    "title": str(title or "")[:120],
                    "missing_facts": len(list(final_assessment.missing_facts or [])),
                    "disallowed_claims": len(list(final_assessment.disallowed_claims or [])),
                    "unsupported_assertions": len(list(final_assessment.unsupported_assertions or [])),
                    "leaked_open_questions": len(list(final_assessment.leaked_open_questions or [])),
                },
            )
        else:
            self.deps.log("section_contract_rewrite_applied", {"title": str(title or "")[:120]})
        return rewritten

    async def _normalize_section_prompt(
        self,
        *,
        language: str,
        raw_system: str,
        raw_payload: Dict[str, Any],
        raw_user_prompt: str,
    ) -> SectionPromptNormalizationOutput | None:
        prompt = self.prompts.get("section_prompt_normalizer")
        payload = {
            "language": language,
            "raw_system_prompt": raw_system,
            "raw_payload": raw_payload,
            "raw_user_prompt": raw_user_prompt,
        }
        try:
            model = self.deps.llm.with_structured_output(SectionPromptNormalizationOutput, method="function_calling")
            result = await model.ainvoke(
                [
                    Message(role=Role.SYSTEM, content=prompt),
                    Message(role=Role.USER, content=json.dumps(payload, ensure_ascii=False)),
                ]
            )
            normalized = result if isinstance(result, SectionPromptNormalizationOutput) else SectionPromptNormalizationOutput.model_validate(result)
            if not str(normalized.system_prompt or "").strip() or not str(normalized.user_prompt or "").strip():
                return None
            return normalized
        except Exception as exc:
            self.deps.log("section_prompt_normalize_failed", {"error": str(exc)[:260], "error_type": type(exc).__name__})
            return None

    async def _persist_section_prompt_debug_bundle(
        self,
        *,
        debug_task_id: str,
        section_number: str,
        section_title: str,
        target_words: int,
        raw_system: str,
        system: str,
        raw_payload: Dict[str, Any],
        raw_user_prompt: str,
        normalized_prompt: Any,
    ) -> None:
        try:
            file_id, file_path = report_file_manager.create_report_file(
                intent="section_prompt_debug",
                task_id=str(debug_task_id or "anonymous"),
            )
            normalized_meta = {
                "used": bool(normalized_prompt),
                "clean_section_goal_chars": len(str(getattr(normalized_prompt, "clean_section_goal", "") or "")),
                "evidence_slice_summary_chars": len(str(getattr(normalized_prompt, "evidence_slice_summary", "") or "")),
            }
            compressed_payload = {
                "clean_section_goal": str(getattr(normalized_prompt, "clean_section_goal", "") or "").strip(),
                "evidence_slice_summary": str(getattr(normalized_prompt, "evidence_slice_summary", "") or "").strip(),
                "final_user_prompt_chars": len(str(raw_user_prompt or "")),
                "final_system_prompt_chars": len(str(system or "")),
            }
            parts: List[str] = [
                "# Section Prompt Debug",
                "",
                "## Section Meta",
                "",
                "```json",
                json.dumps(
                    {
                        "section_number": str(section_number or ""),
                        "section_title": str(section_title or ""),
                        "target_words": int(target_words or 0),
                        "normalized_prompt": normalized_meta,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                "```",
                "",
                "## Raw System Prompt",
                "",
                "```text",
                str(raw_system or ""),
                "```",
                "",
                "## Final System Prompt",
                "",
                "```text",
                str(system or ""),
                "```",
                "",
                "## Raw Section Payload",
                "",
                "```json",
                json.dumps(raw_payload or {}, ensure_ascii=False, indent=2, default=str),
                "```",
                "",
                "## Compressed Section Payload",
                "",
                "```json",
                json.dumps(compressed_payload, ensure_ascii=False, indent=2),
                "```",
                "",
                "## Final User Prompt",
                "",
                "```text",
                str(raw_user_prompt or ""),
                "```",
            ]
            await report_file_manager.overwrite_content(file_path, "\n".join(parts) + "\n")
            self.deps.log(
                "section_prompt_saved",
                {
                    "section_number": str(section_number or ""),
                    "section_title": str(section_title or ""),
                    "file_id": file_id,
                    "path": str(file_path),
                },
            )
        except Exception as exc:
            self.deps.log(
                "section_prompt_save_failed",
                {
                    "section_number": str(section_number or ""),
                    "section_title": str(section_title or ""),
                    "error": str(exc)[:260],
                },
            )

    @staticmethod
    def heading_by_level(level: int) -> str:
        lv = max(1, min(4, int(level or 1)))
        return "#" * (lv + 1)

    @staticmethod
    def strip_leading_number(text: str) -> str:
        raw = str(text or "").strip()
        if not raw:
            return raw
        return re.sub(r"^\s*\d+(?:\.\d+)*[\.\s、:-]+", "", raw).strip() or raw

    @staticmethod
    def _body_only_contract_context(contract_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        return body_only_contract_context(contract_context)

    def clean_section_title(self, title: str, number: str) -> str:
        raw = self.strip_leading_number(title)
        no = str(number or "").strip()
        if no and raw.startswith(no):
            raw = raw[len(no):].strip(" .、:-")
        raw = re.sub(r"^[一二三四五六七八九十]+、", "", raw).strip()
        raw = re.sub(r"^[（(][一二三四五六七八九十]+[）)]", "", raw).strip()
        return raw or str(title or "").strip() or "Section"

    @staticmethod
    def _title_has_explicit_numbering(title: str) -> bool:
        raw = str(title or "").strip()
        if not raw:
            return False
        patterns = (
            r"^\d+(?:\.\d+)*[\.\s、:-]+",
            r"^[一二三四五六七八九十]+、",
            r"^[（(][一二三四五六七八九十]+[）)]",
        )
        return any(re.match(pattern, raw) for pattern in patterns)

    def format_display_title(self, title: str, number: str, language: str, numbering_style: str = "hierarchical") -> str:
        raw = str(title or "").strip()
        if self._title_has_explicit_numbering(raw):
            return raw
        clean = self.clean_section_title(raw, number)
        # numbering_style="none" → render section heading without leading
        # numbers. Short-form dynamic deliverables (resume, cover letter)
        # use this so headings omit the numeric prefix.
        if str(numbering_style or "").strip().lower() == "none":
            return clean
        if resolve_language(text=clean, language=language) == "zh":
            return f"{number} {clean}".strip()
        return f"{number} {clean}".strip()

    async def write_section(
        self,
        *,
        title: str,
        objective: str,
        key_points: List[str],
        evidence_focus: List[str],
        must_cover_facts: List[Dict[str, Any]] | None = None,
        allowed_claim_types: List[str] | None = None,
        disallowed_claim_types: List[str] | None = None,
        open_questions: List[str] | None = None,
        running_summary: str,
        language: str,
        target_words: int,
        style_md: str,
        level: int,
        number: str,
        visual_hint: str,
        source_refs: List[Dict[str, Any]],
        writer_evidence_packet: Dict[str, Any],
        document_state: Optional[DocumentState] = None,
        previous_section_summary: Optional[SectionSummary] = None,
        next_section_title: str = "",
        section_role: str = "analysis",
        contract_context: Optional[Dict[str, Any]] = None,
        debug_task_id: str = "anonymous",
        prompt_variant: str = "",
        numbering_style: str = "hierarchical",
    ) -> str:
        body_contract_context = self._body_only_contract_context(contract_context)
        clean_title = self.clean_section_title(title, number)
        heading = self.heading_by_level(level)
        display_title = self.format_display_title(title, number, language, numbering_style)
        doc_state = document_state or DocumentState()
        prev_summary = previous_section_summary or SectionSummary()
        normalized_facts: List[Dict[str, Any]] = []
        seen_fact_summaries = set()
        for idx, item in enumerate(list(must_cover_facts or [])[:12], start=1):
            if isinstance(item, dict):
                payload = {
                    "fact_id": str(item.get("fact_id") or f"fact_{idx}").strip(),
                    "fact_type": str(item.get("fact_type") or "fact").strip(),
                    "summary": str(item.get("summary") or "").strip(),
                    "source_kind": str(item.get("source_kind") or "").strip(),
                    "source_ref": str(item.get("source_ref") or "").strip(),
                    "raw_evidence": str(item.get("raw_evidence") or item.get("summary") or "").strip(),
                }
            else:
                summary = str(item or "").strip()
                if not summary:
                    continue
                payload = {
                    "fact_id": f"fact_{idx}",
                    "fact_type": "fact",
                    "summary": summary,
                    "source_kind": "legacy_text",
                    "source_ref": "",
                    "raw_evidence": summary,
                }
            summary = str(payload.get("summary") or "").strip()
            if not summary or summary in seen_fact_summaries:
                continue
            seen_fact_summaries.add(summary)
            normalized_facts.append(payload)
        allowed_claim_types = [str(x).strip() for x in list(allowed_claim_types or []) if str(x).strip()][:8]
        disallowed_claim_types = [str(x).strip() for x in list(disallowed_claim_types or []) if str(x).strip()][:8]
        open_questions = [str(x).strip() for x in list(open_questions or []) if str(x).strip()][:8]
        packet = WriterEvidencePacket.model_validate(writer_evidence_packet or {})
        packet_markdown = render_section_writer_evidence_packet(packet)
        prompt = {
            "title": clean_title,
            "objective": objective,
            "key_points": key_points,
            "evidence_focus": evidence_focus,
            "must_cover_facts": normalized_facts,
            "allowed_claim_types": allowed_claim_types,
            "disallowed_claim_types": disallowed_claim_types,
            "open_questions": open_questions,
            "argument_items": list((body_contract_context or {}).get("argument_items") or [])[:8],
            "running_summary": running_summary[-3000:],
            "writer_evidence_packet_present": True,
            "reference_sources": source_refs[:12],
            "target_words": target_words,
            "language": language,
            "heading_level": level,
            "section_number": number,
            "section_role": str(section_role or "analysis"),
            "previous_section_summary": prev_summary.model_dump(),
            "next_section_title": str(next_section_title or "").strip(),
            "document_state": doc_state.model_dump(),
            "contract_context": body_contract_context,
        }
        from app.enterprise_capabilities.content.writer_engine.unified_compose.assembler import ContractPromptAssembler
        section_prompt_name = f"section_writer_{prompt_variant}" if prompt_variant else "section_writer"
        system = self.prompts.get(
            section_prompt_name,
            language_name=self.deps.language_name(language),
            heading=heading,
            display_title=display_title,
            target_words=str(target_words),
        )

        # System prompt keeps only role and hard rules; task/detail moves to user markdown.
        blocks = ContractPromptAssembler.assemble_blocks(body_contract_context)
        identity_split = _split_identity_block(str(blocks.get("identity_block") or ""))
        final_system = ""
        if identity_split.get("system_identity"):
            final_system += str(identity_split.get("system_identity") or "") + "\n\n"
        final_system += system + "\n\n"
        if blocks.get("evidence_usage_block"):
            final_system += blocks["evidence_usage_block"] + "\n\n"
        final_system += (
            "## Evidence Prioritization Rule\n"
            "Use the Writer Evidence Packet as the factual boundary for this section. "
            "Prioritize packet material that best matches the current section objective and evidence_focus.\n\n"
        )
        if resolve_language(text=clean_title, language=language) == "zh":
            final_system += (
                "## Heading Language Consistency\n"
                "- This section belongs to a Chinese deliverable.\n"
                "- Any reader-facing subsection headings generated inside this section must use Chinese as the heading language.\n"
                "- Fixed product names, protocol names, or UI labels may remain in their original language when they are not naturally localized.\n"
                "- Keep heading language consistent within the section.\n\n"
            )
        system = final_system.strip()
        user_parts: List[str] = []
        user_parts.append(
            _markdown_section(
                "Section Task",
                "\n".join(
                    [
                        f"- section_number: {number}",
                        f"- title: {clean_title}",
                        f"- objective: {objective}",
                        f"- section_role: {section_role}",
                        f"- target_words: {target_words}",
                        f"- heading_level: {level}",
                    ]
                ),
            )
        )
        if key_points:
            user_parts.append(_markdown_section("Key Points", _markdown_bullets(key_points)))
        if evidence_focus:
            user_parts.append(_markdown_section("Evidence Focus", _markdown_bullets(evidence_focus)))
        if normalized_facts:
            user_parts.append(_markdown_section("Must Cover Facts", _render_fact_contract_markdown(normalized_facts, language=language)))
        if allowed_claim_types or disallowed_claim_types:
            user_parts.append(
                _markdown_section(
                    "Section Claim Contract",
                    _render_claim_contract_markdown(
                        allowed_claim_types=allowed_claim_types,
                        disallowed_claim_types=disallowed_claim_types,
                        language=language,
                    ),
                )
            )
        if open_questions:
            user_parts.append(_markdown_section("Section Open Questions", _markdown_bullets(open_questions)))
        argument_items = list((body_contract_context or {}).get("argument_items") or [])[:8]
        if argument_items:
            user_parts.append(
                _markdown_section(
                    "Argument Items",
                    _markdown_bullets([_compact_scalar(json.dumps(item, ensure_ascii=False), limit=300) for item in argument_items]),
                )
            )
        if running_summary:
            user_parts.append(_markdown_section("Running Summary", running_summary[-2200:]))
        user_parts.append(
            _markdown_section(
                "Document Context",
                "\n".join(
                    [
                        f"- previous_section_core_claim: {str(prev_summary.core_claim or '').strip()}",
                        f"- next_section_title: {str(next_section_title or '').strip()}",
                        f"- report_thesis: {str(doc_state.report_thesis or '').strip()}",
                    ]
                ),
            )
        )
        user_parts.append(_markdown_section("References", _markdown_bullets([f"[{int(r.get('index') or 0)}] {str(r.get('title') or r.get('url') or '').strip()} {str(r.get('url') or '').strip()}".strip() for r in source_refs[:12]])))
        constraints_md = _format_writer_constraints_markdown(_project_writer_constraints(body_contract_context))
        if constraints_md:
            user_parts.append(constraints_md)
        if identity_split.get("formatting_block"):
            user_parts.append(str(identity_split.get("formatting_block") or "").strip())
        if blocks.get("publish_narrative_block"):
            user_parts.append(blocks["publish_narrative_block"].strip())
        if blocks.get("must_include_block"):
            user_parts.append(blocks["must_include_block"].strip())
        if blocks.get("fewshot_block"):
            user_parts.append(blocks["fewshot_block"].strip())
        if style_md:
            user_parts.append(_markdown_section("Selected Style Skill", style_md[:3000]))
        writing_mode = str(((body_contract_context or {}).get("compose_policy") or {}).get("writing_mode") or "").strip().lower()
        output_rules = [
            "- Output final publishable markdown for this section only.",
            f"- Start with heading `{heading} {display_title}`.",
            "- Do not output JSON or planning notes.",
            "- Prefer concrete business context over generic industry commentary.",
            "- Include at least one specific scenario, actor, or workflow step in this section when the task allows it.",
            "- Turn conclusions into actions: make clear who should do what, in what order, and why now.",
            "- Avoid generic consulting-report cliches and empty transitions, including formulaic claims about ongoing development, fundamental nature, importance, or obvious conclusions.",
        ]
        output_language = resolve_language(text=clean_title, language=language)
        if writing_mode == "evidence_bound":
            output_rules.append("- Keep the main narrative limited to confirmed facts from the provided evidence.")
            output_rules.append("- Treat `Confirmed Facts` as the authoritative source for flows, rules, thresholds, defaults, permissions, and button behavior.")
            output_rules.append("- Treat `Must Cover Facts` as the minimum section-scoped factual contract.")
            output_rules.append("- Treat `Section Claim Contract` as the semantic boundary for what this section may or may not assert.")
            output_rules.append("- Do not invent operational rules or UI logic that are absent from `Confirmed Facts` or explicit evidence items.")
            output_rules.append(
                "- If uncertainty or a suggested completion must be mentioned, place it under a short trailing subsection "
                + ("whose Chinese title means Pending Confirmation and Suggested Additions." if output_language == "zh" else "titled Pending Confirmation and Suggested Additions.")
            )
        if output_language == "zh":
            output_rules.append("- All reader-facing headings and subheadings must be in Chinese unless they are fixed UI labels or product names.")
            output_rules.append("- Any generated subsection labels such as 1.1 / 1.2 must use Chinese heading text, not English words like Background / Scope / Goal.")
        user_parts.append(
            _markdown_section(
                "Output Requirement",
                "\n".join(output_rules),
            )
        )
        user_markdown = "\n\n".join(part for part in user_parts if str(part).strip()).strip()
        raw_section_payload = {
            "section_payload": prompt,
            "style_markdown": style_md,
            "publish_narrative_block": str(blocks.get("publish_narrative_block") or ""),
            "must_include_block": str(blocks.get("must_include_block") or ""),
            "fewshot_block": str(blocks.get("fewshot_block") or ""),
        }
        normalized_prompt = await self._normalize_section_prompt(
            language=language,
            raw_system=system,
            raw_payload=raw_section_payload,
            raw_user_prompt=user_markdown,
        )
        if normalized_prompt is not None:
            system = str(normalized_prompt.system_prompt or "").strip()
            user_markdown = str(normalized_prompt.user_prompt or "").strip()
        user_markdown = "\n\n".join(part for part in [user_markdown, packet_markdown] if part).strip()
        budgeted_prompt = fit_writer_prompt(system=system, user=user_markdown)
        system = budgeted_prompt.system
        user_markdown = budgeted_prompt.user
        try:
            self.deps.log(
                "section_prompt",
                {
                    "section_number": number,
                    "section_title": clean_title,
                    "system_preview": _truncate_text(system, 1800),
                    "payload_preview": _truncate_text(user_markdown, 2400),
                    "target_words": target_words,
                    "writer_evidence_packet_active": True,
                    "writer_evidence_packet_chars": len(packet_markdown),
                    "writer_evidence_packet_coverage_complete": bool(packet.coverage.complete),
                    "normalized_prompt_used": bool(normalized_prompt),
                    "normalized_section_goal_chars": len(str(getattr(normalized_prompt, "clean_section_goal", "") or "")),
                    "normalized_evidence_slice_chars": len(str(getattr(normalized_prompt, "evidence_slice_summary", "") or "")),
                    "final_input_estimated_tokens": budgeted_prompt.estimated_tokens,
                    "final_input_truncated": budgeted_prompt.truncated,
                },
            )
        except Exception:
            pass
        await self._persist_section_prompt_debug_bundle(
            debug_task_id=debug_task_id,
            section_number=number,
            section_title=clean_title,
            target_words=target_words,
            raw_system=final_system.strip(),
            system=system,
            raw_payload=raw_section_payload,
            raw_user_prompt=user_markdown,
            normalized_prompt=normalized_prompt,
        )
        class SectionOutput(BaseModel):
            markdown_content: str = Field(description="The complete markdown content for the section, starting with the heading.")

        @retry(stop=stop_after_attempt(3), wait=wait_fixed(1), reraise=True)
        async def _invoke_writer():
            resp = await self.deps.llm.ainvoke([Message(role=Role.SYSTEM, content=system), Message(role=Role.USER, content=user_markdown)])
            raw = str(getattr(resp, "content", "") or "").strip()
            # Handle potential non-JSON raw markdown gracefully
            if not raw.startswith("{"):
                return {"markdown_content": raw}
            data = json.loads(raw.replace("```json", "").replace("```", "").strip())
            validated = SectionOutput.model_validate(data)
            return validated.model_dump()

        try:
            data = await _invoke_writer()
            content = str(data.get("markdown_content", "")).strip()
        except Exception as e:
            self.deps.log("section_write_failed", {"title": clean_title, "error": str(e)[:260]})
            content = ""
        if not content:
            content = f"{heading} {display_title}\n\n" + ("待补充信息。" if language == "zh" else "Pending details.")
        header_prefix = f"{heading} {display_title}".strip()
        if not content.lstrip().startswith("#"):
            content = f"{header_prefix}\n\n" + content
        if not content.lstrip().startswith(header_prefix):
            content = f"{header_prefix}\n\n" + re.sub(r"^\s*#+\s+.*$", "", content, count=1, flags=re.MULTILINE).strip()
        content = await self._enforce_section_contract(
            section_markdown=content,
            title=clean_title,
            objective=objective,
            language=language,
            must_cover_facts=normalized_facts,
            allowed_claim_types=allowed_claim_types,
            disallowed_claim_types=disallowed_claim_types,
            open_questions=open_questions,
        )
        return content

    async def summarize_section(
        self,
        *,
        section_markdown: str,
        section_number: str,
        section_title: str,
        next_section_title: str,
        language: str,
        existing_state: Optional[DocumentState] = None,
    ) -> SectionSummaryBundle:
        prompt = {
            "section_number": section_number,
            "section_title": section_title,
            "next_section_title": str(next_section_title or "").strip(),
            "section_markdown": str(section_markdown or "")[:5000],
            "existing_state": (existing_state or DocumentState()).model_dump(),
            "language": language,
        }
        system = self.prompts.get("section_summarizer", language_name=self.deps.language_name(language))

        @retry(stop=stop_after_attempt(3), wait=wait_fixed(1), reraise=True)
        async def _invoke_summarizer():
            resp = await self.deps.llm.ainvoke([Message(role=Role.SYSTEM, content=system), Message(role=Role.USER, content=json.dumps(prompt, ensure_ascii=False))])
            raw = str(getattr(resp, "content", "") or "").strip()
            data = json.loads(raw.replace("```json", "").replace("```", "").strip())
            validated = SectionSummaryBundle.model_validate(data)
            return validated

        try:
            return await _invoke_summarizer()
        except Exception as e:
            self.deps.log("section_summary_failed", {"section_number": section_number, "error": str(e)[:260]})
        return SectionSummaryBundle(
            summary=SectionSummary(
                section_number=section_number,
                section_title=section_title,
                core_claim=section_title,
            )
        )

    async def calibrate_length(self, *, section_markdown: str, language: str, target_words: int) -> str:
        text = section_markdown or ""
        length = len(text)
        low = int(target_words * 0.8)
        high = int(target_words * 1.15)
        if low <= length <= high:
            return text
        action = "expand" if length < low else "compress"
        prompt = {
            "action": action,
            "target_words": target_words,
            "current_len": length,
            "markdown": text,
            "rules": [
                "Keep title and section numbering unchanged.",
                "Keep factual claims and source references unchanged.",
                "Do not remove visualization blocks.",
                "Output markdown only.",
                "When compressing, aim close to target_words instead of keeping long safe redundancy.",
                "Prefer removing repetitive filler, generic transitions, and duplicated summaries first.",
            ],
        }
        system = self.prompts.get("section_calibrator", language_name=self.deps.language_name(language))
        class CalibratedOutput(BaseModel):
            rewritten_markdown: str = Field(description="The calibrated markdown content")

        @retry(stop=stop_after_attempt(3), wait=wait_fixed(1), reraise=True)
        async def _invoke_calibrator():
            resp = await self.deps.llm.ainvoke([Message(role=Role.SYSTEM, content=system), Message(role=Role.USER, content=json.dumps(prompt, ensure_ascii=False))])
            raw = str(getattr(resp, "content", "") or "").strip()
            if not raw.startswith("{"):
                return {"rewritten_markdown": raw}
            data = json.loads(raw.replace("```json", "").replace("```", "").strip())
            validated = CalibratedOutput.model_validate(data)
            return validated.model_dump()

        try:
            data = await _invoke_calibrator()
            rewritten = str(data.get("rewritten_markdown", "")).strip()
            if rewritten:
                return rewritten
        except Exception as e:
            self.deps.log("section_calibrate_failed", {"error": str(e)[:260]})
        return text

    async def inject_visual_if_missing(self, *, section_markdown: str, language: str, visual_hint: str, visual_helper: VisualAugmenter) -> str:
        if visual_hint in {"", "none"}:
            return section_markdown
        if visual_helper.contains_visual(section_markdown):
            return section_markdown
        prompt = {
            "visual_hint": visual_hint,
            "markdown": section_markdown,
            "rules": [
                "Append one visualization block at the end of this section.",
                "For chart use ```chart with valid JSON only.",
                "For mermaid use simple flowchart TD.",
                "For table use compact markdown table.",
                "Do not alter existing section content.",
            ],
        }
        system = self.prompts.get("visual_injector", language_name=self.deps.language_name(language))
        class VisualInjectorOutput(BaseModel):
            markdown_with_visual: str = Field(description="The markdown content with the visualization block appended")

        @retry(stop=stop_after_attempt(3), wait=wait_fixed(1), reraise=True)
        async def _invoke_injector():
            resp = await self.deps.llm.ainvoke([Message(role=Role.SYSTEM, content=system), Message(role=Role.USER, content=json.dumps(prompt, ensure_ascii=False))])
            raw = str(getattr(resp, "content", "") or "").strip()
            if not raw.startswith("{"):
                return {"markdown_with_visual": raw}
            data = json.loads(raw.replace("```json", "").replace("```", "").strip())
            validated = VisualInjectorOutput.model_validate(data)
            return validated.model_dump()

        try:
            data = await _invoke_injector()
            rewritten = str(data.get("markdown_with_visual", "")).strip()
            if rewritten and visual_helper.contains_visual(rewritten):
                return rewritten
        except Exception as e:
            self.deps.log("visual_inject_failed", {"error": str(e)[:260]})
        # deterministic fallback
        english = str(language or "").lower().startswith("en")
        if visual_hint == "table":
            appendix = (
                "\n\n| Dimension | Current State | Assessment |\n|---|---|---|\n| A | - | - |\n| B | - | - |\n"
                if english else "\n\n| 维度 | 现状 | 判断 |\n|---|---|---|\n| A | - | - |\n| B | - | - |\n"
            )
        elif visual_hint == "mermaid":
            appendix = (
                "\n\n```mermaid\nflowchart TD\nA[Input] --> B[Analysis]\nB --> C[Conclusion]\n```\n"
                if english else "\n\n```mermaid\nflowchart TD\nA[输入] --> B[分析]\nB --> C[结论]\n```\n"
            )
        elif visual_hint == "chart":
            appendix = (
                "\n\n```chart\n"
                + ("{\"type\":\"line\",\"title\":\"Trend Illustration\",\"labels\":[\"Q1\",\"Q2\",\"Q3\",\"Q4\"]," if english else "{\"type\":\"line\",\"title\":\"趋势示意\",\"labels\":[\"Q1\",\"Q2\",\"Q3\",\"Q4\"],")
                + "\"series\":[{\"name\":\"Index\",\"data\":[100,118,129,143]}]}\n"
                + "```\n"
            )
        else:
            return section_markdown
        return (section_markdown or "").rstrip() + appendix
