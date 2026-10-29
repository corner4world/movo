from __future__ import annotations

import asyncio

from app.services.skill_packages import readiness


def test_plain_skill_has_no_environment_state():
    skill = {"id": "plain", "package_digest": "a" * 64, "package_files": [{"path": "SKILL.md"}]}
    assert asyncio.run(readiness.environment_status(skill)) is None


def test_declared_dependency_uses_manager_state(monkeypatch):
    skill = {
        "id": "with-deps", "package_digest": "b" * 64,
        "package_files": [{"path": "requirements.txt"}],
    }
    async def status(digest):
        assert digest == "b" * 64
        return "preparing"
    monkeypatch.setattr(readiness, "dependency_status", status)
    asyncio.run(readiness.attach_environment_status([skill]))
    assert skill["environment_status"] == "preparing"


def test_explicit_no_dependency_flag_skips_status(monkeypatch):
    skill = {
        "package_digest": "c" * 64, "package_requires_environment": False,
        "package_files": [{"path": "requirements.txt"}],
    }
    async def unexpected(_):
        raise AssertionError("manager must not be called")
    monkeypatch.setattr(readiness, "dependency_status", unexpected)
    assert asyncio.run(readiness.environment_status(skill)) is None


def test_pending_upgrade_keeps_active_fields_until_ready(monkeypatch):
    skill = {
        "id": "old", "user_id": "owner", "package_digest": "a" * 64,
        "package_requires_environment": False,
        "pending_package": {"digest": "b" * 64, "fields": {"package_digest": "b" * 64}},
    }
    async def status(digest):
        assert digest == "b" * 64
        return "preparing"
    monkeypatch.setattr(readiness, "dependency_status", status)
    assert asyncio.run(readiness.environment_status(skill)) == "preparing"
    assert skill["package_digest"] == "a" * 64


def test_ready_pending_upgrade_is_promoted(monkeypatch):
    skill = {
        "id": "old", "user_id": "owner", "package_digest": "a" * 64,
        "pending_package": {"digest": "b" * 64, "fields": {"package_digest": "b" * 64}},
    }
    promoted = []
    async def status(_): return "ready"
    async def promote(row):
        promoted.append(row["id"])
        row.update(row["pending_package"]["fields"])
        row.pop("pending_package")
    monkeypatch.setattr(readiness, "dependency_status", status)
    monkeypatch.setattr(readiness, "promote_if_ready", promote)
    assert asyncio.run(readiness.environment_status(skill)) == "ready"
    assert promoted == ["old"]
    assert skill["package_digest"] == "b" * 64
