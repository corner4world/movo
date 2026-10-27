"""Stable model-facing semantics for internal knowledge retrieval outcomes."""

from __future__ import annotations

from typing import Any

from app.enterprise_capabilities.knowledge_source.result_messages import knowledge_result_message


def available_result(*, query: str, retrieval_mode: str, total: int, items: list[dict[str, Any]], language: str = "zh") -> dict[str, Any]:
    return {
        "success": True,
        "retrieval_status": "completed" if items else "empty",
        "evidence_available": bool(items),
        "query": query,
        "retrieval_mode": retrieval_mode,
        "total": total,
        "items": items,
        "message": knowledge_result_message("completed" if items else "empty", language),
    }


def unavailable_result(*, query: str, error: Exception, language: str = "zh") -> dict[str, Any]:
    return {
        # The tool invocation completed and returned a governed availability
        # observation. This is deliberately not represented as an empty search.
        "success": True,
        "retrieval_status": "service_unavailable",
        "evidence_available": False,
        "query": query,
        "retrieval_mode": "unavailable",
        "total": None,
        "items": [],
        "message": knowledge_result_message("unavailable", language),
        "error": {"code": "knowledge_service_unavailable", "detail": str(error)},
    }
