"""Localize script validation diagnostics without changing validation rules."""

from __future__ import annotations

import re
from typing import Any


_ENGLISH = {
    "CODE_TOO_LARGE": "Script code must not exceed 200 KB.",
    "MISSING_RUN": "Define the entry point def run(inputs, context):.",
    "ASYNC_RUN": "The run entry point must be a regular function, not async def.",
    "RUN_SIGNATURE": "The first two run arguments must be inputs and context.",
    "MISSING_RETURN": "The run function must return a dict, usually containing artifacts and logs.",
    "TOP_LEVEL_EXECUTION": "Do not execute business logic at module level; put it in run(inputs, context) or a helper function.",
    "WRITE_PATH_REVIEW": "The write path should come from context['output_dir']. Confirm it does not point to an input directory or fixed absolute path.",
    "OUTPUT_PATH_REVIEW": "Use os.path.join(context['output_dir'], filename) for the output file path.",
    "ABSOLUTE_PATH_LITERAL": "The script contains a fixed absolute path, which is usually inaccessible when the plugin runs.",
    "OUTPUT_DIR_NOT_REFERENCED": "No clear reference to context['output_dir'] was found. Files must be written there.",
    "OUTPUT_FILES_NOT_REFERENCED": "No clear files/artifacts return value was found. A later export node might not receive files.",
}

_DYNAMIC = {
    "SYNTAX_ERROR": (r"Python 语法错误：(.*)", "Python syntax error: {}"),
    "DENIED_IMPORT": (r"不允许导入模块：(.*)。", "Importing module {} is not allowed."),
    "DENIED_CALL": (r"不允许调用(?:危险系统函数|危险函数)：(.*)。", "Calling dangerous function {} is not allowed."),
    "POSSIBLE_HARDCODED_CASE": (r"生成代码包含处理要求之外的疑似业务硬编码：(.*)。", "Generated code may contain business values outside the processing request: {}."),
}


def localize_script_check(result: dict[str, Any], accept_language: str | None) -> dict[str, Any]:
    language = (accept_language or "zh").split(",", 1)[0].split(";", 1)[0].strip().lower()
    if not language.startswith("en"):
        return result
    localized = dict(result)
    for field in ("errors", "warnings"):
        issues = []
        for issue in result.get(field) or []:
            item = dict(issue)
            code = str(item.get("code") or "")
            message = str(item.get("message") or "")
            translation = _ENGLISH.get(code)
            if code == "DENIED_IMPORT" and message.startswith("不允许 from "):
                match = re.fullmatch(r"不允许 from (.*) import \.\.\.。", message)
                translation = f"Importing from {match.group(1)} is not allowed." if match else None
            elif code in _DYNAMIC:
                pattern, template = _DYNAMIC[code]
                match = re.fullmatch(pattern, message)
                translation = template.format(match.group(1)) if match else None
            if translation is None and any("\u3400" <= char <= "\u9fff" for char in message):
                translation = "Script validation issue"
            item["message"] = translation or message
            issues.append(item)
        localized[field] = issues
    return localized
