from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from app.enterprise_capabilities.content.style_contract_renderer import is_writer_style_contract_block
from app.enterprise_capabilities.content.structure_roles import resolve_language


def _compact_scalar(value: Any, *, limit: int = 280) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "...<truncated>"


def _compact_string_list(values: Any, *, limit: Optional[int] = 8, item_limit: int = 180) -> List[str]:
    out: List[str] = []
    items = list(values or [])
    if limit is not None:
        items = items[:limit]
    for item in items:
        token = _compact_scalar(item, limit=item_limit)
        if token and token not in out:
            out.append(token)
    return out


def _style_prompt_limit(selected_style_md: str, *, legacy_limit: int) -> int:
    return 16000 if is_writer_style_contract_block(selected_style_md) else legacy_limit


def _project_writer_constraints(strategy: Dict[str, Any]) -> Dict[str, Any]:
    compose = dict(strategy.get("compose_policy") or {})
    structure = dict(strategy.get("structure_contract") or {})
    evidence = dict(strategy.get("evidence_policy") or {})
    quality = dict(strategy.get("quality_gates") or {})
    prompt_contract = dict(strategy.get("prompt_contract") or {})
    output_contract = dict(strategy.get("output_contract") or {})
    content_plan = dict(strategy.get("content_plan") or {})

    style_reference = dict(prompt_contract.get("style_reference") or {})
    formatting_rules = dict(prompt_contract.get("formatting_rules") or {})
    anti_patterns = dict(prompt_contract.get("anti_patterns") or {})

    must_include_items = _compact_string_list(prompt_contract.get("must_include") or [], limit=None, item_limit=180)
    required_section_items = _compact_string_list(structure.get("required_blocks") or [], limit=None, item_limit=120)
    seen_required = {str(item).strip() for item in must_include_items}
    required_sections = [item for item in required_section_items if str(item).strip() and str(item).strip() not in seen_required]
    visible_heading_plan: List[str] = []
    for item in list(content_plan.get("sections") or [])[:10]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if title and title not in visible_heading_plan:
            visible_heading_plan.append(title)

    constraints = {
        "must_include": must_include_items,
        "required_sections": required_sections,
        "visible_heading_plan": visible_heading_plan,
        "section_roles": list(compose.get("section_roles") or [])[:8],
        "content_form": str(compose.get("content_form") or "").strip(),
        "writing_mode": str(compose.get("writing_mode") or strategy.get("writing_mode") or "").strip(),
        "publish_channel": str(compose.get("publish_channel") or "").strip(),
        "forbidden_patterns": _compact_string_list(
            strategy.get("forbidden_patterns") or prompt_contract.get("forbidden_patterns") or [],
            limit=None,
            item_limit=180,
        ),
        "citation_required": bool(evidence.get("citation_required")),
        "length_target": {
            "min_words": int(quality.get("min_words") or 0),
            "max_words": int(quality.get("max_words") or 0),
        },
        "formatting_rules": {
            "heading_style": _compact_scalar(formatting_rules.get("heading_style") or "", limit=60),
            "paragraph_style": _compact_scalar(formatting_rules.get("paragraph_style") or "", limit=60),
            "citation_style": _compact_scalar(formatting_rules.get("citation_style") or "", limit=60),
            "deliverable": _compact_scalar(output_contract.get("deliverable") or "", limit=80),
        },
        "style_reference": {
            "positive": _compact_scalar(style_reference.get("positive") or "", limit=220),
            "negative": _compact_scalar(style_reference.get("negative") or "", limit=180),
        },
        "meta_discourse_banned": bool(anti_patterns.get("meta_discourse_banned")),
        "voice": {
            "tone": _compact_scalar(compose.get("tone") or "", limit=80),
            "audience": _compact_scalar(compose.get("audience") or "", limit=160),
            "publish_channel": _compact_scalar(compose.get("publish_channel") or "", limit=60),
            "content_form": _compact_scalar(compose.get("content_form") or "", limit=60),
        },
    }
    return constraints


def _markdown_section(title: str, body: str) -> str:
    text = str(body or "").strip()
    if not text:
        return ""
    return f"## {title}\n{text}"


