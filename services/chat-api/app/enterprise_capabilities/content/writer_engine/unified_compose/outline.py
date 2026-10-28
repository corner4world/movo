from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from app.llm.types import Message, Role
from app.llm.decision_turn import DecisionTurnSpec, invoke_structured_decision
from tenacity import retry, stop_after_attempt, wait_fixed
from app.enterprise_capabilities.evidence.foundation.writer_packet import (
    WriterEvidencePacket,
    render_section_writer_evidence_packet,
)
from app.enterprise_capabilities.content.style_contract_renderer import is_writer_style_contract_block
from .models import ComposeDeps, OutlinePromptNormalizationOutput, ReportOutlinePlan
from .prompt_formatting import _style_prompt_limit
from .shared import _exception_debug_payload, _truncate_text


class OutlinePlanner:
    def __init__(self, deps: ComposeDeps, prompt_registry: Any):
        self.deps = deps
        self.prompts = prompt_registry

    async def _normalize_outline_prompt(
        self,
        *,
        language: str,
        raw_system: str,
        raw_payload: Dict[str, Any],
        raw_user_prompt: str,
    ) -> OutlinePromptNormalizationOutput | None:
        prompt = self.prompts.get("outline_prompt_normalizer")
        payload = {
            "language": language,
            "raw_system_prompt": raw_system,
            "raw_payload": raw_payload,
            "raw_user_prompt": raw_user_prompt,
        }
        try:
            model = self.deps.llm.with_structured_output(OutlinePromptNormalizationOutput, method="function_calling")
            result = await model.ainvoke(
                [
                    Message(role=Role.SYSTEM, content=prompt),
                    Message(role=Role.USER, content=json.dumps(payload, ensure_ascii=False)),
                ]
            )
            normalized = result if isinstance(result, OutlinePromptNormalizationOutput) else OutlinePromptNormalizationOutput.model_validate(result)
            if not str(normalized.system_prompt or "").strip() or not str(normalized.user_prompt or "").strip():
                return None
            return normalized
        except Exception as exc:
            self.deps.log("outline_prompt_normalize_failed", {"error": str(exc)[:260], "error_type": type(exc).__name__})
            return None

    def normalize_outline_nodes(self, sections: List[Dict[str, Any]], numbering_style: str) -> List[Dict[str, Any]]:
        numbering_style = (numbering_style or "hierarchical").lower()
        allowed_visual = {"table", "chart", "mermaid", "none"}

        def _normalize_visual_hint(raw: str) -> str:
            v = str(raw or "").strip().lower()
            mapping = {
                "markdown_table": "table",
                "md_table": "table",
                "ascii_diagram": "mermaid",
                "callout_blockquote": "none",
                "blockquote": "none",
                "list": "none",
            }
            v = mapping.get(v, v)
            return v if v in allowed_visual else "none"

        def _walk(nodes: List[Dict[str, Any]], parent_no: str, level: int) -> List[Dict[str, Any]]:
            out: List[Dict[str, Any]] = []
            for idx, node in enumerate(nodes, start=1):
                if not isinstance(node, dict):
                    continue
                no = str(idx) if not parent_no else f"{parent_no}.{idx}"
                title = str(node.get("title") or node.get("name") or "").strip()
                objective = str(node.get("objective") or node.get("core_question") or "").strip()
                key_points = [str(x) for x in (node.get("key_points") or []) if str(x).strip()]
                evidence_focus = [str(x) for x in (node.get("evidence_focus") or []) if str(x).strip()]
                visual_hint = _normalize_visual_hint(node.get("visual_hint") or "")
                out.append(
                    {
                        "number": no if numbering_style == "hierarchical" else str(len(out) + 1),
                        "level": max(1, min(4, int(node.get("level") or level))),
                        "title": title or f"Section {no}",
                        "objective": objective,
                        "key_points": key_points[:8],
                        "evidence_focus": evidence_focus[:8],
                        "visual_hint": visual_hint,
                        "weight": max(1, min(5, int(node.get("weight") or 3))),
                        "section_role": str(node.get("section_role") or "analysis").strip() or "analysis",
                    }
                )
                children = node.get("children") or []
                if isinstance(children, list) and children:
                    out.extend(_walk(children, no, level + 1))
            return out

        return _walk(sections, "", 1)

    @staticmethod
    def _build_outline_contract_context(contract_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        ctx = dict(contract_context or {})
        compose_policy = dict(ctx.get("compose_policy") or {})
        structure_contract = dict(ctx.get("structure_contract") or {})
        evidence_policy = dict(ctx.get("evidence_policy") or {})
        quality_gates = dict(ctx.get("quality_gates") or {})
        visual_contract = dict(ctx.get("visual_contract") or {})
        prompt_contract = dict(ctx.get("prompt_contract") or {})

        slim = {
            "compose_policy": {
                "publish_channel": compose_policy.get("publish_channel"),
                "content_form": compose_policy.get("content_form"),
                "writing_mode": compose_policy.get("writing_mode"),
                "tone": compose_policy.get("tone"),
                "audience": compose_policy.get("audience"),
            },
            "structure_contract": {
                "required_blocks": list(structure_contract.get("required_blocks") or []),
                "section_count": structure_contract.get("section_count"),
                "outline_depth": structure_contract.get("outline_depth"),
            },
            "evidence_policy": {
                "citation_required": bool(evidence_policy.get("citation_required")),
            },
            "quality_gates": {
                "min_words": quality_gates.get("min_words"),
                "max_words": quality_gates.get("max_words"),
            },
            "prompt_contract": {
                "identity": prompt_contract.get("identity"),
                "must_include": list(prompt_contract.get("must_include") or []),
                "style_reference": {
                    "positive": str((prompt_contract.get("style_reference") or {}).get("positive") or "")[:240],
                    "negative": str((prompt_contract.get("style_reference") or {}).get("negative") or "")[:160],
                },
                "formatting_rules": dict(prompt_contract.get("formatting_rules") or {}),
                "meta_discourse_banned": bool((prompt_contract.get("anti_patterns") or {}).get("meta_discourse_banned")),
            },
        }
        return slim

    async def generate(
        self,
        *,
        user_query: str,
        language: str,
        writer_evidence_packet: Dict[str, Any],
        strategy: Dict[str, Any],
        style_md: str,
        contract_context: Optional[Dict[str, Any]] = None,
        prompt_variant: str = "",
        commentary_sink: Any = None,
    ) -> Dict[str, Any]:
        target_sections = int(strategy.get("section_count") or 10)
        outline_depth = int(strategy.get("outline_depth") or 3)
        numbering_style = str(strategy.get("numbering_style") or "hierarchical")
        word_budget = strategy.get("word_budget") or {}
        total_target = int(word_budget.get("total_target") or 7000)
        prompt = {
            "user_goal": user_query,
            "language": language,
            "target_sections": target_sections,
            "outline_depth": outline_depth,
            "numbering_style": numbering_style,
            "total_target_words": total_target,
            "contract_context": self._build_outline_contract_context(contract_context),
        }
        packet = WriterEvidencePacket.model_validate(writer_evidence_packet or {})
        packet_markdown = render_section_writer_evidence_packet(packet)
        from app.enterprise_capabilities.content.writer_engine.unified_compose.assembler import ContractPromptAssembler
        outline_prompt_name = f"outline_planner_{prompt_variant}" if prompt_variant else "outline_planner"
        system = self.prompts.get(outline_prompt_name, language_name=self.deps.language_name(language))
        blocks = ContractPromptAssembler.assemble_outline_blocks(contract_context)
        prompt_contract = dict((contract_context or {}).get("prompt_contract") or {})
        compact_style = str(prompt_contract.get("style_markdown_compact") or "").strip()

        final_system = ""
        if blocks.get("role_block"):
            final_system += blocks["role_block"] + "\n\n"
        if blocks.get("anchors_block"):
            final_system += blocks["anchors_block"] + "\n\n"
        final_system += system + "\n\n"
        if str(language or "").strip().lower().startswith("zh"):
            final_system += (
                "## Heading Language Consistency\n"
                "- This is a Chinese deliverable.\n"
                "- The document title and outline section titles must use Chinese as the reader-facing language.\n"
                "- Fixed product names, protocol names, or UI labels may remain in their original language when they are not naturally localized.\n"
                "- Do not mix heading languages within the same deliverable.\n\n"
            )
        if is_writer_style_contract_block(style_md):
            final_system += "## Writer Style Contract\n" + style_md[:_style_prompt_limit(style_md, legacy_limit=700)] + "\n\n"
        elif compact_style:
            final_system += "## Protocol Axes\n" + compact_style[:700] + "\n\n"
        elif style_md:
            final_system += "## Protocol Axes\n" + style_md[:700] + "\n\n"
        if blocks.get("must_include_block"):
            final_system += blocks["must_include_block"] + "\n\n"
        if blocks.get("fewshot_block"):
            final_system += blocks["fewshot_block"] + "\n\n"
        system = final_system.strip()
        user_prompt = json.dumps(prompt, ensure_ascii=False)
        normalized_prompt = await self._normalize_outline_prompt(
            language=language,
            raw_system=system,
            raw_payload=prompt,
            raw_user_prompt=user_prompt,
        )
        if normalized_prompt is not None:
            system = str(normalized_prompt.system_prompt or "").strip()
            user_prompt = str(normalized_prompt.user_prompt or "").strip()
        user_prompt = "\n\n".join(part for part in [user_prompt, packet_markdown] if part).strip()
        try:
            self.deps.log(
                "outline_contract_used",
                {
                    "role_len": len(str(blocks.get("role_block") or "")),
                    "anchors_len": len(str(blocks.get("anchors_block") or "")),
                    "must_include_len": len(str(blocks.get("must_include_block") or "")),
                    "fewshot_len": len(str(blocks.get("fewshot_block") or "")),
                    "compact_style_len": len(compact_style),
                    "system_len": len(system),
                    "normalized_prompt_used": bool(normalized_prompt),
                },
            )
            self.deps.log(
                "outline_prompt",
                {
                    "system_preview": _truncate_text(system, 1800),
                    "payload_preview": _truncate_text(user_prompt, 1600),
                    "target_sections": target_sections,
                    "outline_depth": outline_depth,
                },
            )
        except Exception:
            pass

        @retry(stop=stop_after_attempt(3), wait=wait_fixed(1), reraise=True)
        async def _invoke_llm():
            parsed = await invoke_structured_decision(
                self.deps.llm,
                ReportOutlinePlan,
                [
                    Message(role=Role.SYSTEM, content=system),
                    Message(role=Role.USER, content=user_prompt),
                ],
                spec=DecisionTurnSpec(
                    locale=language,
                    turn_id="writing.outline",
                    sink=commentary_sink,
                ),
            )
            validated = parsed if isinstance(parsed, ReportOutlinePlan) else ReportOutlinePlan.model_validate(parsed)
            return validated.model_dump()

        try:
            data = await _invoke_llm()
            if data and data.get("sections"):
                normalized_raw = self.normalize_outline_nodes(list(data.get("sections") or []), numbering_style)
                req_blocks = [
                    str(x).strip()
                    for x in (((contract_context or {}).get("structure_contract") or {}).get("required_blocks") or [])
                    if str(x).strip()
                ]
                target_for_outline = max(int(target_sections or 1), len(req_blocks))
                target_for_outline = max(1, min(24, target_for_outline))
                normalized = normalized_raw[:target_for_outline]
                try:
                    self.deps.log(
                        "outline_result",
                        {
                            "title": str(data.get("title") or ""),
                            "section_count_raw": len(normalized_raw),
                            "section_count_used": len(normalized),
                            "target_sections": target_for_outline,
                            "sections": [
                                {
                                    "number": str(s.get("number") or ""),
                                    "level": int(s.get("level") or 1),
                                    "title": str(s.get("title") or ""),
                                    "visual_hint": str(s.get("visual_hint") or ""),
                                    "weight": int(s.get("weight") or 3),
                                    "section_role": str(s.get("section_role") or "analysis"),
                                }
                                for s in normalized
                            ],
                        },
                    )
                except Exception:
                    pass
                return {
                    "title": str(data.get("title") or ""),
                    "sections": normalized,
                }
        except Exception as e:
            self.deps.log("outline_failed", _exception_debug_payload(e))
        # deterministic safe fallback
        req_blocks = [
            str(x).strip()
            for x in (((contract_context or {}).get("structure_contract") or {}).get("required_blocks") or [])
            if str(x).strip()
        ]
        fallback_title = "结构化文档" if language == "zh" else "Structured Document"
        fallback_sections = []
        fallback_count = max(1, min(16, int(target_sections or 1)))
        for idx in range(fallback_count):
            n = idx + 1
            fallback_title_item = req_blocks[idx] if idx < len(req_blocks) else (
                f"{'补充章节' if language == 'zh' else 'Additional Section'} {n}"
            )
            fallback_sections.append(
                {
                    "number": str(n),
                    "level": 1,
                    "title": fallback_title_item,
                    "objective": "Organize the available facts for this section",
                    "key_points": [],
                    "evidence_focus": [],
                    "visual_hint": "chart" if 1 < n < fallback_count else "table",
                    "weight": 3,
                    "section_role": "analysis",
                }
            )
        return {"title": fallback_title, "sections": fallback_sections}
