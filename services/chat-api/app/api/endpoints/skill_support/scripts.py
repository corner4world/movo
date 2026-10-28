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


from .models import ScriptPluginCheckRequest, ScriptPluginFixRequest, ScriptPluginGenerateRequest
from .workflow import _extract_json_object, _normalize_bool

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
