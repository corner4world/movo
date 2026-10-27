from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import EvaluationReport


def _items(values: list[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "None"


def write_report(report: EvaluationReport, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"dsh-{report.baseline_version}-to-{report.candidate_version}"
    json_path = output_dir / f"{stem}.json"
    markdown_path = output_dir / f"{stem}.md"
    payload = report.to_dict()
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    checks = "\n".join(
        f"| {item['name']} | {'Passed' if item['passed'] else 'Failed'} | {item['duration_seconds']:.3f}s |"
        for item in payload["checks"]
    )
    dependencies = payload["dependency_delta"]
    capabilities = payload.get("capability_delta") or {}
    enabled_modules = capabilities.get("enabled_modules") or {"added": [], "removed": []}
    code_capabilities = capabilities.get("code_capability_tools") or {"added": [], "removed": []}
    api_removed = {
        name: delta["removed"] for name, delta in payload["public_api_delta"].items()
        if delta.get("removed")
    }
    markdown = f"""# DSH Candidate Upgrade Evaluation

- Baseline version: `{report.baseline_version}`
- Candidate version: `{report.candidate_version}`
- Generated at: `{report.generated_at_utc}`
- Contract evaluation: **{'Passed' if payload['decision']['contract_ready'] else 'Failed'}**
- Release decision: **Not accepted** (full stack and packaging verification is required on the upgrade branch)

## Automated Checks

| Check | Result | Duration |
|---|---:|---:|
{checks}

## Official Package Capability Changes

- Added top-level dependencies: {_items(dependencies['added'])}
- Removed top-level dependencies: {_items(dependencies['removed'])}
- Removed public exports from core packages: {json.dumps(api_removed, ensure_ascii=False) if api_removed else 'None'}
- Added Host modules: {_items(enabled_modules['added'])}
- Removed Host modules: {_items(enabled_modules['removed'])}
- Added Code tools: {_items(code_capabilities['added'])}
- Removed Code tools: {_items(code_capabilities['removed'])}
- Changed ordinary-session model tool contracts: {_items(list(capabilities.get('ordinary_model_tool_contract_changes', {})))}
- Changed Code model tool contracts: {_items(list(capabilities.get('code_model_tool_contract_changes', {})))}

## Existing Session Recovery

- Baseline creation: {'Passed' if payload['old_session_resume'].get('created') else 'Failed'}
- Candidate resume: {'Passed' if payload['old_session_resume'].get('resumed') else 'Failed'}

## Remaining Release Requirements

""" + "\n".join(f"- {reason}" for reason in payload["decision"]["release_requirements"]) + "\n"
    markdown_path.write_text(markdown, encoding="utf-8")
    return json_path, markdown_path
