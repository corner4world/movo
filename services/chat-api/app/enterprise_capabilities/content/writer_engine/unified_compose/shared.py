from __future__ import annotations

import json
from typing import Any, Dict


def _truncate_text(value: Any, limit: int = 1400) -> str:
    raw = str(value or "")
    if len(raw) <= limit:
        return raw
    return raw[:limit] + "...<truncated>"


def _exception_debug_payload(exc: Exception) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "exc_type": type(exc).__name__,
        "exc_repr": _truncate_text(repr(exc), 1200),
        "error": _truncate_text(str(exc), 1200),
    }
    status_code = getattr(exc, "status_code", None)
    if status_code is not None:
        payload["status_code"] = status_code
    body = getattr(exc, "body", None)
    if body is not None:
        try:
            payload["body"] = _truncate_text(json.dumps(body, ensure_ascii=False), 2400)
        except Exception:
            payload["body"] = _truncate_text(body, 2400)
    response = getattr(exc, "response", None)
    if response is not None:
        payload["response_type"] = type(response).__name__
        response_text = getattr(response, "text", None)
        if callable(response_text):
            try:
                response_text = response_text()
            except Exception:
                response_text = None
        if response_text:
            payload["response_text"] = _truncate_text(response_text, 2400)
        request_id = getattr(response, "request_id", None) or getattr(response, "headers", {}).get("x-request-id") if getattr(response, "headers", None) else None
        if request_id:
            payload["request_id"] = str(request_id)
    for key in ("code", "param", "type"):
        value = getattr(exc, key, None)
        if value is not None:
            payload[key] = value
    return payload
