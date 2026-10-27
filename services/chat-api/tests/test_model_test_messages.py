from __future__ import annotations

import unittest

from app.api.model_test_messages import model_test_config_error, model_test_failure, model_test_message


class ModelTestMessageTests(unittest.TestCase):
    def test_status_respects_request_language(self) -> None:
        self.assertEqual(model_test_message("connecting", None), "正在连接模型...")
        self.assertEqual(model_test_message("connecting", "en-US,en;q=0.9"), "Connecting to the model...")
        self.assertEqual(model_test_message("connected", "en-US"), "Model connection test succeeded.")

    def test_failure_keeps_safe_error_detail(self) -> None:
        self.assertEqual(model_test_failure("model_failed", RuntimeError("timeout"), None), "模型连接测试失败: timeout")
        self.assertEqual(model_test_failure("model_failed", RuntimeError("timeout"), "en-US"), "Model connection test failed: timeout")
        self.assertEqual(model_test_failure("image_failed", RuntimeError("连接失败"), "en-US"), "Image model connection test failed")

    def test_config_error_does_not_leak_chinese_to_english(self) -> None:
        error = ValueError("模型不存在")
        self.assertEqual(model_test_config_error(error, None, "model_failed"), "模型不存在")
        self.assertEqual(model_test_config_error(error, "en-US", "model_failed"), "Model connection test failed")


if __name__ == "__main__":
    unittest.main()
