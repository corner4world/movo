from __future__ import annotations

import unittest

from app.enterprise_capabilities.knowledge_result import available_result, unavailable_result
from app.enterprise_capabilities.knowledge_source.result_messages import knowledge_result_message
from app.enterprise_capabilities.knowledge_source.mapping import map_response


class KnowledgeResultMessageTests(unittest.TestCase):
    def test_existing_chinese_status_and_english_status(self) -> None:
        chinese = available_result(query="q", retrieval_mode="qa", total=0, items=[])
        english = available_result(query="q", retrieval_mode="qa", total=0, items=[], language="en-US")
        self.assertEqual(chinese["message"], "内部知识检索已完成，但没有命中授权范围内的内容。")
        self.assertEqual(english["message"], "Internal knowledge retrieval completed, but found no content within the authorized scope.")
        self.assertEqual(chinese["retrieval_status"], english["retrieval_status"])

    def test_unavailable_remains_distinct_from_empty(self) -> None:
        result = unavailable_result(query="q", error=RuntimeError("503"), language="en")
        self.assertEqual(result["retrieval_status"], "service_unavailable")
        self.assertIn("does not mean", result["message"])
        self.assertEqual(result["error"]["detail"], "503")
        self.assertEqual(knowledge_result_message("answer_completed", "en"), "Internal knowledge question answering completed.")

    def test_external_result_uses_language_without_changing_evidence(self) -> None:
        outcome = {"success": True, "raw": {"answer": "Verified answer"}}
        config = {"displayName": "Company KB", "mapping": {"answerPath": "answer"}}
        chinese = map_response(outcome, config)
        english = map_response(outcome, config, language="en-US")
        self.assertEqual(chinese["message"], "已从Company KB获取答案。")
        self.assertEqual(english["message"], "Retrieved an answer from Company KB.")
        self.assertEqual(chinese["answer"], english["answer"])
        self.assertEqual(chinese["evidence_bundle"]["sources"], english["evidence_bundle"]["sources"])

    def test_external_failure_preserves_chinese_and_uses_english_fallback(self) -> None:
        outcome = {"success": False, "message": "远端检索失败"}
        with self.assertRaisesRegex(ValueError, "远端检索失败"):
            map_response(outcome, {})
        with self.assertRaisesRegex(ValueError, "External knowledge base call failed"):
            map_response(outcome, {}, language="en")


if __name__ == "__main__":
    unittest.main()
