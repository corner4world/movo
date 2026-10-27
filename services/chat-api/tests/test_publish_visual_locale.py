from __future__ import annotations

import unittest
import importlib.util
from pathlib import Path


_SOURCE = Path(__file__).resolve().parents[1] / "app" / "enterprise_capabilities" / "content" / "publish_assembly" / "alt_text_generator.py"
_SPEC = importlib.util.spec_from_file_location("publish_alt_text_generator", _SOURCE)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
AltTextGenerator = _MODULE.AltTextGenerator


class PublishVisualLocaleTests(unittest.TestCase):
    def test_generic_alt_text_respects_language(self) -> None:
        kwargs = {"section_title": "", "slot_role": "", "slot_description": "", "fallback_index": 2}
        self.assertEqual(AltTextGenerator.generate(**kwargs, language="zh-CN"), "配图 2")
        self.assertEqual(AltTextGenerator.generate(**kwargs, language="en-US"), "Visual 2")


if __name__ == "__main__":
    unittest.main()
