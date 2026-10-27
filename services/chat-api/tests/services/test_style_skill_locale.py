from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from app.services import skills as skills_module
from app.services.style_skill_locale import source_style_language


def test_style_language_falls_back_to_source_text() -> None:
    assert source_style_language({}, "A plain English style sample") == "en"
    assert source_style_language({}, "中文写作样本") == "zh"


def test_style_skill_prompt_follows_document_language(monkeypatch) -> None:
    complete = AsyncMock(return_value="---\nrole: style\n---\nGuidance")
    monkeypatch.setattr(skills_module.llm_service, "chat_complete", complete)
    service = skills_module.UserSkillService()

    asyncio.run(service._compile_style_skill_md({"language": "en"}, "English prose"))
    assert "Write the guidance in English" in complete.await_args.args[0][0]["content"]

    asyncio.run(service._compile_style_skill_md({"language": "zh"}, "中文正文"))
    assert "Write the guidance in Chinese" in complete.await_args.args[0][0]["content"]
