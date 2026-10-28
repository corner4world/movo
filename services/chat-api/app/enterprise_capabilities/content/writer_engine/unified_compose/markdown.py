from __future__ import annotations

import re
from typing import Any, Dict, List
from app.enterprise_capabilities.content.body_projection import (
    strip_inline_visual_suggestions,
    strip_unrenderable_markdown_images,
)
from app.enterprise_capabilities.content.structure_roles import localize_heading_label, resolve_language


class MarkdownPostProcessor:
    @staticmethod
    def sanitize_markdown_noise(text: str) -> str:
        raw = str(text or "")
        if not raw:
            return raw

        def _clean_core(raw_text: str) -> str:
            lines = raw_text.splitlines()
            cleaned: List[str] = []
            fence_open = False
            for line in lines:
                stripped = line.strip()
                low = stripped.lower()
                if stripped.startswith("```"):
                    if low in {"```markdown", "```table"}:
                        line = "```"
                    fence_open = not fence_open
                    cleaned.append(line)
                    continue
                if not fence_open and low in {"markdown", "table", "```markdown", "```table"}:
                    continue
                cleaned.append(line)
            if fence_open:
                cleaned.append("```")
            out = "\n".join(cleaned)
            out = re.sub(r"\n{3,}", "\n\n", out).strip()
            return out + ("\n" if out else "")

        return _clean_core(raw)

    @staticmethod
    def sanitize_runtime_artifacts(markdown: str) -> str:
        text = str(markdown or "")
        if not text.strip():
            return text

        text = re.sub(r"\[\[(?:PLANNED_)?IMAGE_SLOT_\d+\]\]", "", text)
        text = strip_inline_visual_suggestions(text)
        text = strip_unrenderable_markdown_images(text)
        lines = text.splitlines()

        def _is_editorial_annotation_line(line: str) -> bool:
            stripped = str(line or "").strip()
            if not stripped.startswith(">"):
                return False
            body = stripped.lstrip(">").strip()
            if not body:
                return False
            # Internal editorial/assembly note style: quoted label-like annotation,
            # often enclosed in brackets and not meant for the final reader-facing copy.
            if re.match(r"^[\[\(（【].{0,120}[\]\)）】](?:[:：].*)?$", body):
                return True
            return False

        cleaned_lines: List[str] = []
        pending_annotation_block: List[str] = []
        for line in lines:
            if _is_editorial_annotation_line(line):
                pending_annotation_block.append(line)
                continue
            if pending_annotation_block:
                pending_annotation_block = []
            cleaned_lines.append(line)
        text = "\n".join(cleaned_lines)
        artifact_titles = {
            "artifact",
            "artifact.post_md",
            "source_material",
            "source material",
            "word count check",
            "字数自检",
        }

        sections: List[List[str]] = []
        current: List[str] = []
        for line in cleaned_lines:
            if re.match(r"^\s{0,3}#{1,6}\s+", line) and current:
                sections.append(current)
                current = [line]
            else:
                current.append(line)
        if current:
            sections.append(current)

        def _is_visual_inventory_section(section: List[str]) -> bool:
            if not section:
                return False
            first = str(section[0] or "")
            heading_match = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$", first)
            heading_title = str(heading_match.group(2) or "").strip().lower() if heading_match else ""
            heading_level = len(str(heading_match.group(1) or "")) if heading_match else 0
            body = section[1:] if heading_match else section
            meaningful: List[str] = []
            for line in body:
                stripped = str(line or "").strip()
                if not stripped or stripped in {"---", "***"}:
                    continue
                meaningful.append(stripped)
            if not meaningful:
                return False
            # Preserve publishable sections such as document titles and body headings,
            # even if they temporarily contain only one inline image.
            if heading_level == 1:
                return False
            inventory_markers = (
                "配图",
                "图片",
                "图示",
                "插图",
                "视觉",
                "asset",
                "assets",
                "visual",
                "gallery",
                "image",
                "images",
            )
            if heading_title and not any(marker in heading_title for marker in inventory_markers):
                return False

            visual_only = 0
            for line in meaningful:
                candidate = re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", line)
                candidate = re.sub(r"!\[[^\]]*\]\(([^)]*)\)", "", candidate).strip()
                candidate = re.sub(r"^[（(]\s*[^）)]{0,80}\s*[）)]$", "", candidate).strip()
                candidate = re.sub(r"^[：:、,;；\\-–—\\s]+|[：:、,;；\\-–—\\s]+$", "", candidate).strip()
                if not candidate:
                    visual_only += 1
            return visual_only == len(meaningful)

        kept: List[str] = []
        for section in sections:
            first = str(section[0] or "").strip()
            m = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", first)
            title = str(m.group(1) or "").strip().lower() if m else ""
            if title in artifact_titles:
                continue
            if _is_visual_inventory_section(section):
                continue
            kept.extend(section)

        cleaned = "\n".join(kept)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return cleaned + ("\n" if cleaned else "")

    @staticmethod
    def sanitize_delivery_artifact_markdown(markdown: str) -> str:
        text = MarkdownPostProcessor.sanitize_runtime_artifacts(markdown)
        if not text.strip():
            return text

        cleaned_lines: List[str] = []
        for line in text.splitlines():
            stripped = str(line or "").strip()
            low = stripped.lower()
            if "data:application/" in low:
                continue
            if re.search(r"(?:下载|可下载|导出).{0,30}(?:word|docx|pdf|xlsx|文件|附件)", stripped, re.I):
                continue
            if re.search(r"(?:download|export).{0,30}(?:word|docx|pdf|xlsx|file)", stripped, re.I):
                continue
            if re.search(r"已.{0,12}(?:生成|按要求|完成|提供).{0,30}(?:可下载|下载|docx|word|pdf|xlsx|文件)", stripped, re.I):
                continue
            cleaned_lines.append(line)

        cleaned = "\n".join(cleaned_lines)
        cleaned = MarkdownPostProcessor.remove_leading_duplicate_scaffold(cleaned)
        cleaned = re.sub(
            r"\A\s*#{1,6}\s*(?:标题|报告标题|文档标题|文章标题|题目|Title|Report Title)\s*\n+([^#\n][^\n]{1,120})\n+",
            lambda m: "# " + str(m.group(1) or "").strip().strip("《》") + "\n\n",
            cleaned,
            flags=re.I,
        )
        cleaned = re.sub(r"\A(?:\s*[-*_]{3,}\s*)+", "", cleaned)
        cleaned = re.sub(r"(?:\n\s*[-*_]{3,}\s*)+\Z", "", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return cleaned + ("\n" if cleaned else "")

    @staticmethod
    def remove_leading_duplicate_scaffold(markdown: str) -> str:
        text = str(markdown or "")
        if not text.strip():
            return text
        lines = text.splitlines()
        heading_indices: List[tuple[int, int, str]] = []
        for idx, line in enumerate(lines):
            match = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$", line)
            if not match:
                continue
            title = str(match.group(2) or "").strip()
            norm = re.sub(r"^[\d一二三四五六七八九十]+[\.、\s]+", "", title)
            norm = re.sub(r"\s+", "", norm).lower()
            if norm:
                heading_indices.append((idx, len(match.group(1)), norm))
        if len(heading_indices) < 2:
            return text
        first_start, first_level, first_norm = heading_indices[0]
        generic_first = first_norm in {"标题", "报告标题", "文档标题", "文章标题", "题目", "title", "reporttitle", "documenttitle"}
        if not generic_first:
            return text
        first_end = len(lines)
        for start, level, _norm in heading_indices[1:]:
            if level <= first_level:
                first_end = start
                break
        scaffold_child_norms = {norm for start, level, norm in heading_indices[1:] if start < first_end and level > first_level}
        later_norms = {norm for start, _level, norm in heading_indices if start >= first_end}
        if not scaffold_child_norms or not scaffold_child_norms.issubset(later_norms):
            return text
        title_line = ""
        for line in lines[first_start + 1:first_end]:
            stripped = str(line or "").strip()
            if not stripped or re.match(r"^\s{0,3}#{1,6}\s+", stripped):
                continue
            title_line = stripped.strip("《》")
            break
        prefix = list(lines[:first_start])
        if title_line:
            prefix.extend([f"# {title_line}", ""])
        return "\n".join(prefix + lines[first_end:])

    @staticmethod
    def normalize_section_headings(section_markdown: str, level: int, language: str = "zh") -> str:
        text = str(section_markdown or "")
        if not text.strip():
            return text
        main_lv = max(2, min(4, int(level or 1) + 1))
        sub_lv = min(5, main_lv + 1)
        main_prefix = "#" * main_lv
        sub_prefix = "#" * sub_lv

        lines = text.splitlines()
        out: List[str] = []
        first_heading_done = False
        for line in lines:
            m = re.match(r"^\s*(#{1,6})\s+(.*)$", line)
            if not m:
                out.append(line)
                continue
            title = str(m.group(2) or "").strip()
            if not title:
                out.append(line)
                continue
            title = MarkdownPostProcessor._localize_heading_title(title, language=language)
            if not first_heading_done:
                out.append(f"{main_prefix} {title}")
                first_heading_done = True
                continue
            out.append(f"{sub_prefix} {title}")
        return "\n".join(out)

    @staticmethod
    def _localize_heading_title(title: str, *, language: str = "zh") -> str:
        raw = str(title or "").strip()
        if not raw:
            return raw
        if resolve_language(text=raw, language=language) != "zh":
            return raw
        prefix_match = re.match(r"^((?:\d+(?:\.\d+)*|[一二三四五六七八九十]+)(?:[\.、]\s*|\s+))(.+)$", raw)
        prefix = ""
        core = raw
        if prefix_match:
            prefix = str(prefix_match.group(1) or "")
            core = str(prefix_match.group(2) or "").strip()
        localized = localize_heading_label(core, language="zh")
        return f"{prefix}{localized}".strip()

    @staticmethod
    def normalize_list_item_style(markdown: str) -> str:
        text = str(markdown or "")
        if not text:
            return text
        lines = text.splitlines()
        out: List[str] = []
        for line in lines:
            m_num = re.match(r"^(\s*\d+\.\s+)\*\*(.+?)\*\*\s*$", line)
            if m_num:
                out.append(f"{m_num.group(1)}{m_num.group(2)}")
                continue
            m_bul = re.match(r"^(\s*[-*]\s+)\*\*(.+?)\*\*\s*$", line)
            if m_bul:
                out.append(f"{m_bul.group(1)}{m_bul.group(2)}")
                continue
            if re.match(r"^\s*(\d+\.\s+|[-*]\s+)", line):
                out.append(line.replace("**", "").replace("__", ""))
                continue
            out.append(line)
        return "\n".join(out)

    @staticmethod
    def ensure_section_citation(section_markdown: str, refs: List[Dict[str, Any]], language: str) -> str:
        text = str(section_markdown or "").rstrip()
        if not text or not refs:
            return text
        if re.search(r"\[\d+\]", text):
            return text
        idx = int(refs[0].get("index") or 1)
        return text + (f"\n\n参考依据：[{idx}]" if language == "zh" else f"\n\nReference: [{idx}]")
