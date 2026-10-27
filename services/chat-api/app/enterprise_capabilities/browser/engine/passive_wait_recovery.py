"""Bound condition-free waiting using the existing execution history."""
from .agent_loop.protocol import Decision, Observation


def recover_passive_wait(decision: Decision, observation: Observation, history: list) -> Decision:
    if decision.tool != "browser_wait_for" or (decision.args or {}).get("text"):
        return decision
    count = 0
    for record in reversed(history):
        if record.observation.url != observation.url:
            break
        tool = record.decision.tool
        if tool == "browser_wait_for":
            count += 1
        elif tool not in {"browser_observe", "browser_read_text", "browser_screenshot"}:
            break
    if count < 2:
        return decision
    return Decision(
        "browser_observe", {"with_screenshot": True},
        "Repeated waiting did not advance the task. Read the current state instead. A local loading indicator does not make the whole page unavailable; "
        "use controls that are already actionable, scroll to the target area, or handle an observed overlay. "
        "Do not wait again without a condition. If progress is impossible, explain the specific obstacle.",
    )
