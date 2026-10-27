"""Translate fixed test and discovery status text at the API boundary."""

from __future__ import annotations

import re
from typing import Any


def localize_tool_status(data: dict[str, Any], accept_language: str | None) -> dict[str, Any]:
    language = (accept_language if isinstance(accept_language, str) else "zh").split(",", 1)[0].split(";", 1)[0].strip().lower()
    if not language.startswith("en"):
        return data
    result = dict(data)
    message = str(result.get("message") or "")
    discovered = re.fullmatch(r"(?:MCP 连接成功，)?发现 (\d+) 个 (?:MCP )?tools(.*)", message)
    timeout = re.fullmatch(r"请求超时：超过 ([\d.]+) 秒未收到响应", message)
    if discovered:
        suffix = discovered.group(2)
        translated = f"Discovered {discovered.group(1)} MCP tools"
        if suffix:
            limit = re.search(r"超过 (\d+) 个.*不超过 (\d+) 个", suffix)
            translated += (
                f"; more than {limit.group(1)} tools were found, so the connection remains disabled. "
                f"Select no more than {limit.group(2)} tools before enabling it"
                if limit else "; the connection remains disabled because the tool limit was exceeded"
            )
        result["message"] = translated
    elif timeout:
        result["message"] = f"Request timed out: no response within {timeout.group(1)} seconds"
    elif any("\u3400" <= char <= "\u9fff" for char in message):
        result["message"] = "Tool test failed" if not result.get("success") else "Tool test completed"
    if result.get("responseSummary") == message and result.get("message") != message:
        result["responseSummary"] = result["message"]
    return result
