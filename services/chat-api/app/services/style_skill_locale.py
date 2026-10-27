"""Choose the source document language for generated writing-style Skills."""

from __future__ import annotations

import re
from typing import Any


def source_style_language(analysis: dict[str, Any], sample: str) -> str:
    declared = str(analysis.get("language") or "").strip().lower()
    if declared in {"zh", "en", "mixed"}:
        return declared
    return "zh" if re.search(r"[\u3400-\u9fff]", sample) else "en"


def style_description_fallback(language: str) -> str:
    return "用户写作规范" if language == "zh" else "User writing style guide"


def style_body_language_instruction(language: str) -> str:
    if language == "zh":
        return "Write the guidance in Chinese, matching the source document."
    if language == "en":
        return "Write the guidance in English, matching the source document."
    return "Preserve the source document's mixed-language usage in the guidance."
