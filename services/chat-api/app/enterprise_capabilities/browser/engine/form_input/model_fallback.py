from __future__ import annotations

import json
import logging
from typing import List, Literal

from pydantic import BaseModel, Field

from app.llm.factory import get_request_scoped_llm_client
from app.llm.types import Message, Role
from app.llm.decision_turn import DecisionOutput, DecisionTurnSpec, invoke_structured_decision

from .binding_authority import (
    authoritative_publish_candidate,
    contains_serialized_media,
    direct_authoritative_binding,
    has_structured_media,
)
from .contracts import FieldBinding, FieldDescriptor
from .input_context import BrowserInputContext


logger = logging.getLogger(__name__)


class _ModelBinding(BaseModel):
    field_key: str
    resolution: Literal["direct", "transform", "selection", "attachment", "skip"]
    candidate_id: str = ""
    value: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = ""


class _ModelPlan(DecisionOutput):
    bindings: List[_ModelBinding] = Field(default_factory=list)


class FormInputModelResolver:
    def __init__(self, llm=None) -> None:
        self._llm = llm or get_request_scoped_llm_client(
            streaming=False,
            intent="browser_automation",
            stage="browser_form_input_resolution",
        )

    async def resolve(
        self,
        *,
        fields: List[FieldDescriptor],
        context: BrowserInputContext,
        lang: str,
        task_goal: str = "",
    ) -> List[FieldBinding]:
        if not fields:
            return []
        field_map = {field.field_key: field for field in fields}
        candidates = context.by_id()
        payload = {
            "original_user_request": context.original_request[:3000],
            "current_browser_node_goal": str(task_goal or "")[:4000],
            "fields": [
                {
                    "field_key": field.field_key,
                    "label": field.semantic_label,
                    "placeholder_hint": field.placeholder,
                    "scope_id": field.scope_id,
                    "scope_name": field.scope_name,
                    "scope_role": field.scope_role,
                    "label_source": str(field.raw.get("labelSource") or field.raw.get("label_source") or ""),
                    "control_kind": field.control_kind,
                    "required": field.required,
                    "options": field.options[:50],
                }
                for field in fields
            ],
            "available_inputs": context.model_payload(),
        }
        system = _system_prompt(lang)
        try:
            result = await invoke_structured_decision(
                self._llm,
                _ModelPlan,
                [
                    Message(role=Role.SYSTEM, content=system),
                    Message(role=Role.USER, content=json.dumps(payload, ensure_ascii=False)),
                ],
                spec=DecisionTurnSpec(locale=lang, turn_id="browser.form_input_resolution"),
            )
        except Exception as exc:
            logger.warning(
                "browser form input resolution failed",
                extra={"event": "browser.form_input_model_failed", "error": str(exc)},
            )
            return []
        return _validated_bindings(
            result.bindings,
            field_map=field_map,
            candidates=candidates,
            lang=lang,
        )


def _validated_bindings(raw, *, field_map, candidates, lang: str = "zh") -> List[FieldBinding]:
    bindings: List[FieldBinding] = []
    seen = set()
    all_candidates = list(candidates.values())
    for item in raw:
        field = field_map.get(item.field_key)
        if field is None or item.field_key in seen:
            continue
        authoritative = authoritative_publish_candidate(field, all_candidates)
        if item.resolution == "transform" and authoritative is not None:
            bindings.append(direct_authoritative_binding(
                field=field,
                candidate=authoritative,
                confidence=max(item.confidence, 0.99),
                rationale=(
                    f"{item.rationale} [publish_payload_authority] "
                    "preserved canonical upstream content"
                ).strip(),
            ))
            seen.add(item.field_key)
            continue
        candidate = candidates.get(item.candidate_id) if item.candidate_id else None
        if item.candidate_id and candidate is None:
            continue
        if item.resolution in {"direct", "attachment"} and candidate is None:
            continue
        binding = None
        if item.resolution == "direct":
            if candidate.value_kind == "file" or field.control_kind == "file":
                continue
            binding = FieldBinding(
                field_key=field.field_key, action="fill",
                source_kind="user_input" if candidate.source_kind == "user_input" else "upstream",
                value=str(candidate.value or ""), candidate_id=candidate.candidate_id,
                source_path=candidate.source_path, confidence=item.confidence,
                plain_text=candidate.plain_text,
                rich_html=candidate.rich_html,
                rationale=item.rationale,
            )
        elif item.resolution == "attachment":
            if field.control_kind != "file" or candidate.value_kind != "file":
                continue
            binding = FieldBinding(
                field_key=field.field_key, action="upload", source_kind="attachment",
                value=list(candidate.value or []), candidate_id=candidate.candidate_id,
                source_path=candidate.source_path, confidence=item.confidence,
                rationale=item.rationale,
            )
        elif item.resolution == "selection":
            option = _valid_option(item.value, field.options)
            if not option:
                continue
            binding = FieldBinding(
                field_key=field.field_key, action="select", source_kind="selection",
                value=option, candidate_id=item.candidate_id,
                source_path=candidate.source_path if candidate else "",
                confidence=item.confidence, rationale=item.rationale,
            )
        elif item.resolution == "transform":
            value = str(item.value or "").strip()
            if not value or field.control_kind in {"file", "toggle"}:
                continue
            if contains_serialized_media(value) and has_structured_media(all_candidates):
                continue
            binding = FieldBinding(
                field_key=field.field_key, action="fill", source_kind="transform",
                value=value, candidate_id=item.candidate_id,
                source_path=candidate.source_path if candidate else "",
                confidence=item.confidence, rationale=item.rationale,
            )
        elif item.resolution == "skip":
            binding = FieldBinding(
                field_key=field.field_key, action="skip", source_kind="unknown",
                confidence=item.confidence, rationale=item.rationale,
            )
        if binding is not None:
            bindings.append(binding)
            seen.add(item.field_key)
    return bindings