def _split_identity_block(identity_block: str) -> Dict[str, str]:
    text = str(identity_block or "").strip()
    if not text:
        return {"system_identity": "", "formatting_block": ""}
    sections = re.split(r"(?=^##\s+)", text, flags=re.MULTILINE)
    kept: List[str] = []
    formatting = ""
    for sec in sections:
        stripped = str(sec or "").strip()
        if not stripped:
            continue
        if stripped.startswith("## Formatting Rules"):
            formatting = stripped
            continue
        kept.append(stripped)
    return {
        "system_identity": "\n\n".join(kept).strip(),
        "formatting_block": formatting,
    }


def _markdown_bullets(items: List[str]) -> str:
    clean = [str(x).strip() for x in (items or []) if str(x).strip()]
    return "\n".join(f"- {item}" for item in clean)


def _markdown_fact_objects(items: List[Dict[str, Any]]) -> str:
    rendered: List[str] = []
    for item in list(items or [])[:12]:
        if not isinstance(item, dict):
            continue
        summary = str(item.get("summary") or "").strip()
        if not summary:
            continue
        fact_type = str(item.get("fact_type") or "").strip()
        source_kind = str(item.get("source_kind") or "").strip()
        source_ref = str(item.get("source_ref") or "").strip()
        lines = [f"- summary: {summary}"]
        if fact_type:
            lines.append(f"  fact_type: {fact_type}")
        if source_kind:
            lines.append(f"  source_kind: {source_kind}")
        if source_ref:
            lines.append(f"  source_ref: {source_ref}")
        rendered.append("\n".join(lines))
    return "\n".join(rendered)


_CLAIM_TYPE_LABELS_ZH: Dict[str, str] = {
    "background": "背景与现状事实",
    "scope": "范围与边界说明",
    "goal": "目标与建设意图",
    "existing_capability": "已确认的现有能力",
    "module_responsibility": "模块职责与边界",
    "flow_relationship": "流程关系与模块衔接",
    "data_path": "数据流向与回流路径",
    "page_component": "页面组成与功能区块",
    "field": "可见字段、指标名称与配置项",
    "interaction": "已出现的按钮、操作与交互行为",
    "view_structure": "视图结构、层级关系与展示方式",
    "step_definition": "流程步骤定义",
    "input_output": "步骤输入与输出",
    "status_transition": "状态变化与结果去向",
    "observed_interaction": "界面中已观察到的操作行为",
    "metric_definition": "指标定义与统计对象",
    "metric_formula_boundary": "指标口径边界与可确认的计算范围",
    "data_source": "指标来源页面、字段或环节",
    "module_mapping": "指标与模块/流程节点的映射关系",
    "constraint_definition": "规则、约束与适用条件",
    "parameter_boundary": "参数边界、阈值与配置范围",
    "status_semantics": "状态含义与状态区分",
    "boundary_confirmation_gap": "待确认的边界与未证实项",
    "confirmed_fact": "已确认事实",
    "trend": "趋势判断依据",
    "recommendation": "建议或后续动作",
    "impact_analysis": "影响分析与推演",
    "next_action": "行动建议",
    "strategy_suggestion": "策略建议",
    "workflow_rule": "流程规则补写",
    "interaction_default": "默认交互规则补写",
    "future_recommendation": "未来方案建议",
    "ui_rule": "界面规则推断",
    "field_default": "字段默认值推断",
    "implementation_detail": "实现细节扩写",
    "implicit_business_rule": "隐含业务规则推断",
    "permission_rule": "权限规则补写",
    "validation_rule": "校验规则补写",
    "hidden_rule": "未显式展示的隐藏规则",
    "state_machine_rule": "状态机规则补写",
    "frontend_validation_rule": "前端校验逻辑补写",
    "relationship_tree_inference": "树状关系结构的额外推断",
    "metric_formula_expansion": "超出证据的公式扩展",
    "workflow_rewrite": "对已观察流程的重写",
    "unsupported_rule": "未被证据支持的规则",
    "unsupported_inference": "未被证据支持的推断",
    "fabricated_metric": "虚构指标或虚构口径",
}


def _humanize_claim_type(claim_type: str, *, language: str) -> str:
    raw = str(claim_type or "").strip()
    if not raw:
        return ""
    lang = resolve_language(text=raw, language=language)
    if lang == "zh":
        return _CLAIM_TYPE_LABELS_ZH.get(raw, raw.replace("_", " "))
    return raw.replace("_", " ")


