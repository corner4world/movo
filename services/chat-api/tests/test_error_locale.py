import unittest

from app.api.error_locale import localize_detail


class ErrorLocaleTests(unittest.TestCase):
    def test_english_known_and_unknown_errors(self):
        self.assertEqual(localize_detail("定时任务不存在", 404, "en-US"), "Scheduled task not found")
        self.assertEqual(localize_detail("未知中文错误", 400, "en-US"), "Invalid request")

    def test_chinese_unchanged_and_structured_error_code_preserved(self):
        detail = {"code": "position_role_denied", "message": "无权限"}
        self.assertEqual(localize_detail("定时任务不存在", 404, "zh-CN"), "定时任务不存在")
        self.assertEqual(localize_detail(detail, 403, "en-US")["code"], "position_role_denied")
        self.assertEqual(localize_detail(detail, 403, "en-US")["message"], "Access denied")
        self.assertEqual(detail["message"], "无权限")


if __name__ == "__main__":
    unittest.main()
