from __future__ import annotations
from app.infrastructure.observability.config import log_print

import ast
import asyncio
import json
import os
import re
import tempfile
import uuid
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Query, Header
from pydantic import AliasChoices, BaseModel, Field

from app.api.time_utils import utc_iso
from app.services.skill_assets.trajectory_distiller import distill_trajectory, refine_steps
from app.services.skills import user_skill_service
from app.services.org_skill_adapter import _workflow_markdown, _workflow_nodes, organization_skill_adapter
from app.services.personal_knowledge.document_selection import validate_personal_workflow_documents
from app.core.config import get_settings
from app.llm.factory import get_llm_client
from app.llm.types import Message, Role
from app.utils.oss_uploader import AliyunOSSUploader
from app.utils.uploads import read_upload_with_limit
from app.product.resource_access import filter_allowed_resource_ids
from app.api.principal import require_api_principal
from app.api.workflow_messages import localized_workflow_message
from app.api.script_validation_messages import localize_script_check
from app.api.workflow_check_messages import workflow_check_fallback, workflow_check_language_instruction

import yaml as _yaml


from .models import WorkflowLogicCheckRequest, WorkflowNodePolishRequest, WorkflowNodesGenerateRequest, WorkflowStepsGenerateRequest
from .workflow import (
    _extract_json_object,
    _extract_workflow_nodes_from_text,
    _extract_workflow_steps_from_text,
    _normalize_workflow_check_result,
    _normalize_workflow_node,
    _normalize_workflow_node_catalog,
    _resolved_workflow_node_count,
    _resolved_workflow_step_count,
)

