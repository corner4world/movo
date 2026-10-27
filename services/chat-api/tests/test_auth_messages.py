import unittest

from app.api.auth_messages import localized_auth_message


class AuthMessagesTests(unittest.TestCase):
    def test_login_error_uses_request_language(self):
        self.assertEqual(localized_auth_message("用户名或密码错误", "zh-CN"), "用户名或密码错误")
        self.assertEqual(localized_auth_message("用户名或密码错误", "en-US"), "Incorrect username or password")

    def test_unknown_message_has_english_fallback(self):
        self.assertEqual(localized_auth_message("未知认证错误", "en-US"), "Authentication failed")


if __name__ == "__main__":
    unittest.main()
