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


from .models import AdminShapeSkillPayload, WorkflowNodesGenerateRequest, WorkflowStepsGenerateRequest

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
        "environmentStatus": skill.get("environment_status"),
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
