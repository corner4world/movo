from __future__ import annotations

from . import desktop_agent_executor as api


async def complete_step(s):
    s.effect_task_outcome = api.applied_effect_task_outcome(
        context=s.task_context,
        tracks_context_state=s.context_tracks_state,
        receipt=s.deferred_success_receipt,
    )
    if s.effect_task_outcome.terminal:
        s.summary, s.completion_meta = api.build_effect_completion(
            receipt=s.deferred_success_receipt,
            objective=str(s.node.goal or ""),
            steps=len(s.history),
            lang=s.lang,
            outcome=s.effect_task_outcome,
            result_data=api.project_verified_operation_result(
                receipt=s.deferred_success_receipt,
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

    # Driver hook — lets stateful drivers (SkillDriver script
    # cursor, future drivers' internal state) react to
    # whatever decision actually executed. Errors here MUST
    # NOT break the main loop: the driver might be holding
    # invalid internal state but the executor and contexts
    # are still functioning.
    try:
        api.notify_step_completed(s.planner, s.decision, s.ok, s.current_obs, s.result)
    except Exception as exc:
        api.logger.warning("browser driver after-step hook failed", extra={"event": "browser.driver_after_step_failed", "error": str(exc)})

    # Stagnation check — only meaningful for tools that SHOULD
    # advance page state. Reads / waits don't count (they're
    # supposed to leave the page alone). browser_navigate also
    # skipped because URL change is its own, stronger signal.
    s._progress_tools = {
        "browser_click", "browser_press", "browser_select",
        "browser_fill", "browser_upload_file",
        "browser_paste_image", "browser_execute_plan",
    }
    if s.ok and s.decision.tool in s._progress_tools:
        s.post_action_ledger = None
        if s.context_tracks_state:
            try:
                s.post_action_ledger = s.task_context.build_state_ledger(s.current_obs)
            except Exception:
                s.post_action_ledger = None
        s.signature = api.browser_progress_signature(
            s.current_obs,
            state_ledger=s.post_action_ledger,
        )
        if s.last_progress_signature is not None and s.signature == s.last_progress_signature:
            s.no_progress_streak += 1
        else:
            s.no_progress_streak = 0
            s.last_progress_signature = s.signature
            s.stagnation_notices = 0
        if s.no_progress_streak >= s.NO_PROGRESS_STREAK_LIMIT:
            s.hint = (
                "⚠ {n} consecutive ok=True actions but page URL / element "
                "count / text have not changed at all — the operations are "
                "not actually advancing the business state."
                "\nLikely causes:"
                "\n  1. Required fields (textbox with '*' in name) not filled yet — a disabled submit can ignore a dispatched click"
                "\n  2. Target button is disabled (attributes.disabled / aria-disabled)"
                "\n  3. You clicked a decorative div/span, not an interactive control"
                "\nSwitch tactics now:"
                "\n  - browser_observe to rescan elements (attributes included), find who is disabled"
                "\n  - browser_fill all required inputs, THEN click submit"
                "\n  - if the button is truly disabled, browser_fail and name the missing precondition"
            ).format(n=s.no_progress_streak + 1)
            s.history.append(api.StepRecord(
                observation=s.current_obs,
                decision=api.Decision(tool="__stagnation_notice__", args={},
                                  rationale="system stagnation detector"),
                ok=False, error=s.hint, result_digest="",
            ))
            yield {"type": "activity", "content": {
                "kind": "warning",
                "message": (
                    f"检测到 {s.no_progress_streak + 1} 步操作未推进页面状态，已提示换策略"
                    if s.lang == "zh"
                    else f"{s.no_progress_streak + 1} actions without page-state progress — nudging planner to switch tactics"
                ),
            }}, {}
            api.logger.warning(
                "browser stagnation noticed",
                extra={"event": "browser.stagnation_notice", "streak": s.no_progress_streak + 1, "url": s.signature[0], "elements": s.signature[1]},
            )
            s.stagnation_notices += 1
            s.stagnation_budget_exhausted = s.stagnation_budget.record_notice(s.signature[0])
            if s.stagnation_notices >= 2 or s.stagnation_budget_exhausted:
                s.assistance = api.browser_human_assistance(
                    source=api.NAVIGATION_STAGNATION,
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
                if s.assistance is None:
                    s.blocked_reason = (
                        "页面连续多轮没有推进，自动恢复已经用尽"
                        if s.lang == "zh" else
                        "The page did not advance across repeated automatic recovery cycles"
                    )
                    s.recovery = s.terminal_recovery_plan(
                        source=api.INTERACTION_BLOCKED,
                        error=s.blocked_reason,
                    )
                    if s.recovery_assistance_available(s.recovery):
                        async for s.event in s.suspend_for_recovery(
                            s.recovery,
                            next_step=s.step + 1,
                        ):
                            yield s.event
                        s.terminal = True
                        return
                s.reason = (
                    "页面连续多轮没有推进，已停止重复操作；需要重新观察或人工介入"
                    if s.lang == "zh" else
                    "The page did not advance across repeated recovery cycles; stopping duplicate actions"
                )
                yield {"type": "activity", "content": {
                    "kind": "error", "message": s.reason,
                }}, {}
                yield {"type": "subagent_done", "content": {
                    "subagent_id": s.subagent_id,
                    "node_id": s.node.node_id,
                    "status": "failed_terminal",
                }}, {"browser_receipt": s.browser_failure_receipt(error=s.reason)}
                s.terminal = True
                return
            s.no_progress_streak = 0
            s.last_progress_signature = None

    # Track navigate targets for post-login redirect. Skip login-like
    # URLs so an LLM-driven navigate to /login can't poison the resume
    # target (which would trap the login wait loop polling /login
    # against itself forever).
    if s.decision.tool in ("browser_navigate", "browser_tab_new"):
        s.target = str(s.decision.args.get("url") or "")
        if s.target and not api._is_login_like_url(s.target):
            s.last_navigate_target = s.target

    # Remember the last non-login URL for each domain. Used as the
    # resume target after login, and as the recovery URL when a
    # spurious login signal fires on an already-authenticated domain.
    # A healthy (non-login) observation also resets the domain's
    # recovery budget — the session is clearly working fine right
    # now, so any later login glitch deserves a fresh retry window.
    s._cur_domain = api._domain(s.current_obs.url) or ""
    s._cur_scope = api.site_scope(s.current_obs.url) or s._cur_domain
    if s._cur_domain and s.current_obs.url and not api._is_login_like_url(s.current_obs.url):
        s.last_safe_url_by_domain[s._cur_scope] = s.current_obs.url
        s.login_recovery_failures.pop(s._cur_scope, None)

    # Capture the DOM-level login flag from the latest dispatch
    # result so the ask_user branch can tell a URL-substring match
    # (stale / harmless) from a genuine login form.
    s.last_dom_login_flag = bool(api._login_detected(s.result))

    # JS-heavy SPA backends like creator consoles often land on a
    # fully valid non-login URL before the first interactive
    # elements hydrate. If we feed a transient 0-element snapshot
    # straight back into the planner, it tends to misdiagnose the
    # page as broken or unauthenticated and navigate to /login.
    # Give the page a short, bounded re-observe window first.
    s.stabilized_obs, s.stabilized, s._retry_screenshot = await s.executor._retry_empty_spa_observation(
        current_obs=s.current_obs,
        lang=s.lang,
        step=s.step,
    )
    if s.stabilized_obs is not s.current_obs:
        s.current_obs = s.stabilized_obs
        if s.current_obs.url:
            s._cur_domain = api._domain(s.current_obs.url) or ""
            s._cur_scope = api.site_scope(s.current_obs.url) or s._cur_domain
            if s._cur_domain and not api._is_login_like_url(s.current_obs.url) and s.current_obs.elements:
                s.last_safe_url_by_domain[s._cur_scope] = s.current_obs.url
                s.login_recovery_failures.pop(s._cur_scope, None)
        if s.stabilized:
            s.last_dom_login_flag = False
            yield {"type": "activity", "content": {
                "kind": "analyze",
                "message": (
                    f"页面已完成渲染，检测到 {len(list(s.current_obs.elements or []))} 个可交互元素"
                    if s.lang == "zh"
                    else f"Page hydration completed; found {len(list(s.current_obs.elements or []))} interactive elements"
                ),
            }}, {}

    # Login detection: persist the exact browser state and end this
    # run as suspended. The session-bound auth watcher marks the
    # suspension ready; a later run resumes from this checkpoint.
    if api._login_detected(s.result):
        s.login_domain = api._domain(s.current_obs.url) or ""
        s.login_scope = api.site_scope(s.current_obs.url) or s.login_domain
        s.initial_auth = api.assessment_from_payload(s.result)
        s.auth_tracker.observe(
            url=s.current_obs.url,
            assessment=s.initial_auth,
            has_page_evidence=bool(s.current_obs.elements or s.current_obs.page_text or s.current_obs.title),
        )
        # Authenticated-domain recovery path: once a domain has
        # completed login this session, give it a bounded number of
        # chances to be recovered via a safe-URL bounce before we
        # concede that the session genuinely expired. Without this
        # budget, a real cookie expiry on an "authenticated" domain
        # would trap us in a silent bounce loop.
        if s.login_scope and s.login_scope in s.authenticated_domains:
            s.attempts = s.login_recovery_failures.get(s.login_scope, 0)
            if s.attempts < api.MAX_LOGIN_RECOVERY_ATTEMPTS:
                s.login_recovery_failures[s.login_scope] = s.attempts + 1
                s.safe_url = (
                    s.last_safe_url_by_domain.get(s.login_scope)
                    or (s.last_navigate_target if s.last_navigate_target and not api._is_login_like_url(s.last_navigate_target) else "")
                    or (f"https://{s.login_domain}/" if s.login_domain else "")
                )
                s.remaining = api.MAX_LOGIN_RECOVERY_ATTEMPTS - s.attempts - 1
                yield {"type": "activity", "content": {
                    "kind": "analyze",
                    "message": (
                        f"已登录的 {s.login_domain} 上出现登录信号，尝试恢复回 {s.safe_url}（剩余 {s.remaining} 次）"
                        if s.lang == "zh"
                        else f"Login signal on authenticated {s.login_domain}; recovering to {s.safe_url} (remaining {s.remaining})"
                    ),
                }}, {}
                if s.safe_url:
                    try:
                        s.re_result = await s.executor._dispatch(api.Decision(
                            tool="browser_navigate",
                            args={"url": s.safe_url},
                            rationale="safe-URL recovery on authenticated domain"))
                        s.re_data = s.re_result[0]
                        if isinstance(s.re_data, dict):
                            s.new_obs = api._obs_from_payload(s.re_data.get("observation") or s.re_data)
                            if s.new_obs:
                                s.current_obs = s.new_obs
                            s.last_dom_login_flag = bool(api._login_detected(s.re_data))
                            # If the recovery landed on a non-login
                            # page, dismiss any stale login modal
                            # left over from a prior wait loop on
                            # this domain.
                            if not s.last_dom_login_flag and not api._is_login_like_url(s.current_obs.url):
                                yield {"type": "intervention_cleared", "content": {
                                    "category": "login",
                                    "url": s.current_obs.url,
                                    "domain": s.login_domain,
                                    "reason": "authenticated_domain_recovery_succeeded",
                                }}, {}
                    except Exception:
                        pass
                s.continue_step = True
                return
            # Budget exhausted — session really expired. Drop the
            # authenticated flag + counter and fall through to the
            # real login flow below.
            s.authenticated_domains.discard(s.login_scope)
            s.login_recovery_failures.pop(s.login_scope, None)
            yield {"type": "activity", "content": {
                "kind": "analyze",
                "message": (
                    f"{s.login_domain} 恢复重试已用尽，判定为真实登录过期，走正常重新登录"
                    if s.lang == "zh"
                    else f"Recovery budget for {s.login_domain} exhausted; treating as real session expiry"
                ),
            }}, {}

        s.auth_category = "registration" if s.initial_auth.get("state") == "registration_required" else "login"
        async for s.event in s.suspend_for_authentication(
            category=s.auth_category,
            source="login_detected",
            next_step=s.step + 1,
        ):
            yield s.event
        s.terminal = True
        return

    if not s.ok:
        s.consecutive_failures += 1
        if s.consecutive_failures >= api.MAX_CONSECUTIVE_FAILURES:
            # First-hit at the ceiling: try one forced observation to
            # refresh DOM state (stale refs are the usual triple-fail
            # cause). Reset the counter once and let the planner see
            # the refreshed snapshot in the next turn.
            if not s.soft_recovery_used:
                s.soft_recovery_used = True
                yield {"type": "activity", "content": {
                    "kind": "warning",
                    "message": (
                        "连续 3 步失败，先刷新页面状态再继续" if s.lang == "zh"
                        else "3 consecutive failures — refreshing page state before retrying"
                    ),
                }}, {}
                try:
                    s.probe_result, s.probe_ok, s._probe_err = await s.executor._dispatch(
                        api.Decision(tool="browser_observe", args={},
                                 rationale="soft recovery after 3 consecutive failures"),
                    )
                    if s.probe_ok and isinstance(s.probe_result, dict):
                        s.refreshed = api._obs_from_payload(s.probe_result)
                        if s.refreshed:
                            s.current_obs = s.refreshed
                    s.history.append(api.StepRecord(
                        observation=s.current_obs,
                        decision=api.Decision(tool="browser_observe", args={},
                                          rationale="system soft-recovery"),
                        ok=bool(s.probe_ok),
                        error=None if s.probe_ok else "soft-recovery observe also failed",
                        result_digest="",
                    ))
                    api.logger.info("browser soft recovery probe completed", extra={"event": "browser.soft_recovery", "probe_ok": bool(s.probe_ok), "url": str(getattr(s.current_obs, "url", "") or "")})
                except Exception as exc:
                    api.logger.warning("browser soft recovery failed", extra={"event": "browser.soft_recovery_failed", "error": str(exc)})
                s.consecutive_failures = 0
                await s.save_checkpoint(phase="running", next_step=s.step + 1)
                s.continue_step = True
                return
            # Recovery was already spent and we're still failing —
            # genuine terminal. Emit as an activity warning (not a
            # final-answer string) so it doesn't leak into the
            # downstream compose node's rendered output.
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
            if s.assistance is None:
                s.recovery = s.terminal_recovery_plan(
                    source=api.LOOP_EXHAUSTED,
                    error=str(s.err or "repeated browser action failures"),
                )
                if s.recovery_assistance_available(s.recovery):
                    async for s.event in s.suspend_for_recovery(
                        s.recovery,
                        next_step=s.step + 1,
                    ):
                        yield s.event
                    s.terminal = True
                    return
            yield {"type": "activity", "content": {
                "kind": "error",
                "message": (
                    "连续失败 3 次，且恢复尝试未成功，已中止浏览器任务" if s.lang == "zh"
                    else "3 consecutive failures after soft recovery — aborting browser task"
                ),
            }}, {}
            yield {"type": "subagent_done", "content": {
                "subagent_id": s.subagent_id, "node_id": s.node.node_id, "status": "failed_terminal",
            }}, {"browser_receipt": s.browser_failure_receipt(error=s.err or "repeated failures")}
            s.terminal = True
            return
    elif not api.is_technical_recovery_observation(s.decision):
        s.consecutive_failures = 0

    await s.save_checkpoint(phase="running", next_step=s.step + 1)


async def finish_run(s):
    if s.execution_budget_exhausted:
        if s.execution_budget_effect_unknown:
            async for s.event in s.suspend_for_human_assistance(
                question=api.unknown_effect_verification_question(s.lang),
                next_step=max(s.start_step, s.step),
                category=api.FORM_EFFECT_VERIFY_CATEGORY,
            ):
                yield s.event
            s.terminal = True
            return
        await s.save_checkpoint(
            phase="execution_budget_reached",
            next_step=max(s.start_step, s.step),
            status="failed_retryable",
        )
        s.continuation = api.build_budget_continuation(
            context=s.task_context,
            observation=s.current_obs,
            tracks_context_state=s.context_tracks_state,
            lang=s.lang,
            objective=str(s.node.goal or s.goal or ""),
            steps=len(s.history),
        )
        yield {"type": "activity", "content": {
            "kind": "warning",
            "message": s.continuation.summary,
        }}, {}
        yield {"type": "subagent_done", "content": {
            "subagent_id": s.subagent_id,
            "node_id": s.node.node_id,
            "status": "partial_success",
        }}, s.continuation.artifacts
        s.terminal = True
        return

    # A policy/failure break may happen well before the configured budget.
    # Keep that distinct from genuine budget exhaustion in user-visible
    # output and receipts.
    s.exhausted_step_budget = s.step >= api.MAX_STEPS
    s.unresolved_effect = next((
        api.EffectReceipt.model_validate(item)
        for item in reversed(s.effect_tracker.receipts())
        if str(item.get("status") or "") in {"pending", "unknown"}
    ), None)
    if s.unresolved_effect is not None:
        s.verification = api.build_effect_verification_decision(
            s.unresolved_effect,
            lang=s.lang,
        )
        async for s.event in s.suspend_for_human_assistance(
            question=str(s.verification.args.get("question") or ""),
            next_step=s.step + 1,
            category=api.FORM_EFFECT_VERIFY_CATEGORY,
            handoff=dict(s.verification.args.get("handoff") or {}),
        ):
            yield s.event
        s.terminal = True
        return
    s.terminal_error = str(
        (s.history[-1].error if s.history else "")
        or (
            "max steps exhausted"
            if s.exhausted_step_budget
            else "browser loop stopped after repeated blocked or failed actions"
        )
    )
    s.recovery = s.terminal_recovery_plan(
        source=api.LOOP_EXHAUSTED,
        error=s.terminal_error,
    )
    if s.recovery_assistance_available(s.recovery):
        async for s.event in s.suspend_for_recovery(
            s.recovery,
            next_step=s.step + 1,
        ):
            yield s.event
        s.terminal = True
        return
    s.loop_failure_reason = (
        "max steps exhausted"
        if s.exhausted_step_budget
        else "browser loop stopped after repeated blocked or failed actions"
    )
    yield {"type": "activity", "content": {
        "kind": "warning",
        "message": (
            (
                f"达到最大步数 {api.MAX_STEPS}"
                if s.exhausted_step_budget
                else "连续操作被拦截或失败，浏览器任务已停止"
            )
            if s.lang == "zh"
            else (
                f"Reached max steps {api.MAX_STEPS}"
                if s.exhausted_step_budget
                else "Browser task stopped after repeated blocked or failed actions"
            )
        ),
    }}, {}
    yield {"type": "subagent_done", "content": {
        "subagent_id": s.subagent_id, "node_id": s.node.node_id, "status": "failed_terminal",
    }}, {"browser_receipt": s.browser_failure_receipt(error=s.loop_failure_reason)}
