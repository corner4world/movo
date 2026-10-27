"""Localized status text for internal knowledge retrieval results."""

from __future__ import annotations

_MESSAGES = {
    "completed": {
        "zh": "内部知识检索完成。",
        "en": "Internal knowledge retrieval completed.",
    },
    "empty": {
        "zh": "内部知识检索已完成，但没有命中授权范围内的内容。",
        "en": "Internal knowledge retrieval completed, but found no content within the authorized scope.",
    },
    "unavailable": {
        "zh": "内部知识服务暂不可用；该状态不代表知识库没有命中结果。",
        "en": "The internal knowledge service is temporarily unavailable; this does not mean the knowledge base had no matching results.",
    },
    "answer_completed": {
        "zh": "内部知识问答完成。",
        "en": "Internal knowledge question answering completed.",
    },
    "answer_empty": {
        "zh": "内部知识检索已完成，但没有找到可支持答案的依据。",
        "en": "Internal knowledge retrieval completed, but found no evidence to support an answer.",
    },
}


def knowledge_result_message(key: str, language: str = "zh") -> str:
    locale = "en" if str(language or "").lower().startswith("en") else "zh"
    return _MESSAGES[key][locale]
