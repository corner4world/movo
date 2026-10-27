"""Evidence projection for ordered knowledge document reads."""

from __future__ import annotations

from typing import Any

from app.enterprise_capabilities.evidence.foundation import EvidenceNormalizer


def build_knowledge_document_evidence(result: dict[str, Any], *, language: str = "zh") -> dict[str, Any]:
    english = str(language or "").lower().startswith("en")
    fallback_title = "Knowledge document" if english else "知识文档"
    source_name = "Internal knowledge document" if english else "内部知识文档"
    results = []
    for segment in list(result.get("segments") or []):
        if not isinstance(segment, dict) or not str(segment.get("text") or "").strip():
            continue
        results.append({
            "tool": "knowledge_read_document",
            "title": str(result.get("document_name") or result.get("document_id") or fallback_title),
            "source": source_name,
            "content": str(segment["text"]),
            "summary": str(segment["text"])[:1200],
            "meta": {
                "document_id": str(result.get("document_id") or ""),
                "source_id": str(result.get("source_id") or ""),
                "checksum": str(result.get("checksum") or ""),
                "chunk_id": str(segment.get("chunk_id") or ""),
                "ordinal": segment.get("ordinal"),
                "char_offset": segment.get("char_offset"),
                "page_no": segment.get("page_no"),
                "title_path": list(segment.get("title_path") or []),
                "provenance": "authorized_knowledge_document_read",
            },
        })
    if not results:
        return {}
    bundle = EvidenceNormalizer.build_research_bundle(
        query=(
            f"Read knowledge document {result.get('document_name') or result.get('document_id')}"
            if english else f"读取知识文档 {result.get('document_name') or result.get('document_id')}"
        ),
        tools_used=["knowledge_read_document"],
        results=results,
        raw_tool_results=[{
            "tool": "knowledge_read_document",
            "result": {
                "document_id": result.get("document_id"),
                "source_id": result.get("source_id"),
                "has_more": result.get("has_more"),
            },
        }],
    )
    bundle["language"] = language
    return bundle
