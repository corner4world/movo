"""Require English text for literal Chinese HTTP errors in public APIs."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SERVICES = ("chat-api", "admin-api")


def has_han(value: str) -> bool:
    return any("\u3400" <= char <= "\u9fff" for char in value)


def translations(service: str) -> set[str]:
    source = ROOT / "services" / service / "app" / "api" / "error_locale.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "_ENGLISH_DETAILS" for target in node.targets
        ):
            return set(ast.literal_eval(node.value))
    raise RuntimeError(f"Missing translation catalog: {source}")


def check_service(service: str) -> list[str]:
    catalog = translations(service)
    failures: list[str] = []
    for path in (ROOT / "services" / service / "app").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name) or node.func.id != "HTTPException":
                continue
            for keyword in node.keywords:
                value = keyword.value
                if keyword.arg != "detail" or not isinstance(value, ast.Constant):
                    continue
                if isinstance(value.value, str) and has_han(value.value) and value.value not in catalog:
                    failures.append(f"{path.relative_to(ROOT)}:{node.lineno}: missing English translation for {value.value!r}")
    return failures


def check_admin_service_errors() -> list[str]:
    """Cover literal validation errors that routes forward as HTTP details."""
    catalog = translations("admin-api")
    failures: list[str] = []
    for path in (ROOT / "services" / "admin-api" / "app").rglob("*.py"):
        if path.name == "error_locale.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
                continue
            call = node.exc
            if not isinstance(call.func, ast.Name) or call.func.id not in {"ValueError", "RuntimeError", "PermissionError"}:
                continue
            if not call.args or not isinstance(call.args[0], ast.Constant):
                continue
            value = call.args[0].value
            if isinstance(value, str) and has_han(value) and value not in catalog:
                failures.append(f"{path.relative_to(ROOT)}:{node.lineno}: missing English translation for {value!r}")
    return failures


def check_auth_messages() -> list[str]:
    source = ROOT / "services" / "chat-api" / "app" / "api" / "auth_messages.py"
    catalog = set()
    for node in ast.parse(source.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "_ENGLISH_MESSAGES" for target in node.targets
        ):
            catalog = set(ast.literal_eval(node.value))
    route = ROOT / "services" / "chat-api" / "app" / "api" / "endpoints" / "auth.py"
    failures = []
    for node in ast.walk(ast.parse(route.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id != "localized_auth_message" or not node.args:
            continue
        message = node.args[0]
        if isinstance(message, ast.Constant) and isinstance(message.value, str) and message.value not in catalog:
            failures.append(f"{route.relative_to(ROOT)}:{node.lineno}: missing auth translation for {message.value!r}")
    return failures


if __name__ == "__main__":
    failures = [failure for service in SERVICES for failure in check_service(service)] + check_admin_service_errors() + check_auth_messages()
    if failures:
        raise SystemExit("\n".join(failures))
    print("Literal Chinese HTTP errors and auth responses have English translations.")