async def _generate_workflow_steps_with_llm(payload: WorkflowStepsGenerateRequest) -> List[str]:
    name = payload.name.strip()
    description = str(payload.description or "").strip()
    scenario = str(payload.scenario or "").strip()
    max_steps = _resolved_workflow_step_count(payload)
    existing_steps = [str(item or "").strip() for item in list(payload.existing_steps or []) if str(item or "").strip()]
    mode = str(payload.mode or "generate").strip().lower()
    supplement = str(payload.supplement or "").strip()
    node_catalog = _normalize_workflow_node_catalog(payload.node_catalog)
    if mode == "supplement_step":
        existing_instruction = (
            "Do not rewrite the entire workflow. Supplement only the new business step in the current input field."
            f"Expand the user's new business point into one clearer, more complete business step ready to add to the list. New business point: {supplement or '(not provided)'}."
            "Do not rewrite existing steps, return multiple steps, or generate a full workflow."
        )
    elif mode == "supplement":
        existing_instruction = (
            "Supplement the business steps. If existing steps are present, preserve their core business intent and approximate order."
            f"Insert the user's new business point at the most suitable place; rewrite adjacent steps or add one if needed. New business point: {supplement or '(not provided)'}."
            "If there are no existing steps, generate a complete business-logic draft around the new point. Return the full updated step list, not only the added steps."
        )
    elif mode == "optimize" and existing_steps:
        existing_instruction = (
            "Optimize the existing steps. Preserve their core business intent and order. Rewrite, merge, or add detail only where wording is unclear or judgment criteria, exception handling, or output requirements are missing."
            "Do not invent an unrelated workflow. Return the complete optimized step list."
        )
    elif existing_steps:
        existing_instruction = (
            "Use the existing steps as a reference together with the Skill information to generate a complete step list. Preserve valid business intent and fill obvious gaps."
        )
    else:
        existing_instruction = "Generate initial business steps from the Skill name, description, and scenario as a complete business-logic draft."

    system_prompt = (
        "You are a senior business analyst helping nontechnical users articulate a Skill's business logic."
        "At this stage, produce a business-logic draft that can later be parsed into a structured workflow, not an executable technical workflow."
        "Use natural language to express the business goal, input boundaries, default rules, decision criteria, exception handling, and output requirements."
        "Do not decompose steps into variables, fields, forms, or node configurations or require technical knowledge from the user."
        "Each step should, ideally in one business-language sentence, state the information to examine, the decision criteria, and the intermediate conclusion."
        "For defaults, missing information, uncertain results, or abnormal changes, specify the business handling approach."
        "For dependencies on internal rules, historical standards, knowledge bases, operating standards, or meeting conclusions, say to find or confirm that source first."
        "If the source cannot be obtained, require additional user input, mark the fact unknown, or give a limited conclusion from confirmed information. Never assume the source exists or is usable."
        "Do not describe underlying tools, interfaces, APIs, databases, MCP, HTTP, field names, node links, or technical implementation."
        "Every step must be understandable to business staff and clear enough for later structured parsing."
        "Return only JSON in the form {\"steps\":[\"step 1\", \"step 2\"]}."
    )
    user_prompt = (
        f"Skill name: {name}\n"
        f"Skill description: {description or '(none)'}\n"
        f"Applicable scenario: {scenario or '(none)'}\n"
        f"Suggested maximum step count: {max_steps}\n"
        f"Generation mode: {mode}\n"
        f"Available node capability catalog: {json.dumps(node_catalog, ensure_ascii=False) if node_catalog else '(not provided)'}\n"
        f"Existing steps for reference: {json.dumps(existing_steps, ensure_ascii=False) if existing_steps else '(none)'}\n\n"
        f"{existing_instruction}\n\n"
        "Generate natural-language steps for business-logic clarification with these requirements:\n"
        "1. For supplement_step, return exactly one expanded step. Otherwise choose the count by Skill complexity: 4-5 for simple, 5-7 for ordinary, 7-9 for complex, never above the suggested maximum.\n"
        "2. Start by confirming the user's goal and input boundaries; end by defining the output.\n"
        "3. Cover scope confirmation, default rules, business decision criteria, exception or missing-information handling, conclusions, and recommendations.\n"
        "4. Where natural, each step should include at least two of: business information to examine, decision basis or threshold, handling for exceptions or gaps, and the intermediate conclusion.\n"
        "5. If the Skill description is broad, retain flexibility with business wording such as 'first clarify,' 'if not provided,' or 'choose according to the business goal.' Do not invent fixed field names.\n"
        "6. For internal rules, historical standards, knowledge bases, operating standards, or meeting conclusions, say to find or confirm them first. If unavailable, request more input or give a limited conclusion; never assume they exist.\n"
        "7. Describe how to judge and handle matters in business language. Do not mention specific tools, interfaces, system calls, parameter fields, JSON Schema, nodes, or technical terms.\n"
        "8. Make each step one sentence ready for the configuration page; it may be somewhat long, but not a multi-paragraph explanation.\n"
        "9. Use the node capability catalog only to understand platform capabilities. Do not copy catalog examples or output English node type names."
    )
    llm = get_llm_client(streaming=False, stage="admin_workflow_steps", intent="generation")
    resp = await llm.ainvoke(
        [
            Message(role=Role.SYSTEM, content=system_prompt),
            Message(role=Role.USER, content=user_prompt),
        ]
    )
    return _extract_workflow_steps_from_text(str((resp.content if resp else "") or ""), max_steps)


