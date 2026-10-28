from __future__ import annotations

from . import desktop_agent_executor as api


async def prepare_effect(s):
    if (
        (
            s.decision.tool in {"browser_click", "browser_click_at"}
            or s.submit_press
        )
        and isinstance(s.decision.args, dict)
    ):
        s.effect_target = (
            api.resolve_effect_target(s.decision, s.current_obs)
            if s.decision.tool in {"browser_click", "browser_click_at"}
            else s.dependency_target
        )
        if s.effect_target is not None:
            try:
                s.prepared_effect = (
                    await s.effect_tracker.prepare_click(
                        target=s.effect_target,
                        before=s.current_obs,
                    )
                    if not s.submit_press else
                    s.effect_tracker.prepare_submit_press(
                        key=str((s.decision.args or {}).get("key") or ""),
                        target=s.effect_target,
                        before=s.current_obs,
                    )
                )
            except api.SemanticActionRejected as exc:
                s.alignment = exc.alignment
                s.model_semantic_hint = (
                    "Blocked a click whose business object conflicts with the task: "
                    f"expected {s.alignment.intended.entity or s.alignment.intended.operation!r}, "
                    f"target represents {s.alignment.observed.entity or s.alignment.observed.operation!r}. "
                    "Observe again and select a semantically compatible element."
                )
                s.semantic_hint = (
                    "已阻止与任务业务对象不一致的点击："
                    f"目标需要“{s.alignment.intended.entity or s.alignment.intended.operation}”，"
                    f"当前元素表示“{s.alignment.observed.entity or s.alignment.observed.operation}”。"
                    "请重新观察并选择与目标一致的元素。"
                    if s.lang == "zh" else
                    s.model_semantic_hint
                )
                s.history.append(api.StepRecord(
                    observation=s.current_obs,
                    decision=s.decision,
                    ok=False,
                    error=s.model_semantic_hint,
                    result_digest=api.json.dumps(
                        s.alignment.model_dump(mode="json"),
                        ensure_ascii=False,
                    )[:4000],
                ))
                yield {"type": "activity", "content": {
                    "kind": "warning", "message": s.semantic_hint,
                }}, {}
                api.logger.warning(
                    "browser semantic action rejected",
                    extra={
                        "event": "browser.semantic_action_rejected",
                        "intended_entity": s.alignment.intended.entity,
                        "observed_entity": s.alignment.observed.entity,
                        "confidence": s.alignment.confidence,
                    },
                )
                s.consecutive_failures += 1
                if s.consecutive_failures >= api.MAX_CONSECUTIVE_FAILURES:
                    s.break_step = True
                    return
                s.continue_step = True
                return
            if s.prepared_effect is not None:
                s.enriched_contract = s.form_transaction.enrich_contract(
                    s.prepared_effect.contract,
                    target=s.effect_target,
                    purpose_override=(
                        s.task_context.interaction_purpose(s.decision, s.current_obs)
                        if s.context_tracks_state else ""
                    ),
                )
                s.precondition = api.enforce_commit_preconditions(
                    s.enriched_contract,
                    requires_form_input=s.requires_authoritative_form_input,
                    has_confirmed_form_input=bool(
                        dict(s.enriched_contract.fingerprint or {}).get(
                            "confirmed_fill_count",
                        )
                    ) or s.form_transaction.has_confirmed_value(
                        s.authoritative_form_values,
                    ),
                )
                if s.precondition.downgraded:
                    api.logger.info(
                        "browser commit downgraded to entry transition",
                        extra={
                            "event": "browser.commit_precondition_downgraded",
                            "action": s.enriched_contract.action_name,
                            "reason": s.precondition.reason,
                            "intended_operation": (
                                s.enriched_contract.intended_operation
                            ),
                        },
                    )
                s.contract = s.precondition.contract
                if s.contract.is_commit:
                    s.contract = s.business_actions.bind_contract(
                        s.contract,
                        s.current_obs,
                        target_hint=s.task_context.business_target_hint(s.current_obs),
                    )
                s.prepared_effect = s.effect_tracker.update_contract(
                    s.prepared_effect,
                    s.contract,
                )
                if s.prepared_effect is None:
                    api.logger.info(
                        "browser click excluded from business effect tracking",
                        extra={
                            "event": "browser.effect_tracking_cancelled",
                            "reason": "confirmed non-business interaction purpose",
                        },
                    )
                s.context_effect_blocker = (
                    s.task_context.business_effect_blocker(s.prepared_effect.contract)
                    if s.prepared_effect is not None and s.context_tracks_state
                    else ""
                )
                if s.context_effect_blocker:
                    s.history.append(api.StepRecord(
                        observation=s.current_obs,
                        decision=s.decision,
                        ok=False,
                        error=s.context_effect_blocker,
                        result_digest=str(
                            s.prepared_effect.contract.business_action_id or ""
                        ),
                    ))
                    yield {"type": "activity", "content": {
                        "kind": "warning",
                        "message": s.context_effect_blocker,
                    }}, {}
                    s.pending_resolved_decision = api.Decision(
                        tool="browser_observe",
                        args={},
                        rationale="verify the already confirmed business effect before any new commit",
                    )
                    api.logger.info(
                        "browser context blocked additional business effect",
                        extra={
                            "event": "browser.context_business_effect_blocked",
                            "contract_key": s.prepared_effect.contract.key(),
                        },
                    )
                    s.continue_step = True
                    return
                s.commit_blocker = (
                    s.form_transaction.commit_blocker(
                        s.current_obs,
                        target=s.effect_target,
                    )
                    if s.prepared_effect is not None else None
                )
                if s.prepared_effect is not None and s.commit_blocker is not None:
                    s.blocked_fields = "、".join(s.commit_blocker.fields)
                    s.model_commit_hint = (
                        f"Commit blocked: fill results for {', '.join(s.commit_blocker.fields)} "
                        "are not confirmed. Observe and verify or refill before committing."
                    )
                    s.commit_hint = (
                        f"已阻止提交：字段“{s.blocked_fields}”的填写结果尚未确认。"
                        "请重新观察并确认字段值，必要时重新填写，再执行提交。"
                        if s.lang == "zh" else
                        s.model_commit_hint
                    )
                    s.history.append(api.StepRecord(
                        observation=s.current_obs,
                        decision=s.decision,
                        ok=False,
                        error=s.model_commit_hint,
                        result_digest=api.json.dumps(
                            s.form_transaction.summaries(),
                            ensure_ascii=False,
                        )[:4000],
                    ))
                    yield {"type": "activity", "content": {
                        "kind": "warning",
                        "message": s.commit_hint,
                    }}, {}
                    api.logger.warning(
                        "browser commit blocked by unverified fill",
                        extra={
                            "event": "browser.commit_blocked_unverified_fill",
                            "fields": list(s.commit_blocker.fields),
                        },
                    )
                    s.consecutive_failures += 1
                    s.continue_step = True
                    return
                s.replay_blocker = (
                    s.effect_tracker.replay_blocker(s.prepared_effect)
                    if s.prepared_effect is not None else None
                )
                s.business_replay = (
                    s.business_actions.replay_blocker(s.prepared_effect.contract)
                    if s.prepared_effect is not None else None
                )
                if s.replay_blocker is None and s.business_replay is not None:
                    s.model_replay_hint = (
                        "The same operation on this business object is already executed or pending verification; "
                        "the re-rendered control will not be submitted again. Verify the result only."
                    )
                    s.replay_hint = (
                        "同一业务对象上的相同操作已经执行或正在验收，"
                        "已阻止因页面重渲染产生的重复提交；请只验证结果。"
                        if s.lang == "zh" else
                        s.model_replay_hint
                    )
                    s.history.append(api.StepRecord(
                        observation=s.current_obs,
                        decision=s.decision,
                        ok=False,
                        error=s.model_replay_hint,
                        result_digest=s.business_replay.identity.business_action_id,
                    ))
                    yield {"type": "activity", "content": {
                        "kind": "warning", "message": s.replay_hint,
                    }}, {}
                    s.pending_resolved_decision = api.Decision(
                        tool="browser_observe",
                        args={},
                        rationale="verify the pending business action instead of replaying it",
                    )
                    s.consecutive_failures += 1
                    s.continue_step = True
                    return
                if s.replay_blocker is not None:
                    s.model_replay_hint = (
                        f"Action {s.replay_blocker.action_name!r} already has status "
                        f"{s.replay_blocker.status}; replay blocked. Verify the result instead."
                    )
                    s.replay_hint = (
                        f"操作“{s.replay_blocker.action_name}”已有状态 {s.replay_blocker.status}，"
                        "已阻止重复提交；请只验证结果，不要再次执行该操作。"
                        if s.lang == "zh" else
                        s.model_replay_hint
                    )
                    s.history.append(api.StepRecord(
                        observation=s.current_obs,
                        decision=s.decision,
                        ok=False,
                        error=s.model_replay_hint,
                        result_digest=api.json.dumps(
                            s.replay_blocker.model_dump(mode="json"),
                            ensure_ascii=False,
                        )[:4000],
                    ))
                    yield {"type": "activity", "content": {
                        "kind": "warning", "message": s.replay_hint,
                    }}, {}
                    api.logger.warning(
                        "browser side effect replay blocked",
                        extra={
                            "event": "browser.effect_replay_blocked",
                            "contract_key": s.replay_blocker.contract_key,
                            "status": s.replay_blocker.status,
                        },
                    )
                    s.consecutive_failures += 1
                    s.continue_step = True
                    return
                s.history_preflight = (
                    await s.action_history.preflight(
                        contract=s.prepared_effect.contract,
                        observation=s.current_obs,
                        semantic_operation=s.target_history.operation,
                    )
                    if s.prepared_effect is not None else None
                )
                if s.history_preflight is not None and s.history_preflight.blocked:
                    s.alternative_recovery = s.alternative_target_recovery.recovery_decision(
                        history=s.history,
                        target_id=s.history_preflight.intent.target_id,
                    )
                    s.history_hint = (
                        f"{s.history_preflight.reason} "
                        + (
                            "正在返回候选列表并排除当前目标。"
                            if s.alternative_recovery is not None else
                            "当前历史中没有可证明的候选列表，不会猜测其他目标。"
                        )
                        if s.lang == "zh" else
                        f"{s.history_preflight.reason} "
                        + (
                            "Returning to the proven candidate list and excluding this target."
                            if s.alternative_recovery is not None else
                            "No candidate list is proven by history; no alternative target will be guessed."
                        )
                    )
                    s.history.append(api.StepRecord(
                        observation=s.current_obs,
                        decision=api.Decision(
                            tool="__business_replay_skipped__",
                            args={
                                "business_key": s.history_preflight.intent.business_key,
                                "target": s.history_preflight.intent.target_id,
                            },
                            rationale="cross-run business replay guard",
                        ),
                        ok=True,
                        error=None,
                        result_digest=s.history_hint,
                    ))
                    yield {"type": "activity", "content": {
                        "kind": "analyze",
                        "message": s.history_hint,
                    }}, {}
                    api.logger.info(
                        "browser cross-run action replay skipped",
                        extra={
                            "event": "browser.action_history_blocked",
                            "business_key": s.history_preflight.intent.business_key,
                            "operation": s.history_preflight.intent.operation_id,
                            "target": s.history_preflight.intent.target_id,
                            "recovery": (
                                s.alternative_recovery.tool
                                if s.alternative_recovery is not None else "none"
                            ),
                            "recovery_url": (
                                str(s.alternative_recovery.args.get("url") or "")
                                if s.alternative_recovery is not None else ""
                            ),
                            "excluded_target_count": len(
                                s.alternative_target_recovery.excluded_target_ids
                            ),
                        },
                    )
                    s.pending_resolved_decision = (
                        s.alternative_recovery
                        or api.Decision(
                            tool="browser_observe",
                            args={},
                            rationale="verify the prior durable action without replaying it",
                        )
                    )
                    s.consecutive_failures = 0
                    s.continue_step = True
                    return

    if s.decision.tool == "browser_fill":
        s.fill_preflight = api.validate_fill_target(
            s.current_obs,
            dict(s.decision.args or {}),
        )
        if not s.fill_preflight.ok:
            s.model_stale_fill_hint = (
                "The fill target is not an editable field in the latest page state. "
                "The stale element ref was rejected; observing again before resolving the field."
            )
            s.stale_fill_hint = (
                "填写目标已不属于当前页面中的可编辑字段，已停止使用旧元素编号；"
                "正在重新读取页面并定位输入框。"
                if s.lang == "zh" else
                s.model_stale_fill_hint
            )
            s.history.append(api.StepRecord(
                observation=s.current_obs,
                decision=s.decision,
                ok=False,
                error=s.model_stale_fill_hint,
                result_digest=s.fill_preflight.reason,
            ))
            s.pending_resolved_decision = api.Decision(
                tool="browser_observe",
                args={},
                rationale="fill target preflight failed; refresh DOM before resolving the field again",
            )
            yield {"type": "activity", "content": {
                "kind": "warning", "message": s.stale_fill_hint,
            }}, {}
            api.logger.warning(
                "browser fill target rejected before dispatch",
                extra={
                    "event": "browser.fill_target_preflight_rejected",
                    "ref": s.fill_preflight.ref,
                    "reason": s.fill_preflight.reason,
                },
            )
            try:
                api.notify_driver_rejection(
                    s.planner,
                    s.decision,
                    s.current_obs,
                    category="stale_fill_target",
                    reason=s.fill_preflight.reason,
                )
            except Exception as exc:
                api.logger.warning(
                    "browser driver rejection hook failed",
                    extra={
                        "event": "browser.driver_rejection_hook_failed",
                        "category": "stale_fill_target",
                        "error": str(exc),
                    },
                )
            s.continue_step = True
            return

    s.superseded_receipts = s.effect_tracker.supersede_pending_for_action(
        s.decision,
        preserve_contract_key=(
            s.prepared_effect.contract.key()
            if s.prepared_effect is not None else ""
        ),
    )
    for s.superseded_receipt in s.superseded_receipts:
        s.business_actions.record(s.superseded_receipt)
    if s.superseded_receipts:
        api.logger.info(
            "browser pending verification window superseded",
            extra={
                "event": "browser.pending_effect_superseded",
                "tool": s.decision.tool,
                "contracts": [
                    item.contract_key for item in s.superseded_receipts
                ],
            },
        )

    s.dispatch_before_obs = s.current_obs
