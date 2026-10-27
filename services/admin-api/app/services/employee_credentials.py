from __future__ import annotations

from typing import Any

from app.services.employee_credential_messages import (
    EXTERNAL_IDENTITY_PASSWORD,
    INITIAL_PASSWORD_REQUIRED,
    LOGIN_NAME_REQUIRED,
    PASSWORD_TOO_SHORT,
)


MIN_PASSWORD_LENGTH = 10


def normalize_employee_credentials(
    *,
    source: str,
    login_name: str,
    password: str,
    creating: bool,
    has_existing_password: bool = False,
) -> tuple[str, str]:
    """Validate local credentials and remove them for externally managed users."""
    normalized_login = login_name.strip()

    if source != "local":
        if password:
            raise ValueError(EXTERNAL_IDENTITY_PASSWORD)
        return "", ""

    if not normalized_login:
        raise ValueError(LOGIN_NAME_REQUIRED)

    password_is_required = creating or not has_existing_password
    if password_is_required and not password:
        raise ValueError(INITIAL_PASSWORD_REQUIRED)
    if password and len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(PASSWORD_TOO_SHORT)

    return normalized_login, password


def redact_credential_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Prevent plaintext passwords from entering audit logs."""
    result = dict(payload)
    for key in ("initialPassword", "resetPassword", "password"):
        if key in result:
            result[key] = "***" if result[key] else ""
    return result