def _valid_option(value: str, options: List[str]) -> str:
    normalized = str(value or "").strip().casefold()
    for option in options:
        if option.strip().casefold() == normalized:
            return option
    return ""


def _system_prompt(lang: str) -> str:
    if str(lang or "").startswith("zh"):
        return (
            "Bind inputs only for form fields already present on the current page. Choose field_key and candidate_id only from supplied candidates; never invent identifiers. "
            "Use direct for complete existing artifacts and attachment for files. Allow transform/selection only for short page-level adaptations such as title, summary, notes, or category. "
            "Do not regenerate standalone long-form artifacts such as reports or articles here. If such an artifact is missing or cannot be judged reliably, do not bind that field; the browser Agent Loop decides whether to ask the user. "
            "selection.value must exactly match an option for that field. Skip optional fields when the user goal does not require them and no corresponding input exists. Leave only unresolved fields truly required for the user goal to the Agent Loop. "
            "Do not fill passwords or verification codes. Return at most one binding per field. current_browser_node_goal is this browser node's immediate goal and governs field filling; original_user_request only supplements overall intent. "
            "For every supplied field, return either a binding or an explicit skip; omit none silently. For short in-page text such as comments, replies, or email notes, use transform when original_user_request and available_inputs provide enough facts. "
            "Do not infer a missing long-form artifact solely from a field label such as body or content. If a title/subject field lacks a separate title candidate but the original request or upstream body clearly establishes the topic, use transform to produce the short page title. "
            "placeholder_hint is only a potentially changing page hint; never treat it as the value to fill or the field's unique identity. scope_name/scope_role identify the business container: process only fields in the current container and do not combine across containers. "
            "Titles and bodies in available_inputs with binding_authority=publish_payload are authoritative upstream artifacts: use direct only, with no transform, summary, rewriting, or conversion of images into HTML/Markdown text. "
            "Leave image files for a separate media transaction."
        )
    return (
        "Resolve inputs only for form fields already visible on the current page. Use only supplied field_key and "
        "candidate_id values. Use direct for complete inputs and attachment for files. transform/selection are only "
        "for short page-bound adaptations such as titles, summaries, notes, and categories. Never create a missing "
        "standalone report or article here; omit the field binding when required information is unavailable so the "
        "browser Agent Loop owns any user intervention. A selection value must "
        "exactly match one supplied option. Skip optional fields that are not requested and have no matching input; "
        "leave unresolved required fields to the Agent Loop. Never fill passwords or verification codes."
        " Treat current_browser_node_goal as the authoritative instruction for the current browser node and "
        "original_user_request as supporting context. Return one binding or an explicit skip for every supplied field."
        " For short page-bound comments, replies, or message text, use transform when the original request and "
        "available inputs provide enough facts; a generic content/body label alone does not imply a missing article."
        " If a title, subject, or headline field lacks a dedicated title candidate but the request or upstream body "
        "already establishes the topic, use transform to produce the short page-bound title."
        " placeholder_hint is an unstable page hint; never use it as the value to enter or as field identity."
        " scope_name and scope_role identify the owning interaction container; never combine fields across containers."
        " A title or body marked binding_authority=publish_payload is canonical upstream content: bind it directly and "
        "never transform, summarize, rewrite, or serialize its media as HTML/Markdown text. Structured media remains "
        "owned by the separate media transaction."
    )
