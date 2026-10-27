"""Display labels for stored audit records, selected by response language."""

from __future__ import annotations

from typing import Any


_ENGLISH_MODULES = {
    "模型中心": "Model Center",
    "Skill 管理": "Skill Management",
    "工具与 MCP": "Tools and MCP",
    "知识文档": "Knowledge Documents",
    "账号组与账号": "Account Groups and Accounts",
    "组织与用户": "Organizations and Users",
    "用户岗位角色": "User Position Roles",
    "流量分配": "Traffic Allocation",
    "系统设置": "System Settings",
    "账号与登录": "Accounts and Login",
    "系统初始化": "System Setup",
    "管理后台": "Admin Console",
    "Agent 能力": "Agent Capabilities",
    "历史管理操作": "Historical Admin Operation",
}


def localize_audit_page(page: dict[str, Any], accept_language: str | None) -> dict[str, Any]:
    language = (accept_language or "zh").split(",", 1)[0].split(";", 1)[0].strip().lower()
    if not language.startswith("en"):
        return page
    items = []
    for original in page.get("items") or []:
        item = dict(original)
        module = str(item.get("module") or "")
        item["module"] = _ENGLISH_MODULES.get(module, module)
        items.append(item)
    return {**page, "items": items}
