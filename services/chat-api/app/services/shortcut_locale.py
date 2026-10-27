"""Localize built-in shortcut labels while preserving custom labels and storage."""

from __future__ import annotations

from typing import Any


_GROUPS = {
    "content": ("内容生成", "Content Creation"),
    "external": ("外部搜索", "Web Search"),
    "internal": ("内部知识", "Internal Knowledge"),
    "systems": ("连接系统", "Connected Systems"),
    "personal": ("我的常用", "My Favorites"),
}

_ENTRIES = {
    "content.wechat": ("微信/小红书", "WeChat / Xiaohongshu"),
    "content.report": ("报告方案", "Report Plan"),
    "content.ppt": ("PPT生成", "Presentation"),
    "content.image_prd": ("图片转PRD", "Image to PRD"),
    "content.translate": ("文档翻译", "Document Translation"),
    "content.fill_form": ("文档填表", "Fill Spreadsheet"),
    "external.web": ("联网查资料", "Search the Web"),
    "external.industry": ("行业研究", "Industry Research"),
    "external.competitor": ("竞品分析", "Competitor Analysis"),
    "external.policy_news": ("政策/新闻", "Policies / News"),
    "external.overview": ("资料综述", "Research Overview"),
    "external.fact_check": ("事实核查", "Fact Check"),
    "internal.search": ("搜知识库", "Search Knowledge Base"),
    "internal.history": ("查历史文档", "Find Past Documents"),
    "internal.policy": ("查企业制度", "Find Company Policies"),
    "internal.project": ("查项目资料", "Find Project Materials"),
    "internal.customer": ("查客户资料", "Find Customer Information"),
    "internal.training": ("查培训材料", "Find Training Materials"),
    "systems.sales": ("查销售", "Check Sales"),
    "systems.root_cause": ("找根因", "Find Root Causes"),
    "systems.inventory": ("查库存", "Check Inventory"),
    "systems.customer": ("查客户", "Check Customers"),
    "systems.daily": ("经营日报", "Daily Operations Report"),
    "systems.mcp": ("调用MCP", "Use MCP"),
}

_PLAN_NAME = ("企业默认方案", "Organization Default Plan")


def _translated(value: Any, pair: tuple[str, str] | None, english: bool) -> Any:
    if pair and value in pair:
        return pair[1] if english else pair[0]
    return value


def translate_plan(plan: dict[str, Any], *, english: bool) -> dict[str, Any]:
    result = dict(plan)
    if "name" in plan:
        result["name"] = _translated(plan.get("name"), _PLAN_NAME, english)
    result["entries"] = [
        {
            **entry,
            "label": _translated(entry.get("label"), _ENTRIES.get(str(entry.get("id") or "")), english),
            "categoryLabel": _translated(entry.get("categoryLabel"), _GROUPS.get(str(entry.get("categoryKey") or "")), english),
        }
        for entry in plan.get("entries") or []
    ]
    result["groups"] = [
        {**group, "label": _translated(group.get("label"), _GROUPS.get(str(group.get("key") or "")), english)}
        for group in plan.get("groups") or []
    ]
    return result


def english_requested(accept_language: str | None) -> bool:
    return (accept_language or "zh").split(",", 1)[0].split(";", 1)[0].strip().lower().startswith("en")


def translate_preferences(preferences: dict[str, Any], *, english: bool) -> dict[str, Any]:
    result = dict(preferences)
    group = preferences.get("personalGroup")
    if isinstance(group, dict):
        result["personalGroup"] = {**group, "label": _translated(group.get("label"), _GROUPS["personal"], english)}
    result["personalEntries"] = [
        {
            **entry,
            "categoryLabel": _translated(entry.get("categoryLabel"), _GROUPS["personal"], english),
        }
        for entry in preferences.get("personalEntries") or []
    ]
    return result