def _render_claim_contract_markdown(
    *,
    allowed_claim_types: List[str],
    disallowed_claim_types: List[str],
    language: str,
) -> str:
    lines: List[str] = []
    if allowed_claim_types:
        title = "本节允许写入的内容类型" if resolve_language(text="", language=language) == "zh" else "Allowed content types"
        lines.append(title + ":")
        lines.extend(f"- {_humanize_claim_type(item, language=language)}" for item in allowed_claim_types if _humanize_claim_type(item, language=language))
    if disallowed_claim_types:
        title = "本节禁止扩写的内容类型" if resolve_language(text="", language=language) == "zh" else "Disallowed content types"
        lines.append(title + ":")
        lines.extend(f"- {_humanize_claim_type(item, language=language)}" for item in disallowed_claim_types if _humanize_claim_type(item, language=language))
    return "\n".join(lines).strip()


def _render_fact_contract_markdown(items: List[Dict[str, Any]], *, language: str) -> str:
    rendered: List[str] = []
    zh = resolve_language(text="", language=language) == "zh"
    for item in list(items or [])[:12]:
        if not isinstance(item, dict):
            continue
        summary = str(item.get("summary") or "").strip()
        if not summary:
            continue
        fact_type = _humanize_claim_type(str(item.get("fact_type") or "").strip(), language=language)
        source_kind = str(item.get("source_kind") or "").strip()
        source_ref = str(item.get("source_ref") or "").strip()
        lines = [f"- {'事实' if zh else 'Fact'}: {summary}"]
        if fact_type:
            lines.append(f"  {'类型' if zh else 'Type'}: {fact_type}")
        source_bits = [bit for bit in [source_kind, source_ref] if bit]
        if source_bits:
            lines.append(f"  {'来源' if zh else 'Source'}: {' / '.join(source_bits)}")
        rendered.append("\n".join(lines))
    return "\n".join(rendered)


def _format_writer_constraints_markdown(constraints: Dict[str, Any]) -> str:
    parts: List[str] = []
    must_include = _markdown_bullets(list(constraints.get("must_include") or []))
    if must_include:
        parts.append(_markdown_section("Must Include", must_include))
    required_sections = _markdown_bullets(list(constraints.get("required_sections") or []))
    if required_sections:
        parts.append(_markdown_section("Required Sections", required_sections))
    visible_heading_plan = _markdown_bullets(list(constraints.get("visible_heading_plan") or []))
    if visible_heading_plan:
        parts.append(_markdown_section("Visible Heading Plan", visible_heading_plan))
    forbidden_patterns = _markdown_bullets(list(constraints.get("forbidden_patterns") or []))
    if forbidden_patterns:
        parts.append(_markdown_section("Avoid", forbidden_patterns))
    length_target = dict(constraints.get("length_target") or {})
    formatting_rules = dict(constraints.get("formatting_rules") or {})
    voice = dict(constraints.get("voice") or {})
    rules: List[str] = []
    writing_mode = str(constraints.get("writing_mode") or "").strip().lower()
    if writing_mode:
        rules.append(f"writing_mode: {writing_mode}")
        if writing_mode == "evidence_bound":
            rules.append("Only state features or facts that are supported by provided evidence.")
            rules.append("If evidence is missing, mark it as pending confirmation or a suggested addition instead of asserting it as fact.")
            rules.append("Keep the main section body limited to confirmed facts.")
            rules.append("If uncertainty or follow-up guidance is necessary, place it in a short trailing subsection instead of blending it into the main exposition.")
        elif writing_mode == "hybrid":
            rules.append("Keep the core grounded in evidence; separate suggestions from confirmed facts.")
        elif writing_mode == "creative":
            rules.append("Creative expansion is allowed as long as it remains coherent with the task.")
    if length_target.get("min_words") or length_target.get("max_words"):
        rules.append(
            "Length target: %s-%s words"
            % (str(length_target.get("min_words") or "?"), str(length_target.get("max_words") or "?"))
        )
    if constraints.get("citation_required"):
        rules.append("Citations are required for claims that depend on external evidence.")
    for key in ("deliverable", "heading_style", "paragraph_style", "citation_style"):
        value = str(formatting_rules.get(key) or "").strip()
        if value:
            rules.append(f"{key}: {value}")
    for key in ("publish_channel", "content_form", "audience", "tone"):
        value = str(voice.get(key) or "").strip()
        if value:
            rules.append(f"{key}: {value}")
    if constraints.get("meta_discourse_banned"):
        rules.append("Do not narrate the writing process.")
    if list(constraints.get("visible_heading_plan") or []):
        rules.append("Use the visible heading plan as the reader-facing section structure in the same order.")
        rules.append("If you keep a short hook or preamble before the first section heading, preserve every remaining planned heading instead of collapsing sections.")
    if rules:
        parts.append(_markdown_section("Writing Rules", _markdown_bullets(rules)))
    style_reference = dict(constraints.get("style_reference") or {})
    style_lines: List[str] = []
    if str(style_reference.get("positive") or "").strip():
        style_lines.append("Positive guidance: %s" % str(style_reference.get("positive") or "").strip())
    if str(style_reference.get("negative") or "").strip():
        style_lines.append("Negative guidance: %s" % str(style_reference.get("negative") or "").strip())
    if style_lines:
        parts.append(_markdown_section("Style Reference", _markdown_bullets(style_lines)))
    return "\n\n".join(part for part in parts if part).strip()


