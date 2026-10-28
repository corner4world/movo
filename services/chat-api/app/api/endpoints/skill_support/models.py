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



def _encode_composite_yaml(
    *,
    name: str,
    description: str,
    triggers: List[str],
    steps: List[Dict[str, Any]],
) -> str:
    """Serialize composite-skill fields as YAML frontmatter markdown.

    Mirrors ``frontend/src/api/compositeSkill.ts::encodeCompositeSkill``
    but routes through PyYAML so arbitrary strings survive safely."""
    payload: Dict[str, Any] = {"name": name}
    if description:
        payload["description"] = description
    if triggers:
        payload["triggers"] = list(triggers)
    payload["steps"] = list(steps)
    body = _yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
    return f"---\n{body}---\n"

class ApiResponse(BaseModel):
    code: int = 0
    message: Optional[str] = None
    data: Optional[object] = None


class SkillGenerateRequest(BaseModel):
    user_id: str = Field(..., description="User ID from login")
    main_id: Optional[str] = Field(None, validation_alias=AliasChoices("main_id", "mainId"), description="Tenant / main account ID")
    name: str = Field(..., description="Skill name")
    description: Optional[str] = Field(default="", description="Skill description")
    summary: Optional[str] = Field(default="", description="Short summary")
    category: Optional[str] = Field(default="document", description="Skill category")
    role: Optional[str] = Field(default=None, description="Skill role: execution/renderer/style")
    skill_type: Optional[str] = Field(default="style", description="Skill type: style/execution/renderer/composite_task")
    tags: Optional[List[str]] = Field(default_factory=list, description="Skill tags")
    visibility: Optional[str] = Field(default="private", description="Visibility")
    formats: Optional[List[str]] = Field(default_factory=list, description="Supported formats")
    notes: Optional[str] = Field(default="", description="Additional notes")
    sources: Optional[List[str]] = Field(default_factory=list, description="OSS object paths for source docs")
    resources: Optional[Dict[str, List[Dict[str, str]]]] = Field(
        default_factory=dict, description="Typed resources"
    )
    skill_markdown: Optional[str] = Field(default="", description="User provided SKILL.md")
    input_profile: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Structured user input profile")
    contract_json: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Structured skill contract")
    advanced: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Advanced settings")
    is_active: Optional[bool] = Field(default=False, description="Whether the skill is selectable")


class SkillUpdateRequest(BaseModel):
    user_id: str = Field(..., description="User ID from login")
    main_id: Optional[str] = Field(None, validation_alias=AliasChoices("main_id", "mainId"), description="Tenant / main account ID")
    name: Optional[str] = Field(None, description="Skill name")
    description: Optional[str] = Field(None, description="Skill description")
    summary: Optional[str] = Field(None, description="Short summary")
    category: Optional[str] = Field(None, description="Skill category")
    role: Optional[str] = Field(None, description="Skill role: execution/renderer/style")
    skill_type: Optional[str] = Field(None, description="Skill type: style/execution/renderer/composite_task")
    tags: Optional[List[str]] = Field(default=None, description="Skill tags")
    visibility: Optional[str] = Field(None, description="Visibility")
    formats: Optional[List[str]] = Field(default=None, description="Supported formats")
    notes: Optional[str] = Field(None, description="Additional notes")
    resources: Optional[Dict[str, List[Dict[str, str]]]] = Field(default=None, description="Typed resources")
    skill_markdown: Optional[str] = Field(None, description="Updated SKILL.md")
    input_profile: Optional[Dict[str, Any]] = Field(default=None, description="Structured user input profile")
    contract_json: Optional[Dict[str, Any]] = Field(default=None, description="Structured skill contract")
    advanced: Optional[Dict[str, Any]] = Field(default=None, description="Advanced settings")
    is_active: Optional[bool] = Field(None, description="Whether the skill is selectable")


class SkillListRequest(BaseModel):
    user_id: str = Field(..., description="User ID from login")
    main_id: Optional[str] = Field(None, validation_alias=AliasChoices("main_id", "mainId"), description="Tenant / main account ID")


class AdminShapeSkillPayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str = ""
    scenario: str = ""
    type: str = Field(default="writing_style", pattern=r"^(writing_style|workflow|ordinary)$")
    config: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = False


class SkillEnabledPayload(BaseModel):
    enabled: bool


class RecordingEventModel(BaseModel):
    type: str = Field(..., description="click | fill | navigate | select")
    url: Optional[str] = Field(default="")
    value: Optional[str] = Field(default="")
    target: Optional[Dict[str, Any]] = Field(default_factory=dict)
    instruction: Optional[str] = Field(default="")


class RecordingEditModel(BaseModel):
    op: str = Field(..., description="delete | set_instruction | set_variable")
    index: int = Field(..., ge=0)
    value: Optional[str] = Field(default=None)
    field: Optional[str] = Field(default=None)
    var: Optional[str] = Field(default=None)


