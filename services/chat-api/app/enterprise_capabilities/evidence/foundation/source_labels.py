"""Fallback labels for evidence sources with no user-provided title."""

from __future__ import annotations


_LABELS = {
    "web": ("网页资料", "Web source"),
    "external_knowledge": ("外部知识库", "External knowledge base"),
    "source": ("资料来源", "Source"),
    "internal_knowledge": ("内部知识库", "Internal knowledge base"),
    "document_fragment": ("文档片段", "Document excerpt"),
}


def evidence_source_label(key: str, language: str) -> str:
    zh, en = _LABELS[key]
    return en if str(language or "").lower().startswith("en") else zh
