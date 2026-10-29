"""Secret-free Tool Profile metadata used by ASKAI's execution Timeline."""

from __future__ import annotations

from typing import Any

from app.dsh_runtime.profile.models import RuntimeProfileSnapshot


def tool_presentations(profile: RuntimeProfileSnapshot) -> dict[str, dict[str, Any]]:
    presentations = {
        tool.name: {
            "display_name": tool.display_name or tool.mcp_tool_name or tool.name,
            "description": tool.description,
            "risk_level": tool.risk_level,
            "delivery_mode": tool.delivery_mode,
        }
        for tool in profile.tools
    }
    owners: dict[str, list[dict[str, str]]] = {}
    for plugin in profile.plugins:
        for name in plugin.get("tool_names") or []:
            if isinstance(name, str) and name:
                owners.setdefault(name, []).append({
                    "name": str(plugin.get("name") or ""),
                    "version": str(plugin.get("version") or ""),
                    "spec": str(plugin.get("spec") or ""),
                })
    for name, plugins in owners.items():
        if len(plugins) == 1 and plugins[0]["name"] and name not in presentations:
            presentations[name] = {
                "display_name": name,
                "plugin_name": plugins[0]["name"],
                "plugin_version": plugins[0]["version"],
                "plugin_spec": plugins[0]["spec"],
            }
    return presentations
