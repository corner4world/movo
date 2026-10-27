from __future__ import annotations

import unittest

from app.api.workflow_proxy_messages import workflow_check_fallback, workflow_proxy_error


class WorkflowProxyMessageTests(unittest.TestCase):
    def test_generation_error_respects_request_language(self) -> None:
        self.assertEqual(workflow_proxy_error(None, "生成服务不可用", "zh-CN"), "生成服务不可用")
        self.assertEqual(workflow_proxy_error(None, "生成服务不可用", "en-US"), "The workflow generation service is unavailable")

    def test_check_fallback_preserves_structure_and_localizes_text(self) -> None:
        chinese = workflow_check_fallback(None, nodes=True, accept_language="zh-CN")
        english = workflow_check_fallback(None, nodes=True, accept_language="en-US")
        self.assertEqual(chinese["source"], english["source"])
        self.assertEqual(chinese["logic"]["label"], "检查失败")
        self.assertEqual(english["logic"]["label"], "Workflow check failed")
        self.assertEqual(english["conclusion"], "The backend semantic node check did not complete.")


if __name__ == "__main__":
    unittest.main()
