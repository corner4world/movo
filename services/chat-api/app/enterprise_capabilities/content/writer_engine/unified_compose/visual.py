from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional
from app.llm.types import Message, Role
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_fixed
from .models import ComposeDeps
from .shared import _truncate_text


class VisualAugmenter:
    VISUAL_TYPES = {"none", "table", "mermaid", "chart", "infographic"}

    def __init__(self, deps: ComposeDeps, prompt_registry: Any):
        self.deps = deps
        self.prompts = prompt_registry

    @staticmethod
    def contains_visual(markdown: str) -> bool:
        text = markdown or ""
        if "```mermaid" in text.lower() or "```chart" in text.lower():
            return True
        return bool(re.search(r"^\s*\|.+\|\s*$", text, flags=re.MULTILINE))

    async def decide_type(
        self,
        *,
        section_title: str,
        section_markdown: str,
        visual_hint: str,
        language: str,
        infographic_budget_left: int,
        contract_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not section_markdown.strip():
            return {"type": "none", "confidence": 0.4, "reason": "empty_section"}
        allowed_infographic = infographic_budget_left > 0
        safe_hint = str(visual_hint or "").strip().lower()
        if safe_hint not in self.VISUAL_TYPES:
            safe_hint = "chart"
        visual_contract = {}
        if isinstance(contract_context, dict):
            visual_contract = dict(contract_context.get("visual_contract") or {})
        prompt = {
            "section_title": section_title,
            "visual_hint": safe_hint,
            "section_excerpt": section_markdown[:1800],
            "contract_context": {"visual_contract": visual_contract},
            "infographic_allowed": allowed_infographic,
            "rules": {"prefer_markdown_visuals": True, "infographic_only_when_necessary": True},
        }
        system = self.prompts.get("visual_decider", language_name=self.deps.language_name(language))
        try:
            self.deps.log(
                "visual_prompt",
                {
                    "section_title": section_title,
                    "system_preview": _truncate_text(system, 1200),
                    "payload_preview": _truncate_text(json.dumps(prompt, ensure_ascii=False), 2200),
                },
            )
        except Exception:
            pass

        class VisualDecision(BaseModel):
            type: str = Field(description="The chosen visual type, must be one of: none, table, mermaid, chart, infographic")
            confidence: float = Field(description="Confidence score between 0.0 and 1.0")
            reason: str = Field(description="A brief explanation for the decision")

        @retry(stop=stop_after_attempt(3), wait=wait_fixed(1), reraise=True)
        async def _invoke_visual():
            resp = await self.deps.llm.ainvoke([Message(role=Role.SYSTEM, content=system), Message(role=Role.USER, content=json.dumps(prompt, ensure_ascii=False))])
            raw = str(getattr(resp, "content", "") or "").strip()
            data = json.loads(raw.replace("```json", "").replace("```", "").strip())
            validated = VisualDecision.model_validate(data)
            return validated.model_dump()

        try:
            data = await _invoke_visual()
            vt = str(data.get("type") or "none").strip().lower()
            if vt not in self.VISUAL_TYPES:
                vt = "none"
            if vt == "infographic" and not allowed_infographic:
                fallback = safe_hint if safe_hint in {"table", "chart", "mermaid"} else "chart"
                return {"type": fallback, "confidence": 0.85, "reason": "infographic_budget_exhausted_fallback"}
            return {"type": vt, "confidence": float(data.get("confidence") or 0.5), "reason": str(data.get("reason") or "visual_decider_llm")}
        except Exception as e:
            self.deps.log("visual_decider_failed", {"error": str(e)[:260]})
        if not allowed_infographic:
            fallback = safe_hint if safe_hint in {"table", "chart", "mermaid"} else "chart"
            return {"type": fallback, "confidence": 0.6, "reason": "visual_decider_fallback_non_infographic"}
        return {"type": "none", "confidence": 0.4, "reason": "visual_decider_fallback"}
