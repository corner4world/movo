from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List
from app.llm.decision_turn import DecisionOutput
from pydantic import BaseModel, Field


@dataclass
class ComposeDeps:
    llm: Any
    language_name: Any
    log: Any


class SectionSummary(BaseModel):
    section_number: str = ""
    section_title: str = ""
    core_claim: str = ""
    facts_used: List[str] = Field(default_factory=list)
    transition_to_next: str = ""
    avoid_repeating: List[str] = Field(default_factory=list)


class DocumentState(BaseModel):
    report_thesis: str = ""
    completed_sections: List[SectionSummary] = Field(default_factory=list)
    open_threads: List[str] = Field(default_factory=list)
    used_source_indices: List[int] = Field(default_factory=list)


class SectionSummaryBundle(BaseModel):
    report_thesis: str = ""
    summary: SectionSummary = Field(default_factory=SectionSummary)
    open_threads: List[str] = Field(default_factory=list)
    used_source_indices: List[int] = Field(default_factory=list)


class SectionContractAssessment(BaseModel):
    ok: bool = False
    rewrite_needed: bool = False
    missing_facts: List[str] = Field(default_factory=list)
    disallowed_claims: List[str] = Field(default_factory=list)
    unsupported_assertions: List[str] = Field(default_factory=list)
    leaked_open_questions: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class SectionContractRewriteOutput(BaseModel):
    markdown_content: str = Field(default="", description="Rewritten section markdown that preserves the section heading.")


class HeadingAlignmentRewriteOutput(BaseModel):
    markdown_content: str = Field(default="", description="Markdown rewritten to align reader-facing H2 headings with the visible heading plan.")


class PlanAlignmentAssessment(DecisionOutput):
    ok: bool = False
    rewrite_needed: bool = False
    missing_sections: List[str] = Field(default_factory=list)
    misaligned_sections: List[str] = Field(default_factory=list)
    extra_sections: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class OutlinePromptNormalizationOutput(BaseModel):
    system_prompt: str = Field(default="", description="Final clean system prompt for outline generation.")
    user_prompt: str = Field(default="", description="Final clean user prompt for outline generation.")
    clean_outline_goal: str = Field(default="", description="Natural restatement of the outline planning goal.")


class OutlineSectionPlan(BaseModel):
    title: str = Field(description="Objective section title without decorative language")
    objective: str = Field(default="", description="What this section aims to establish and analyze")
    key_points: List[str] = Field(default_factory=list, description="Core arguments of this section")
    evidence_focus: List[str] = Field(default_factory=list, description="Evidence supporting the arguments")
    visual_hint: str = Field(default="none", description="One of: table, chart, mermaid, none")
    weight: int = Field(default=3, description="Relative section weight from 1 to 5")
    section_role: str = Field(
        default="analysis",
        description="Narrative role of this section, such as intro, background, analysis, case, comparison, conclusion",
    )
    level: int = Field(default=1, description="Heading level")
    children: List["OutlineSectionPlan"] = Field(default_factory=list, description="Sub-sections")


class ReportOutlinePlan(DecisionOutput):
    title: str = Field(default="", description="Document title")
    sections: List[OutlineSectionPlan] = Field(default_factory=list, description="Section tree")


class SectionPromptNormalizationOutput(BaseModel):
    system_prompt: str = Field(default="", description="Final clean system prompt for section writing.")
    user_prompt: str = Field(default="", description="Final clean user prompt for section writing.")
    clean_section_goal: str = Field(default="", description="Natural restatement of the current section task.")
    evidence_slice_summary: str = Field(default="", description="Section-level evidence brief preserved from the raw inputs.")


OutlineSectionPlan.model_rebuild()
