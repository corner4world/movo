"""Localized fallback content when the workflow backend cannot be reached."""

from __future__ import annotations

from app.api.error_locale import localize_detail


def workflow_proxy_error(detail: object, fallback: str, accept_language: str | None) -> str:
    text = str(detail or fallback)
    return str(localize_detail(text, 502, accept_language))


def workflow_check_fallback(detail: object, *, nodes: bool, accept_language: str | None) -> dict[str, object]:
    message = workflow_proxy_error(detail, "检查服务不可用", accept_language)
    return {
        "pass": False,
        "logic": {"label": workflow_proxy_error(None, "检查失败", accept_language), "level": "warning", "summary": message},
        "coverage": [],
        "readiness": [],
        "suggestions": [workflow_proxy_error(None, "后端检查服务暂不可用，请稍后重试。", accept_language)],
        "conclusion": workflow_proxy_error(None, "本次未完成后端语义节点检查。" if nodes else "本次未完成后端语义检查。", accept_language),
        "source": "error",
        "message": message,
    }
