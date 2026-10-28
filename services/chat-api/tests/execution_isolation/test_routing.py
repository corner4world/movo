from __future__ import annotations

import pytest

from app.execution_isolation import ExecutionTarget, route_capability, route_plugin


def test_script_tool_cannot_be_routed_to_shared_runtime() -> None:
    assert route_capability("data.run_script@v1") == ExecutionTarget.TASK_CONTAINER
    assert route_capability("file.run_script_plugin") == ExecutionTarget.TASK_CONTAINER
    assert route_capability("artifact.export@v1") == ExecutionTarget.SHARED_RUNTIME
    with pytest.raises(ValueError):
        route_capability("plugin:unknown")


def test_installed_dsh_bundle_is_always_a_plugin_runtime() -> None:
    assert route_plugin({"engine": "dsh", "tool_names": []}) == ExecutionTarget.PLUGIN_RUNTIME_CONTAINER


def test_unknown_or_unverified_plugin_cannot_execute() -> None:
    for installation in ({}, {"engine": "standalone"}, {"engine": "other"}):
        with pytest.raises(ValueError):
            route_plugin(installation)


def test_standalone_plugin_requires_verified_contract() -> None:
    assert route_plugin({"engine": "standalone", "execution_contract_verified": True}) == ExecutionTarget.TASK_CONTAINER
