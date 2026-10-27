"""Map an external tool response to user-visible knowledge evidence."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from .external_messages import external_answer_message, external_failure_message, external_message, external_summary_message


def value_at(value: Any, path: str) -> Any:
    if not path:
        return None
    current = value
    for segment in path.split("."):
        if isinstance(current, dict):
            current = current.get(segment)
        elif isinstance(current, list) and segment.isdigit() and int(segment) < len(current):
            current = current[int(segment)]
        else:
            return None
    return current


def response_body(outcome: dict[str, Any]) -> Any:
    raw = outcome.get("raw")
    if isinstance(raw, dict) and isinstance(raw.get("structuredContent"), dict):
        return {**raw, "response": raw["structuredContent"]}
    if isinstance(raw, dict) and isinstance(raw.get("content"), list):
        for block in raw["content"]:
            if isinstance(block, dict) and block.get("type") == "text":
                try:
                    return {**raw, "response": json.loads(str(block.get("text") or ""))}
                except (ValueError, TypeError):
                    continue
    return raw


def safe_url(value: Any) -> str:
    candidate = str(value or "").strip()
    parsed = urlparse(candidate)
    return candidate[:2048] if parsed.scheme in {"http", "https"} and parsed.netloc else ""


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def map_response(outcome: dict[str, Any], config: dict[str, Any], *, language: str = "zh") -> dict[str, Any]:
    if not outcome.get("success"):
        raise ValueError(external_failure_message(outcome.get("message"), language))
    mapping = dict(config.get("mapping") or {})
    body = response_body(outcome)
    answer = value_at(body, str(mapping.get("answerPath") or ""))
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError(external_message("answer_missing", language))
    label = _text(config.get("displayName") or external_message("default_label", language), 120)
    rows = value_at(body, str(mapping.get("sourcesPath") or ""))
    rows = rows if isinstance(rows, list) else []
    sources: list[dict[str, Any]] = []
    for index, row in enumerate(rows[:20]):
        if not isinstance(row, dict):
            continue
        title = _text(value_at(row, str(mapping.get("titlePath") or "")), 300)
        document_url = safe_url(value_at(row, str(mapping.get("documentUrlPath") or "")))
        snippet = _text(value_at(row, str(mapping.get("snippetPath") or "")), 1500)
        if not (title or document_url or snippet):
            continue
        sources.append({
            "id": f"external-{index + 1}",
            "title": title or label,
            "source_name": label,
            "source_type": "external_knowledge",
            "source_url": document_url,
            "snippet": snippet,
            "content": snippet,
        })
    if not sources:
        sources.append({
            "id": "external-source", "title": label, "source_name": label,
            "source_type": "external_knowledge", "snippet": "", "content": "",
        })
    return {
        "success": True,
        "ok": True,
        "provider": "external_knowledge_qa",
        "answer": answer.strip(),
        "message": external_answer_message(label, language),
        "retrieval_status": "completed",
        "retrieval_mode": "qa",
        "total": len(sources),
        "evidence_available": True,
        "evidence_bundle": {
            "summary": external_summary_message(label, language),
            "sources": sources,
            "confirmed_facts": [],
            "open_questions": [],
        },
    }
