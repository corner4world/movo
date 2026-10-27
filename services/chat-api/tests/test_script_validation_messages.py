from __future__ import annotations

import unittest

from app.api.script_validation_messages import localize_script_check


class ScriptValidationMessageTests(unittest.TestCase):
    def test_english_translation_preserves_code_and_line(self) -> None:
        original = {
            "pass": False,
            "errors": [
                {"level": "error", "code": "MISSING_RUN", "message": "必须定义入口函数 def run(inputs, context):。", "line": None},
                {"level": "error", "code": "DENIED_IMPORT", "message": "不允许 from os.path import ...。", "line": 3},
            ],
            "warnings": [{"level": "warning", "code": "OUTPUT_DIR_NOT_REFERENCED", "message": "未明显使用 context['output_dir']，如果要生成文件，必须写入该目录。", "line": None}],
        }
        translated = localize_script_check(original, "en-US")
        self.assertEqual(translated["errors"][0]["message"], "Define the entry point def run(inputs, context):.")
        self.assertEqual(translated["errors"][1]["message"], "Importing from os.path is not allowed.")
        self.assertEqual(translated["errors"][1]["line"], 3)
        self.assertEqual(translated["warnings"][0]["code"], "OUTPUT_DIR_NOT_REFERENCED")
        self.assertEqual(original["errors"][0]["message"], "必须定义入口函数 def run(inputs, context):。")

    def test_chinese_response_is_unchanged(self) -> None:
        original = {"errors": [{"code": "MISSING_RUN", "message": "必须定义入口函数 def run(inputs, context):。"}]}
        self.assertIs(localize_script_check(original, "zh-CN"), original)


if __name__ == "__main__":
    unittest.main()
