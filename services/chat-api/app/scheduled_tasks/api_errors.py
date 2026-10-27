from __future__ import annotations

from fastapi import HTTPException
from app.api.error_locale import localize_detail


def localized_error(status_code: int, detail: str, accept_language: str | None) -> HTTPException:
    translated = localize_detail(detail, status_code, accept_language)
    return HTTPException(status_code=status_code, detail=translated)
