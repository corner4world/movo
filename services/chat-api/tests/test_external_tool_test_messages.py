from __future__ import annotations

import unittest

from app.api.external_tool_test_messages import localize_tool_status


class ExternalToolTestMessagesTests(unittest.TestCase):
    def test_discovery_and_timeout_are_localized_without_changing_raw(self) -> None:
        discovered = {"success": True, "message": "发现 7 个 MCP tools", "tools": [{"name": "sample"}]}
        english = localize_tool_status(discovered, "en-US")
        self.assertEqual(english["message"], "Discovered 7 MCP tools")
        self.assertEqual(english["tools"], discovered["tools"])
        self.assertEqual(discovered["message"], "发现 7 个 MCP tools")
        timed_out = {"success": False, "message": "请求超时：超过 15 秒未收到响应", "responseSummary": "请求超时：超过 15 秒未收到响应"}
        english_timeout = localize_tool_status(timed_out, "en-US")
        self.assertEqual(english_timeout["message"], english_timeout["responseSummary"])


if __name__ == "__main__":
    unittest.main()
