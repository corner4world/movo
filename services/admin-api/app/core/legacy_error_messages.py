"""Stable Chinese service errors retained for existing clients."""


def backend_unavailable(reason: object) -> str:
    return f"backend 不可用：{reason}"