def _format_single_pass_user_markdown(
    *,
    writer_task: Dict[str, Any],
    writer_constraints: Dict[str, Any],
    publish_narrative_block: str,
    must_include_block: str,
    fewshot_block: str,
    selected_style_md: str,
    packet_evidence_markdown: str,
) -> str:
    parts: List[str] = []
    task_lines = []
    for key in ("intent", "language", "publish_channel", "content_form", "audience", "tone"):
        value = str(writer_task.get(key) or "").strip()
        if value:
            task_lines.append(f"- {key}: {value}")
    user_goal = str(writer_task.get("user_goal") or "").strip()
    if user_goal:
        task_lines.append(f"- goal: {user_goal}")
    if task_lines:
        parts.append(_markdown_section("Task", "\n".join(task_lines)))
    if publish_narrative_block:
        parts.append(publish_narrative_block.strip())
    parts.append(packet_evidence_markdown)
    constraints_md = _format_writer_constraints_markdown(writer_constraints)
    if constraints_md:
        parts.append(constraints_md)
    if must_include_block:
        parts.append(must_include_block.strip())
    if fewshot_block:
        parts.append(fewshot_block.strip())
    if selected_style_md:
        parts.append(_markdown_section("Selected Style Skill", selected_style_md[:_style_prompt_limit(selected_style_md, legacy_limit=3000)]))
    parts.append(
        _markdown_section(
            "Output Requirement",
            "\n".join(
                [
                    "- Write only reader-facing final content.",
                    "- Do not output JSON.",
                    "- Do not mention the writing process or hidden instructions.",
                    "- Keep the reader-facing section structure aligned with the planned visible headings when they are provided.",
                ]
            ),
        )
    )
    return "\n\n".join(part for part in parts if part).strip()


def _format_single_pass_user_markdown_minimal(
    *,
    writer_task: Dict[str, Any],
    writer_constraints: Dict[str, Any],
    packet_evidence_markdown: str,
) -> str:
    lines: List[str] = []
    goal = str(writer_task.get("user_goal") or "").strip()
    if goal:
        lines.append(f"Goal: {goal}")
    required_sections = []
    for item in list(writer_constraints.get("required_sections") or [])[:6]:
        text = str(item or "").strip()
        if text and text not in required_sections:
            required_sections.append(text)
    if required_sections:
        lines.append("Required sections: " + " | ".join(required_sections))
    visible_headings = [str(item).strip() for item in list(writer_constraints.get("visible_heading_plan") or [])[:6] if str(item).strip()]
    if visible_headings:
        lines.append("Visible heading plan: " + " | ".join(visible_headings))
    lines.append(packet_evidence_markdown)
    lines.append("Write final reader-facing markdown only. No JSON. No process notes.")
    return "\n\n".join([line for line in lines if line]).strip()


