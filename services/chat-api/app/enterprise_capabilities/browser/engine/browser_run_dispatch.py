from __future__ import annotations

from . import desktop_agent_executor as api


async def dispatch_action(s):
    s.click_outcome = api.ClickOutcome(ok=True)
    # Lifecycle starts immediately before the real sidecar dispatch.
    # Post-action observation and stabilization remain part of this
    # same operation, so the row stays active until they finish.
    yield {"type": "tool_requested", "content": {
        "tool": s.decision.tool, "args": s.decision.args,
        "rationale": s.decision.rationale,
        "rationale_source": s.decision.rationale_source,
    }}, {}
    try:
        s.result, s.ok, s.err = await s.execution_budget.wait_for(
            s.executor._dispatch(s.decision)
        )
    except api.BrowserExecutionBudgetExpired:
        s.execution_budget_exhausted = True
        s.execution_budget_effect_unknown = api.interrupted_effect_requires_handoff(
            capability_id=s.action_capability_id,
            tool=s.decision.tool,
            final_commit_control=bool(
                s.prepared_effect is not None
                and s.prepared_effect.contract.is_commit
            ),
        )
        s.break_step = True
        return
    if s.ok and api.observation_retry_required(s.result):
        yield {"type": "activity", "content": {
            "kind": "analyze",
            "message": (
                "点击已执行，正在单独刷新页面状态" if s.lang == "zh"
                else "The click was dispatched; refreshing page state separately"
            ),
        }}, {}
        s.probe_result, s.probe_ok, s.probe_err = await s.executor._dispatch(
            api.Decision(
                tool="browser_observe",
                args={},
                rationale="post-action observation retry without replaying mutation",
            )
        )
        if s.probe_ok and isinstance(s.result, dict):
            s.result = api.reconcile_post_action_observation(s.result, s.probe_result)
            api.logger.info(
                "post-action observation recovered",
                extra={"event": "browser.post_action_observation_recovered", "tool": s.decision.tool},
            )
        else:
            s.pending_resolved_decision = api.Decision(
                tool="browser_observe",
                args={},
                rationale="action dispatched; observation still pending and must be refreshed before another mutation",
            )
            api.logger.warning(
                "post-action observation remains pending",
                extra={
                    "event": "browser.post_action_observation_pending",
                    "tool": s.decision.tool,
                    "error": str(s.probe_err or "observation retry failed"),
                },
            )
    if s.ok:
        s.result = await api.stabilize_transition_observation(
            decision=s.decision,
            before=s.dispatch_before_obs,
            result=s.result,
            dispatch=s.executor._dispatch,
        )
    if s.ok:
        s.click_outcome = s.click_outcome_policy.evaluate(
            s.decision,
            s.result,
            s.dispatch_before_obs,
        )
        if not s.click_outcome.ok:
            s.ok = False
            s.err = s.click_outcome.error
    if s.decision.tool == "browser_click":
        if s.ok:
            s.interaction_target_recovery.record_success(s.decision, s.dispatch_before_obs)
        else:
            s.interaction_target_recovery.record_failure(s.decision, s.dispatch_before_obs, s.err)
            s._failed_click_ref = str((s.decision.args or {}).get("ref") or "")
            s._failed_click_target = next((
                item for item in s.dispatch_before_obs.elements
                if isinstance(item, dict) and str(item.get("ref") or "") == s._failed_click_ref
            ), {})
            api.logger.warning(
                "browser click dispatch failed",
                extra={
                    "event": "browser.click_dispatch_failed",
                    "ref": s._failed_click_ref,
                    "revision": str(s.dispatch_before_obs.revision or ""),
                    "selector": str(s._failed_click_target.get("selector") or "")[:500],
                    "backend_node_id": s._failed_click_target.get("backendNodeId"),
                    "role": str(s._failed_click_target.get("role") or ""),
                    "target_name": str(s._failed_click_target.get("name") or "")[:240],
                    "href": str(s._failed_click_target.get("href") or "")[:1000],
                    "content_context_id": str(
                        s._failed_click_target.get("contentContextId") or ""
                    )[:500],
                    "error": str(s.err or "unknown click failure")[:4000],
                },
            )
    if s.decision.tool == "browser_fill" and not s.ok:
        s._failed_fill_ref = str((s.decision.args or {}).get("ref") or "")
        s._failed_fill_target = next((
            item for item in s.dispatch_before_obs.elements
            if isinstance(item, dict) and str(item.get("ref") or "") == s._failed_fill_ref
        ), {})
        api.logger.warning(
            "browser fill dispatch failed",
            extra={
                "event": "browser.fill_dispatch_failed",
                "ref": s._failed_fill_ref,
                "revision": str(s.dispatch_before_obs.revision or ""),
                "selector": str(s._failed_fill_target.get("selector") or ""),
                "role": str(s._failed_fill_target.get("role") or ""),
                "error": str(s.err or "unknown fill failure")[:1000],
            },
        )
    if s.decision.tool == "browser_execute_plan" and not s.ok:
        api.logger.warning(
            "browser action plan dispatch failed",
            extra={
                "event": "browser.action_plan_dispatch_failed",
                "revision": str(s.dispatch_before_obs.revision or ""),
                "error": str(s.err or "unknown action-plan failure")[:1000],
                "result_digest": api._digest(s.decision.tool, s.result)[:4000],
                "receipts": (
                    list(s.result.get("receipts") or [])[:8]
                    if isinstance(s.result, dict) else []
                ),
            },
        )
    yield {"type": "tool_completed", "content": {
        "tool": s.decision.tool, "ok": s.ok, "result": s.result,
        **({"error": s.err} if not s.ok and s.err else {}),
    }}, {}

    # A successful text lookup is only useful if its resolved target
    # is acted on before SPA re-rendering invalidates the ref. Local
    # high-confidence rules click directly; ambiguous/unknown matches
    # go through a constrained candidate-only picker. The follow-up is
    # queued here and consumed before the general planner gets another
    # turn. The normal pre-dispatch gates still apply to the click.
    if api.should_resolve_wait_action(s.decision, ok=s.ok, result=s.result):
        s._wait_observation = api._update_obs(s.current_obs, s.decision.tool, s.result)
        s._resolved_action = await api.resolve_wait_for_action(
            goal=s.goal,
            query=str(s.decision.args.get("text") or ""),
            result=s.result,
            observation=s._wait_observation,
            domain=str(s.decision.args.get("domain") or api._domain(s._wait_observation.url) or ""),
            lang=s.lang,
        )
        if s._resolved_action.decision is not None:
            s._source_text = (
                "本地规则已确认目标，下一步直接执行点击"
                if s._resolved_action.source == "local_rule" and s.lang == "zh"
                else "候选已确认，下一步执行受约束点击"
                if s.lang == "zh"
                else "Local rule resolved target; click queued"
                if s._resolved_action.source == "local_rule"
                else "Candidate selected; constrained click queued"
            )
            yield {"type": "activity", "content": {
                "kind": "analyze", "message": s._source_text,
            }}, {}
            s.pending_resolved_decision = s._resolved_action.decision

    # Post-dispatch bookkeeping for wait_for: cache any returned
    # ref keyed by the queried text (for P1-hard rewrite on the
    # next call) + debug log. Invocation counter is already
    # maintained in the pre-gate block.
    if (
        s.decision.tool == "browser_wait_for"
        and isinstance(s.decision.args, dict)
    ):
        s._wait_text_after = str(s.decision.args.get("text") or "").strip()
        if s._wait_text_after and s.ok and isinstance(s.result, dict):
            s._target = api.confirmed_click_target(s.result)
            if s._target is not None:
                s.wait_for_click_targets[s._wait_text_after] = s._target
                s.wait_for_text_refs[s._wait_text_after] = s._target.ref
            else:
                s.wait_for_click_targets.pop(s._wait_text_after, None)
                s.wait_for_text_refs.pop(s._wait_text_after, None)
        if s._wait_text_after:
            api.logger.debug(
                "wait_for text call",
                extra={"event": "browser.wait_for_text_call", "text": s._wait_text_after, "ok": bool(s.ok), "count": s.wait_for_text_calls.get(s._wait_text_after, 0), "max": s.WAIT_FOR_TEXT_MAX_CALLS, "cached_ref": s.wait_for_text_refs.get(s._wait_text_after, "")},
            )

    s.current_obs = api._update_obs(s.current_obs, s.decision.tool, s.result)
    if (
        s.decision.tool in {"browser_upload_file", "browser_paste_image"}
        and not s.ok
        and api.is_media_delivery_handoff_error(tool=s.decision.tool, error=s.err)
    ):
        s.driver_state = s.planner.export_checkpoint_state()
        s.handoff = api.build_media_upload_handoff(
            context=s.input_context,
            completed_candidate_ids=api.completed_media_candidate_ids(s.driver_state),
            user_id=s.executor.user_id,
        )
        if s.handoff:
            s.pending_resolved_decision = api.media_upload_assistance_decision(
                s.handoff,
                lang=s.lang,
            )
    s.form_transaction.after_action(
        s.decision,
        before=s.dispatch_before_obs,
        after=s.current_obs,
        ok=s.ok,
    )
    if s.decision.tool in {"browser_click", "browser_click_at"} and not s.ok and api.is_stale_interaction_target_error(s.err):
        s.covered = api.obstruction_evidence(s.err)
        s.pending_resolved_decision = api.Decision(
            tool="browser_observe",
            args={"with_screenshot": True} if s.covered else {},
            rationale=api.OBSTRUCTION_GUIDANCE if s.covered else "click target changed during dispatch; refresh DOM before resolving another target",
        )
        yield {"type": "activity", "content": {
            "kind": "warning",
            "message": (
                ("目标存在但被覆盖，正在检查覆盖层；不会继续点击底层控件。" if s.covered else "点击目标已发生变化，正在重新读取当前页面，不再使用旧元素编号")
                if s.lang == "zh" else
                "The click target changed; refreshing the page instead of reusing the stale ref"
            ),
        }}, {}
    if s.decision.tool in {"browser_fill", "browser_observe"}:
        s.reconciliation = api.reconcile_input_step(
            decision=s.decision, before=s.dispatch_before_obs, after=s.current_obs,
            result=s.result, ok=s.ok, error=s.err,
            transaction=s.form_transaction, retry=s.fill_retry_policy, lang=s.lang,
        )
        s.current_obs = s.reconciliation.observation
        if s.reconciliation.next_decision is not None:
            s.pending_resolved_decision = s.reconciliation.next_decision
        if s.reconciliation.message:
            yield {"type": "activity", "content": {
                "kind": "analyze", "message": s.reconciliation.message,
            }}, {}
    s.history.append(api.StepRecord(
        observation=s.current_obs, decision=s.decision, ok=s.ok, error=s.err,
        result_digest=api._digest(s.decision.tool, s.result),
        decision_observation=s.dispatch_before_obs,
    ))

    if (
        s.prepared_effect is not None
        and s.ok
        and not s.current_obs.fresh
    ):
        s.deferred_receipt = s.effect_tracker.defer_until_fresh_observation(
            prepared=s.prepared_effect,
            reason="post-action observation unavailable; verification deferred",
        )
        s.business_actions.record(s.deferred_receipt)
        s.pending_resolved_decision = api.Decision(
            tool="browser_observe",
            args={},
            rationale="verify the dispatched business action from a fresh DOM snapshot",
        )
    elif api.effect_verification_eligible(
        prepared_effect=s.prepared_effect,
        action_ok=s.ok,
        click_outcome=s.click_outcome,
    ):
        s.effect_receipt = await s.effect_tracker.record(
            prepared=s.prepared_effect,
            after=s.current_obs,
            supplemental_evidence=s.form_transaction.outcome_evidence(s.current_obs),
        )
        if s.effect_receipt is None:
            yield {"type": "activity", "content": {
                "kind": "analyze",
                "message": (
                    "已进入可编辑状态，继续填写后再提交"
                    if s.lang == "zh" else
                    "An editable surface opened; fill it before submitting"
                ),
            }}, {}
        else:
            s.business_actions.record(s.effect_receipt)
            api.notify_effect_receipt(s.planner, s.effect_receipt)
            await s.persist_confirmed_effect(s.effect_receipt, s.current_obs)
            if s.effect_receipt.status == "confirmed_success":
                s.deferred_success_receipt = s.effect_receipt
            elif s.effect_receipt.status in {"pending", "unknown"}:
                s.pending_resolved_decision = api.Decision(
                    tool="browser_observe",
                    args={},
                    rationale="recheck the dispatched business effect before planning another action",
                )
            s.form_transaction.after_effect(s.effect_receipt, s.current_obs)
            s.receipt_application = api.apply_effect_receipt(
                context=s.task_context,
                tracks_context_state=s.context_tracks_state,
                receipt=s.effect_receipt,
                observation=s.current_obs,
            )
            if s.receipt_application.error:
                api.logger.warning(
                    "browser context effect hook failed",
                    extra={
                        "event": "browser.context_effect_hook_failed",
                        "error": s.receipt_application.error,
                    },
                )
            s.history.append(api.StepRecord(
                observation=s.current_obs,
                decision=api.Decision(
                    tool="__effect_verification__",
                    args={"contract_key": s.effect_receipt.contract_key},
                    rationale="system effect verification",
                ),
                ok=s.effect_receipt.status == "confirmed_success",
                error=None if s.effect_receipt.status == "confirmed_success" else s.effect_receipt.reason,
                result_digest=api.json.dumps(s.effect_receipt.model_dump(mode="json"), ensure_ascii=False)[:6000],
            ))
            s.effect_message = api._effect_timeline_message(
                s.effect_receipt.status,
                s.effect_receipt.reason,
                lang=s.lang,
            )
            yield {"type": "activity", "content": {
                "kind": "complete" if s.effect_receipt.status == "confirmed_success" else "analyze",
                "message": s.effect_message[:240],
            }}, {}
            yield {"type": "runtime_status", "content": {
                "side_effect_guard": {
                    "status": s.effect_receipt.status,
                    "blocks_replay": s.effect_receipt.blocks_replay,
                    "contract_key": s.effect_receipt.contract_key,
                    "action_name": s.effect_receipt.action_name,
                    "receipt": s.effect_receipt.model_dump(mode="json"),
                },
            }}, {}
            api.logger.info(
                "browser effect verified",
                extra={
                    "event": "browser.effect_verified",
                    "contract_key": s.effect_receipt.contract_key,
                    "status": s.effect_receipt.status,
                    "confidence": s.effect_receipt.confidence,
                    "action": s.effect_receipt.action_name,
                },
            )
            if s.effect_receipt.status == "confirmed_failure":
                s._topology = (getattr(s.inputs, "output_spec", None) or {}).get("graph_topology") or []
                for s.failure_event in api.build_effect_business_failure_events(
                    receipt=s.effect_receipt,
                    objective=str(s.node.goal or ""),
                    steps=len(s.history),
                    lang=s.lang,
                    result_data=api.project_verified_operation_result(
                        receipt=s.effect_receipt,
                        context=s.task_context,
                        form_state=s.form_transaction.export_state(),
                        observation=s.current_obs,
                    ),
                    subagent_id=s.subagent_id,
                    node_id=s.node.node_id,
                    emit_answer=not bool(s._topology),
                ):
                    yield s.failure_event
                s.terminal = True
                return
            if s.receipt_application.goal_completed:
                s.summary, s.completion_meta = api.build_effect_completion(
                    receipt=s.effect_receipt,
                    objective=str(s.node.goal or ""),
                    steps=len(s.history),
                    lang=s.lang,
                    result_data=api.project_verified_operation_result(
                        receipt=s.effect_receipt,
                        context=s.task_context,
                        form_state=s.form_transaction.export_state(),
                        observation=s.current_obs,
                    ),
                )
                s._topology = (getattr(s.inputs, "output_spec", None) or {}).get("graph_topology") or []
                if not s._topology:
                    yield {"type": "answer", "content": s.summary}, {}
                s.schedule_workflow_capture()
                yield {"type": "subagent_done", "content": {
                    "subagent_id": s.subagent_id,
                    "node_id": s.node.node_id,
                    "status": "succeeded",
                }}, s.completion_meta
                s.terminal = True
                return

    if s.prepared_effect is None and s.ok and s.decision.tool in {
        "browser_observe", "browser_read_text", "browser_navigate",
        "browser_scroll", "browser_back", "browser_forward",
    }:
        s.refreshed_receipts = await s.effect_tracker.refresh_pending(
            after=s.current_obs,
            supplemental_evidence=s.form_transaction.outcome_evidence(s.current_obs),
        )
        for s.refreshed_receipt in s.refreshed_receipts:
            s.business_actions.record(s.refreshed_receipt)
            api.notify_effect_receipt(s.planner, s.refreshed_receipt)
            await s.persist_confirmed_effect(s.refreshed_receipt, s.current_obs)
            if s.refreshed_receipt.status == "confirmed_success":
                s.deferred_success_receipt = s.refreshed_receipt
            s.form_transaction.after_effect(s.refreshed_receipt, s.current_obs)
            s.receipt_application = api.apply_effect_receipt(
                context=s.task_context,
                tracks_context_state=s.context_tracks_state,
                receipt=s.refreshed_receipt,
                observation=s.current_obs,
            )
            if s.receipt_application.error:
                api.logger.warning(
                    "browser context delayed effect hook failed",
                    extra={
                        "event": "browser.context_delayed_effect_hook_failed",
                        "error": s.receipt_application.error,
                    },
                )
            s.history.append(api.StepRecord(
                observation=s.current_obs,
                decision=api.Decision(
                    tool="__effect_reverification__",
                    args={"contract_key": s.refreshed_receipt.contract_key},
                    rationale="system pending effect reverification",
                ),
                ok=s.refreshed_receipt.status == "confirmed_success",
                error=(
                    None if s.refreshed_receipt.status == "confirmed_success"
                    else s.refreshed_receipt.reason
                ),
                result_digest=api.json.dumps(
                    s.refreshed_receipt.model_dump(mode="json"),
                    ensure_ascii=False,
                )[:6000],
            ))
            yield {"type": "activity", "content": {
                "kind": (
                    "complete" if s.refreshed_receipt.status == "confirmed_success"
                    else "analyze"
                ),
                "message": (
                    f"操作复核：{s.refreshed_receipt.status}（{s.refreshed_receipt.reason}）"
                    if s.lang == "zh" else
                    f"Operation recheck: {s.refreshed_receipt.status} ({s.refreshed_receipt.reason})"
                )[:240],
            }}, {}
            if s.refreshed_receipt.status == "confirmed_failure":
                s._topology = (getattr(s.inputs, "output_spec", None) or {}).get("graph_topology") or []
                for s.failure_event in api.build_effect_business_failure_events(
                    receipt=s.refreshed_receipt,
                    objective=str(s.node.goal or ""),
                    steps=len(s.history),
                    lang=s.lang,
                    result_data=api.project_verified_operation_result(
                        receipt=s.refreshed_receipt,
                        context=s.task_context,
                        form_state=s.form_transaction.export_state(),
                        observation=s.current_obs,
                    ),
                    subagent_id=s.subagent_id,
                    node_id=s.node.node_id,
                    emit_answer=not bool(s._topology),
                ):
                    yield s.failure_event
                s.terminal = True
                return
            if bool((s.refreshed_receipt.fingerprint or {}).get("verification_exhausted")):
                s.pending_resolved_decision = api.build_effect_verification_decision(
                    s.refreshed_receipt,
                    lang=s.lang,
                )
                yield {"type": "activity", "content": {
                    "kind": "warning",
                    "message": (
                        "自动复核已用尽，将请你确认保存/提交结果；系统不会重复执行该动作。"
                        if s.lang == "zh" else
                        "Automatic verification is exhausted. Human confirmation is required; the action will not be replayed."
                    ),
                }}, {}
                break
            if s.receipt_application.goal_completed:
                s.summary, s.completion_meta = api.build_effect_completion(
                    receipt=s.refreshed_receipt,
                    objective=str(s.node.goal or ""),
                    steps=len(s.history),
                    lang=s.lang,
                    result_data=api.project_verified_operation_result(
                        receipt=s.refreshed_receipt,
                        context=s.task_context,
                        form_state=s.form_transaction.export_state(),
                        observation=s.current_obs,
                    ),
                )
                s._topology = (getattr(s.inputs, "output_spec", None) or {}).get("graph_topology") or []
                if not s._topology:
                    yield {"type": "answer", "content": s.summary}, {}
                s.schedule_workflow_capture()
                yield {"type": "subagent_done", "content": {
                    "subagent_id": s.subagent_id,
                    "node_id": s.node.node_id,
                    "status": "succeeded",
                }}, s.completion_meta
                s.terminal = True
                return

    # Let the selected context update its durable state from the
    # observed action transition.
    if s.context_tracks_state:
        try:
            for s.context_transition in api.context_action_transitions(
                s.decision,
                result=s.result,
                ok=s.ok,
                error=s.err,
                before=s.dispatch_before_obs,
                after=s.current_obs,
            ):
                s.task_context.after_transition(
                    s.context_transition.transition,
                    s.context_transition.result,
                    s.context_transition.ok,
                    error=s.context_transition.error,
                )
        except Exception as exc:
            api.logger.warning(
                "browser context after step failed",
                extra={
                    "event": "browser.context_after_step_failed",
                    "context": type(s.task_context).__name__,
                    "error": str(exc),
                },
            )
