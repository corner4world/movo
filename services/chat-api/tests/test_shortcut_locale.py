from __future__ import annotations

import unittest

from app.services.shortcut_locale import translate_plan, translate_preferences


class ShortcutLocaleTests(unittest.TestCase):
    def test_builtin_labels_are_localized_without_touching_prompt(self) -> None:
        original = {"entries": [{"id": "content.wechat", "categoryKey": "content", "categoryLabel": "内容生成", "label": "微信/小红书", "prompt": "Write about {topic}"}], "groups": [{"key": "content", "label": "内容生成"}]}
        english = translate_plan(original, english=True)
        self.assertEqual(english["entries"][0]["label"], "WeChat / Xiaohongshu")
        self.assertEqual(english["groups"][0]["label"], "Content Creation")
        self.assertEqual(english["entries"][0]["prompt"], original["entries"][0]["prompt"])
        self.assertEqual(translate_plan(english, english=False), original)

    def test_default_personal_label_round_trips(self) -> None:
        original = {"personalGroup": {"key": "personal", "label": "我的常用"}, "personalEntries": []}
        english = translate_preferences(original, english=True)
        self.assertEqual(english["personalGroup"]["label"], "My Favorites")
        self.assertEqual(translate_preferences(english, english=False), original)


if __name__ == "__main__":
    unittest.main()
