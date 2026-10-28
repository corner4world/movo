"""Coordinate the stages of a desktop browser execution run."""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import Any, AsyncIterator, Dict, Tuple

from app.enterprise_capabilities.runtime.execution_contracts import CapabilityInputs, CapabilityTask

from .browser_run_completion import complete_step, finish_run
from .browser_run_decisions import handle_terminal_decision
from .browser_run_dispatch import dispatch_action
from .browser_run_effects import prepare_effect
from .browser_run_guards import validate_action
from .browser_run_planning import plan_step
from .browser_run_recovery import prepare_recovery, resume_session
from .browser_run_setup import prepare_request, prepare_session
from . import desktop_agent_executor as executor_module


async def run_browser_execution(
    executor: Any,
    *,
    node: CapabilityTask,
    inputs: CapabilityInputs,
) -> AsyncIterator[Tuple[Dict[str, Any], Dict[str, Any]]]:
    state = SimpleNamespace(executor=executor, node=node, inputs=inputs, terminal=False)
    for phase in (prepare_request, prepare_session, prepare_recovery, resume_session):
        result = phase(state)
        if inspect.isasyncgen(result):
            async for event in result:
                yield event
        else:
            await result
        if state.terminal:
            return

    for state.step in range(state.start_step, executor_module.MAX_STEPS + 1):
        state.break_step = False
        state.continue_step = False
        for phase in (
            plan_step,
            handle_terminal_decision,
            validate_action,
            prepare_effect,
            dispatch_action,
            complete_step,
        ):
            result = phase(state)
            if inspect.isasyncgen(result):
                async for event in result:
                    yield event
            else:
                await result
            if state.terminal:
                return
            if state.break_step or state.continue_step:
                break
        if state.break_step:
            break
        if state.continue_step:
            continue

    async for event in finish_run(state):
        yield event
