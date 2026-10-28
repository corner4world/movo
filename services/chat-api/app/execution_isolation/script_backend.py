"""Client boundary between the legacy script contract and job containers."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from uuid import uuid4

import httpx


def container_backend_enabled() -> bool:
    return bool(os.environ.get("MOVO_SANDBOX_MANAGER_URL", "").strip())


@contextmanager
def script_workspace() -> Iterator[Path]:
    if not container_backend_enabled():
        with tempfile.TemporaryDirectory(prefix="askai_script_plugin_") as path:
            yield Path(path)
        return
    root = Path(os.environ.get("MOVO_SANDBOX_WORKSPACE_ROOT", "/workspaces"))
    root.mkdir(parents=True, exist_ok=True)
    path = root / uuid4().hex
    path.mkdir(mode=0o700)
    # The worker runs as an unprivileged UID and sees only this subdirectory.
    path.chmod(0o777)
    try:
        yield path
    finally:
        shutil.rmtree(path)


def child_path(path: Path, work_dir: Path) -> str:
    if not container_backend_enabled():
        return str(path)
    return str(Path("/job") / path.relative_to(work_dir))


def run_script_job(
    *, work_dir: Path, runner_path: Path, plugin_path: Path, stdin_path: Path,
    env: dict[str, str], timeout_seconds: int, limit_child_process, skill_digest: str = "",
) -> subprocess.CompletedProcess[str]:
    if not container_backend_enabled():
        return subprocess.run(
            [os.sys.executable, "-I", str(runner_path), str(plugin_path), str(stdin_path)],
            cwd=str(work_dir), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=timeout_seconds, preexec_fn=limit_child_process,
        )
    url = os.environ["MOVO_SANDBOX_MANAGER_URL"].rstrip("/")
    token = os.environ.get("MOVO_SANDBOX_MANAGER_TOKEN", "")
    if len(token) < 32:
        raise RuntimeError("Sandbox manager token is missing")
    if skill_digest:
        (work_dir / "skill-digest").write_text(skill_digest, encoding="ascii")
    with httpx.Client(timeout=timeout_seconds + 30, trust_env=False) as client:
        response = client.post(
            f"{url}/v1/script-jobs", json={"job_id": work_dir.name},
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        payload = response.json()
    return subprocess.CompletedProcess(
        args=["sandbox-script-job", work_dir.name],
        returncode=int(payload["exit_code"]),
        stdout=str(payload.get("stdout") or ""),
        stderr=str(payload.get("stderr") or ""),
    )
