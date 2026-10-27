from __future__ import annotations

import re


_MESSAGES = {
    "模型连接测试失败": "Model connection test failed",
    "API Key 解密失败，请重新保存模型配置": "Could not decrypt the API key. Save the model configuration again.",
    "Azure Deployment 名称不能为空（使用模型 ID 字段填写）": "Azure Deployment name is required (enter it in the model ID field).",
    "Azure Endpoint 不能为空": "Azure Endpoint is required",
    "API Key 不能为空": "API key is required",
    "模型 ID 不能为空": "Model ID is required",
    "Base URL 不能为空": "Base URL is required",
    "模型接口连接超时": "The model endpoint connection timed out",
}


def localize_model_test_message(message: str) -> str | None:
    if message in _MESSAGES:
        return _MESSAGES[message]
    match = re.fullmatch(r"模型接口返回 (\d+): (.*)", message, re.DOTALL)
    if match:
        return _with_safe_detail(f"The model endpoint returned HTTP {match.group(1)}", match.group(2))
    match = re.fullmatch(r"模型接口连接失败: (.*)", message, re.DOTALL)
    if match:
        return _with_safe_detail("Could not connect to the model endpoint", match.group(1))
    match = re.fullmatch(r"模型连接测试失败: (.*)", message, re.DOTALL)
    if match:
        return _with_safe_detail("Model connection test failed", match.group(1))
    if message.startswith("模型接口 TLS 证书校验失败。"):
        return (
            "The model endpoint TLS certificate could not be verified. "
            "Set ASKAI_ADMIN_MODEL_TEST_CA_BUNDLE to a CA certificate path in the admin API environment. "
            "For development only, you can temporarily set "
            "ASKAI_ADMIN_MODEL_TEST_INSECURE_SKIP_VERIFY=true."
        )
    return None


def _with_safe_detail(prefix: str, detail: str) -> str:
    return f"{prefix}: {detail}" if not any("\u3400" <= char <= "\u9fff" for char in detail) else prefix
