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


router = APIRouter(dependencies=[Depends(require_api_principal)])


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


async def _download_object(object_path: str) -> bytes:
    uploader = AliyunOSSUploader()
    return uploader.read_bytes(object_path)


def _extract_text_sync(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext in {".txt", ".md"}:
        try:
            return open(file_path, "r", encoding="utf-8", errors="ignore").read()
        except Exception:
            return ""
    if ext == ".pdf":
        try:
            import subprocess
            import sys

            script = os.path.join(
                os.path.dirname(__file__),
                "..",
                "..",
                "skills_specs",
                "pdf",
                "scripts",
                "extract_pdf_text.py",
            )
            script = os.path.abspath(script)
            result = subprocess.run(
                [sys.executable, script, file_path, "--max-pages", "8"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                return result.stdout
        except Exception:
            return ""
    if ext == ".docx":
        try:
            from docx import Document

            doc = Document(file_path)
            parts = [p.text for p in doc.paragraphs if p.text]
            return "\n".join(parts)
        except Exception:
            return ""
    return ""


async def _extract_text_from_object(object_path: str) -> str:
    content = await _download_object(object_path)
    filename = os.path.basename(object_path)
    suffix = os.path.splitext(filename)[1] or ".bin"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        return await asyncio.to_thread(_extract_text_sync, tmp_path)
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass


def _truncate(text: str, limit: int = 20000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit]


def _estimate_workflow_step_count(payload: WorkflowStepsGenerateRequest) -> int:
    existing_steps = [str(item or "").strip() for item in list(payload.existing_steps or []) if str(item or "").strip()]
    if existing_steps:
        base = len(existing_steps)
        mode = str(payload.mode or "generate").strip().lower()
        if mode == "optimize":
            return max(4, min(base, 10))
        if mode == "supplement":
            return max(4, min(base + 1, 10))
        if mode == "supplement_step":
            return 1
        return max(4, min(base, 10))

    text = " ".join(
        [
            str(payload.name or "").strip(),
            str(payload.description or "").strip(),
            str(payload.scenario or "").strip(),
            str(payload.supplement or "").strip(),
        ]
    )
    complexity_score = 0
    text_length = len(text)
    if text_length >= 80:
        complexity_score += 1
    if text_length >= 180:
        complexity_score += 1
    if text_length >= 320:
        complexity_score += 1

    complexity_keywords = [
        "多",
        "多个",
        "跨",
        "并行",
        "协同",
        "审批",
        "汇总",
        "复盘",
        "分析",
        "诊断",
        "策略",
        "区域",
        "门店",
        "团队",
        "客户",
        "经营",
        "异常",
        "规则",
        "判断",
        "分支",
        "例外",
        "风险",
        "预警",
        "对比",
        "跟进",
        "闭环",
        "workflow",
    ]
    keyword_hits = sum(1 for token in complexity_keywords if token in text)
    complexity_score += min(keyword_hits // 2, 4)

    target = 4 + complexity_score
    return max(4, min(target, 9))


def _resolved_workflow_step_count(payload: WorkflowStepsGenerateRequest) -> int:
    if payload.max_steps is None:
        return _estimate_workflow_step_count(payload)
    return max(4, min(int(payload.max_steps), 10))


def _resolved_workflow_node_count(payload: WorkflowNodesGenerateRequest) -> int:
    if payload.max_nodes is None:
        return 8
    return max(4, min(int(payload.max_nodes), 12))


def _safe_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "on"}:
        return True
    if text in {"false", "0", "no", "off"}:
        return False
    return default


def _time_text(value: Any) -> str:
    return utc_iso(value)


def _workflow_text_steps(config: Dict[str, Any]) -> List[str]:
    raw_steps = config.get("workflowSteps") or config.get("workflow_steps")
    if not isinstance(raw_steps, list):
        return []
    steps: List[str] = []
    for item in raw_steps:
        if isinstance(item, dict):
            text = str(item.get("text") or item.get("description") or "").strip()
        else:
            text = str(item or "").strip()
        if text:
            steps.append(text)
    return steps


def _admin_shape_payload_to_user_payload(
    payload: AdminShapeSkillPayload,
    *,
    user_id: str,
    main_id: str,
) -> Dict[str, Any]:
    skill_type = str(payload.type or "writing_style").strip().lower()
    config = _safe_dict(payload.config)
    name = str(payload.name or "").strip()
    description = str(payload.description or "").strip()
    scenario = str(payload.scenario or "").strip()
    enabled = bool(payload.enabled)

    if skill_type == "workflow":
        nodes = _workflow_nodes(config)
        steps = [
            str(node.get("description") or "").strip()
            for node in nodes
            if str(node.get("description") or "").strip()
        ] or _workflow_text_steps(config)
        skill_markdown = _workflow_markdown(
            name=name,
            description=description,
            scenario=scenario,
            steps=steps,
            nodes=nodes,
        )
        contract_json = {
            "skill_type": "composite_task",
            "name": name,
            "summary": description or scenario,
            "applicable_scenarios": scenario,
            "notes": description,
        }
        return {
            "user_id": user_id,
            "main_id": main_id,
            "name": name,
            "description": description,
            "summary": description or scenario,
            "category": "Workflow",
            "role": "execution",
            "skill_type": "composite_task",
            "tags": ["workflow"],
            "visibility": "private",
            "formats": ["markdown"],
            "notes": scenario,
            "input_profile": contract_json,
            "contract_json": contract_json,
            "skill_markdown": skill_markdown,
            "resources": {},
            "advanced": {},
            "is_active": enabled,
            "type": "workflow",
            "config": config,
            "scenario": scenario,
            "enabled": enabled,
        }

    contract_json = _safe_dict(config.get("contractJson") or config.get("contract_json"))
    input_profile = _safe_dict(config.get("inputProfile") or config.get("input_profile")) or contract_json
    skill_markdown = str(config.get("skillMarkdown") or config.get("skill_markdown") or "").strip()
    return {
        "user_id": user_id,
        "main_id": main_id,
        "name": name,
        "description": description,
        "summary": description or scenario,
        "category": "Writing Guidelines",
        "role": "style",
        "skill_type": "style",
        "tags": ["writing_style"],
        "visibility": "private",
        "formats": ["markdown"],
        "notes": scenario,
        "input_profile": input_profile,
        "contract_json": contract_json,
        "skill_markdown": skill_markdown,
        "resources": {},
        "advanced": {},
        "is_active": enabled,
        "type": "writing_style",
        "config": config,
        "scenario": scenario,
        "enabled": enabled,
    }


def _admin_shape_skill(skill: Dict[str, Any]) -> Dict[str, Any]:
    from app.services.skill_lifecycle import SkillLifecycleService

    lifecycle = SkillLifecycleService()
    skill = lifecycle.display_snapshot(skill)
    config = _safe_dict(skill.get("config"))
    raw_type = str(skill.get("type") or "").strip().lower()
    if raw_type not in {"writing_style", "workflow", "ordinary", "expert_package"}:
        normalized_skill_type = str(skill.get("skill_type") or "").strip().lower()
        raw_type = "workflow" if normalized_skill_type == "composite_task" else "ordinary" if normalized_skill_type in {"ordinary", "execution"} else "writing_style"
    if not config:
        if raw_type == "writing_style":
            config = {
                "inputProfile": _safe_dict(skill.get("input_profile")),
                "contractJson": _safe_dict(skill.get("contract_json")),
                "skillMarkdown": str(skill.get("skill_markdown") or ""),
            }
        else:
            config = {}
    return {
        "id": str(skill.get("id") or skill.get("_id") or ""),
        "mainId": str(skill.get("main_id") or skill.get("mainId") or "default"),
        "name": str(skill.get("name") or ""),
        "description": str(skill.get("description") or ""),
        "scenario": str(skill.get("scenario") or skill.get("notes") or ""),
        "type": raw_type,
        "config": config,
        "enabled": _safe_bool(skill.get("enabled"), _safe_bool(skill.get("is_active"), True)),
        "createdAt": _time_text(skill.get("created_at")),
        "updatedAt": _time_text(skill.get("updated_at")),
        "packageSource": _safe_dict(skill.get("package_source")),
        "distributionId": str(skill.get("distribution_id") or ""),
        "feedback": _safe_dict(skill.get("feedback")),
        "locallyModified": bool(skill.get("locally_modified", False)),
        "lifecycle": lifecycle.lifecycle_view(skill),
        "package": {
            "slug": str(skill.get("package_slug") or ""),
            "version": str(skill.get("package_version") or ""),
            "digest": str(skill.get("package_digest") or ""),
            "files": list(skill.get("package_files") or []),
            "warnings": list(skill.get("package_warnings") or []),
            "kind": str(skill.get("package_kind") or raw_type or "ordinary"),
            "children": list(skill.get("package_children") or []),
        } if skill.get("package_id") else None,
    }


def _selectable_skill_type(skill: Dict[str, Any]) -> str:
    raw_type = str(skill.get("type") or "").strip().lower()
    if raw_type in {"writing_style", "workflow", "ordinary", "expert_package"}:
        return raw_type
    return "workflow" if str(skill.get("skill_type") or "").strip().lower() == "composite_task" else "writing_style"


def _skill_source_scope(skill: Dict[str, Any]) -> str:
    visibility = str(skill.get("visibility") or "").strip().lower()
    owner = str(skill.get("user_id") or "").strip().lower()
    skill_id = str(skill.get("id") or skill.get("_id") or "").strip()
    if visibility == "organization" or owner == "organization" or skill_id.startswith("org_skill:"):
        return "organization"
    return "user"


def _selectable_skill_item(skill: Dict[str, Any]) -> Dict[str, Any]:
    source_scope = _skill_source_scope(skill)
    return {
        "id": str(skill.get("id") or skill.get("_id") or ""),
        "mainId": str(skill.get("main_id") or skill.get("mainId") or "default"),
        "name": str(skill.get("name") or ""),
        "description": str(skill.get("description") or skill.get("summary") or ""),
        "scenario": str(skill.get("scenario") or skill.get("notes") or ""),
        "type": _selectable_skill_type(skill),
        "sourceScope": source_scope,
        "enabled": _safe_bool(skill.get("enabled"), _safe_bool(skill.get("is_active"), True)),
        "updatedAt": _time_text(skill.get("updated_at")),
    }


def _matches_skill_keyword(skill: Dict[str, Any], keyword: str) -> bool:
    query = str(keyword or "").strip().lower()
    if not query:
        return True
    haystack = "\n".join(
        str(skill.get(key) or "")
        for key in ("name", "description", "summary", "scenario", "notes")
    ).lower()
    return query in haystack


def _cursor_offset(cursor: str | None) -> int:
    try:
        return max(0, int(str(cursor or "0").strip() or "0"))
    except Exception:
        return 0


def _extract_workflow_steps_from_text(text: str, max_steps: int) -> List[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    candidates = [raw]
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        candidates.insert(0, match.group(0))
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        raw_steps: Any = parsed.get("steps") if isinstance(parsed, dict) else parsed
        if not isinstance(raw_steps, list):
            continue
        steps: List[str] = []
        for item in raw_steps:
            if isinstance(item, dict):
                value = item.get("text") or item.get("step") or item.get("instruction") or ""
            else:
                value = item
            value = re.sub(r"\s+", " ", str(value or "")).strip()
            value = re.sub(r"^\d+[\.、\)]\s*", "", value).strip()
            if value:
                steps.append(value[:360])
        if steps:
            return steps[:max_steps]
    steps = []
    for line in raw.splitlines():
        value = re.sub(r"^\s*(?:[-*]|\d+[\.、\)])\s*", "", line).strip()
        if value:
            steps.append(value[:360])
    return steps[:max_steps]


def _extract_json_object(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    candidates = [raw]
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        candidates.insert(0, match.group(0))
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


_WORKFLOW_NODE_TYPES = {
    "read_material",
    "extract_resources",
    "understand_image",
    "extract_info",
    "compute_metric",
    "data_collect",
    "browser_automation",
    "internal_search",
    "external_search",
    "call_tool",
    "script_plugin",
    "generate_content",
    "translate_rewrite",
    "fill_table",
    "review_check",
    "export_delivery",
}

_NODE_TYPE_ALIASES = {
    "读取材料": "read_material",
    "文档读取": "read_material",
    "提取资源": "extract_resources",
    "资源提取": "extract_resources",
    "提取图片": "extract_resources",
    "提取链接": "extract_resources",
    "提取附件": "extract_resources",
    "图片理解": "understand_image",
    "图像理解": "understand_image",
    "多模态理解": "understand_image",
    "图片识别": "understand_image",
    "识图": "understand_image",
    "文档抽取": "extract_info",
    "抽取信息": "extract_info",
    "信息抽取": "extract_info",
    "统计计算": "compute_metric",
    "指标计算": "compute_metric",
    "数据采集": "data_collect",
    "网页采集": "data_collect",
    "链接采集": "data_collect",
    "浏览器自动化": "browser_automation",
    "浏览器操作": "browser_automation",
    "网页操作": "browser_automation",
    "内部知识搜索": "internal_search",
    "知识检索": "internal_search",
    "外部搜索": "external_search",
    "公网搜索": "external_search",
    "调用工具": "call_tool",
    "MCP工具": "call_tool",
    "MCP 工具": "call_tool",
    "脚本插件": "script_plugin",
    "插件脚本": "script_plugin",
    "运行脚本": "script_plugin",
    "代码插件": "script_plugin",
    "生成内容": "generate_content",
    "内容生成": "generate_content",
    "翻译改写": "translate_rewrite",
    "翻译": "translate_rewrite",
    "文档翻译": "translate_rewrite",
    "填表制表": "fill_table",
    "校验复核": "review_check",
    "审核检查": "review_check",
    "复核检查": "review_check",
    "导出交付": "export_delivery",
    "导出": "export_delivery",
}


def _normalize_workflow_node_type(value: Any, fallback: str = "generate_content") -> str:
    token = str(value or "").strip()
    if token in _WORKFLOW_NODE_TYPES:
        return token
    lowered = token.lower()
    if lowered in _WORKFLOW_NODE_TYPES:
        return lowered
    return _NODE_TYPE_ALIASES.get(token, fallback)


def _normalize_workflow_node_catalog(raw_items: Any) -> List[Dict[str, str]]:
    catalog: List[Dict[str, str]] = []
    if not isinstance(raw_items, list):
        return catalog
    for raw in raw_items[:30]:
        if not isinstance(raw, dict):
            continue
        node_type = str(raw.get("type") or "").strip()
        if node_type not in _WORKFLOW_NODE_TYPES:
            continue
        catalog.append({
            "type": node_type,
            "name": re.sub(r"\s+", " ", str(raw.get("name") or raw.get("label") or node_type).strip())[:80],
            "usageDescription": re.sub(r"\s+", " ", str(raw.get("usageDescription") or raw.get("usage_description") or "").strip())[:600],
            "usageExample": re.sub(r"\s+", " ", str(raw.get("usageExample") or raw.get("usage_example") or "").strip())[:600],
        })
    return catalog


def _normalize_workflow_node(raw: Any, index: int) -> Dict[str, Any] | None:
    if isinstance(raw, str):
        raw = {"description": raw}
    if not isinstance(raw, dict):
        return None
    node_type = _normalize_workflow_node_type(raw.get("type") or raw.get("node_type"))
    title = re.sub(r"\s+", " ", str(raw.get("title") or raw.get("name") or "").strip())[:80]
    description = re.sub(
        r"\s+",
        " ",
        str(raw.get("description") or raw.get("instruction") or raw.get("text") or "").strip(),
    )[:420]
    if not description and title:
        description = title
    if not title and description:
        title = description[:48]
    if not description:
        return None
    business_config = raw.get("businessConfig") or raw.get("business_config") or {}
    if not isinstance(business_config, dict):
        business_config = {}
    output_alias = str(raw.get("outputAlias") or raw.get("output_alias") or business_config.get("outputAlias") or business_config.get("output_alias") or "").strip()[:80]
    bound_writing_skill_id = str(raw.get("boundWritingSkillId") or raw.get("bound_writing_skill_id") or "").strip()[:120]
    return {
        "id": str(raw.get("id") or f"node_{index + 1}"),
        "type": node_type,
        "title": title,
        "description": description,
        "businessConfig": business_config,
        "boundWritingSkillId": bound_writing_skill_id,
        "outputAlias": output_alias,
    }


def _extract_workflow_nodes_from_text(text: str, max_nodes: int) -> List[Dict[str, Any]]:
    raw = str(text or "").strip()
    if not raw:
        return []
    candidates = [raw]
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        candidates.insert(0, match.group(0))
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        raw_nodes = parsed.get("nodes") if isinstance(parsed, dict) else parsed
        if not isinstance(raw_nodes, list):
            continue
        nodes = [_normalize_workflow_node(item, idx) for idx, item in enumerate(raw_nodes)]
        nodes = [item for item in nodes if item]
        if nodes:
            return nodes[:max_nodes]
    return []


def _normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    return text in {"true", "1", "yes", "y", "是", "已覆盖", "可解析", "通过"}


def _normalize_workflow_check_result(payload: Dict[str, Any], accept_language: str | None = None) -> Dict[str, Any]:
    logic = payload.get("logic") if isinstance(payload.get("logic"), dict) else {}
    coverage = payload.get("coverage") if isinstance(payload.get("coverage"), list) else []
    readiness = payload.get("readiness") if isinstance(payload.get("readiness"), list) else []
    suggestions = payload.get("suggestions") if isinstance(payload.get("suggestions"), list) else []
    normalized_coverage = []
    for item in coverage:
        if not isinstance(item, dict):
            continue
        normalized_coverage.append({
            "key": str(item.get("key") or ""),
            "label": str(item.get("label") or ""),
            "covered": _normalize_bool(item.get("covered")),
        })
    normalized_readiness = []
    for item in readiness:
        if not isinstance(item, dict):
            continue
        normalized_readiness.append({
            "key": str(item.get("key") or ""),
            "label": str(item.get("label") or ""),
            "ready": _normalize_bool(item.get("ready")),
        })
    return {
        "pass": _normalize_bool(payload.get("pass")),
        "logic": {
            "label": str(logic.get("label") or workflow_check_fallback("logic_label", accept_language))[:40],
            "level": "success" if str(logic.get("level") or "").lower() == "success" else "warning",
            "summary": str(logic.get("summary") or workflow_check_fallback("logic_summary", accept_language))[:320],
        },
        "coverage": normalized_coverage[:8],
        "readiness": normalized_readiness[:8],
        "suggestions": [str(item or "").strip()[:220] for item in suggestions if str(item or "").strip()][:5],
        "conclusion": str(payload.get("conclusion") or workflow_check_fallback("conclusion", accept_language))[:320],
    }


_SCRIPT_PLUGIN_ALLOWED_IMPORT_ROOTS = {"json", "os", "re", "shutil", "zipfile", "csv", "math", "statistics", "datetime", "collections", "docx", "openpyxl", "pptx", "urllib"}
_SCRIPT_PLUGIN_ALLOWED_IMPORT_MODULES = {"urllib.parse"}
_SCRIPT_PLUGIN_DENIED_IMPORT_ROOTS = {
    "subprocess", "socket", "requests", "http", "ftplib", "smtplib", "paramiko", "asyncio",
    "multiprocessing", "threading", "ctypes", "sys", "pathlib", "importlib", "builtins",
}
_SCRIPT_PLUGIN_DENIED_CALLS = {"eval", "exec", "compile", "__import__", "input", "breakpoint", "globals", "locals", "vars"}
_SCRIPT_PLUGIN_DENIED_FULL_CALLS = {
    "os.system", "os.popen", "os.spawn", "os.fork", "os.execv", "os.execve",
    "os.remove", "os.unlink", "os.rmdir", "os.removedirs", "os.chdir", "os.chmod", "os.chown",
    "os.kill", "os.killpg", "shutil.rmtree",
}
_SCRIPT_PLUGIN_WRITE_FUNCS = {"open", "copyfile", "copy", "copy2", "move"}
_SCRIPT_PLUGIN_CODE_MAX_BYTES = 200 * 1024


def _script_issue(level: str, code: str, message: str, line: int | None = None) -> Dict[str, Any]:
    return {"level": level, "code": code, "message": message, "line": line}


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _literal_string(node: ast.AST | None) -> str:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else ""


def _is_allowed_script_import(module_name: str) -> bool:
    if not module_name:
        return False
    root = module_name.split(".")[0]
    if module_name in _SCRIPT_PLUGIN_ALLOWED_IMPORT_MODULES:
        return True
    if root == "urllib":
        return False
    return root in _SCRIPT_PLUGIN_ALLOWED_IMPORT_ROOTS and root not in _SCRIPT_PLUGIN_DENIED_IMPORT_ROOTS


def _looks_like_output_dir_expr(node: ast.AST | None, safe_names: set[str] | None = None) -> bool:
    safe_names = safe_names or set()
    if node is None:
        return False
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "context":
        return _literal_string(node.slice) == "output_dir"
    if isinstance(node, ast.Call) and _call_name(node.func).endswith(".get"):
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == "context":
            return bool(node.args and _literal_string(node.args[0]) == "output_dir")
    if isinstance(node, ast.Name):
        return node.id in {"out_dir", "output_dir"} or node.id in safe_names
    if isinstance(node, ast.Call) and _call_name(node.func) in {"os.path.join", "join"}:
        return bool(node.args and _looks_like_output_dir_expr(node.args[0], safe_names))
    return False


def _assign_target_names(node: ast.AST) -> List[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, (ast.Tuple, ast.List)):
        names: List[str] = []
        for item in node.elts:
            names.extend(_assign_target_names(item))
        return names
    return []


def _collect_output_path_names(tree: ast.AST) -> set[str]:
    safe_names: set[str] = set()
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                if _looks_like_output_dir_expr(node.value, safe_names):
                    for target in node.targets:
                        for name in _assign_target_names(target):
                            if name not in safe_names:
                                safe_names.add(name)
                                changed = True
            elif isinstance(node, ast.AnnAssign):
                if _looks_like_output_dir_expr(node.value, safe_names):
                    for name in _assign_target_names(node.target):
                        if name not in safe_names:
                            safe_names.add(name)
                            changed = True
    return safe_names


def _is_import_only_try(node: ast.Try) -> bool:
    def _safe_try_body_item(item: ast.AST) -> bool:
        return isinstance(item, (ast.Import, ast.ImportFrom))

    def _safe_handler_item(item: ast.AST) -> bool:
        if isinstance(item, ast.Assign):
            return all(isinstance(target, ast.Name) for target in item.targets) and isinstance(item.value, (ast.Constant, ast.Name))
        return isinstance(item, ast.Pass)

    return (
        bool(node.handlers)
        and all(_safe_try_body_item(item) for item in node.body)
        and not node.orelse
        and not node.finalbody
        and all(all(_safe_handler_item(item) for item in handler.body) for handler in node.handlers)
    )


def _validate_script_plugin_static(code: str) -> Dict[str, Any]:
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    raw = str(code or "")
    if len(raw.encode("utf-8")) > _SCRIPT_PLUGIN_CODE_MAX_BYTES:
        errors.append(_script_issue("error", "CODE_TOO_LARGE", "脚本代码不能超过 200KB。"))
    try:
        tree = ast.parse(raw)
    except SyntaxError as exc:
        errors.append(_script_issue("error", "SYNTAX_ERROR", f"Python 语法错误：{exc.msg}", exc.lineno))
        return {"pass": False, "rulePass": False, "errors": errors, "warnings": warnings, "llm": None}

    output_path_names = _collect_output_path_names(tree)
    run_defs = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "run"]
    if not run_defs:
        errors.append(_script_issue("error", "MISSING_RUN", "必须定义入口函数 def run(inputs, context):。"))
        run_def = None
    else:
        run_def = run_defs[0]
        arg_names = [arg.arg for arg in run_def.args.args]
        if isinstance(run_def, ast.AsyncFunctionDef):
            errors.append(_script_issue("error", "ASYNC_RUN", "run 入口必须是普通函数，不能使用 async def。", run_def.lineno))
        if arg_names[:2] != ["inputs", "context"]:
            errors.append(_script_issue("error", "RUN_SIGNATURE", "run 函数前两个参数必须是 inputs, context。", run_def.lineno))
        if not any(isinstance(node, ast.Return) for node in ast.walk(run_def)):
            errors.append(_script_issue("error", "MISSING_RETURN", "run 函数必须 return 一个 dict，通常包含 artifacts 和 logs。", run_def.lineno))

    for node in tree.body:
        if isinstance(node, (ast.Expr, ast.For, ast.While, ast.With, ast.Try, ast.If)):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                continue
            if isinstance(node, ast.Try) and _is_import_only_try(node):
                continue
            errors.append(_script_issue("error", "TOP_LEVEL_EXECUTION", "禁止在顶层直接执行业务逻辑，请放到 run(inputs, context) 或辅助函数中。", getattr(node, "lineno", None)))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if not _is_allowed_script_import(alias.name):
                    errors.append(_script_issue("error", "DENIED_IMPORT", f"不允许导入模块：{alias.name}。", node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if not _is_allowed_script_import(node.module or ""):
                errors.append(_script_issue("error", "DENIED_IMPORT", f"不允许 from {node.module or ''} import ...。", node.lineno))
        elif isinstance(node, ast.Call):
            name = _call_name(node.func)
            short = name.split(".")[-1]
            if short in _SCRIPT_PLUGIN_DENIED_CALLS:
                errors.append(_script_issue("error", "DENIED_CALL", f"不允许调用危险函数：{short}。", node.lineno))
            if name in _SCRIPT_PLUGIN_DENIED_FULL_CALLS:
                errors.append(_script_issue("error", "DENIED_CALL", f"不允许调用危险系统函数：{name}。", node.lineno))
            if name in {"open", "io.open"}:
                mode = _literal_string(node.args[1] if len(node.args) > 1 else None) or _literal_string(next((kw.value for kw in node.keywords if kw.arg == "mode"), None))
                if any(flag in mode for flag in ("w", "a", "x", "+")) and not _looks_like_output_dir_expr(node.args[0] if node.args else None, output_path_names):
                    warnings.append(_script_issue("warning", "WRITE_PATH_REVIEW", "写文件路径应来自 context['output_dir']。请确认没有写到输入目录或固定绝对路径。", node.lineno))
            if name in {"shutil.copyfile", "shutil.copy", "shutil.copy2", "shutil.move"} and len(node.args) >= 2:
                if not _looks_like_output_dir_expr(node.args[1], output_path_names):
                    warnings.append(_script_issue("warning", "OUTPUT_PATH_REVIEW", "输出文件目标路径建议使用 os.path.join(context['output_dir'], filename)。", node.lineno))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if re.match(r"^/(Users|var|tmp|etc|private|home|root)/", node.value):
                warnings.append(_script_issue("warning", "ABSOLUTE_PATH_LITERAL", "脚本中出现固定绝对路径，插件运行时通常不可访问。", getattr(node, "lineno", None)))

    if raw.count("context[\"output_dir\"]") + raw.count("context['output_dir']") + raw.count("context.get(\"output_dir\")") + raw.count("context.get('output_dir')") == 0:
        warnings.append(_script_issue("warning", "OUTPUT_DIR_NOT_REFERENCED", "未明显使用 context['output_dir']，如果要生成文件，必须写入该目录。"))
    if "\"artifacts\"" not in raw and "'artifacts'" not in raw and "\"files\"" not in raw and "'files'" not in raw:
        warnings.append(_script_issue("warning", "OUTPUT_FILES_NOT_REFERENCED", "未明显返回 files/artifacts；如果该节点要导出文件，后续导出节点可能拿不到文件。"))
    return {"pass": not errors, "rulePass": not errors, "errors": errors[:50], "warnings": warnings[:50], "llm": None}


def _normalize_script_llm_review(payload: Dict[str, Any], accept_language: str | None = None) -> Dict[str, Any]:
    risks = payload.get("risks") if isinstance(payload.get("risks"), list) else []
    suggestions = payload.get("suggestions") if isinstance(payload.get("suggestions"), list) else []
    return {
        "pass": _normalize_bool(payload.get("pass")),
        "level": str(payload.get("level") or "warning")[:20],
        "summary": str(payload.get("summary") or workflow_check_fallback("script_review_summary", accept_language))[:320],
        "risks": [str(item or "").strip()[:220] for item in risks if str(item or "").strip()][:8],
        "suggestions": [str(item or "").strip()[:220] for item in suggestions if str(item or "").strip()][:8],
    }


def _generated_code_hardcode_warnings(code: str, instruction: str) -> List[Dict[str, Any]]:
    warnings: List[Dict[str, Any]] = []
    instruction_text = str(instruction or "")
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return warnings
    generic_terms = {
        "未检测到可处理的文件",
        "处理完成",
        "处理失败",
        "输入为空",
        "输出文件",
        "处理结果",
        "数据处理结果",
        "无法打开文件",
        "保存文件失败",
    }
    seen: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        text = re.sub(r"\s+", "", node.value)
        if len(text) < 8 or not re.search(r"[\u4e00-\u9fff]", text):
            continue
        if text in seen or text in generic_terms or text in instruction_text:
            continue
        if re.search(r"(中心|公司|项目|白皮书|报告|发稿|统计|客户|定版|原版|\d{4}年|\d{8})", text):
            warnings.append(_script_issue("warning", "POSSIBLE_HARDCODED_CASE", f"生成代码包含处理要求之外的疑似业务硬编码：{text[:60]}。", getattr(node, "lineno", None)))
            seen.add(text)
        if len(warnings) >= 8:
            break
    return warnings


async def _review_script_plugin_with_llm(payload: ScriptPluginCheckRequest, static_result: Dict[str, Any], accept_language: str | None = None) -> Dict[str, Any]:
    system_prompt = (
        "You review script plugins for code standards and business risks only; do not execute the code."
        "The plugin must define run(inputs, context), prefer files/documents/images/urls/texts/tables/data from inputs['selected'], write output to context['output_dir'], and return a dict."
        "Focus on possible file or image loss, missing returned artifacts, inadequate exception handling, and mismatches between business intent and script logic."
        "Do not suggest networking or external dependencies. Return JSON only."
        + workflow_check_language_instruction(accept_language)
    )
    user_prompt = (
        f"Node title: {payload.node_title or '(none)'}\n"
        f"Node description: {payload.node_description or '(none)'}\n"
        f"Rule check result: {json.dumps(static_result, ensure_ascii=False)}\n"
        f"Script code:\n{payload.code[:12000]}\n\n"
        "Return JSON: {\"pass\": true, \"level\": \"success|warning\", \"summary\": \"one-sentence conclusion\", \"risks\": [], \"suggestions\": []}"
    )
    llm = get_llm_client(streaming=False, stage="script_plugin_check", intent="classification")
    resp = await llm.ainvoke([
        Message(role=Role.SYSTEM, content=system_prompt),
        Message(role=Role.USER, content=user_prompt),
    ])
    return _normalize_script_llm_review(_extract_json_object(str((resp.content if resp else "") or "")), accept_language)


async def _fix_script_plugin_with_llm(payload: ScriptPluginFixRequest, static_result: Dict[str, Any]) -> Dict[str, Any]:
    system_prompt = (
        "You repair Python script plugins. Make the smallest changes needed to satisfy platform script-plugin rules."
        "Preserve the original business logic; do not rewrite it as a different program."
        "Rules: define def run(inputs, context); prefer files/documents/images/urls/texts/tables/data from inputs['selected'];"
        "write output files only to context['output_dir']; return a dict containing files/data/logs or artifacts/data/logs."
        "Do not use networking, subprocesses, eval/exec, fixed local paths, or dangerous operations such as os.remove/os.unlink/shutil.rmtree."
        "python-docx XML operations such as parent.remove(element) are allowed."
        "Prefer importing optional dependencies inside run, or wrap only imports in top-level try/except ImportError; never process data at module scope."
        "Output path variables must derive directly or indirectly from context['output_dir'], for example output_dir = context.get('output_dir'); out_path = os.path.join(output_dir, filename)."
        "Return only JSON: {\"code\":\"complete repaired code\", \"notes\":[\"change description\"]}."
    )
    issues = payload.issues or []
    user_prompt = (
        f"Node title: {payload.node_title or '(none)'}\n"
        f"Node description: {payload.node_description or '(none)'}\n"
        f"Current rule check result: {json.dumps(static_result, ensure_ascii=False)}\n"
        f"Issues shown to the user: {json.dumps(issues, ensure_ascii=False)}\n"
        f"Original code:\n{payload.code[:20000]}\n\n"
        "Repair the code under these requirements:\n"
        "1. Change only violations and clear I/O contract mismatches where possible.\n"
        "2. Do not remove valid python-docx XML operations such as parent.remove(element).\n"
        "3. If top-level try/except imports dependencies, prefer moving them inside run or keep an ImportError fallback containing only imports and assignments.\n"
        "4. Keep an output-path variable if it derives from context['output_dir'], or rewrite it slightly for clarity.\n"
        "5. Return complete paste-ready code, without Markdown."
    )
    llm = get_llm_client(streaming=False, stage="script_plugin_fix", intent="generation")
    resp = await llm.ainvoke([
        Message(role=Role.SYSTEM, content=system_prompt),
        Message(role=Role.USER, content=user_prompt),
    ])
    parsed = _extract_json_object(str((resp.content if resp else "") or ""))
    fixed_code = str(parsed.get("code") or "").strip()
    notes = parsed.get("notes") if isinstance(parsed.get("notes"), list) else []
    return {
        "code": fixed_code,
        "notes": [str(item or "").strip()[:300] for item in notes if str(item or "").strip()][:10],
    }


async def _generate_script_plugin_with_llm(payload: ScriptPluginGenerateRequest) -> Dict[str, Any]:
    input_types = [str(item or "").strip() for item in list(payload.selected_input_types or []) if str(item or "").strip()]
    nodes = []
    for item in list(payload.workflow_nodes or [])[:20]:
        if not isinstance(item, dict):
            continue
        config = item.get("businessConfig") if isinstance(item.get("businessConfig"), dict) else {}
        nodes.append(
            {
                "type": str(item.get("type") or "")[:80],
                "title": str(item.get("title") or "")[:160],
                "outputAlias": str(item.get("outputAlias") or config.get("outputAlias") or "")[:120],
            }
        )
    system_prompt = (
        "You generate Python code for the platform's data-processing node."
        "Produce complete paste-ready script-plugin code from the business description and return JSON only."
        "The script must define def run(inputs, context): and must not execute business logic at module scope."
        "At runtime, read data only from inputs and context; prefer files/documents/images/urls/texts/tables/data from inputs.get('selected')."
        "Write output files only to context['output_dir'], using os.path.join(context['output_dir'], filename) for paths."
        "Return a dict, preferably {\"files\": [{\"path\": filename_or_full_path, \"type\": extension}], \"data\": {}, \"logs\": []}."
        "Do not use networking, subprocesses, eval/exec, fixed local paths, delete system files, or modify input files."
        "Generate business logic only from the user's processing requirements; do not introduce specific customer names, project names, titles, dates, or case names absent from them."
        "If requirements are unclear, generate robust general-purpose processing code with clear logs; do not invent external data."
        "You may use common standard libraries and platform document libraries such as python-docx, openpyxl, python-pptx, and pypdf."
        "Do not put business execution code such as try/if/for/with at module scope; import optional dependencies inside run with a fallback."
        "Return only JSON: {\"code\":\"complete Python code\", \"notes\":[\"explanation\"]}."
    )
    user_prompt = (
        f"Processing requirement: {payload.processing_instruction.strip()}\n"
        f"Current node title: {payload.node_title or '(none)'}\n"
        f"Input source configuration: {payload.selected_input_source or 'all'}\n"
        f"Input type configuration: {json.dumps(input_types or ['files', 'documents', 'images', 'urls', 'texts', 'data'], ensure_ascii=False)}\n"
        f"Simplified workflow context: {json.dumps(nodes, ensure_ascii=False)[:4000]}\n\n"
        "Generate code for the data-processing node under these requirements:\n"
        "1. Use inputs['selected'] as the main input adapter; do not require the user to know upstream filenames.\n"
        "2. Guard against empty files/images/texts/urls/documents/data.\n"
        "3. If generating files, use safe fixed business filenames, not absolute paths from the user's machine.\n"
        "4. For DOCX processing, preserve images and prefer python-docx rather than converting through Markdown.\n"
        "5. Do not hard-code customer names, project names, official titles, or dates absent from the requirements into code or output filenames.\n"
        "6. Return complete Python code without Markdown fences."
    )
    llm = get_llm_client(streaming=False, stage="script_plugin_generate", intent="generation")
    resp = await llm.ainvoke([
        Message(role=Role.SYSTEM, content=system_prompt),
        Message(role=Role.USER, content=user_prompt),
    ])
    parsed = _extract_json_object(str((resp.content if resp else "") or ""))
    code = str(parsed.get("code") or "").strip()
    notes = parsed.get("notes") if isinstance(parsed.get("notes"), list) else []
    return {
        "code": code,
        "notes": [str(item or "").strip()[:300] for item in notes if str(item or "").strip()][:10],
    }


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


@router.post("/skills/upload", response_model=ApiResponse)
async def upload_skill_source(
    user_id: str = Form(...),
    file: UploadFile = File(...),
) -> ApiResponse:
    settings = get_settings()
    uploader = AliyunOSSUploader()
    content = await read_upload_with_limit(
        file,
        max_bytes=settings.MAX_UPLOAD_SKILL_SOURCE_BYTES,
        label="Skill source upload",
    )
    url, object_path = uploader.upload_bytes_with_path(
        content,
        user_id=str(user_id),
        file_name=file.filename or "skill_source.bin",
        content_type=file.content_type,
    )
    return ApiResponse(
        code=0,
        message="success",
        data={
            "object_path": object_path,
            "url": url,
            "filename": file.filename,
            "content_type": file.content_type,
            "size": len(content),
        },
    )


@router.post("/skills/analyze_template", response_model=ApiResponse)
async def analyze_template(
    file: UploadFile = File(...),
) -> ApiResponse:
    try:
        settings = get_settings()
        content = await read_upload_with_limit(
            file,
            max_bytes=settings.MAX_UPLOAD_TEMPLATE_BYTES,
            label="Template upload",
        )
        filename = file.filename or "unknown.txt"
        data = await user_skill_service.generate_style_skill_from_document(filename, content)
        return ApiResponse(code=0, message="success", data=data)
    except ValueError as e:
        import traceback
        with open("/tmp/askai_backend_error.log", "a") as f:
            f.write(f"Analyze template error (ValueError): {str(e)}\n")
            f.write(traceback.format_exc())
            f.write("\n")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log_print(f"Analyze template error: {e}")
        import traceback
        with open("/tmp/askai_backend_error.log", "a") as f:
            f.write(f"Analyze template error: {str(e)}\n")
            f.write(traceback.format_exc())
            f.write("\n")
        raise HTTPException(status_code=500, detail="Failed to analyze template")


@router.post("/skills/generate", response_model=ApiResponse)
async def generate_skill(payload: SkillGenerateRequest) -> ApiResponse:
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Skill name is required")

    skill_md = (payload.skill_markdown or "").strip()
    if not skill_md and payload.sources:
        sources_text = []
        for obj in payload.sources:
            try:
                text = await _extract_text_from_object(obj)
                if text:
                    sources_text.append(text)
            except Exception:
                continue
        combined = _truncate("\n\n".join(sources_text))
        skill_md = await user_skill_service.build_skill_markdown(
            payload.name,
            payload.description or "",
            payload.formats or [],
            combined,
            payload.notes or "",
        )
    
    if not skill_md and not payload.contract_json:
        skill_md = (
            "# Purpose\n\n"
            "# When to use\n- \n\n"
            "# Inputs\n- \n\n"
            "# Workflow\n1. \n2. \n\n"
            "# Output format\n- \n\n"
            "# Examples\n## Input\n\n## Output\n\n"
            "# Rules\n- \n\n"
            "# Failure handling\n- \n"
        )
    skill_object_path = ""
    try:
        _, skill_object_path = await user_skill_service.persist_skill_markdown(
            payload.user_id,
            payload.name,
            skill_md,
        )
    except Exception as exc:
        # Do not block creation if OSS is unavailable
        skill_object_path = ""
        log_print(f"[skills] persist_skill_markdown failed: {exc}", flush=True)
    skill_id = uuid.uuid4().hex
    created = await user_skill_service.create_skill(
        payload.user_id,
        {
            "id": skill_id,
            "main_id": payload.main_id,
            "name": payload.name,
            "description": payload.description,
            "summary": payload.summary,
            "category": payload.category,
            "role": payload.role,
            "skill_type": payload.skill_type,
            "tags": payload.tags,
            "visibility": payload.visibility,
            "formats": payload.formats,
            "input_profile": payload.input_profile or {},
            "contract_json": payload.contract_json or {},
            "skill_markdown": skill_md,
            "skill_object_path": skill_object_path,
            "sources": [{"object_path": p} for p in payload.sources],
            "resources": payload.resources or {},
            "advanced": payload.advanced or {},
            "notes": payload.notes,
            "is_active": bool(payload.is_active),
        },
    )
    return ApiResponse(code=0, message="success", data=created)


@router.post("/skills/from_recording", response_model=ApiResponse)
async def skill_from_recording(payload: SkillFromRecordingRequest) -> ApiResponse:
    """Persist a recorded browser trajectory as a composite_task skill.

    The agent's recorder emits semantic events while the user walks
    through the real flow; this endpoint converts them into the same
    CompositeStep YAML shape the manual editor produces, so downstream
    consumers (parser, runtime, UI) stay on a single code path."""
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Skill name is required")
    raw_events = [e.model_dump() for e in payload.events]
    steps = distill_trajectory(
        raw_events,
        site_profile_id=str(payload.site_profile_id or ""),
        variables=dict(payload.variables or {}),
    )
    if payload.edits:
        steps = refine_steps(steps, edits=[e.model_dump() for e in payload.edits])
    if not steps:
        raise HTTPException(status_code=400, detail="No usable events in recording")

    skill_markdown = _encode_composite_yaml(
        name=payload.name.strip(),
        description=str(payload.description or "").strip(),
        triggers=list(payload.triggers or []),
        steps=steps,
    )

    skill_object_path = ""
    try:
        _, skill_object_path = await user_skill_service.persist_skill_markdown(
            payload.user_id, payload.name, skill_markdown,
        )
    except Exception as exc:
        log_print(f"[skills] persist_skill_markdown failed: {exc}", flush=True)

    skill_id = uuid.uuid4().hex
    created = await user_skill_service.create_skill(
        payload.user_id,
        {
            "id": skill_id,
            "main_id": payload.main_id,
            "name": payload.name,
            "description": payload.description or "",
            "summary": payload.description or "",
            "category": "Browser Automation",
            "skill_type": "composite_task",
            "tags": ["composite_task", "recorded"],
            "visibility": payload.visibility or "private",
            "formats": ["markdown"],
            "input_profile": {},
            "contract_json": {},
            "skill_markdown": skill_markdown,
            "skill_object_path": skill_object_path,
            "sources": [],
            "resources": {},
            "advanced": {},
            "notes": "",
            "is_active": bool(payload.is_active),
        },
    )
    return ApiResponse(code=0, message="success", data=created)


@router.post("/skills/enrich_draft", response_model=ApiResponse)
async def enrich_skill_draft(payload: SkillEnrichRequest) -> ApiResponse:
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Skill name is required")
    enriched = await user_skill_service.enrich_skill_contract_draft(
        input_profile={
            **(payload.input_profile or {}),
            "name": payload.name,
            "skill_type": payload.skill_type or "style",
        },
        description=payload.description or "",
    )
    return ApiResponse(code=0, message="success", data=enriched)


@router.post("/skills/enrich-writing-style", response_model=ApiResponse)
async def enrich_writing_style(
    payload: Dict[str, Any],
    user_id: str = Query(..., alias="userId"),
    main_id: str = Query("default", alias="mainId"),
    main_id_snake: Optional[str] = Query(None, alias="main_id"),
) -> ApiResponse:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Skill name is required")
    draft = _safe_dict(payload.get("draft"))
    input_profile = {
        "skill_type": "style",
        "name": name,
        "summary": str(payload.get("description") or "").strip(),
        "applicable_scenarios": str(payload.get("scenario") or "").strip(),
        "publish_channel": draft.get("publishChannel") or [],
        "content_form": draft.get("contentForm") or [],
        "target_audience": draft.get("targetAudience") or [],
        "preferred_style": draft.get("preferredStyle") or [],
        "target_length": draft.get("targetLength") or {},
        "section_structure": draft.get("sectionStructure") or [],
        "required_sections": draft.get("requiredSections") or [],
        "required_elements": draft.get("requiredElements") or [],
        "forbidden_elements": draft.get("forbiddenElements") or [],
        "notes": str(draft.get("notes") or "").strip(),
        "main_id": main_id_snake or main_id,
        "user_id": user_id,
    }
    enriched = await user_skill_service.enrich_skill_contract_draft(
        input_profile=input_profile,
        description=str(payload.get("description") or "").strip(),
    )
    data = _safe_dict(enriched)
    return ApiResponse(
        code=0,
        message="success",
        data={
            "inputProfile": _safe_dict(data.get("input_profile")),
            "contractJson": _safe_dict(data.get("contract_json")),
            "skillMarkdown": str(data.get("skill_markdown") or ""),
        },
    )


@router.post("/skills/generate-workflow-steps", response_model=ApiResponse)
async def generate_workflow_steps(payload: WorkflowStepsGenerateRequest, accept_language: str | None = Header(default=None)) -> ApiResponse:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Skill name is required")
    max_steps = _resolved_workflow_step_count(payload)
    source = "llm"
    message = "success"
    try:
        steps = await _generate_workflow_steps_with_llm(payload)
    except Exception as exc:
        log_print(f"[skills] generate_workflow_steps failed: {exc}", flush=True)
        steps = []
        source = "error"
        message = str(exc) or "生成失败"
    if not steps and source != "error":
        source = "empty"
        message = "模型未返回可用步骤"
    message = localized_workflow_message(message, accept_language, "Workflow generation failed")
    return ApiResponse(
        code=0,
        message=message,
        data={
            "steps": [{"id": f"step_{idx + 1}", "text": text} for idx, text in enumerate(steps[:max_steps])],
            "source": source,
            "message": message,
        },
    )


@router.post("/skills/generate-workflow-nodes", response_model=ApiResponse)
async def generate_workflow_nodes(payload: WorkflowNodesGenerateRequest, accept_language: str | None = Header(default=None)) -> ApiResponse:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Skill name is required")
    max_nodes = _resolved_workflow_node_count(payload)
    source = "llm"
    message = "success"
    try:
        nodes = await _generate_workflow_nodes_with_llm(payload)
    except Exception as exc:
        log_print(f"[skills] generate_workflow_nodes failed: {exc}", flush=True)
        nodes = []
        source = "error"
        message = str(exc) or "生成失败"
    if not nodes and source != "error":
        source = "empty"
        message = "模型未返回可用节点"
    message = localized_workflow_message(message, accept_language, "Workflow generation failed")
    return ApiResponse(
        code=0,
        message=message,
        data={
            "nodes": nodes[:max_nodes],
            "source": source,
            "message": message,
        },
    )


@router.post("/skills/polish-workflow-node", response_model=ApiResponse)
async def polish_workflow_node(payload: WorkflowNodePolishRequest, accept_language: str | None = Header(default=None)) -> ApiResponse:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Skill name is required")
    source = "llm"
    message = "success"
    try:
        text = await _polish_workflow_node_with_llm(payload)
    except Exception as exc:
        log_print(f"[skills] polish_workflow_node failed: {exc}", flush=True)
        text = ""
        source = "error"
        message = str(exc) or "润色失败"
    if not text and source != "error":
        source = "empty"
        message = "模型未返回可用节点要求"
    message = localized_workflow_message(message, accept_language, "Failed to refine the node requirement")
    return ApiResponse(
        code=0,
        message=message,
        data={
            "text": text,
            "source": source,
            "message": message,
        },
    )


@router.post("/skills/check-workflow-logic", response_model=ApiResponse)
async def check_workflow_logic(payload: WorkflowLogicCheckRequest, accept_language: str | None = Header(default=None)) -> ApiResponse:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Skill name is required")
    source = "llm"
    message = "success"
    try:
        result = await _check_workflow_logic_with_llm(payload, accept_language)
    except Exception as exc:
        log_print(f"[skills] check_workflow_logic failed: {exc}", flush=True)
        result = {}
        source = "error"
        message = str(exc) or "检查失败"
    message = localized_workflow_message(message, accept_language, "Workflow check failed")
    return ApiResponse(
        code=0,
        message=message,
        data={
            **result,
            "source": source,
            "message": message,
        },
    )


@router.post("/skills/check-workflow-nodes", response_model=ApiResponse)
async def check_workflow_nodes(payload: WorkflowLogicCheckRequest, accept_language: str | None = Header(default=None)) -> ApiResponse:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Skill name is required")
    source = "llm"
    message = "success"
    try:
        normalized_nodes = [
            node for idx, raw in enumerate(list(payload.nodes or []))
            for node in [_normalize_workflow_node(raw, idx)]
            if node
        ]
        node_steps = [
            "：".join([str(node.get("title") or "").strip(), str(node.get("description") or "").strip()]).strip("：")
            for node in normalized_nodes
        ]
        enriched_payload = payload.model_copy(update={
            "nodes": normalized_nodes,
            "steps": [str(item or "").strip() for item in (payload.steps or node_steps) if str(item or "").strip()],
        })
        result = await _check_workflow_logic_with_llm(enriched_payload, accept_language)
    except Exception as exc:
        log_print(f"[skills] check_workflow_nodes failed: {exc}", flush=True)
        result = {}
        source = "error"
        message = str(exc) or "检查失败"
    message = localized_workflow_message(message, accept_language, "Workflow check failed")
    return ApiResponse(
        code=0,
        message=message,
        data={
            **result,
            "source": source,
            "message": message,
        },
    )


@router.post("/skills/check-script-plugin", response_model=ApiResponse)
async def check_script_plugin(payload: ScriptPluginCheckRequest, accept_language: str | None = Header(default=None)) -> ApiResponse:
    static_result = _validate_script_plugin_static(payload.code)
    source = "rules"
    message = "success"
    llm_result = None
    if static_result.get("rulePass"):
        source = "rules+llm"
        try:
            llm_result = await _review_script_plugin_with_llm(payload, static_result, accept_language)
        except Exception as exc:
            log_print(f"[skills] check_script_plugin llm review failed: {exc}", flush=True)
            source = "rules"
            message = "规则检测通过，LLM 审查暂不可用"
            llm_result = {
                "pass": True,
                "level": "warning",
                "summary": "规则检测已通过，但 LLM 审查暂不可用。",
                "risks": [],
                "suggestions": [],
            }
    else:
        message = "规则检测未通过"
    message = localized_workflow_message(message, accept_language, "Script validation failed")
    if llm_result is not None and source == "rules":
        llm_result["summary"] = localized_workflow_message(
            str(llm_result.get("summary") or ""), accept_language, "LLM review is unavailable"
        )
    return ApiResponse(
        code=0,
        message=message,
        data={
            **localize_script_check(static_result, accept_language),
            "pass": bool(static_result.get("rulePass")),
            "llm": llm_result,
            "source": source,
            "message": message,
        },
    )


@router.post("/skills/fix-script-plugin", response_model=ApiResponse)
async def fix_script_plugin(payload: ScriptPluginFixRequest, accept_language: str | None = Header(default=None)) -> ApiResponse:
    static_result = _validate_script_plugin_static(payload.code)
    try:
        fixed = await _fix_script_plugin_with_llm(payload, static_result)
    except Exception as exc:
        log_print(f"[skills] fix_script_plugin failed: {exc}", flush=True)
        raise HTTPException(status_code=500, detail=str(exc) or "修复失败")
    fixed_code = str(fixed.get("code") or "").strip()
    if not fixed_code:
        raise HTTPException(status_code=500, detail="模型未返回可用代码")
    recheck = _validate_script_plugin_static(fixed_code)
    return ApiResponse(
        code=0,
        message="success",
        data={
            "code": fixed_code,
            "notes": fixed.get("notes") or [],
            "check": localize_script_check(recheck, accept_language),
        },
    )


@router.post("/skills/generate-script-plugin", response_model=ApiResponse)
async def generate_script_plugin(payload: ScriptPluginGenerateRequest, accept_language: str | None = Header(default=None)) -> ApiResponse:
    try:
        generated = await _generate_script_plugin_with_llm(payload)
    except Exception as exc:
        log_print(f"[skills] generate_script_plugin failed: {exc}", flush=True)
        raise HTTPException(status_code=500, detail=str(exc) or "生成失败")
    code = str(generated.get("code") or "").strip()
    if not code:
        raise HTTPException(status_code=500, detail="模型未返回可用代码")
    check = _validate_script_plugin_static(code)
    hardcode_warnings = _generated_code_hardcode_warnings(code, payload.processing_instruction)
    if hardcode_warnings:
        check["warnings"] = [*(check.get("warnings") or []), *hardcode_warnings][:50]
    return ApiResponse(
        code=0,
        message="success",
        data={
            "code": code,
            "notes": generated.get("notes") or [],
            "check": localize_script_check(check, accept_language),
        },
    )


@router.get("/skills", response_model=ApiResponse)
async def list_skills(
    user_id: str = Query(..., alias="userId"),
    main_id: str = Query("default", alias="mainId"),
    main_id_snake: Optional[str] = Query(None, alias="main_id"),
) -> ApiResponse:
    main_id = main_id_snake or main_id
    from app.services.skill_sharing.legacy_migration import legacy_skill_share_migration
    await legacy_skill_share_migration.migrate_owned(main_id=main_id, owner_user_id=user_id)
    await legacy_skill_share_migration.migrate_installed(main_id=main_id, recipient_user_id=user_id)
    skills = await user_skill_service.list_skills(user_id, main_id=main_id)
    from app.services.resource_feedback.summary import skill_feedback_summary_service
    await skill_feedback_summary_service.attach(main_id=main_id, user_id=user_id, skills=skills)
    return ApiResponse(code=0, message="success", data=[_admin_shape_skill(item) for item in skills])


@router.get("/skills/selectable", response_model=ApiResponse)
async def list_selectable_skills(
    user_id: str = Query(..., alias="userId"),
    main_id: str = Query("default", alias="mainId"),
    main_id_snake: Optional[str] = Query(None, alias="main_id"),
    scope: str = Query("all"),
    keyword: str = Query(""),
    cursor: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=50),
) -> ApiResponse:
    resolved_main_id = main_id_snake or main_id
    source_scope = str(scope or "all").strip().lower()
    if source_scope not in {"all", "user", "organization"}:
        source_scope = "all"
    try:
        user_skills = await user_skill_service.list_skills(user_id, main_id=resolved_main_id)
    except Exception:
        user_skills = []
    try:
        org_skills = await organization_skill_adapter.list_runtime_skills(main_id=resolved_main_id)
    except Exception:
        org_skills = []
    organization_ids = [
        str(skill.get("id") or skill.get("_id") or "").strip()
        for skill in org_skills or []
        if isinstance(skill, dict)
    ]
    allowed_organization_ids = await filter_allowed_resource_ids(
        "skill",
        main_id=resolved_main_id,
        user_id=user_id,
        resource_ids=organization_ids,
    )

    items: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for skill in list(user_skills or []) + list(org_skills or []):
        if not isinstance(skill, dict):
            continue
        if not _safe_bool(skill.get("enabled"), _safe_bool(skill.get("is_active"), True)):
            continue
        skill_id = str(skill.get("id") or skill.get("_id") or "").strip()
        if _skill_source_scope(skill) == "organization" and skill_id not in allowed_organization_ids:
            continue
        if not skill_id or skill_id in seen:
            continue
        current_scope = _skill_source_scope(skill)
        if source_scope != "all" and current_scope != source_scope:
            continue
        if not _matches_skill_keyword(skill, keyword):
            continue
        seen.add(skill_id)
        items.append(_selectable_skill_item(skill))

    offset = _cursor_offset(cursor)
    page = items[offset:offset + limit]
    next_offset = offset + len(page)
    has_more = next_offset < len(items)
    return ApiResponse(
        code=0,
        message="success",
        data={
            "items": page,
            "nextCursor": str(next_offset) if has_more else "",
            "hasMore": has_more,
        },
    )


async def _validate_personal_workflow_documents(
    payload: AdminShapeSkillPayload, *, main_id: str, user_id: str,
) -> None:
    if payload.type != "workflow":
        return
    try:
        await validate_personal_workflow_documents(
            main_id=main_id, user_id=user_id, nodes=_workflow_nodes(payload.config),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="无权使用所选知识文档，请重新选择") from exc
    except LookupError as exc:
        raise HTTPException(status_code=409, detail="所选知识文档已删除或尚未解析，请重新选择") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="请先选择要读取的知识文档") from exc


@router.post("/skills", response_model=ApiResponse)
async def create_admin_shape_skill(
    payload: AdminShapeSkillPayload,
    user_id: str = Query(..., alias="userId"),
    main_id: str = Query("default", alias="mainId"),
    main_id_snake: Optional[str] = Query(None, alias="main_id"),
) -> ApiResponse:
    resolved_main_id = main_id_snake or main_id
    await _validate_personal_workflow_documents(payload, main_id=resolved_main_id, user_id=user_id)
    created = await user_skill_service.create_skill(
        user_id,
        _admin_shape_payload_to_user_payload(payload, user_id=user_id, main_id=resolved_main_id),
    )
    from app.services.skill_lifecycle import SkillLifecycleService
    lifecycle = SkillLifecycleService()
    await lifecycle.initialize_draft(
        main_id=resolved_main_id,
        user_id=user_id,
        skill_id=str(created.get("id") or ""),
        draft=created,
        new_skill=True,
    )
    current = await user_skill_service.get_skill(user_id, str(created.get("id") or ""), main_id=resolved_main_id)
    return ApiResponse(code=0, message="success", data=_admin_shape_skill(current or created))


@router.get("/skills/{skill_id}", response_model=ApiResponse)
async def get_skill(
    skill_id: str,
    user_id: str = Query(..., alias="userId"),
    main_id: str = Query("default", alias="mainId"),
    main_id_snake: Optional[str] = Query(None, alias="main_id"),
) -> ApiResponse:
    resolved_main_id = main_id_snake or main_id
    skill = await user_skill_service.get_skill(user_id, skill_id, main_id=resolved_main_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return ApiResponse(code=0, message="success", data=_admin_shape_skill(skill))


@router.put("/skills/{skill_id}", response_model=ApiResponse)
async def update_skill(
    skill_id: str,
    payload: AdminShapeSkillPayload,
    user_id: str = Query(..., alias="userId"),
    main_id: str = Query("default", alias="mainId"),
    main_id_snake: Optional[str] = Query(None, alias="main_id"),
) -> ApiResponse:
    resolved_main_id = main_id_snake or main_id
    updates = _admin_shape_payload_to_user_payload(payload, user_id=user_id, main_id=resolved_main_id)
    from app.services.skill_lifecycle import SkillLifecycleError, SkillLifecycleService
    current = await user_skill_service.get_skill(user_id, skill_id, main_id=resolved_main_id)
    if not current:
        raise HTTPException(status_code=404, detail="Skill not found")
    await _validate_personal_workflow_documents(payload, main_id=resolved_main_id, user_id=user_id)
    lifecycle = SkillLifecycleService()
    if not lifecycle.is_platform_skill(current):
        updated = await user_skill_service.update_skill(user_id, skill_id, updates, main_id=resolved_main_id)
        return ApiResponse(code=0, message="success", data=_admin_shape_skill(updated or current))
    try:
        await lifecycle.save_draft(
            main_id=resolved_main_id, user_id=user_id, skill_id=skill_id, draft=updates,
        )
    except SkillLifecycleError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail()) from exc
    updated = await user_skill_service.get_skill(user_id, skill_id, main_id=resolved_main_id)
    return ApiResponse(code=0, message="success", data=_admin_shape_skill(updated or {}))


@router.patch("/skills/{skill_id}/enabled", response_model=ApiResponse)
async def set_skill_enabled(
    skill_id: str,
    payload: SkillEnabledPayload,
    user_id: str = Query(..., alias="userId"),
    main_id: str = Query("default", alias="mainId"),
    main_id_snake: Optional[str] = Query(None, alias="main_id"),
) -> ApiResponse:
    resolved_main_id = main_id_snake or main_id
    current = await user_skill_service.get_skill(user_id, skill_id, main_id=resolved_main_id)
    if not current:
        raise HTTPException(status_code=404, detail="Skill not found")
    if payload.enabled and str(current.get("publication_status") or "") == "draft" and not current.get("published_version"):
        raise HTTPException(status_code=409, detail={
            "code": "skill_publish_required", "message": "Publish this Skill before enabling it",
        })
    updated = await user_skill_service.set_skill_enabled(
        user_id, skill_id, bool(payload.enabled), main_id=resolved_main_id,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Skill not found")
    return ApiResponse(code=0, message="success", data=_admin_shape_skill(updated))


@router.delete("/skills/{skill_id}", response_model=ApiResponse)
async def delete_skill(
    skill_id: str,
    user_id: str = Query(..., alias="userId"),
    main_id: str = Query("default", alias="mainId"),
    main_id_snake: Optional[str] = Query(None, alias="main_id"),
) -> ApiResponse:
    main_id = main_id_snake or main_id
    ok = await user_skill_service.delete_skill(user_id, skill_id, main_id=main_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Skill not found")
    return ApiResponse(code=0, message="success", data={"id": skill_id})
