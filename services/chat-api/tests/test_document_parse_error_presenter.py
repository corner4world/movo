from __future__ import annotations

import unittest

from app.services.document_parse_error_presenter import user_facing_parse_error


class DocumentParseErrorPresenterTests(unittest.TestCase):
    def test_language_changes_guidance_without_exposing_raw_error(self) -> None:
        kwargs = {"parse_error": "HTTP 404 No Such Key", "filename": "report.pdf", "has_object_path": True}
        self.assertIn("文件已收到", user_facing_parse_error(**kwargs, language="zh-CN"))
        english = user_facing_parse_error(**kwargs, language="en-US")
        self.assertIn("file was received", english)
        self.assertNotIn("No Such Key", english)

    def test_filename_is_preserved_in_generic_english_error(self) -> None:
        self.assertIn("report.pdf", user_facing_parse_error(parse_error="unexpected", filename="report.pdf", language="en-US"))


if __name__ == "__main__":
    unittest.main()
