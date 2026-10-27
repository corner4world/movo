from __future__ import annotations

import unittest

from app.api.dashboard_messages import localize_dashboard_todos


class DashboardMessagesTests(unittest.TestCase):
    def test_english_dashboard_keeps_severity_and_route(self) -> None:
        original = [{"level": "error", "title": "工具测试失败", "description": "3 个工具连接需要检查。", "route": "/tools"}]
        assets = {"models": {"failedHealth": 0}, "tools": {"failed": 3, "untested": 0}}
        metrics = {"failedCalls24h": 0}
        english = localize_dashboard_todos(original, metrics, assets, "en-US")
        self.assertEqual(english[0], {"level": "error", "title": "Tool tests failed", "description": "3 tool connections need attention.", "route": "/tools"})
        self.assertEqual(original[0]["title"], "工具测试失败")
        self.assertIs(localize_dashboard_todos(original, metrics, assets, "zh-CN"), original)


if __name__ == "__main__":
    unittest.main()
