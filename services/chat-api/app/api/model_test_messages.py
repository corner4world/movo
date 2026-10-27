"""User-facing status text for model connectivity probes."""

from __future__ import annotations


_MESSAGES = {
    "connecting": {"zh": "正在连接模型...", "en": "Connecting to the model..."},
    "connected": {"zh": "模型连接测试成功。", "en": "Model connection test succeeded."},
    "model_failed": {"zh": "模型连接测试失败", "en": "Model connection test failed"},
    "image_failed": {"zh": "图片模型连接测试失败", "en": "Image model connection test failed"},
}


def model_test_message(key: str, accept_language: object) -> str:
    language = accept_language if isinstance(accept_language, str) else "zh"
    return _MESSAGES[key]["en" if language.split(",", 1)[0].split(";", 1)[0].strip().lower().startswith("en") else "zh"]


def model_test_failure(key: str, error: BaseException, accept_language: object) -> str:
    prefix = model_test_message(key, accept_language)
    detail = str(error)
    if key == "model_failed" and detail.startswith(_MESSAGES[key]["zh"] + ": "):
        detail = detail[len(_MESSAGES[key]["zh"]) + 2:]
    if key == "image_failed" and detail.startswith(_MESSAGES[key]["zh"] + ": "):
        detail = detail[len(_MESSAGES[key]["zh"]) + 2:]
    if prefix == _MESSAGES[key]["en"] and any("\u3400" <= char <= "\u9fff" for char in detail):
        return prefix
    return f"{prefix}: {detail}" if detail else prefix


def model_test_config_error(error: BaseException, accept_language: object, fallback_key: str) -> str:
    detail = str(error)
    language = accept_language if isinstance(accept_language, str) else "zh"
    if language.split(",", 1)[0].split(";", 1)[0].strip().lower().startswith("en") and any("\u3400" <= char <= "\u9fff" for char in detail):
        return model_test_message(fallback_key, language)
    return detail
