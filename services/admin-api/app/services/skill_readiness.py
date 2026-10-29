"""Expose package environment readiness to the organization Skill UI."""

from __future__ import annotations

import asyncio
from typing import Any

from .skill_package_proxy import organization_skill_dependency_status


DEPENDENCY_FILES = frozenset({"requirements.txt", "package.json", "apt-packages.txt"})


def needs_environment(row: dict[str, Any]) -> bool:
    if (row.get("pending_package") or {}).get("digest"):
        return True
    return bool(row.get("package_digest")) and any(
        isinstance(item, dict) and item.get("path") in DEPENDENCY_FILES
        for item in row.get("package_files") or []
    )


def environment_status(row: dict[str, Any], main_id: str) -> str | None:
    if not needs_environment(row):
        return None
    result = organization_skill_dependency_status(main_id=main_id, skill_id=str(row["_id"]))
    return str(result.get("status") or "unavailable")


async def attach_environment_status(rows: list[dict[str, Any]], main_id: str) -> None:
    semaphore = asyncio.Semaphore(8)

    async def attach(row: dict[str, Any]) -> None:
        if not needs_environment(row):
            return
        async with semaphore:
            try:
                row["environment_status"] = await asyncio.to_thread(environment_status, row, main_id)
            except Exception:
                row["environment_status"] = "unavailable"

    await asyncio.gather(*(attach(row) for row in rows))
