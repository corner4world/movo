"""Compile adaptive ASKAI workflows into declarative DSH Skill bodies."""

from __future__ import annotations

import json
from typing import Any

from app.dsh_runtime.profile.tools import ToolProfileDefinition
from app.enterprise_capabilities.runtime.workflow_mapping import workflow_capability_for_node
from app.services.org_skill_adapter import _workflow_nodes as normalize_workflow_nodes

from .workflow_contract import resolved_review_config, validate_external_bindings, validate_node_identity, validate_read_material_source
from .delivery_semantics import intermediate_artifact_nodes
from .review_protocol import review_check_guidance


def workflow_nodes(row: dict[str, Any]) -> list[dict[str, Any]]:
    contract = row.get("skill_contract") if isinstance(row.get("skill_contract"), dict) else {}
    structure = contract.get("structure") if isinstance(contract.get("structure"), dict) else {}
    nodes = structure.get("workflow_nodes")
    contracted = [dict(item) for item in nodes if isinstance(item, dict)] if isinstance(nodes, list) else []
    if contracted:
        return contracted

    # Personal workflows created before the DSH migration keep their tested
    # node definitions in config.workflowNodes. Reuse the same normalizer used
    # by organization Skills so both sources compile to one native contract.
    config = row.get("config") if isinstance(row.get("config"), dict) else {}
    return normalize_workflow_nodes(config)


def compile_workflow_body(
    row: dict[str, Any],
    *,
    tools: tuple[ToolProfileDefinition, ...],
    style_refs: dict[str, str],
) -> tuple[str, tuple[str, ...]]:
    nodes = workflow_nodes(row)
    if not nodes:
        raise ValueError(f"workflow Skill has no executable nodes: {row.get('name')}")
    validate_node_identity(nodes)
    by_capability = {tool.capability_ref: tool for tool in tools if tool.capability_ref}
    external_tools = [tool for tool in tools if tool.source_type in {"http", "mcp"}]
    rendered: list[str] = []
    capability_refs: list[str] = []
    intermediate_nodes = intermediate_artifact_nodes(nodes)
    for index, node in enumerate(nodes, start=1):
        node_type = str(node.get("type") or "").strip()
        validate_read_material_source(node)
        binding = workflow_capability_for_node(node)
        tool_name = ""
        if binding.runtime_shape == "tool":
            tool = by_capability.get(binding.capability_ref)
            if tool is None:
                raise PermissionError(
                    f"workflow node {node_type} requires unavailable capability {binding.capability_ref}"
                )
            tool_name = tool.name
        elif binding.runtime_shape == "external_tool":
            if not external_tools:
                raise PermissionError("workflow call_tool node requires an authorized HTTP or MCP tool")
            configured = node.get("businessConfig") if isinstance(node.get("businessConfig"), dict) else {}
            wanted = str(
                configured.get("preferredToolId")
                or configured.get("externalToolId")
                or configured.get("external_tool_id")
                or configured.get("toolId")
                or configured.get("tool_id")
                or ""
            ).strip()
            if wanted:
                matched = next((tool for tool in external_tools if tool.external_tool_id == wanted), None)
                if matched is None:
                    raise PermissionError(f"workflow references unauthorized external tool: {wanted}")
                tool_name = matched.name
                validate_external_bindings(node, matched)
        capability_refs.append(binding.capability_ref)
        instruction = str(node.get("description") or node.get("title") or node_type).strip()
        line = f"{index}. {instruction}\n   - capability_ref: `{binding.capability_ref}`"
        alias = str(node.get("outputAlias") or node.get("output_alias") or "").strip()
        if alias:
            line += f"\n   - Output of this step: {alias}"
        if tool_name:
            line += f"\n   - Call tool: `{tool_name}`"
        config = node.get("businessConfig") if isinstance(node.get("businessConfig"), dict) else {}
        if binding.capability_ref == "knowledge.read_document@v1":
            line += (
                "\n   - Call arguments: "
                f"`scope={config['knowledgeScope']}`, `source_id={config['knowledgeSourceId']}`. "
                "Continue reading with `next_cursor` until `has_more=false`; never treat a retrieved excerpt as the complete document."
            )
        if node_type == "review_check":
            config = resolved_review_config(nodes, index - 1)
            if str(config.get("outputMode") or "report") in {"annotated_docx", "both"}:
                for ref in ("document.review_source@v1", "document.annotate@v1"):
                    required_tool = by_capability.get(ref)
                    if required_tool is None:
                        raise PermissionError(f"workflow review output requires unavailable capability {ref}")
                    capability_refs.append(ref)
            for guidance in review_check_guidance(config):
                line += f"\n   - {guidance}"
        if index - 1 in intermediate_nodes:
            line += "\n   - This artifact is only for later steps; pass `delivery_scope=intermediate` when calling tools and do not deliver it as a standalone attachment."
        bound_style_id = str(node.get("boundWritingSkillId") or "").strip()
        if bound_style_id:
            if node_type != "generate_content":
                raise ValueError("writing standard may only bind to a generate_content node")
            style_ref = style_refs.get(bound_style_id)
            if not style_ref:
                raise PermissionError(f"workflow writing standard is unavailable: {bound_style_id}")
            line += f"\n   - Pass `writing_style_ref={style_ref}` when generating content."
        public_config = (
            {key: value for key, value in config.items() if key != "sourceRole"}
            if node_type == "read_material" else config
        )
        if node_type == "review_check":
            public_config = {
                key: value for key, value in config.items()
                if key not in {"evidenceRequirement", "failurePolicy"}
            }
        if public_config:
            line += f"\n   - Business constraints: {json.dumps(public_config, ensure_ascii=False, sort_keys=True)}"
        rendered.append(line)
    name = str(row.get("name") or "Workflow").strip()
    description = str(row.get("description") or row.get("summary") or "").strip()
    scenario = str(row.get("notes") or row.get("applicable_scenarios") or "").strip()
    scenario_text = scenario or "Use when the user's goal matches this workflow description."
    body = f"""# {name}

## Objective
{description or name}

## Applicable Scenarios
{scenario_text}

## Suggested Steps
{chr(10).join(rendered)}

## Execution Principles
- This is an adaptive Skill for the DSH Agent Loop, not a fixed graph execution plan.
- Based on the current context, decide whether to skip, repeat, or parallelize independent steps, without crossing authorization boundaries.
- Pass search evidence, parsed attachments, and structured artifacts from earlier steps into later steps; never fabricate them again.
- Adjust to actual tool failures; never claim that an action succeeded when it did not.

## Acceptance
- Deliver all user-requested outputs and provide traceable evidence for key conclusions.
- All external write operations follow MOVO approval policy.
- Writing standards constrain content generation nodes only, not retrieval, calculation, browser, or ordinary tool calls.
"""
    return body.strip(), tuple(dict.fromkeys(capability_refs))
