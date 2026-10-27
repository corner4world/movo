from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


_SOURCE = Path(__file__).resolve().parents[1] / "app" / "enterprise_capabilities" / "content" / "publish_assembly" / "section_locator.py"
_SPEC = importlib.util.spec_from_file_location("section_locator_locale_test", _SOURCE)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


class SectionLocatorLocaleTests(unittest.TestCase):
    def test_paragraph_fallback_title_respects_language(self) -> None:
        markdown = "This is a full paragraph with enough detail to avoid being treated as a heading.\n\nAnother full paragraph with enough detail to stay as body text."
        self.assertEqual(_MODULE.locate_final_body_sections(markdown, language="zh-CN")[0].title, "正文 1")
        self.assertEqual(_MODULE.locate_final_body_sections(markdown, language="en-US")[0].title, "Body 1")


if __name__ == "__main__":
    unittest.main()
