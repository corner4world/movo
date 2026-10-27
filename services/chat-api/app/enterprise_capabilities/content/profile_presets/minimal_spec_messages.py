"""Language specific defaults for generated content profiles."""

from __future__ import annotations


def defaults(language: str, *, content_form: str, audience: str) -> dict[str, object]:
    if str(language or "").lower().startswith("en"):
        return {
            "required_block": "Core content",
            "audience": "General readers",
            "identity": f"A {content_form or 'article'} writer for {audience}, focused on clarity, accuracy, and actionable guidance.",
            "positive_style": "Answer the question first, then develop the response in a clear structure and offer actionable advice.",
            "negative_style": "Avoid vague conclusions, jargon overload, and unsupported claims.",
            "must_include": ("Explanation of key concepts", "Actionable recommendations"),
        }
    return {
        "required_block": "核心内容",
        "audience": "通用读者",
        "identity": f"面向{audience}的{content_form or 'article'}写作者，强调清晰、准确、可执行。",
        "positive_style": "先回答问题，再结构化展开，并给出可执行建议。",
        "negative_style": "避免空泛结论、术语堆砌和无依据判断。",
        "must_include": ("关键概念解释", "可执行建议"),
    }
