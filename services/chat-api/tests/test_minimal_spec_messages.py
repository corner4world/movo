from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


_SOURCE = Path(__file__).resolve().parents[1] / "app" / "enterprise_capabilities" / "content" / "profile_presets" / "minimal_spec_messages.py"
_SPEC = importlib.util.spec_from_file_location("minimal_spec_messages_test", _SOURCE)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


class MinimalSpecMessagesTests(unittest.TestCase):
    def test_default_profile_copy_follows_language(self) -> None:
        chinese = _MODULE.defaults("zh-CN", content_form="article", audience="经理")
        english = _MODULE.defaults("en-US", content_form="article", audience="managers")
        self.assertEqual(chinese["required_block"], "核心内容")
        self.assertEqual(english["required_block"], "Core content")
        self.assertIn("managers", english["identity"])
        self.assertEqual(len(chinese["must_include"]), len(english["must_include"]))


if __name__ == "__main__":
    unittest.main()
