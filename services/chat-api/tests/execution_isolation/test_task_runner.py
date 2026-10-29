from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from app.execution_isolation.runner_source import runner_source


def _run(work: Path, code: str, call: str) -> subprocess.CompletedProcess[str]:
    folder = work / "calls" / call
    folder.mkdir(parents=True)
    (folder / "runner.py").write_text(runner_source(container_isolated=True))
    (folder / "plugin.py").write_text(code)
    (folder / "stdin.json").write_text(json.dumps({
        "inputs": {}, "context": {"work_dir": str(work), "skill_dir": "", "allow_network": False},
    }))
    return subprocess.run([sys.executable, "-I", str(folder / "runner.py"),
                           str(folder / "plugin.py"), str(folder / "stdin.json")],
                          text=True, capture_output=True, check=False)


def test_isolated_runner_reuses_workspace_and_accepts_one_argument(tmp_path: Path) -> None:
    first = _run(tmp_path, "def run(inputs):\n    open('intermediate.log', 'w').write('kept')\n    return {}\n", "a")
    second = _run(tmp_path, "def run():\n    return {'value': open('intermediate.log').read()}\n", "b")
    assert first.returncode == 0
    assert second.returncode == 0
    assert json.loads(second.stdout)["value"] == "kept"
