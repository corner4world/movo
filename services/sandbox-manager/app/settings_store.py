"""Persistent administrator settings for the sandbox manager."""

from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4


class SettingsStore:
    def __init__(self, root: Path) -> None:
        self.path = root / "sandbox-settings.json"

    def max_pending(self, default: int) -> int:
        if not self.path.exists():
            return default
        value = json.loads(self.path.read_text(encoding="utf-8")).get("max_pending")
        if not isinstance(value, int) or not 0 <= value <= 100:
            raise ValueError("Invalid sandbox pending queue setting")
        return value

    def save_max_pending(self, value: int) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("x", encoding="utf-8") as stream:
                os.chmod(temporary, 0o600)
                json.dump({"max_pending": value}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)
