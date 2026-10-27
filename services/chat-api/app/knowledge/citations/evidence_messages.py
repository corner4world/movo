"""Localized labels for knowledge citation bundles."""

from __future__ import annotations


def evidence_summary(count: int, language: str = "zh") -> str:
    if str(language or "").lower().startswith("en"):
        return f"Internal knowledge Q&A retrieved {count} cited sources"
    return f"内部知识问答检索到 {count} 条引用来源"


def evidence_question(query: str, language: str = "zh") -> str:
    return f"Question: {query}" if str(language or "").lower().startswith("en") else f"问题：{query}"


def default_knowledge_label(language: str = "zh") -> str:
    return "Internal knowledge" if str(language or "").lower().startswith("en") else "内部知识"


def localized_knowledge_label(label: str, scope: str, language: str = "zh") -> str:
    source = str(label or "").strip()
    if not str(language or "").lower().startswith("en"):
        return source or default_knowledge_label(language)
    known = {
        "个人知识": "Personal knowledge",
        "企业知识": "Organization knowledge",
        "内部知识": "Internal knowledge",
    }
    if source in known:
        return known[source]
    if not source:
        return {
            "personal": "Personal knowledge",
            "organization": "Organization knowledge",
        }.get(str(scope or "").lower(), default_knowledge_label(language))
    return source
