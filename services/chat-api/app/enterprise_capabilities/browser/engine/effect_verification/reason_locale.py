"""Locale fixed browser verification reasons without changing evidence values."""

from __future__ import annotations


_REASONS = {
    "no_state_change": ("没有观测到可验证的状态变化", "No verifiable state change was observed"),
    "object_id": ("提交后页面获得了新的稳定业务对象标识", "The page gained a stable business object ID after submission"),
    "value_added": ("提交值已离开编辑字段，并作为新增内容出现在非编辑结果区", "The submitted value left the edit field and appeared as new content in the results"),
    "count_increased": ("提交后编辑表单关闭，且结果集合中的项目数量增加", "The edit form closed and the result count increased after submission"),
    "result_present": ("提交后页面发生跳转、编辑表单关闭，且结果页面包含本次填写内容", "The page navigated, the edit form closed, and the result contains the submitted content"),
    "result_unverified": ("提交后页面发生跳转且编辑表单关闭，但尚未核验业务结果中存在本次填写内容", "The page navigated and the edit form closed, but the submitted content has not been verified in the result"),
    "pending_notice": ("，同时捕获到处理中提示", "; a processing notice was also observed"),
    "pending_state": ("捕获到处理中状态，等待最终结果或执行回查", "A processing state was observed; wait for the final result or verify it again"),
    "model_unavailable": ("模型验证不可用", "Model verification is unavailable"),
}


def verification_reason(key: str, lang: str) -> str:
    zh, en = _REASONS[key]
    return zh if str(lang or "").startswith("zh") else en
