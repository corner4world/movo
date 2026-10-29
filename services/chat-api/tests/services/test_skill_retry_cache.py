from __future__ import annotations

import asyncio

from app.services.skill_packages import retry_cache


def test_retry_reuses_cached_bundle_without_reading_archive(tmp_path, monkeypatch):
    digest = "a" * 64
    cached = tmp_path / "skill-cache" / digest / "example"
    cached.mkdir(parents=True)
    (cached / "SKILL.md").write_text("# Example")
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path))

    async def unexpected_read(*_args):
        raise AssertionError("cached bundle must not be read again")

    monkeypatch.setattr(retry_cache, "read_archive", unexpected_read)
    assert asyncio.run(retry_cache.ensure_retry_bundle_cached(None, {
        "digest": digest, "root_prefix": "example/", "slug": "example",
    })) == digest


def test_retry_recovers_missing_cache_from_archive(tmp_path, monkeypatch):
    digest = "b" * 64
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path))
    reads = []

    async def read(_db, package):
        reads.append(package["digest"])
        return b"archive"

    monkeypatch.setattr(retry_cache, "read_archive", read)
    monkeypatch.setattr(retry_cache, "cache_skill_bundle", lambda bundle, _root: bundle.digest)
    assert asyncio.run(retry_cache.ensure_retry_bundle_cached(None, {
        "digest": digest, "root_prefix": "example/", "slug": "example",
    })) == digest
    assert reads == [digest]