async def _generate_workflow_nodes_with_llm(payload: WorkflowNodesGenerateRequest) -> List[Dict[str, Any]]:
    name = payload.name.strip()
    description = str(payload.description or "").strip()
    scenario = str(payload.scenario or "").strip()
    max_nodes = _resolved_workflow_node_count(payload)
    existing_nodes = [
        node for idx, raw in enumerate(list(payload.existing_nodes or []))
        for node in [_normalize_workflow_node(raw, idx)]
        if node
    ]
    allowed_config_keys = {
        "input", "target", "method", "format", "source", "failurePolicy",
        "resourceTypes", "outputAlias", "toolId", "toolName", "toolScope",
        "sourceType", "knowledgeScope", "knowledgeSourceId",
        "reviewSubject", "reviewCriteria", "reviewSubjectNodeId", "reviewCriteriaNodeId", "reviewCriteriaMode",
        "targetName", "targetUrl",
    }
    for node in existing_nodes:
        config = node.get("businessConfig") if isinstance(node.get("businessConfig"), dict) else {}
        node["businessConfig"] = {
            key: value for key, value in config.items()
            if key in allowed_config_keys and value not in (None, "", [], {})
        }
    mode = str(payload.mode or "generate").strip().lower()
    supplement = str(payload.supplement or "").strip()
    node_catalog = _normalize_workflow_node_catalog(payload.node_catalog)
    system_prompt = (
        "You are a business-process Skill configuration assistant. Turn a nontechnical user's business intent into semantic business-step nodes."
        "These nodes strongly guide graph planning but are not a fixed execution graph. Do not generate field schemas, input/output contracts, loops, conditional branches, tool parameters, or code logic."
        "Node types may use only these English enum values: read_material, extract_resources, understand_image, extract_info, compute_metric, data_collect, browser_automation, internal_search, external_search, call_tool, "
        "script_plugin, generate_content, translate_rewrite, fill_table, review_check, export_delivery."
        "Each node describes only a business step using type, title, description, businessConfig, outputAlias, and boundWritingSkillId."
        "businessConfig may contain only business-level phrases such as input, target, method, format, source, and failurePolicy."
        "browser_automation may use targetName and targetUrl; do not add other technical parameters."
        "To extract reusable images, URLs, or attachments from documents or materials, use extract_resources and put images/urls/attachments in businessConfig.resourceTypes."
        "To understand visual content in images, screenshots, charts, or embedded document images, use understand_image, usually after extract_resources."
        "To extract semantic facts such as company names, amounts, dates, or field values from text, tables, parsed documents, or image-understanding results, use extract_info."
        "To check upstream results or deliverables item by item against existing evidence, use review_check. It guides Agent review, not a fixed loop."
        "To collect page content from a known URL or an upstream link, use data_collect; to search for unknown public information, use external_search."
        "Use call_tool for MCP, enterprise systems, or third-party tools; use internal_search for internal knowledge bases."
        "Use browser_automation to query, fill, save, submit, upload, or publish through a website or enterprise console."
        "Put the target name (for example OA) in businessConfig.targetName and its URL in businessConfig.targetUrl; leave unknown values empty."
        "The page supplies the full node capability catalog. Use scenarios there to judge node boundaries and examples only to understand style. Never copy example filenames, dates, regions, or business data into the result."
        "Return only JSON in the form {\"nodes\":[...]}."
    )
    if mode == "supplement_step":
        mode_instruction = (
            "Supplement only the single business node entered by the user. Turn the new business point into one semantic node; do not rewrite the full workflow."
            f"New business point: {supplement or '(not provided)'}"
        )
    elif mode == "optimize" and existing_nodes:
        mode_instruction = (
            "Optimize the complete current node configuration. Understand each user-entered requirement and check workflow completeness against the Skill goal."
            "You may rewrite node requirements, reorder nodes, merge duplicates, remove unnecessary nodes, or add missing nodes from the capability catalog."
            "Do not mechanically preserve the original count or order, and do not replace specific user requirements with generic catalog examples."
            "Retained nodes must keep their original ids; new nodes need unique ids such as new_node_1 and new_node_2."
        )
    else:
        mode_instruction = (
            "Generate the full business workflow from scratch. Select only necessary nodes from the capability catalog based on the Skill name, description, and scenario."
            "Write specific requirements for this Skill on every node; do not add irrelevant nodes merely to cover the catalog."
        )
    user_prompt = (
        f"Skill name: {name}\n"
        f"Skill description: {description or '(none)'}\n"
        f"Applicable scenario: {scenario or '(none)'}\n"
        f"Suggested maximum node count: {max_nodes}\n"
        f"Generation mode: {mode}\n"
        f"Available node capability catalog: {json.dumps(node_catalog, ensure_ascii=False) if node_catalog else '(not provided)'}\n"
        f"Existing nodes: {json.dumps(existing_nodes, ensure_ascii=False)}\n\n"
        f"{mode_instruction}\n\n"
        "Requirements:\n"
        "1. Ordinary workflows have 4-7 nodes; complex workflows must stay within the stated maximum.\n"
        "2. Each node description must be one sentence in business language.\n"
        "3. For complex writing, prefer stages such as read/extract/calculate or retrieve/generate/review/export.\n"
        "4. Leave boundWritingSkillId empty on content generation nodes unless a writing Skill was explicitly specified.\n"
        "5. System planning handles missing data, loops, conditions, and failure retries; do not expand them as user-configured nodes.\n"
        "6. Use short, user-understandable outputAlias values, such as campaign data, metric analysis, or review draft.\n"
        "7. description must be an executable business requirement for this Skill. Preserve user-specified files, scope, fields, standards, and outputs whenever possible.\n"
        "8. Choose only nodes needed for this Skill. In optimize mode you may add, remove, merge, and reorder nodes.\n"
        "9. Catalog examples are not current business facts. Never copy their proper names, dates, numbers, or filenames.\n"
        "10. When optimizing retained call_tool, generate_content, or browser_automation nodes, preserve still-applicable bindings: toolId, toolName, boundWritingSkillId, businessConfig.targetName, and businessConfig.targetUrl."
    )
    llm = get_llm_client(streaming=False, stage="admin_workflow_nodes", intent="generation")
    resp = await llm.ainvoke(
        [
            Message(role=Role.SYSTEM, content=system_prompt),
            Message(role=Role.USER, content=user_prompt),
        ]
    )
    from app.services.workflow_node_bindings import restore_workflow_bindings

    generated = _extract_workflow_nodes_from_text(str((resp.content if resp else "") or ""), max_nodes)
    return restore_workflow_bindings(existing_nodes, generated)


