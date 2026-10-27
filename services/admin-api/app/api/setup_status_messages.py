"""Display text for setup health probes, without changing probe results."""

from __future__ import annotations

from typing import Any


_LABELS = {
    "持久化存储": "Persistent Storage",
    "Chat API 与 DSH Runtime": "Chat API and DSH Runtime",
    "文档处理与 Worker": "Document Processing and Worker",
}


def setup_service_label(label: str) -> str:
    return _LABELS.get(label, label)


def localize_setup_services(services: list[Any], accept_language: str | None) -> list[Any]:
    language = (accept_language or "zh").split(",", 1)[0].split(";", 1)[0].strip().lower()
    if not language.startswith("en"):
        return services
    localized = []
    for item in services:
        copy = item.model_copy()
        copy.label = setup_service_label(str(item.label))
        message = str(item.message or "")
        if message == "已就绪":
            copy.message = "Ready"
        elif any("\u3400" <= char <= "\u9fff" for char in message):
            copy.message = "Health check failed"
        localized.append(copy)
    return localized
