from pathlib import Path
from concurrent.futures import Future

import pytest

from app.skill_environments import DependencyPreparationError, SkillEnvironments


class ImageEngine:
    def __init__(self):
        self.images = {"base:latest": "sha256:base"}
        self.created = None

    def image_id(self, name):
        return self.images.get(name)

    def find_compose_service(self, project, service):
        return "proxy"

    def create_internal_network(self, name):
        return "network"

    def connect_network(self, network, container, aliases):
        pass

    def create(self, name, payload):
        self.created = payload
        return "container"

    def start(self, container):
        pass

    def wait(self, container, timeout):
        return 0

    def commit(self, container, repository, tag):
        self.images[f"{repository}:{tag}"] = "sha256:prepared"
        return "sha256:prepared"

    def remove(self, container):
        pass

    def disconnect_network(self, network, container):
        pass

    def remove_network(self, network):
        pass


def test_dependency_image_is_keyed_by_bundle_and_base_image(tmp_path: Path, monkeypatch):
    digest = "a" * 64
    root = tmp_path / "skill-cache" / digest / "sample"
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text("sample")
    (root / "requirements.txt").write_text("humanize==4.13.0")
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_VOLUME", "test-workspaces")
    monkeypatch.setenv("MOVO_SANDBOX_SCRIPT_IMAGE", "base:latest")
    engine = ImageEngine()
    environments = SkillEnvironments(engine)
    assert environments.ready_image(digest) == environments.ready_image(digest)
    assert environments.status(digest) == "ready"
    assert engine.created["HostConfig"]["Mounts"][0]["ReadOnly"] is True
    assert engine.created["HostConfig"]["Mounts"][0]["VolumeOptions"]["Subpath"] == f"skill-cache/{digest}/sample"
    assert engine.created["HostConfig"]["NetworkMode"] == "network"
    assert engine.created["HostConfig"]["CapDrop"] == ["ALL"]
    assert engine.created["HostConfig"]["CapAdd"] == ["CHOWN", "DAC_OVERRIDE", "FOWNER", "SETUID", "SETGID"]


def test_bundle_without_declarations_uses_base_image(tmp_path: Path, monkeypatch):
    digest = "b" * 64
    root = tmp_path / "skill-cache" / digest
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text("sample")
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_VOLUME", "test-workspaces")
    monkeypatch.setenv("MOVO_SANDBOX_SCRIPT_IMAGE", "base:latest")
    engine = ImageEngine()
    environments = SkillEnvironments(engine)
    assert environments.ready_image(digest) == "base:latest"
    assert environments.status(digest) == "not_required"
    assert engine.created is None


def test_status_restarts_preparation_after_manager_restart(tmp_path: Path, monkeypatch):
    digest = "d" * 64
    root = tmp_path / "skill-cache" / digest
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text("sample")
    (root / "requirements.txt").write_text("humanize==4.13.0")
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_VOLUME", "test-workspaces")
    monkeypatch.setenv("MOVO_SANDBOX_SCRIPT_IMAGE", "base:latest")
    environments = SkillEnvironments(ImageEngine())
    assert environments.status(digest) in {"preparing", "ready"}
    assert environments.ready_image(digest).startswith("movo-skill-deps:")


def test_pending_build_returns_bounded_retry_error(tmp_path: Path, monkeypatch):
    digest = "e" * 64
    root = tmp_path / "skill-cache" / digest
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text("sample")
    (root / "requirements.txt").write_text("humanize==4.13.0")
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_VOLUME", "test-workspaces")
    monkeypatch.setenv("MOVO_SANDBOX_SCRIPT_IMAGE", "base:latest")
    environments = SkillEnvironments(ImageEngine())
    image = environments._image_name(digest)
    environments.pending[image] = Future()
    with pytest.raises(DependencyPreparationError, match="still preparing"):
        environments.ready_image(digest, timeout=0.01)


def test_build_error_is_reported_without_exposing_install_logs(tmp_path: Path, monkeypatch):
    digest = "c" * 64
    root = tmp_path / "skill-cache" / digest
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text("sample")
    (root / "package.json").write_text("{}")
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_VOLUME", "test-workspaces")
    monkeypatch.setenv("MOVO_SANDBOX_SCRIPT_IMAGE", "base:latest")

    class FailingEngine(ImageEngine):
        def __init__(self):
            super().__init__()
            self.creates = 0

        def create(self, name, payload):
            self.creates += 1
            return super().create(name, payload)

        def wait(self, container, timeout):
            return 1

        def logs(self, container):
            return bytes([2, 0, 0, 0, 0, 0, 0, 11]) + b"secret-token"

    engine = FailingEngine()
    environments = SkillEnvironments(engine)
    with pytest.raises(DependencyPreparationError, match="check sandbox manager logs") as error:
        environments.ready_image(digest)
    assert "secret-token" not in str(error.value)
    assert environments.status(digest) == "failed"
    with pytest.raises(DependencyPreparationError):
        environments.ready_image(digest)
    assert engine.creates == 1
    assert environments.start(digest, retry_failed=True) in {"preparing", "failed"}
    with pytest.raises(DependencyPreparationError):
        environments.ready_image(digest)
    assert engine.creates == 2