async def _polish_workflow_node_with_llm(payload: WorkflowNodePolishRequest) -> str:
    name = payload.name.strip()
    description = str(payload.description or "").strip()
    scenario = str(payload.scenario or "").strip()
    node = _normalize_workflow_node(payload.node, 0)
    if not node:
        return ""
    existing_nodes = [
        normalized for idx, raw in enumerate(list(payload.existing_nodes or []))
        for normalized in [_normalize_workflow_node(raw, idx)]
        if normalized
    ]
    node_catalog = _normalize_workflow_node_catalog(payload.node_catalog)
    node_type = str(node.get("type") or "").strip()
    catalog_item = next((item for item in node_catalog if item.get("type") == node_type), {})
    current_text = str(node.get("description") or "").strip()
    system_prompt = (
        "You refine business requirements for workflow Skill nodes."
        "Rewrite the business requirement of one node to be clearer and more actionable. Do not change business facts, node type, tool bindings, writing Skill bindings, or workflow order."
        "Do not add filenames, dates, numbers, regions, system names, metric definitions, or deliverables that the user did not provide."
        "Output JSON only, without Markdown or explanation."
    )
    user_prompt = (
        f"Skill name: {name}\n"
        f"Skill description: {description or '(none)'}\n"
        f"Applicable scenario: {scenario or '(none)'}\n"
        f"Current node: {json.dumps(node, ensure_ascii=False)}\n"
        f"Other nodes in this workflow: {json.dumps(existing_nodes, ensure_ascii=False)}\n"
        f"Capability description for this node: {json.dumps(catalog_item, ensure_ascii=False) if catalog_item else '(none)'}\n\n"
        "Refine only the current node's description, subject to these requirements:\n"
        "1. Preserve all existing business facts, scope, entities, standards, exception handling, and output requirements.\n"
        "2. If the description is too short, use the Skill goal and node capability description to make it actionable, without inventing facts.\n"
        "3. Do not output technical implementation, interface parameters, code, field schemas, loops, or branch DSL.\n"
        "4. Express the requirement in one Chinese business sentence, preferably 40-160 Chinese characters.\n"
        "5. Return JSON: {\"text\":\"refined node requirement\"}."
    )
    llm = get_llm_client(streaming=False, stage="admin_workflow_node_polish", intent="generation")
    resp = await llm.ainvoke(
        [
            Message(role=Role.SYSTEM, content=system_prompt),
            Message(role=Role.USER, content=user_prompt),
        ]
    )
    parsed = _extract_json_object(str((resp.content if resp else "") or ""))
    text = re.sub(r"\s+", " ", str(parsed.get("text") or parsed.get("description") or "").strip())[:420]
    return text or current_text


