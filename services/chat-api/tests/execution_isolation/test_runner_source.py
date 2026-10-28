from __future__ import annotations

import json
import subprocess
import sys

from app.execution_isolation.runner_source import runner_source


def test_runner_reads_selected_skill_but_rejects_package_writes(tmp_path):
    job = tmp_path / "job"
    skill = job / "skills" / "sample"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("Sample resource", encoding="utf-8")
    runner = job / "runner.py"
    plugin = job / "plugin.py"
    stdin = job / "stdin.json"
    runner.write_text(runner_source(), encoding="utf-8")
    plugin.write_text(
        "def run(inputs, context):\n"
        "    from pathlib import Path\n"
        "    root = Path(context['skill_dir'])\n"
        "    content = (root / 'SKILL.md').read_text()\n"
        "    try:\n"
        "        (root / 'other.txt').write_text('blocked')\n"
        "    except PermissionError:\n"
        "        return {'content': content, 'write_denied': True}\n"
        "    return {'content': content, 'write_denied': False}\n",
        encoding="utf-8",
    )
    stdin.write_text(json.dumps({
        "inputs": {}, "context": {"work_dir": str(job), "skill_dir": str(skill), "allow_network": False},
    }), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-I", str(runner), str(plugin), str(stdin)],
        cwd=job, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"content": "Sample resource", "write_denied": True}
    assert not (skill / "other.txt").exists()
