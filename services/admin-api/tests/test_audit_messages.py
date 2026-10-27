from __future__ import annotations

import unittest

from app.api.audit_messages import localize_audit_page


class AuditMessageTests(unittest.TestCase):
    def test_display_label_changes_without_mutating_stored_data(self) -> None:
        page = {"total": 1, "items": [{"module": "模型中心", "action": "update", "details": {"name": "用户内容"}}]}
        english = localize_audit_page(page, "en-US")
        self.assertEqual(english["items"][0]["module"], "Model Center")
        self.assertEqual(english["items"][0]["details"], {"name": "用户内容"})
        self.assertEqual(page["items"][0]["module"], "模型中心")
        self.assertIs(localize_audit_page(page, "zh-CN"), page)


if __name__ == "__main__":
    unittest.main()