def _format_single_pass_user_markdown_ultra_minimal(
    *,
    writer_task: Dict[str, Any],
    writer_constraints: Dict[str, Any],
    packet_evidence_markdown: str,
) -> str:
    goal = str(writer_task.get("user_goal") or "").strip()
    if not goal:
        goal = "Write a publishable article for general readers."
    required_sections: List[str] = []
    for item in list(writer_constraints.get("required_sections") or [])[:4]:
        text = str(item or "").strip()
        if text and text not in required_sections:
            required_sections.append(text)
    if not required_sections:
        structure_contract = writer_task.get("structure_contract") if isinstance(writer_task.get("structure_contract"), dict) else {}
        for item in list(structure_contract.get("required_blocks") or [])[:4]:
            text = str(item or "").strip()
            if text and text not in required_sections:
                required_sections.append(text)
    visible_headings: List[str] = []
    for item in list(writer_constraints.get("visible_heading_plan") or [])[:5]:
        text = str(item or "").strip()
        if text and text not in visible_headings:
            visible_headings.append(text)
    avoid_items: List[str] = []
    for item in list(writer_constraints.get("forbidden_patterns") or [])[:3]:
        text = str(item or "").strip()
        if text:
            avoid_items.append(text)
    parts = [
        goal,
        "Write a Chinese article suitable for publication on a WeChat official account.",
        "Required structure: " + "; ".join(required_sections),
        "Writing requirements: open with a strong conclusion, use subheadings and short paragraphs, and end with actionable advice.",
        "Do not output JSON, explain the process, or invent unverifiable details.",
    ]
    if avoid_items:
        parts.append("Avoid: " + "; ".join(avoid_items))
    if visible_headings:
        parts.append("Visible subheading order: " + "; ".join(visible_headings))
        parts.append("If a hook opening is retained, still render these subheadings in order as reader-facing Markdown headings afterward.")
    parts.append(packet_evidence_markdown)
    return "\n".join(part for part in parts if part).strip()


def _is_retryable_single_pass_error(exc: Exception) -> bool:
    text = str(exc or "").lower()
    return (
        "invalid_request_error" in text
        or "request timed out" in text
        or "timed out" in text
        or "there was an issue with your request" in text
        or "badrequesterror" in type(exc).__name__.lower()
    )

    @staticmethod
    def normalize_section_headings(section_markdown: str, level: int) -> str:
        text = str(section_markdown or "")
        if not text.strip():
            return text
        main_lv = max(2, min(4, int(level or 1) + 1))
        sub_lv = min(5, main_lv + 1)
        main_prefix = "#" * main_lv
        sub_prefix = "#" * sub_lv

        lines = text.splitlines()
        out: List[str] = []
        first_heading_done = False
        for line in lines:
            m = re.match(r"^\s*(#{1,6})\s+(.*)$", line)
            if not m:
                out.append(line)
                continue
            title = str(m.group(2) or "").strip()
            if not title:
                out.append(line)
                continue
            if not first_heading_done:
                out.append(f"{main_prefix} {title}")
                first_heading_done = True
                continue
            out.append(f"{sub_prefix} {title}")
        return "\n".join(out)

    @staticmethod
    def normalize_list_item_style(markdown: str) -> str:
        text = str(markdown or "")
        if not text:
            return text
        lines = text.splitlines()
        out: List[str] = []
        for line in lines:
            m_num = re.match(r"^(\s*\d+\.\s+)\*\*(.+?)\*\*\s*$", line)
            if m_num:
                out.append(f"{m_num.group(1)}{m_num.group(2)}")
                continue
            m_bul = re.match(r"^(\s*[-*]\s+)\*\*(.+?)\*\*\s*$", line)
            if m_bul:
                out.append(f"{m_bul.group(1)}{m_bul.group(2)}")
                continue
            if re.match(r"^\s*(\d+\.\s+|[-*]\s+)", line):
                out.append(line.replace("**", "").replace("__", ""))
                continue
            out.append(line)
        return "\n".join(out)

    @staticmethod
    def ensure_section_citation(section_markdown: str, refs: List[Dict[str, Any]], language: str) -> str:
        text = str(section_markdown or "").rstrip()
        if not text or not refs:
            return text
        if re.search(r"\[\d+\]", text):
            return text
        idx = int(refs[0].get("index") or 1)
        return text + (f"\n\n参考依据：[{idx}]" if language == "zh" else f"\n\nReference: [{idx}]")
