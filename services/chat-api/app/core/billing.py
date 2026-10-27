from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict

from app.core.db import get_db
from app.core.product_edition import member_limit

logger = logging.getLogger(__name__)

ORGANIZATION_COLLECTION = "organizations"
USER_COLLECTION = "end_users"


class ModelConfigError(ValueError):
    pass


def _now() -> datetime:
    return datetime.utcnow()


async def get_or_create_organization(main_id: str, default_org_name: str = "个人空间", owner_id: str = "") -> Dict[str, Any]:
    """
    Get the organization, creating one with defaults when absent.
    """
    db = get_db()
    org = await db[ORGANIZATION_COLLECTION].find_one({"main_id": main_id})
    if not org:
        from app.product.extensions import get_product_extension

        defaults = dict(get_product_extension().organization_defaults)
        org = {
            "main_id": main_id,
            "org_name": default_org_name,
            "owner_user_id": str(owner_id),
            **defaults,
            "created_at": _now(),
            "updated_at": _now(),
        }
        await db[ORGANIZATION_COLLECTION].insert_one(org)
    return org


async def check_quota_before_request(main_id: str, config: Dict[str, Any]) -> None:
    """
    Check available organization quota before an LLM request.
    Enforce point balance only for the platform's shared default model.
    Own-model organizations and user-owned models are exempt.
    """
    if not main_id or main_id == "default":
        return

    # Apply platform quota only to the default shared model.
    is_shared_model = str(config.get("main_id") or "default").strip() == "default"

    org = await get_or_create_organization(main_id)

    # Enforce point balance for shared models without own-model privileges.
    if is_shared_model and not org.get("is_own_model", False):
        used = org.get("used_points", 0)
        total = org.get("total_points", 1000000)
        if used >= total:
            raise ModelConfigError(
                f"您的组织/空间额度已耗尽 (当前已使用: {used}/{total} Tokens)。"
                "企业空间请进入管理后台配置自己的模型密钥，或联系管理员进行额度充值。"
            )


async def deduct_points_after_request(main_id: str, total_tokens: int) -> None:
    """
    Record token consumption asynchronously after a request.
    Bill free organizations or those without own-model access.
    """
    if not main_id or main_id == "default" or total_tokens <= 0:
        return

    db = get_db()
    org = await get_or_create_organization(main_id)

    # Count point usage only for the default model or when own models are disabled.
    if org.get("tier") == "free" or not org.get("is_own_model", False):
        await db[ORGANIZATION_COLLECTION].update_one(
            {"main_id": main_id},
            {
                "$inc": {"used_points": total_tokens},
                "$set": {"updated_at": _now()}
            }
        )
        logger.info(
            "organization token points deducted",
            extra={"main_id": main_id, "tokens_deducted": total_tokens}
        )


async def check_member_limit(main_id: str) -> None:
    """
    Check the organization's member limit before adding a member.
    """
    db = get_db()
    org = await get_or_create_organization(main_id)
    limit = member_limit(org)

    if limit is None:
        return

    # Count end_users belonging to this main_id.
    from app.api.endpoints.auth import USER_COLLECTION
    current_count = await db[USER_COLLECTION].count_documents({"main_id": main_id})

    if current_count >= limit:
        tier_label = "个人免费版"
        if org.get("tier") == "plus":
            tier_label = "个人 Plus 版"
        elif org.get("tier") == "pro":
            tier_label = "专业团队版"
        raise ValueError(
            f"当前组织属于 {tier_label}，最大成员数限制为 {limit} 人。已达上限，无法添加新成员。"
        )
