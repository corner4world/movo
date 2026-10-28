"""Compatibility imports for the unified composition components."""

from .markdown import MarkdownPostProcessor
from .models import (
    ComposeDeps,
    SectionSummary,
    DocumentState,
    SectionSummaryBundle,
    SectionContractAssessment,
    SectionContractRewriteOutput,
    HeadingAlignmentRewriteOutput,
    PlanAlignmentAssessment,
    OutlinePromptNormalizationOutput,
    OutlineSectionPlan,
    ReportOutlinePlan,
    SectionPromptNormalizationOutput,
)
from .observations import ObservationAdapter
from .outline import OutlinePlanner
from .prompt_formatting import (
    _compact_scalar,
    _compact_string_list,
    _style_prompt_limit,
    _project_writer_constraints,
    _markdown_section,
    _split_identity_block,
    _markdown_bullets,
    _markdown_fact_objects,
    _humanize_claim_type,
    _render_claim_contract_markdown,
    _render_fact_contract_markdown,
    _format_writer_constraints_markdown,
    _format_single_pass_user_markdown,
    _format_single_pass_user_markdown_minimal,
    _format_single_pass_user_markdown_ultra_minimal,
    _is_retryable_single_pass_error,
)
from .section import SectionWriter
from .shared import _truncate_text, _exception_debug_payload
from .single_pass import SinglePassWriter
from .visual import VisualAugmenter

__all__ = [
    "ComposeDeps",
    "SectionSummary",
    "DocumentState",
    "SectionSummaryBundle",
    "SectionContractAssessment",
    "SectionContractRewriteOutput",
    "HeadingAlignmentRewriteOutput",
    "PlanAlignmentAssessment",
    "OutlinePromptNormalizationOutput",
    "OutlineSectionPlan",
    "ReportOutlinePlan",
    "SectionPromptNormalizationOutput",
    "ObservationAdapter",
    "MarkdownPostProcessor",
    "OutlinePlanner",
    "VisualAugmenter",
    "SectionWriter",
    "SinglePassWriter",
]
