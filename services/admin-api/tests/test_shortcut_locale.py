from __future__ import annotations

import unittest
import importlib.util
from pathlib import Path


def _load(name: str, filename: str):
    path = Path(__file__).resolve().parents[1] / "app" / "shortcut_settings" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


default_entries = _load("shortcut_defaults", "defaults.py").default_entries
translate_plan = _load("shortcut_locale", "locale.py").translate_plan


class ShortcutLocaleTests(unittest.TestCase):
    def test_builtin_labels_round_trip_without_changing_prompt_or_custom_label(self) -> None:
        entries = default_entries()
        entries.append({"id": "custom", "categoryKey": "content", "categoryLabel": "自定义分组", "label": "我的快捷项", "prompt": "Custom prompt"})
        original = {"name": "企业默认方案", "entries": entries, "groups": [{"key": "content", "label": "内容生成"}]}
        english = translate_plan(original, english=True)
        self.assertTrue(all(not any("\u3400" <= char <= "\u9fff" for char in entry["label"]) for entry in english["entries"][:-1]))
        self.assertEqual(english["entries"][0]["label"], "WeChat / Xiaohongshu")
        self.assertEqual(english["entries"][0]["prompt"], original["entries"][0]["prompt"])
        self.assertEqual(english["entries"][-1]["label"], "我的快捷项")
        self.assertEqual(translate_plan(english, english=False)["entries"][0]["label"], entries[0]["label"])
        self.assertEqual(original["groups"][0]["label"], "内容生成")


if __name__ == "__main__":
    unittest.main()
