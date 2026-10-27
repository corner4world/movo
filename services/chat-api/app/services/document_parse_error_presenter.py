from __future__ import annotations

import re
from typing import Any


def user_facing_parse_error(
    *,
    parse_error: Any,
    filename: str = "",
    has_object_path: bool = False,
    has_signed_url: bool = False,
    language: str = "zh",
) -> str:
    """Return a user-safe document parse failure reason.

    Raw parser errors often describe internal transport details, such as a
    signed URL returning HTTP 404 after a fallback attempt. Those details are
    useful in logs but misleading as user guidance because the uploaded file may
    still be valid while the parser service or fallback source failed.
    """
    error = re.sub(r"\s+", " ", str(parse_error or "")).strip()
    english = str(language or "").lower().startswith("en")
    if not error:
        if english:
            return "Document parsing failed without a clear error. Try again later or upload the file again."
        return "文件解析失败，未返回明确错误原因。请稍后重试或重新上传文件。"

    lowered = error.lower()
    if "404" in lowered or "not found" in lowered or "no such key" in lowered:
        if has_object_path or has_signed_url:
            if english:
                return "The file was received, but the parser could not read its contents. Try again later; if it still fails, upload the file again."
            return "文件已收到，但解析服务读取文件内容失败。请稍后重试；如果仍失败，请重新上传文件。"
        if english:
            return "The parser could not read the file contents. Upload the file again and retry."
        return "文件解析服务未能读取到文件内容。请重新上传文件后再试。"

    if any(token in lowered for token in ("timeout", "timed out", "connection", "network")):
        if english:
            return "The parser is temporarily unavailable or the network timed out. Try again later."
        return "文件解析服务暂时不可用或网络超时。请稍后重试。"

    if any(token in lowered for token in ("unsupported", "not supported", "format")):
        if english:
            return "This file format is not supported for parsing. Convert it to a supported document format and retry."
        return "当前文件格式暂不支持解析。请转换为支持的文档格式后再试。"

    if any(token in lowered for token in ("permission", "forbidden", "unauthorized", "403", "401")):
        if english:
            return "The parser cannot access this file right now. Upload it again or retry later."
        return "文件解析服务暂时没有权限读取该文件。请重新上传文件或稍后重试。"

    if english:
        prefix = f"File “{filename}”" if filename else "The file"
        return f"{prefix} could not be parsed. Try again later or upload it again."
    prefix = f"文件《{filename}》" if filename else "文件"
    return f"{prefix}解析失败。请稍后重试或重新上传文件。"
