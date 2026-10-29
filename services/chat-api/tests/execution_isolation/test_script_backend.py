from __future__ import annotations

from pathlib import Path

import pytest

from app.execution_isolation import script_backend


def test_container_workspace_paths_are_job_scoped(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MOVO_SANDBOX_MANAGER_URL", "http://sandbox-manager:8300")
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path))
    with script_backend.script_workspace() as work_dir:
        assert work_dir.parent == tmp_path
        assert len(work_dir.name) == 32
        assert script_backend.child_path(work_dir / "inputs" / "file.docx", work_dir) == "/job/inputs/file.docx"
        assert work_dir.exists()
    assert not work_dir.exists()


def test_configured_backend_fails_closed_without_credential(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MOVO_SANDBOX_MANAGER_URL", "http://sandbox-manager:8300")
    monkeypatch.delenv("MOVO_SANDBOX_MANAGER_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="token is missing"):
        script_backend.run_script_job(
            work_dir=tmp_path, runner_path=tmp_path / "runner.py", plugin_path=tmp_path / "plugin.py",
            stdin_path=tmp_path / "stdin.json", env={}, timeout_seconds=1,
            limit_child_process=lambda: None,
        )


def test_task_workspace_persists_between_calls(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MOVO_SANDBOX_MANAGER_URL", "http://sandbox-manager:8300")
    monkeypatch.setenv("MOVO_SANDBOX_WORKSPACE_ROOT", str(tmp_path))
    with script_backend.script_workspace("message-1") as work:
        (work / "intermediate.txt").write_text("kept")
        assert script_backend.child_path(work / "intermediate.txt", work) == "/job/work/intermediate.txt"
    with script_backend.script_workspace("message-1") as work:
        assert (work / "intermediate.txt").read_text() == "kept"
    with script_backend.script_workspace("message-2") as other:
        assert not (other / "intermediate.txt").exists()