class SkillFromRecordingRequest(BaseModel):
    user_id: str = Field(...)
    main_id: Optional[str] = Field(None, validation_alias=AliasChoices("main_id", "mainId"))
    name: str = Field(...)
    description: Optional[str] = Field(default="")
    triggers: Optional[List[str]] = Field(default_factory=list)
    site_profile_id: Optional[str] = Field(default="")
    events: List[RecordingEventModel] = Field(default_factory=list)
    edits: Optional[List[RecordingEditModel]] = Field(default_factory=list)
    variables: Optional[Dict[str, str]] = Field(default_factory=dict)
    visibility: Optional[str] = Field(default="private")
    is_active: Optional[bool] = Field(default=False)


class SkillEnrichRequest(BaseModel):
    user_id: str = Field(..., description="User ID from login")
    main_id: Optional[str] = Field(None, validation_alias=AliasChoices("main_id", "mainId"), description="Tenant / main account ID")
    name: str = Field(..., description="Skill name")
    description: Optional[str] = Field(default="", description="Skill description")
    skill_type: Optional[str] = Field(default="style", description="Skill type")
    input_profile: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Structured user input profile")


class WorkflowStepsGenerateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120, description="Workflow skill name")
    description: Optional[str] = Field(default="", description="Skill description")
    scenario: Optional[str] = Field(default="", description="Applicable business scenario")
    existing_steps: Optional[List[str]] = Field(default_factory=list, validation_alias=AliasChoices("existing_steps", "existingSteps"))
    max_steps: Optional[int] = Field(default=8, validation_alias=AliasChoices("max_steps", "maxSteps"))
    mode: Optional[str] = Field(default="generate", description="generate | optimize | supplement | supplement_step")
    supplement: Optional[str] = Field(default="", description="New business point to supplement into existing steps")
    node_catalog: Optional[List[Dict[str, Any]]] = Field(default_factory=list, validation_alias=AliasChoices("node_catalog", "nodeCatalog"))


class WorkflowNodesGenerateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120, description="Workflow skill name")
    description: Optional[str] = Field(default="", description="Skill description")
    scenario: Optional[str] = Field(default="", description="Applicable business scenario")
    existing_nodes: Optional[List[Dict[str, Any]]] = Field(default_factory=list, validation_alias=AliasChoices("existing_nodes", "existingNodes"))
    max_nodes: Optional[int] = Field(default=8, validation_alias=AliasChoices("max_nodes", "maxNodes"))
    mode: Optional[str] = Field(default="generate", description="generate | optimize | supplement | supplement_step")
    supplement: Optional[str] = Field(default="", description="New business point to supplement into existing nodes")
    node_catalog: Optional[List[Dict[str, Any]]] = Field(default_factory=list, validation_alias=AliasChoices("node_catalog", "nodeCatalog"))


class WorkflowNodePolishRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120, description="Workflow skill name")
    description: Optional[str] = Field(default="", description="Skill description")
    scenario: Optional[str] = Field(default="", description="Applicable business scenario")
    node: Dict[str, Any] = Field(default_factory=dict, description="Current workflow node")
    existing_nodes: Optional[List[Dict[str, Any]]] = Field(default_factory=list, validation_alias=AliasChoices("existing_nodes", "existingNodes"))
    node_catalog: Optional[List[Dict[str, Any]]] = Field(default_factory=list, validation_alias=AliasChoices("node_catalog", "nodeCatalog"))


class WorkflowLogicCheckRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120, description="Workflow skill name")
    description: Optional[str] = Field(default="", description="Skill description")
    scenario: Optional[str] = Field(default="", description="Applicable business scenario")
    steps: List[str] = Field(default_factory=list, description="Current natural language workflow steps")
    nodes: List[Dict[str, Any]] = Field(default_factory=list, description="Current semantic workflow nodes")


class ScriptPluginCheckRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=262144, description="Python script plugin code")
    node_title: Optional[str] = Field(default="", validation_alias=AliasChoices("node_title", "nodeTitle"))
    node_description: Optional[str] = Field(default="", validation_alias=AliasChoices("node_description", "nodeDescription"))


class ScriptPluginFixRequest(ScriptPluginCheckRequest):
    issues: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Current check issues")


class ScriptPluginGenerateRequest(BaseModel):
    processing_instruction: str = Field(..., min_length=1, max_length=8000, validation_alias=AliasChoices("processing_instruction", "processingInstruction"))
    node_title: Optional[str] = Field(default="", validation_alias=AliasChoices("node_title", "nodeTitle"))
    node_description: Optional[str] = Field(default="", validation_alias=AliasChoices("node_description", "nodeDescription"))
    skill_name: Optional[str] = Field(default="", validation_alias=AliasChoices("skill_name", "skillName"))
    skill_description: Optional[str] = Field(default="", validation_alias=AliasChoices("skill_description", "skillDescription"))
    scenario: Optional[str] = Field(default="", description="Applicable business scenario")
    selected_input_source: Optional[str] = Field(default="all", validation_alias=AliasChoices("selected_input_source", "selectedInputSource"))
    selected_input_types: Optional[List[str]] = Field(default_factory=list, validation_alias=AliasChoices("selected_input_types", "selectedInputTypes"))
    workflow_nodes: Optional[List[Dict[str, Any]]] = Field(default_factory=list, validation_alias=AliasChoices("workflow_nodes", "workflowNodes"))
