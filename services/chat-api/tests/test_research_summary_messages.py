from __future__ import annotations

import unittest
import importlib.util
from pathlib import Path

_SOURCE = Path(__file__).resolve().parents[1] / "app/enterprise_capabilities/research/progressive/summary_messages.py"
_SPEC = importlib.util.spec_from_file_location("research_summary_messages", _SOURCE)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
research_summary = _MODULE.research_summary


class ResearchSummaryMessageTests(unittest.TestCase):
    def test_chinese_summary_unchanged(self) -> None:
        self.assertEqual(
            research_summary(accepted_count=3, provider_searches=5, budget_exhausted=False, language="zh"),
            "渐进式研究完成：采纳 3 条证据，执行 5 次 provider 搜索。",
        )

    def test_english_summary_explains_budget(self) -> None:
        summary = research_summary(accepted_count=3, provider_searches=5, budget_exhausted=True, language="en-US")
        self.assertIn("3 evidence items accepted", summary)
        self.assertIn("5 provider searches executed", summary)
        self.assertIn("candidate queries left unexecuted", summary)


if __name__ == "__main__":
    unittest.main()
