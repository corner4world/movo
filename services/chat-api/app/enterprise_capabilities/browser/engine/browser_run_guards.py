from __future__ import annotations

from . import desktop_agent_executor as api


async def validate_action(s):
    if (
        s.decision.tool in api.READ_ONLY_TOOLS
        and s.current_obs.url
        and not api.is_fill_reconciliation(s.decision)
    ):
        s.same_count = (
            api.observe_count_for_current_interaction_state(s.history, s.current_obs)
            if s.decision.tool == "browser_observe"
            else api.read_count_for_current_state(s.history, s.current_obs)
        )
        if s.same_count >= api.BROWSER_MAX_READS_PER_STATE:
            yield {"type": "activity", "content": {
                "kind": "error",
                "message": (
                    f"已对 {s.current_obs.url} 做过 {s.same_count} 次读取。立即调 browser_done"
                    f"（把已有数据交棒），或 navigate 到其他页面。"
                    if s.lang == "zh"
                    else f"Already read {s.current_obs.url} {s.same_count} times. "
                         f"Call browser_done now or navigate elsewhere."
                ),
            }}, {}
            # Synthesize a failure so the loop feeds back negative
            # signal to the planner instead of executing yet another read.
            s.history.append(api.StepRecord(
                observation=s.current_obs, decision=s.decision, ok=False,
                error=f"read-budget exhausted on {s.current_obs.url}",
                result_digest="",
            ))
            s.consecutive_failures += 1
            if s.consecutive_failures >= api.MAX_CONSECUTIVE_FAILURES:
                s.assistance = api.browser_human_assistance(
                    source=api.READ_BUDGET,
                    observation=s.current_obs,
                    lang=s.lang,
                )
                if s.automatic_assistance_available(s.assistance):
                    async for s.event in s.suspend_for_human_assistance(
                        question=s.assistance.question,
                        next_step=s.step + 1,
                        assistance=s.assistance,
                    ):
                        yield s.event
                    s.terminal = True
                    return
                yield {"type": "activity", "content": {
                    "kind": "error",
                    "message": (
                        "读取循环无法自拔，且本页面的人工协助机会已使用"
                        if s.lang == "zh" else
                        "The read loop remained stuck after human assistance"
                    ),
                }}, {}
                yield {"type": "subagent_done", "content": {
                    "subagent_id": s.subagent_id,
                    "node_id": s.node.node_id,
                    "status": "failed_terminal",
                }}, {"browser_receipt": s.browser_failure_receipt(error="read loop")}
                s.terminal = True
                return
            s.continue_step = True
            return

    s.exploration_stagnation = api.assess_exploration_stagnation(
        s.decision,
        s.history,
        s.current_obs,
    )
    if s.exploration_stagnation.blocked:
        s.hint = (
            "连续滚动或纯等待后页面与滚动位置都没有变化；请更换目标、方向或操作策略。"
            if s.lang == "zh" else
            "Repeated scroll/delay produced no page or viewport progress; choose a different target, direction, or strategy."
        )
        s.history.append(api.StepRecord(
            observation=s.current_obs,
            decision=s.decision,
            ok=False,
            error=s.exploration_stagnation.reason,
            result_digest="",
        ))
        yield {"type": "activity", "content": {
            "kind": "warning",
            "message": s.hint,
        }}, {}
        s.consecutive_failures += 1
        if s.consecutive_failures >= api.MAX_CONSECUTIVE_FAILURES:
            s.assistance = api.browser_human_assistance(
                source=api.EXPLORATION_STAGNATION,
                observation=s.current_obs,
                decision=s.decision,
                lang=s.lang,
            )
            if s.automatic_assistance_available(s.assistance):
                async for s.event in s.suspend_for_human_assistance(
                    question=s.assistance.question,
                    next_step=s.step + 1,
                    assistance=s.assistance,
                ):
                    yield s.event
                s.terminal = True
                return
            s.break_step = True
            return
        s.continue_step = True
        return

    # Real browser tool → dispatch via LocalBridge
    if not api.is_browser_tool(s.decision.tool) and not api.is_control_tool(s.decision.tool):
        yield {"type": "activity", "content": {
            "kind": "error",
            "message": (f"未识别工具：{s.decision.tool}" if s.lang == "zh"
                        else f"Unknown tool: {s.decision.tool}"),
        }}, {}
        s.consecutive_failures += 1
        if s.consecutive_failures >= api.MAX_CONSECUTIVE_FAILURES:
            s.break_step = True
            return
        s.continue_step = True
        return

    # Same-URL navigation is pure step waste. Reject it before
    # dispatch so planner jitter / duplicated first-step
    # shortcut doesn't burn the step budget.
    if s.decision.tool == "browser_navigate" and isinstance(s.decision.args, dict):
        s.nav_url = str(s.decision.args.get("url") or "").strip()
        s.cur_url = str(getattr(s.current_obs, "url", "") or "").strip()
        if s.nav_url and s.cur_url and s.nav_url == s.cur_url:
            s.model_hint = f"Already on {s.cur_url}; do not browser_navigate to the same URL again."
            s.hint = (
                f"已在当前页面 {s.cur_url}，不要重复 browser_navigate 到同一 URL。"
                if s.lang == "zh" else
                s.model_hint
            )
            s.history.append(api.StepRecord(
                observation=s.current_obs, decision=s.decision, ok=False,
                error=s.model_hint, result_digest="",
            ))
            yield {"type": "activity", "content": {
                "kind": "warning",
                "message": s.hint,
            }}, {}
            s.consecutive_failures += 1
            if s.consecutive_failures >= api.MAX_CONSECUTIVE_FAILURES:
                s.break_step = True
                return
            s.continue_step = True
            return

    # Pre-dispatch gate: reject repeated browser_wait_for on a
    # text query we've already missed MAX times. Otherwise the
    # LLM burns MAX_STEPS × 10s on the same impossible lookup.
    s.wait_recovery = api.recover_passive_wait(s.decision, s.current_obs, s.history)
    if s.wait_recovery is not s.decision:
        api.logger.info("passive wait redirected to observation", extra={"event": "browser.passive_wait_recovery", "revision": s.current_obs.revision})
        s.decision = s.wait_recovery
    if (
        s.decision.tool == "browser_wait_for"
        and isinstance(s.decision.args, dict)
    ):
        s._wait_text = str(s.decision.args.get("text") or "").strip()
        # count INVOCATIONS of wait_for-text, not just
        # failures. The primary fix is in the agent (wait_for now
        # returns matched_ref). This counter catches the residual
        # anti-pattern where LLM still re-waits after already
        # getting ok+ref back — strongly directs it to click instead.
        s._per_text_calls = s.wait_for_text_calls.get(s._wait_text, 0) if s._wait_text else 0
        s._total_calls = sum(s.wait_for_text_calls.values())
        s._per_text_tripped = bool(s._wait_text and s._per_text_calls >= s.WAIT_FOR_TEXT_MAX_CALLS)
        s._cross_text_tripped = s._total_calls >= s.WAIT_FOR_TEXT_MAX_CALLS * 2
        # P1-hard · When we already have a cached ref for this text,
        # rewrite the decision into browser_click(ref=…) so the LLM's
        # intent ("confirm that thing exists → proceed") is fulfilled
        # in a single step, instead of endlessly re-waiting. The LLM
        # usually can't remember prior returned refs across turns,
        # so we remember for it. Generic — works for any site that
        # returns ref from wait_for. Never triggers on the FIRST
        # wait_for; only kicks in on the 2nd attempt of the same text.
        s._cached_target = s.wait_for_click_targets.get(s._wait_text) if s._wait_text else None
        s._cached_ref = s._cached_target.ref if s._cached_target else None
        if (
            s._cached_target
            and s._per_text_calls >= 1
            and api.can_reuse_click_target(s._cached_target, s.current_obs)
        ):
            s.rewrite_note = (
                f"browser_wait_for text={s._wait_text!r} 第 {s._per_text_calls + 1} 次调用，"
                f"系统已自动重写为 browser_click(ref={s._cached_ref})"
                if s.lang == "zh"
                else f"browser_wait_for text={s._wait_text!r} (call #{s._per_text_calls + 1})"
                     f" auto-rewritten to browser_click(ref={s._cached_ref})"
            )
            s.decision = api.Decision(
                tool="browser_click",
                args={"ref": s._cached_ref},
                rationale=s.rewrite_note,
            )
            yield {"type": "activity", "content": {
                "kind": "analyze", "message": s.rewrite_note[:160],
            }}, {}
            api.logger.info("wait_for rewritten to click", extra={"event": "browser.wait_for_rewrite_to_click", "text": s._wait_text, "ref": s._cached_ref})
            # Fall through to normal dispatch with the rewritten decision.
        elif s._per_text_tripped or s._cross_text_tripped:
            s.hint = (
                f"⚠ `browser_wait_for text=\"{s._wait_text}\"` invoked "
                f"{s._per_text_calls} times. Successful wait_for returns `matched_ref`"
                " and `clickable_ref` — use that ref directly with browser_click/fill."
                " If no ref was returned, the text isn't on a clickable element;"
                " switch to browser_observe or browser_read_text."
            )
            s.history.append(api.StepRecord(
                observation=s.current_obs, decision=s.decision, ok=False,
                error=s.hint, result_digest="",
            ))
            yield {"type": "activity", "content": {
                "kind": "warning",
                "message": (
                    f"browser_wait_for 被拦截：text={s._wait_text!r} 已调用 "
                    f"{s._per_text_calls} 次，应使用返回的 ref 做下一步"
                    if s.lang == "zh"
                    else f"browser_wait_for blocked: text={s._wait_text!r} invoked "
                         f"{s._per_text_calls}x, use the returned ref instead"
                ),
            }}, {}
            api.logger.warning("wait_for text blocked", extra={"event": "browser.wait_for_text_blocked", "text": s._wait_text, "calls": s._per_text_calls})
            s.consecutive_failures += 1
            if s.consecutive_failures >= api.MAX_CONSECUTIVE_FAILURES:
                s.break_step = True
                return
            s.continue_step = True
            return
        # Count this invocation upfront (not only on failure).
        if s._wait_text:
            s.wait_for_text_calls[s._wait_text] = s._per_text_calls + 1

    # Bind visual coordinates to the latest DOM ref before any state
    # or form validation. The rewritten semantic action must pass the
    # same mission guards as a planner-produced ref action.
    s.coordinate_binding = api.bind_coordinate_action(s.decision, s.current_obs)
    if s.coordinate_binding.blocked:
        s.history.append(api.StepRecord(
            observation=s.current_obs,
            decision=s.decision,
            ok=False,
            error=s.coordinate_binding.reason,
            result_digest="",
        ))
        yield {"type": "activity", "content": {
            "kind": "warning", "message": s.coordinate_binding.reason,
        }}, {}
        s.pending_resolved_decision = api.Decision(
            tool="browser_observe",
            args={},
            rationale="coordinate input must be rebound against the latest editable DOM target",
        )
        s.consecutive_failures += 1
        if s.consecutive_failures >= api.MAX_CONSECUTIVE_FAILURES:
            s.break_step = True
            return
        s.continue_step = True
        return
    if s.coordinate_binding.decision != s.decision:
        api.logger.info(
            "browser coordinate action rebound to live DOM target",
            extra={
                "event": "browser.coordinate_action_rebound",
                "from_tool": s.decision.tool,
                "to_tool": s.coordinate_binding.decision.tool,
                "target_ref": str((s.coordinate_binding.decision.args or {}).get("ref") or ""),
            },
        )
        s.decision = s.coordinate_binding.decision

    # Pre-flight action validation. The planner has the state
    # ledger in its prompt; this layer enforces the same rules
    # even when the LLM disregards them.
    if s.context_tracks_state:
        try:
            s.verdict, s.new_decision, s.v_hint = s.task_context.validate_action(s.decision, s.current_obs)
        except Exception:
            s.verdict, s.new_decision, s.v_hint = ("allow", s.decision, "")
        if s.verdict == "rewrite" and s.new_decision is not None:
            yield {"type": "activity", "content": {
                "kind": "analyze",
                "message": s.v_hint,
            }}, {}
            s.decision = s.new_decision
        elif s.verdict == "reject":
            s.history.append(api.StepRecord(
                observation=s.current_obs, decision=s.decision, ok=False,
                error=s.v_hint, result_digest="",
            ))
            yield {"type": "activity", "content": {
                "kind": "warning",
                "message": s.v_hint,
            }}, {}
            api.logger.info("browser context action rejected", extra={"event": "browser.context_action_rejected", "tool": s.decision.tool, "hint": s.v_hint[:120]})
            s.consecutive_failures += 1
            if s.consecutive_failures >= api.MAX_CONSECUTIVE_FAILURES:
                s.break_step = True
                return
            s.continue_step = True
            return

    # A hidden browser has no renderer-side focus guarantee. Bind key
    # actions to the current form field before scope/dependency checks
    # and let the local agent restore focus immediately before input.
    s.decision = s.form_transaction.bind_interaction_target(
        s.decision,
        s.current_obs,
    )
    s.prepared_decision = api.prepare_driver_dispatch(
        s.planner,
        s.decision,
        s.current_obs,
    )
    if s.prepared_decision != s.decision:
        api.logger.info(
            "browser decision changed by final driver dispatch guard",
            extra={
                "event": "browser.driver_dispatch_guard",
                "driver": s.planner.kind,
                "from_tool": s.decision.tool,
                "to_tool": s.prepared_decision.tool,
                "from_ref": str((s.decision.args or {}).get("ref") or ""),
                "to_ref": str((s.prepared_decision.args or {}).get("ref") or ""),
            },
        )
        s.decision = s.prepared_decision
    s.recovery_blocker = s.interaction_target_recovery.blocker(s.decision, s.current_obs)
    if s.recovery_blocker is not None:
        s.history.append(api.StepRecord(
            observation=s.current_obs,
            decision=s.decision,
            ok=False,
            error=s.recovery_blocker,
            result_digest="",
        ))
        yield {"type": "activity", "content": {
            "kind": "warning", "message": s.recovery_blocker,
        }}, {}
        s.pending_resolved_decision = api.Decision(
            tool="browser_observe",
            args={},
            rationale="quarantined target requires a fresh strategy from current DOM",
        )
        s.consecutive_failures += 1
        if s.consecutive_failures >= api.MAX_CONSECUTIVE_FAILURES:
            s.assistance = api.browser_human_assistance(
                source=api.NAVIGATION_TARGET_BLOCKED,
                observation=s.current_obs,
                decision=s.decision,
                lang=s.lang,
            )
            if s.automatic_assistance_available(s.assistance):
                async for s.event in s.suspend_for_human_assistance(
                    question=s.assistance.question,
                    next_step=s.step + 1,
                    assistance=s.assistance,
                ):
                    yield s.event
                s.terminal = True
                return
            s.break_step = True
            return
        s.continue_step = True
        return
    s.click_blocker = s.click_outcome_policy.blocker(s.decision, s.current_obs)
    if s.click_blocker is not None:
        s.history.append(api.StepRecord(
            observation=s.current_obs,
            decision=s.decision,
            ok=False,
            error=s.click_blocker,
            result_digest="",
        ))
        yield {"type": "activity", "content": {
            "kind": "warning", "message": s.click_blocker,
        }}, {}
        s.consecutive_failures += 1
        if s.consecutive_failures >= api.MAX_CONSECUTIVE_FAILURES:
            s.assistance = api.browser_human_assistance(
                source=api.NAVIGATION_TARGET_BLOCKED,
                observation=s.current_obs,
                decision=s.decision,
                lang=s.lang,
            )
            if s.automatic_assistance_available(s.assistance):
                async for s.event in s.suspend_for_human_assistance(
                    question=s.assistance.question,
                    next_step=s.step + 1,
                    assistance=s.assistance,
                ):
                    yield s.event
                s.terminal = True
                return
            s.break_step = True
            return
        s.continue_step = True
        return

    s.scope_blocker = s.form_transaction.interaction_scope_blocker(
        s.decision,
        s.current_obs,
    )
    if s.scope_blocker is not None:
        s.model_scope_hint = (
            "Cross-form interaction blocked while the current form is still active. "
            "Continue inside that form; the lock is released after submit, close, or navigation."
        )
        s.scope_hint = (
            "已阻止跨表单操作：当前正在编辑的表单尚未完成。"
            "请继续操作当前表单内的字段或按钮；表单提交、关闭或页面切换后会自动解除限制。"
            if s.lang == "zh" else
            s.model_scope_hint
        )
        s.history.append(api.StepRecord(
            observation=s.current_obs,
            decision=s.decision,
            ok=False,
            error=s.model_scope_hint,
            result_digest=api.json.dumps({
                "active_scope": s.scope_blocker.active_scope,
                "target_scope": s.scope_blocker.target_scope,
            }, ensure_ascii=False),
        ))
        yield {"type": "activity", "content": {
            "kind": "warning", "message": s.scope_hint,
        }}, {}
        api.logger.warning(
            "browser cross-form interaction blocked",
            extra={
                "event": "browser.form_scope_blocked",
                "tool": s.decision.tool,
                "ref": str((s.decision.args or {}).get("ref") or ""),
                "active_scope": s.scope_blocker.active_scope,
                "target_scope": s.scope_blocker.target_scope,
            },
        )
        try:
            api.notify_driver_rejection(
                s.planner,
                s.decision,
                s.current_obs,
                category=(
                    "scope_target_unresolved"
                    if s.scope_blocker.target_scope == "unresolved"
                    else "cross_form_target"
                ),
                reason=s.scope_blocker.reason,
            )
        except Exception as exc:
            api.logger.warning(
                "browser driver rejection hook failed",
                extra={
                    "event": "browser.driver_rejection_hook_failed",
                    "category": "form_scope",
                    "error": str(exc),
                },
            )
        s.pending_resolved_decision = api.Decision(
            tool="browser_observe",
            args={},
            rationale=(
                "form target was rejected before dispatch; refresh the "
                "DOM and resolve the field inside the active scope"
            ),
        )
        s.consecutive_failures += 1
        if s.consecutive_failures >= api.MAX_CONSECUTIVE_FAILURES:
            s.break_step = True
            return
        s.continue_step = True
        return

    s.dependency_target = s.form_transaction.resolve_interaction_target(
        s.decision,
        s.current_obs,
    )
    s.dependency_blocker = s.form_transaction.dependent_action_blocker(
        s.current_obs,
        tool=s.decision.tool,
        target=s.dependency_target,
        key=str((s.decision.args or {}).get("key") or ""),
    )
    if s.dependency_blocker is not None:
        s.blocked_fields = "、".join(s.dependency_blocker.fields)
        s.model_dependency_hint = (
            f"Dependent action blocked: fields {', '.join(s.dependency_blocker.fields)} "
            "are not confirmed. Refill and verify them before clicking a button or pressing Enter."
        )
        s.dependency_hint = (
            f"已阻止继续操作：字段“{s.blocked_fields}”尚未确认写入。"
            "必须先重新填写并确认该字段，再点击按钮或按回车。"
            if s.lang == "zh" else
            s.model_dependency_hint
        )
        s.history.append(api.StepRecord(
            observation=s.current_obs,
            decision=s.decision,
            ok=False,
            error=s.model_dependency_hint,
            result_digest="",
        ))
        yield {"type": "activity", "content": {
            "kind": "warning", "message": s.dependency_hint,
        }}, {}
        api.logger.warning(
            "browser dependent action blocked by unverified fill",
            extra={
                "event": "browser.dependent_action_blocked_unverified_fill",
                "tool": s.decision.tool,
                "fields": list(s.dependency_blocker.fields),
            },
        )
        s.consecutive_failures += 1
        if s.consecutive_failures >= api.MAX_CONSECUTIVE_FAILURES:
            s.break_step = True
            return
        s.continue_step = True
        return

    s.prepared_effect: api.PreparedEffect | None = None
    s.submit_press = bool(
        s.decision.tool == "browser_press"
        and str((s.decision.args or {}).get("key") or "").strip().lower() in {"enter", "return"}
        and s.form_transaction.has_confirmed_fill()
    )
