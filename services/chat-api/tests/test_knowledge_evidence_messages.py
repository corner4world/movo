from __future__ import annotations

import unittest

from app.knowledge.citations.evidence_messages import default_knowledge_label, evidence_question, evidence_summary, localized_knowledge_label


class KnowledgeEvidenceMessageTests(unittest.TestCase):
    def test_chinese_defaults_are_unchanged(self) -> None:
        self.assertEqual(evidence_summary(2), "内部知识问答检索到 2 条引用来源")
        self.assertEqual(evidence_question("q"), "问题：q")
        self.assertEqual(default_knowledge_label(), "内部知识")

    def test_english_evidence_labels(self) -> None:
        self.assertEqual(evidence_summary(2, "en-US"), "Internal knowledge Q&A retrieved 2 cited sources")
        self.assertEqual(evidence_question("q", "en-US"), "Question: q")
        self.assertEqual(default_knowledge_label("en-US"), "Internal knowledge")
        self.assertEqual(localized_knowledge_label("个人知识", "personal", "en-US"), "Personal knowledge")
        self.assertEqual(localized_knowledge_label("企业知识", "organization", "en-US"), "Organization knowledge")


if __name__ == "__main__":
    unittest.main()
