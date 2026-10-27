"""Localized wrapper messages for MCP tool outcomes."""

from __future__ import annotations


def mcp_outcome_message(tool_name: str, *, failed: bool, language: str = "zh") -> str:
    if str(language or "").lower().startswith("en"):
        return f"MCP tool {tool_name} failed" if failed else f"MCP tool {tool_name} succeeded"
    return f"MCP tool {tool_name} 执行失败" if failed else f"MCP tool {tool_name} 调用成功"


def safe_mcp_error_message(message: str, tool_name: str, language: str = "zh") -> str:
    if not message:
        return mcp_outcome_message(tool_name, failed=True, language=language)
    if str(language or "").lower().startswith("en") and any("\u3400" <= char <= "\u9fff" for char in message):
        return mcp_outcome_message(tool_name, failed=True, language=language)
    return message
