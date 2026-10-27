"""Localized fixed text for external knowledge source results."""

from __future__ import annotations

_MESSAGES = {
    "call_failed": {"zh": "外部知识库调用失败", "en": "External knowledge base call failed"},
    "answer_missing": {
        "zh": "外部知识库未返回映射的答案字段，请检查知识库配置",
        "en": "The external knowledge base did not return the mapped answer field. Check its configuration.",
    },
    "default_label": {"zh": "外部知识库", "en": "External knowledge base"},
    "tool_unavailable": {
        "zh": "已配置的外部知识库工具不可用，请联系管理员",
        "en": "The configured external knowledge base tool is unavailable. Contact an administrator.",
    },
    "access_denied": {
        "zh": "当前用户无权使用此外部知识库工具",
        "en": "You do not have access to this external knowledge base tool.",
    },
    "mcp_disabled": {
        "zh": "已配置的 MCP 检索工具未启用，请联系管理员",
        "en": "The configured MCP retrieval tool is disabled. Contact an administrator.",
    },
}


def external_message(key: str, language: str = "zh") -> str:
    locale = "en" if str(language or "").lower().startswith("en") else "zh"
    return _MESSAGES[key][locale]


def external_answer_message(label: str, language: str = "zh") -> str:
    if str(language or "").lower().startswith("en"):
        return f"Retrieved an answer from {label}."
    return f"已从{label}获取答案。"


def external_summary_message(label: str, language: str = "zh") -> str:
    if str(language or "").lower().startswith("en"):
        return f"The answer was provided by {label}; document links can be opened only when that knowledge base provides them."
    return f"答案由{label}提供；文档链接仅在该知识库提供时可打开。"


def external_failure_message(message: object, language: str = "zh") -> str:
    raw = str(message or "").strip()[:500]
    if not raw:
        return external_message("call_failed", language)
    if str(language or "").lower().startswith("en") and any("\u3400" <= char <= "\u9fff" for char in raw):
        return external_message("call_failed", language)
    return raw
