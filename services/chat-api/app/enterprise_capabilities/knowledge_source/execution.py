from __future__ import annotations

from typing import Any

from app.product.resource_access import resource_is_allowed
from app.services.external_tools import external_tool_service

from .mapping import map_response
from .external_messages import external_message


async def search_external_knowledge(
    *, query: str, main_id: str, user_id: str, config: dict[str, Any], language: str = "zh",
) -> dict[str, Any]:
    tool_id = str(config.get("toolId") or "")
    tool = await external_tool_service.get(tool_id, main_id, scope="organization")
    if not tool or tool.get("status") != "active":
        raise ValueError(external_message("tool_unavailable", language))
    if not await resource_is_allowed("tool", main_id=main_id, user_id=user_id, resource_id=tool_id):
        raise PermissionError(external_message("access_denied", language))
    tool_type = str(tool.get("type") or "")
    mcp_name = str(config.get("mcpToolName") or "")
    if tool_type == "mcp" and mcp_name not in set((tool.get("config") or {}).get("enabledToolNames") or []):
        raise ValueError(external_message("mcp_disabled", language))
    outcome = await external_tool_service.execute_runtime(
        main_id=main_id,
        external_tool_id=tool_id,
        provider_type=tool_type,
        mcp_tool_name=mcp_name,
        arguments={str(config.get("queryArgument") or "query"): query},
        actor_user_id=user_id,
        language=language,
    )
    return map_response(outcome, config, language=language)
