from __future__ import annotations

import re
from typing import Any, Dict, List
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


class ObservationAdapter:
    @staticmethod
    def compact(observations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for item in observations[:20]:
            if not isinstance(item, dict):
                continue
            out.append(
                {
                    "tool": str(item.get("tool") or ""),
                    "query": str(item.get("query") or ""),
                    "summary": str(item.get("summary") or "")[:1000],
                    "sources": list(item.get("sources") or [])[:10],
                    "artifacts": list(item.get("artifacts") or [])[:6],
                }
            )
        return out

    @staticmethod
    def collect_visual_assets(observations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        assets: List[Dict[str, Any]] = []
        seen = set()
        for obs in observations:
            for art in (obs.get("artifacts") or []):
                if not isinstance(art, dict):
                    continue
                if str(art.get("type") or "").strip().lower() != "image":
                    continue
                url = str(art.get("url") or "").strip()
                if not url or url in seen:
                    continue
                seen.add(url)
                assets.append(
                    {
                        "url": url,
                        "caption": str(art.get("caption") or "可视化图示").strip(),
                        "prompt": str(art.get("prompt") or "").strip(),
                    }
                )
        return assets[:12]

    @staticmethod
    def build_source_index(tool_observations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        refs: List[Dict[str, Any]] = []
        seen = set()

        def _add_ref(title: str, url: str) -> None:
            normalized = ObservationAdapter.normalize_source_url(url)
            if not normalized or normalized in seen:
                return
            seen.add(normalized)
            refs.append({"index": len(refs) + 1, "title": str(title or "").strip(), "url": normalized})

        for obs in tool_observations:
            for src in (obs.get("sources") or [])[:30]:
                title = ""
                url = ""
                if isinstance(src, dict):
                    title = str(src.get("title") or src.get("name") or "").strip()
                    url = str(src.get("url") or src.get("source_url") or "").strip()
                elif isinstance(src, str):
                    url = src.strip()
                url = ObservationAdapter.normalize_source_url(url)
                if not url or url in seen:
                    continue
                _add_ref(title, url)
            if len(refs) >= 40:
                break
            raw_text = "\n".join(
                str(obs.get(key) or "")
                for key in ("summary", "result", "content", "text")
                if str(obs.get(key) or "").strip()
            )
            if not raw_text:
                continue
            lines = raw_text.splitlines()
            for idx, line in enumerate(lines):
                urls = re.findall(r"https?://[^\s)\]>\"']+", line)
                if not urls:
                    continue
                title = ""
                prev = lines[idx - 1].strip() if idx > 0 else ""
                title_match = re.match(r"^\s*\[\d+\]\s*(.+?)\s*$", prev)
                if title_match:
                    title = str(title_match.group(1) or "").strip()
                for url in urls:
                    _add_ref(title, url)
                    if len(refs) >= 40:
                        break
                if len(refs) >= 40:
                    break
        return refs[:40]

    @staticmethod
    def normalize_source_url(url: str) -> str:
        raw = str(url or "").strip().strip("<>").strip()
        if not raw:
            return ""
        if not raw.startswith(("http://", "https://")):
            return raw
        try:
            parsed = urlparse(raw)
            host = (parsed.netloc or "").lower()
            path = parsed.path or ""
            if "beacon." in host or path.endswith("/a.gif") or path.endswith(".gif"):
                return ""
            keep_keys = {"id", "doc", "article", "pdf"}
            query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=False) if k.lower() in keep_keys]
            normalized = parsed._replace(query=urlencode(query, doseq=True), fragment="")
            return urlunparse(normalized)
        except Exception:
            return raw
