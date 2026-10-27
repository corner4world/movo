from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header

from app.api.deps import get_current_admin_user
from app.shortcut_settings.models import ShortcutPlanPayload
from app.shortcut_settings.service import ShortcutSettingsService
from app.shortcut_settings.locale import english_requested, translate_plan


router = APIRouter()
service = ShortcutSettingsService()


def _main_id(user: dict[str, Any]) -> str:
    return str(user.get("main_id") or "default")


@router.get("")
async def get_shortcut_settings(current_user: dict = Depends(get_current_admin_user), accept_language: str | None = Header(default=None)):
    plan = await service.get_default_plan(_main_id(current_user))
    return translate_plan(plan, english=english_requested(accept_language))


@router.put("")
async def save_shortcut_settings(payload: ShortcutPlanPayload, current_user: dict = Depends(get_current_admin_user), accept_language: str | None = Header(default=None)):
    canonical = ShortcutPlanPayload.model_validate(translate_plan(payload.model_dump(), english=False))
    saved = await service.save_default_plan(
        _main_id(current_user),
        str(current_user.get("_id") or current_user.get("id") or ""),
        canonical,
    )
    return translate_plan(saved, english=english_requested(accept_language))
