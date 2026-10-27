"""Interpret structured hit-test evidence, not the generic stale-target text."""
import json
from typing import Any


def obstruction_evidence(error: object) -> dict[str, Any] | None:
    text = str(error or "")
    if "diagnostic=" not in text:
        return None
    try:
        diagnostic, _ = json.JSONDecoder().raw_decode(text.split("diagnostic=", 1)[1])
    except (ValueError, TypeError):
        return None
    if not isinstance(diagnostic, dict) or diagnostic.get("targetResolved") is not True:
        return None
    hit = diagnostic.get("hit")
    if diagnostic.get("hitsTarget") is not False or not isinstance(hit, dict):
        return None
    # Keep only bounded explanatory data, never persist the full page text.
    return {"reason": "occluded", "blocker_tag": str(hit.get("tag") or ""),
            "blocker_role": str(hit.get("role") or ""),
            "blocker_text": str(hit.get("text") or "")[:160]}


OBSTRUCTION_GUIDANCE = (
    "The target node still exists, but another page layer covers its click point; its ref is not stale. "
    "First handle an observed close/back control in the overlay or navigate through an observed target link. "
    "Do not repeatedly click the covered target, fill blindly, or only observe repeatedly. Do not invent links or close buttons. "
    "Check for unsubmitted content before closing or leaving; never discard user input without authorization."
)