async def _check_workflow_logic_with_llm(payload: WorkflowLogicCheckRequest, accept_language: str | None = None) -> Dict[str, Any]:
    name = payload.name.strip()
    description = str(payload.description or "").strip()
    scenario = str(payload.scenario or "").strip()
    steps = [str(item or "").strip() for item in list(payload.steps or []) if str(item or "").strip()]
    nodes = [
        node for idx, raw in enumerate(list(payload.nodes or []))
        for node in [_normalize_workflow_node(raw, idx)]
        if node
    ]
    system_prompt = (
        "You are a senior business analyst evaluating whether natural-language business steps written by a nontechnical user are clear enough."
        "Do not execute the task or generate a technical workflow. Judge whether the steps are suitable input for later structured workflow parsing."
        "Base the evaluation only on the Skill name, description, scenario, and current steps. Do not invent business facts the user did not provide."
        "If a step depends on internal rules, historical standards, a knowledge base, operating standards, or meeting conclusions, check whether it says to find or confirm the source first and what to do if the source is unavailable."
        "Do not suggest technical implementations involving tools, interfaces, APIs, databases, HTTP, nodes, or field mappings."
        "Return JSON only, without Markdown or surrounding explanation."
        + workflow_check_language_instruction(accept_language)
    )
    user_prompt = (
        f"Skill name: {name}\n"
        f"Skill description: {description or '(none)'}\n"
        f"Applicable scenario: {scenario or '(none)'}\n"
        f"Current business steps: {json.dumps(steps, ensure_ascii=False)}\n"
        f"Current semantic nodes: {json.dumps(nodes, ensure_ascii=False)}\n\n"
        "Return the evaluation as JSON in this exact structure:\n"
        "{\n"
        "  \"pass\": true,\n"
        "  \"logic\": {\"label\": \"ready to parse or needs clarification\", \"level\": \"success or warning\", \"summary\": \"one-sentence overall assessment\"},\n"
        "  \"coverage\": [\n"
        "    {\"key\":\"goal\", \"label\":\"business goal\", \"covered\":true},\n"
        "    {\"key\":\"input_scope\", \"label\":\"input boundary\", \"covered\":true},\n"
        "    {\"key\":\"default_rule\", \"label\":\"default rule\", \"covered\":true},\n"
        "    {\"key\":\"decision_rule\", \"label\":\"decision criterion\", \"covered\":true},\n"
        "    {\"key\":\"exception\", \"label\":\"exception handling\", \"covered\":true},\n"
        "    {\"key\":\"output\", \"label\":\"output requirement\", \"covered\":true}\n"
        "  ],\n"
        "  \"readiness\": [\n"
        "    {\"key\":\"step_count\", \"label\":\"sufficient step count\", \"ready\":true},\n"
        "    {\"key\":\"branch_seed\", \"label\":\"recognizable default and exception branches\", \"ready\":true},\n"
        "    {\"key\":\"rule_seed\", \"label\":\"extractable business decision rules\", \"ready\":true},\n"
        "    {\"key\":\"io_seed\", \"label\":\"derivable input and output boundaries\", \"ready\":true}\n"
        "  ],\n"
        "  \"suggestions\": [\"up to five specific suggestions for missing details\"],\n"
        "  \"conclusion\": \"evaluation conclusion\"\n"
        "}\n\n"
        "Decision criteria:\n"
        "1. Set pass=true only when the business goal, input boundaries, default rules, decision criteria, exception handling, and output requirements are sufficiently clear.\n"
        "2. If a step cites an external source without explaining what to do when finding or confirming it fails, mark exception handling or default rules insufficient.\n"
        "3. Suggestions must identify what is missing and how to add it in business language; do not give technical implementation advice."
    )
    llm = get_llm_client(streaming=False, stage="admin_workflow_check", intent="evaluation")
    resp = await llm.ainvoke(
        [
            Message(role=Role.SYSTEM, content=system_prompt),
            Message(role=Role.USER, content=user_prompt),
        ]
    )
    parsed = _extract_json_object(str((resp.content if resp else "") or ""))
    return _normalize_workflow_check_result(parsed, accept_language)
