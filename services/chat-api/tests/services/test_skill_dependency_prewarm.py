from __future__ import annotations

import asyncio
import io
import zipfile

from app.services.skill_packages.prewarm import prewarm_skill_dependencies
from app.services.skill_packages.validator import validate_skill_zip


def package_with(files: dict[str, str]):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("SKILL.md", "---\nname: demo\ndescription: Demo\n---\nRun the script.\n")
        for name, body in files.items():
            archive.writestr(name, body)
    return validate_skill_zip(output.getvalue())


def test_install_without_declarations_does_not_contact_manager(monkeypatch):
    monkeypatch.setenv("MOVO_SANDBOX_MANAGER_URL", "http://manager:8300")
    assert asyncio.run(prewarm_skill_dependencies(package_with({"scripts/run.py": "pass"}))) == "not_required"


def test_root_declaration_starts_preparation(monkeypatch):
    import app.services.skill_packages.prewarm as module

    monkeypatch.setenv("MOVO_SANDBOX_MANAGER_URL", "http://manager:8300")
    seen = []
    monkeypatch.setattr(module, "_start", lambda package: seen.append(package.name) or "preparing")
    result = asyncio.run(prewarm_skill_dependencies(package_with({"requirements.txt": "humanize==4.13.0"})))
    assert result == "preparing"
    assert seen == ["demo"]
