from __future__ import annotations

import unittest

from app.services.mcp_call_result import build_mcp_call_outcome


class McpOutcomeMessageTests(unittest.TestCase):
    def test_existing_chinese_default(self) -> None:
        outcome = build_mcp_call_outcome("search", {"content": [], "isError": True})
        self.assertEqual(outcome["message"], "MCP tool search 执行失败")

    def test_english_wrapper_keeps_remote_data(self) -> None:
        result = {"content": [{"type": "text", "text": "Pages: Overview"}], "isError": False}
        outcome = build_mcp_call_outcome("search", result, language="en-US")
        self.assertEqual(outcome["message"], "MCP tool search succeeded")
        self.assertEqual(outcome["responseSummary"], "Pages: Overview")
        self.assertIs(outcome["raw"], result)

    def test_english_failure_hides_unknown_chinese_wrapper(self) -> None:
        result = {"content": [{"type": "text", "text": "工具异常"}], "isError": True}
        outcome = build_mcp_call_outcome("search", result, language="en-US")
        self.assertEqual(outcome["message"], "MCP tool search failed")
        self.assertIs(outcome["raw"], result)


if __name__ == "__main__":
    unittest.main()
