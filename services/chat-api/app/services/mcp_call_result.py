from __future__ import annotations

import json
from typing import Any, Dict

from app.services.mcp_outcome_messages import mcp_outcome_message, safe_mcp_error_message


def build_mcp_call_outcome(tool_name: str, result: Dict[str, Any], *, language: str = "zh") -> Dict[str, Any]:
    """Translate an MCP CallToolResult into MOVO's shared execution contract."""
    failed = result.get("isError") is True
    summary = _result_summary(result)
    if failed:
        message = safe_mcp_error_message(_error_message(result), tool_name, language)
        return {
            "success": False,
            "status": "failed",
            "errorCode": "mcp_tool_error",
            "message": message,
            "responseSummary": summary or message,
            "raw": result,
        }
    return {
        "success": True,
        "status": "passed",
        "message": mcp_outcome_message(tool_name, failed=False, language=language),
        "responseSummary": summary,
        "raw": result,
    }


def _result_summary(result: Dict[str, Any], limit: int = 4000) -> str:
    text_parts: list[str] = []
    content = result.get("content")
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "text":
                continue
            text = str(block.get("text") or "").strip()
            if text:
                text_parts.append(text)
    if text_parts:
        summary = "\n".join(text_parts)
    else:
        summary = json.dumps(result, ensure_ascii=False, default=str)
    return summary if len(summary) <= limit else summary[:limit] + "...[truncated]"


def _error_message(result: Dict[str, Any]) -> str:
    content = result.get("content")
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "text":
                continue
            text = str(block.get("text") or "").strip()
            if text:
                return text
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        for key in ("message", "error", "detail"):
            text = str(structured.get(key) or "").strip()
            if text:
                return text
    return ""
