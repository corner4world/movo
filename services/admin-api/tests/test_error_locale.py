import unittest

from app.api.error_locale import localize_detail


class ErrorLocaleTests(unittest.TestCase):
    def test_english_known_and_unknown_errors(self):
        self.assertEqual(localize_detail("用户不存在", 404, "en-US"), "User not found")
        self.assertEqual(localize_detail("未知中文错误", 400, "en-US"), "Invalid request")

    def test_chinese_unchanged_and_structured_error_code_preserved(self):
        detail = {"code": "duplicate", "message": "名称已存在"}
        self.assertEqual(localize_detail("用户不存在", 404, "zh-CN"), "用户不存在")
        self.assertEqual(localize_detail(detail, 409, "en-US")["code"], "duplicate")
        self.assertEqual(localize_detail(detail, 409, "en-US")["message"], "Request conflicts with the current state")
        self.assertEqual(detail["message"], "名称已存在")

    def test_dynamic_errors_keep_useful_details(self):
        self.assertEqual(localize_detail("当前版本最多允许 25 名成员", 403, "en-US"), "This edition allows at most 25 members")
        self.assertEqual(localize_detail("仍有 3 名员工未分配岗位角色", 409, "en-US"), "3 employees still need a position role")
        self.assertEqual(localize_detail("请选择PPT 图片生成模型", 400, "en-US"), "Select a presentation image generation model")
        self.assertEqual(localize_detail("PPT 图片生成模型不存在、已禁用或不支持 image_generation 能力", 400, "en-US"), "The presentation image generation model is unavailable, disabled, or does not support image_generation")

    def test_model_test_status_messages(self):
        self.assertEqual(localize_detail("正在连接 backend 模型运行时...", 200, "en-US"), "Connecting to the backend model runtime...")
        self.assertEqual(localize_detail("模型连接测试成功。", 200, "zh-CN"), "模型连接测试成功。")
        self.assertEqual(localize_detail("模型连接测试成功。", 200, "en-US"), "Model connection test succeeded.")

    def test_employee_credential_errors_preserve_meaning(self):
        cases = {
            "外部身份用户不能设置本地密码": "Externally managed users cannot set a local password",
            "请填写登录名": "Enter a login name",
            "请设置至少 10 位密码": "Set a password with at least 10 characters",
            "密码至少 10 位": "The password must be at least 10 characters",
        }
        for chinese, english in cases.items():
            self.assertEqual(localize_detail(chinese, 400, "zh-CN"), chinese)
            self.assertEqual(localize_detail(chinese, 400, "en-US"), english)

    def test_image_runtime_messages_keep_status_and_language(self):
        self.assertEqual(localize_detail("图片模型运行时返回 HTTP 503: unavailable", 200, "en-US"), "The image model runtime returned HTTP 503: unavailable")
        self.assertEqual(localize_detail("无法连接图片模型运行时: connection refused", 200, "en-US"), "Could not connect to the image model runtime: connection refused")
        self.assertEqual(localize_detail("图片模型运行时返回了无效响应", 200, "en-US"), "The image model runtime returned an invalid response")
        self.assertEqual(localize_detail("图片模型运行时返回了无效响应", 200, "zh-CN"), "图片模型运行时返回了无效响应")

    def test_backend_unavailable_keeps_safe_reason(self):
        self.assertEqual(localize_detail("backend 不可用：connection refused", 502, "en-US"), "The backend is unavailable: connection refused")
        self.assertEqual(localize_detail("backend 不可用：连接失败", 502, "en-US"), "The backend is unavailable")


if __name__ == "__main__":
    unittest.main()
