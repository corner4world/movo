"""Localized display copy for dashboard action items."""

from __future__ import annotations

from typing import Any


_ENGLISH = {
    "/models": {
        "尚未配置模型": ("No models configured", "Add a model so users can reliably call the LLM."),
        "存在模型健康异常": ("Model health issues", "{count} models failed their most recent test."),
    },
    "/tools": {
        "工具测试失败": ("Tool tests failed", "{count} tool connections need attention."),
        "工具未完成测试": ("Tools not tested", "{count} tool connections have not been tested."),
    },
    "/skills": {
        "Skill 均未启用": ("No Skills enabled", "Enable at least one Skill for users."),
    },
    "/token-stats": {
        "近 24 小时有失败调用": ("Failed calls in the last 24 hours", "{count} calls failed; review Token statistics."),
    },
}


def localize_dashboard_todos(
    todos: list[dict[str, str]], metrics: dict[str, Any], assets: dict[str, Any], accept_language: str | None,
) -> list[dict[str, str]]:
    language = (accept_language or "zh").split(",", 1)[0].split(";", 1)[0].strip().lower()
    if not language.startswith("en"):
        return todos
    counts = {
        "存在模型健康异常": assets["models"]["failedHealth"],
        "工具测试失败": assets["tools"]["failed"],
        "工具未完成测试": assets["tools"]["untested"],
        "近 24 小时有失败调用": metrics["failedCalls24h"],
    }
    localized = []
    for item in todos:
        title = item["title"]
        copy = _ENGLISH.get(item["route"], {}).get(title)
        if copy:
            localized.append({**item, "title": copy[0], "description": copy[1].format(count=counts.get(title, 0))})
        else:
            localized.append(dict(item))
    return localized
