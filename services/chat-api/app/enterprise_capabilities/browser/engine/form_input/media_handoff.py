from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Set

from app.enterprise_capabilities.browser.engine.agent_loop.protocol import Observation

from .input_context import BrowserInputContext, InputCandidate
from .media_delivery import prefers_media_paste
from .media_editor import media_editor_candidate_payload


_ACTION_ROLES = {"button", "link", "menuitem", "tab"}
_MEDIA_TERMS = (
    "upload", "attach", "attachment", "image", "picture", "photo", "media",
    "上传", "附件", "图片", "图像", "配图", "插图",
)


def pending_media_candidates(
    context: BrowserInputContext,
    completed_candidate_ids: Iterable[str],
) -> list[InputCandidate]:
    completed = {str(item) for item in completed_candidate_ids if str(item)}
    pending = [
        candidate
        for candidate in context.candidates
        if candidate.value_kind == "file"
        and candidate.candidate_id not in completed
        and list(candidate.value or [])
    ]
    anchored = [
        candidate for candidate in pending
        if isinstance(candidate.metadata.get("media_anchor"), dict)
    ]
    if len(anchored) != len(pending):
        return pending
    # Insert from the end of the generated document towards the beginning.
    # DOM insertion at an identical caret position prepends the new node, so
    # descending order also preserves the authored order for adjacent images.
    return sorted(
        pending,
        key=lambda candidate: (
            int(candidate.metadata["media_anchor"].get("plain_offset") or 0),
            int(candidate.metadata["media_anchor"].get("order") or 0),
        ),
        reverse=True,
    )


def augment_media_handoff_ledger(
    *,
    observation: Observation,
    context: BrowserInputContext,
    completed_candidate_ids: Iterable[str],
    state_ledger: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Keep generated media visible to the exploration loop until uploaded.

    A number of rich editors create their file input only after the user
    activates an image/attachment toolbar control. The form driver cannot
    upload before that input exists, so it gives the existing exploration
    driver a constrained pending-media instruction instead of losing the
    upstream file candidate.
    """
    pending = pending_media_candidates(context, completed_candidate_ids)
    if (
        not pending
        or _has_file_input(observation)
        or not _has_editor_surface(observation)
    ):
        return state_ledger

    paste_requested = prefers_media_paste(context.original_request)
    editor_candidates = (
        media_editor_candidate_payload(observation)
        if paste_requested
        else []
    )
    candidate_refs = (
        [str(item.get("ref") or "") for item in editor_candidates]
        if paste_requested
        else _media_activation_candidate_refs(observation)
    )
    ledger = dict(state_ledger or {})
    constraints = list(ledger.get("action_constraints") or [])
    constraints.append(
        (
            "The user explicitly requested insertion of upstream images by copy and paste. Locate the current rich-text body editor "
            "and use browser_paste_image; do not click an image-upload control."
        )
        if paste_requested
        else (
            "Upstream files still need to be added to the current business form. Locate and activate the image, media, or attachment control in the current editor. "
            "If it is an unlabeled icon, use its ref annotation in the current screenshot. Observe again after activation, then pass the file input to browser_upload_file when it appears. "
            "Do not regenerate the file or treat final publication as an upload."
        )
    )
    notes = list(ledger.get("notes") or [])
    notes.append(
        f"pending_media: {len(pending)} media batches remain to upload"
        + (f"; current editor candidate refs={candidate_refs}" if candidate_refs else "")
    )
    pinned_refs = list(ledger.get("pinned_refs") or [])
    pinned_refs.extend(candidate_refs)
    ledger.update({
        "pending_media_count": sum(len(list(item.value or [])) for item in pending),
        "action_constraints": constraints,
        "notes": notes,
        "pinned_refs": list(dict.fromkeys(str(ref) for ref in pinned_refs if str(ref))),
    })
    if editor_candidates:
        ledger["media_editor_candidates"] = editor_candidates
    return ledger


def _has_file_input(observation: Observation) -> bool:
    return any(
        isinstance(element, dict)
        and str(element.get("type") or "").strip().lower() == "file"
        and not element.get("disabled")
        for element in list(observation.elements or [])
    )


def _has_editor_surface(observation: Observation) -> bool:
    return any(
        isinstance(element, dict)
        and element.get("editable")
        and not element.get("searchContext")
        and not element.get("search_context")
        and (
            bool(element.get("contentEditable"))
            or str(element.get("contentEditableMode") or "").strip()
            or str(element.get("tag") or "").strip().lower() == "textarea"
            or bool(element.get("multiline"))
        )
        for element in list(observation.elements or [])
    )


def _media_activation_candidate_refs(observation: Observation) -> list[str]:
    editor_scopes: Set[str] = {
        str(element.get("scopeId") or element.get("scope_id") or "")
        for element in list(observation.elements or [])
        if isinstance(element, dict)
        and element.get("editable")
        and not element.get("searchContext")
        and not element.get("search_context")
    }
    refs: list[str] = []
    for element in list(observation.elements or []):
        if not isinstance(element, dict):
            continue
        role = str(element.get("role") or "").strip().lower()
        if role not in _ACTION_ROLES:
            continue
        if element.get("disabled") or element.get("visible") is False:
            continue
        if element.get("inViewport") is False or element.get("hitTestable") is False:
            continue
        scope_id = str(element.get("scopeId") or element.get("scope_id") or "")
        label = " ".join(
            str(element.get(key) or "")
            for key in ("name", "text", "description", "semanticPurpose")
        ).casefold()
        compact_unlabelled = (
            not label.strip()
            and _compact_control(element)
            and (not editor_scopes or scope_id in editor_scopes)
        )
        semantically_media = any(term in label for term in _MEDIA_TERMS)
        if compact_unlabelled or semantically_media:
            ref = str(element.get("ref") or "").strip()
            if ref and ref not in refs:
                refs.append(ref)
        if len(refs) >= 24:
            break
    return refs


def _compact_control(element: Dict[str, Any]) -> bool:
    try:
        return 0 < float(element.get("width") or 0) <= 120 and 0 < float(
            element.get("height") or 0
        ) <= 120
    except (TypeError, ValueError):
        return False


__all__ = ["augment_media_handoff_ledger", "pending_media_candidates"]
