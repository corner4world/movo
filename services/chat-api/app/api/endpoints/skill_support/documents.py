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
