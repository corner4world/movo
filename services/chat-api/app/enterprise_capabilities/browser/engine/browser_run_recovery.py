from __future__ import annotations

from . import desktop_agent_executor as api


async def prepare_recovery(s):
    async def save_checkpoint(*, phase: str, next_step: int, status: str = "running") -> None:
        if not s.executor.checkpoint_session:
            return
        s.learning_trace.capture_new(s.history)
        await s.executor.checkpoint_session.capture_and_save(
            phase=phase,
            next_step=next_step,
            visible_tool_step=s.visible_tool_step,
            observation=s.current_obs,
            history=s.history,
            authenticated_domains=s.authenticated_domains,
            last_safe_url_by_domain=s.last_safe_url_by_domain,
            login_recovery_failures=s.login_recovery_failures,
            wait_for_text_calls=s.wait_for_text_calls,
            wait_for_text_refs=s.wait_for_text_refs,
            last_navigate_target=s.last_navigate_target,
            consecutive_failures=s.consecutive_failures,
            soft_recovery_used=s.soft_recovery_used,
            no_progress_streak=s.no_progress_streak,
            last_progress_signature=s.last_progress_signature,
            driver_state=s.planner.export_checkpoint_state(),
            context_state=s.task_context.export_checkpoint_state(),
            browser_runtime_state={
                "business_actions": s.business_actions.export_state(),
                "effect_tracker": s.effect_tracker.export_state(),
                "form_transaction": s.form_transaction.export_state(),
                "fill_retry_policy": s.fill_retry_policy.export_state(),
                "alternative_target_recovery": s.alternative_target_recovery.export_state(),
                "completed_target_recovery": s.completed_target_recovery.export_state(),
                "target_history": s.target_history.export_state(),
                "automatic_assistance_counts": dict(s.automatic_assistance_counts),
                "human_recording_id": s.active_human_recording_id,
                "deferred_success_receipt": (
                    s.deferred_success_receipt.model_dump(mode="json")
                    if s.deferred_success_receipt is not None else None
                ),
            },
            learning_trace=s.learning_trace.export(),
            status=status,
        )
    s.save_checkpoint = save_checkpoint

    def schedule_workflow_capture() -> None:
        receipts = [
            item for item in s.effect_tracker.receipts()
            if isinstance(item, dict)
        ]
        # Admission is tied to the terminal business effect, not to any
        # earlier successful click/open action in the same run.
        if not api.terminal_effect_allows_cache(s.action_capability_id, receipts):
            api.logger.info(
                "browser workflow cache skipped unverified terminal effect",
                extra={
                    "event": "browser.workflow_cache_skipped",
                    "reason": "terminal_effect_not_confirmed",
                },
            )
            return
        s.learning_trace.capture_new(s.history)
        distilled_path = s.learning_trace.distill(
            site_id=api.site_id_for_node(s.node),
        )
        learned_history = s.learning_trace.successful_path(
            site_id=api.site_id_for_node(s.node),
        )
        api.logger.info(
            "browser workflow success path distilled",
            extra={
                "event": "browser.workflow_cache_path_distilled",
                "retained_steps": len(distilled_path.entries),
                "dropped_events": distilled_path.dropped_events,
                "critical_gaps": len(distilled_path.critical_gaps),
                "critical_gap_reasons": [
                    f"{gap.tool}:{gap.reason}"
                    for gap in distilled_path.critical_gaps[:10]
                ],
            },
        )
        api.browser_workflow_cache.schedule_success_capture(
            user_id=s.executor.user_id,
            main_id=str(s.runtime_output_spec.get("main_id") or "default"),
            node=s.node,
            input_context=s.input_context,
            history=learned_history,
            run_id=str(s.runtime_output_spec.get("run_id") or ""),
            replayed=False,
            trace_complete=(
                distilled_path.complete
                and s.learning_trace.legacy_gap_count == 0
            ),
            replay_failed=False,
        )
    s.schedule_workflow_capture = schedule_workflow_capture

    async def suspend_for_authentication(
        *,
        category: str,
        source: str,
        next_step: int,
        question: str = "",
    ) -> api.AsyncIterator[api.Tuple[api.Dict[str, api.Any], api.Dict[str, api.Any]]]:
        run_id = str((s.inputs.output_spec or {}).get("run_id") or "")
        interaction = s.current_obs.interaction if isinstance(s.current_obs.interaction, dict) else {}
        tab_id = str(interaction.get("tabId") or interaction.get("tab_id") or "")
        api.logger.info(
            "browser login intervention emitted",
            extra={
                "event": "browser.login_intervention",
                "source": source,
                "authenticated": False,
                "domain": api._domain(s.current_obs.url) or "",
                "url": s.current_obs.url,
                "question": question[:160],
                "dom_login": bool(s.last_dom_login_flag),
            },
        )
        request = api.BrowserAuthIntervention(
            run_id=run_id,
            node_id=s.node.node_id,
            user_id=s.executor.user_id,
            chat_session_id=s.executor.session_id,
            browser_session_id=s.executor.session_id,
            subagent_id=s.subagent_id,
            tab_id=tab_id,
            category=category,
            url=s.current_obs.url,
            domain=api._domain(s.current_obs.url) or "",
            next_step=next_step,
            source=source,
            lang=s.lang,
            question=question,
        )
        async for event in api.suspend_browser_authentication(
            bridge=s.executor.bridge,
            save_checkpoint=s.save_checkpoint,
            request=request,
        ):
            yield event
    s.suspend_for_authentication = suspend_for_authentication

    def automatic_assistance_available(
        assistance: api.BrowserHumanAssistance | None,
    ) -> bool:
        return bool(
            assistance
            and s.automatic_assistance_counts.get(assistance.dedupe_key, 0) < 1
        )
    s.automatic_assistance_available = automatic_assistance_available

    async def suspend_for_human_assistance(
        *,
        question: str,
        next_step: int,
        assistance: api.BrowserHumanAssistance | None = None,
        category: str = "browser",
        handoff: api.Dict[str, api.Any] | None = None,
    ) -> api.AsyncIterator[api.Tuple[api.Dict[str, api.Any], api.Dict[str, api.Any]]]:

        handoff = api.augment_form_assistance_handoff(
            handoff,
            context=s.input_context,
            completed_candidate_ids=api.completed_media_candidate_ids(
                s.planner.export_checkpoint_state(),
            ),
            user_id=s.executor.user_id,
        )

        if assistance is not None:
            s.automatic_assistance_counts[assistance.dedupe_key] = (
                s.automatic_assistance_counts.get(assistance.dedupe_key, 0) + 1
            )

        # Human action changes the live page state. Preserve business,
        # form and effect ledgers, but do not restore stale loop-failure
        # counters and immediately fail again after the fresh observation.
        s.consecutive_failures = 0
        s.soft_recovery_used = False
        s.no_progress_streak = 0
        s.last_progress_signature = None

        run_id = str((s.inputs.output_spec or {}).get("run_id") or "")
        s.active_human_recording_id = (
            f"assist_{run_id}_{s.node.node_id}_{api.uuid.uuid4().hex[:12]}"
            if run_id else f"assist_{api.uuid.uuid4().hex}"
        )
        try:
            # Start before transferring ownership so the first human click
            # cannot fall into the handoff race window.
            s.active_human_recording_id = await api.begin_recorded_human_handoff(
                s.executor.bridge,
                recording_id=s.active_human_recording_id,
                run_id=run_id,
                node_id=s.node.node_id,
                category=category,
            )
        except Exception as exc:
            s.active_human_recording_id = ""
            api.logger.warning(
                "browser human ownership handoff failed",
                extra={
                    "event": "browser.human_ownership_handoff_failed",
                    "error": str(exc),
                },
            )

        interaction = (
            s.current_obs.interaction
            if isinstance(s.current_obs.interaction, dict)
            else {}
        )
        tab_id = str(
            interaction.get("tabId") or interaction.get("tab_id") or ""
        )
        resume_context: api.Dict[str, api.Any] = {}
        if run_id and s.executor.checkpoint_session:
            await s.save_checkpoint(
                phase="waiting_human",
                next_step=next_step,
                status="suspended_waiting_approval",
            )
            suspension = await api.suspend_browser_intervention(
                run_id=run_id,
                task_id=s.executor.session_id,
                node_id=s.node.node_id,
                user_id=s.executor.user_id,
                subagent_id=s.subagent_id,
                browser_session_id=s.executor.session_id,
                tab_id=tab_id,
                category=category,
                reason=question,
                url=s.current_obs.url,
                handoff=handoff,
                mission={
                    "objective": s.step_goal_for_display,
                    "operation": str((s.node.meta or {}).get("capability_id") or "browser.read").removeprefix("browser."),
                    "target_name": str(((s.node.meta or {}).get("semantic_config") or {}).get("targetName") or ""),
                    "target_url": str(((s.node.meta or {}).get("semantic_config") or {}).get("targetUrl") or ""),
                    "language": s.lang,
                },
            )
            resume_context = api.browser_resume_context(suspension)

        yield {"type": "intervention_required", "content": {
            "category": category,
            "reason": question,
            "url": s.current_obs.url,
            "domain": api._domain(s.current_obs.url) or "",
            **({"handoff": handoff} if handoff else {}),
            **resume_context,
        }}, {}
        api.logger.info(
            "browser intervention required",
            extra={
                "event": "browser.intervention_required",
                "source": assistance.source if assistance else "ask_user",
                "domain": api._domain(s.current_obs.url) or "",
                "url": s.current_obs.url,
                "question": question[:160],
            },
        )
        yield {"type": "subagent_done", "content": {
            "subagent_id": s.subagent_id,
            "node_id": s.node.node_id,
            "status": "suspended_waiting_approval",
        }}, {
            "gateway": "SUSPEND",
            "browser_receipt": {
                "status": "intervention_required",
                "reason": question,
            },
            **(
                {"intervention_suspension": resume_context}
                if resume_context else {}
            ),
        }
    s.suspend_for_human_assistance = suspend_for_human_assistance

    def terminal_recovery_plan(
        *,
        source: str,
        error: str,
        prebuilt_assistance: api.Decision | None = None,
        preserved_handoff: api.Dict[str, api.Any] | None = None,
    ) -> api.BrowserRecoveryPlan:
        return api.route_browser_recovery(
            source=source,
            observation=s.current_obs,
            lang=s.lang,
            error=error,
            has_form_payload=s.has_form_handoff_payload,
            effect_statuses=tuple(
                str(item.get("status") or "")
                for item in s.effect_tracker.receipts()
                if isinstance(item, dict)
            ),
            prebuilt_assistance=prebuilt_assistance,
            preserved_handoff=preserved_handoff,
        )
    s.terminal_recovery_plan = terminal_recovery_plan

    def recovery_assistance_available(plan: api.BrowserRecoveryPlan) -> bool:
        return bool(
            plan.can_assist
            and s.automatic_assistance_available(plan.assistance)
        )
    s.recovery_assistance_available = recovery_assistance_available

    async def suspend_for_recovery(
        plan: api.BrowserRecoveryPlan,
        *,
        next_step: int,
    ) -> api.AsyncIterator[api.Tuple[api.Dict[str, api.Any], api.Dict[str, api.Any]]]:
        assert plan.decision is not None
        args = dict(plan.decision.args or {})
        handoff = args.get("handoff")
        async for event in s.suspend_for_human_assistance(
            question=str(args.get("question") or plan.reason),
            next_step=next_step,
            assistance=plan.assistance,
            category=str(args.get("category") or "browser"),
            handoff=dict(handoff) if isinstance(handoff, dict) else None,
        ):
            yield event
    s.suspend_for_recovery = suspend_for_recovery


async def resume_session(s):
    # A resumed auth checkpoint is only considered authenticated after
    # a fresh observation proves that the blocking page is gone. The old
    # implementation marked the scope authenticated unconditionally,
    # which allowed a manual "hand back" on an unchanged login page to
    # resume the planner with a false auth fact.
    if s.resume_checkpoint and s.resume_checkpoint.phase == "waiting_auth":
        s.resume_signal = dict((s.inputs.output_spec or {}).get("resume_signal") or {})
        s.explicit_auth_state = str((s.current_obs.auth or {}).get("state") or "")
        if api.authentication_resume_is_blocked(
            auth_state=s.explicit_auth_state,
            url_looks_blocked=api._is_login_like_url(s.current_obs.url or ""),
            resume_signal=s.resume_signal,
        ):
            s.auth_category = (
                "registration"
                if s.explicit_auth_state == "registration_required"
                else "login"
            )
            async for s.event in s.suspend_for_authentication(
                category=s.auth_category,
                source="resume_validation",
                next_step=s.start_step,
            ):
                yield s.event
            s.terminal = True
            return
        s.resumed_scope = api.site_scope(s.current_obs.url) or api._domain(s.current_obs.url)
        if s.resumed_scope:
            s.authenticated_domains.add(s.resumed_scope)
            s.last_safe_url_by_domain[s.resumed_scope] = s.current_obs.url

    s.resume_signal = dict(s.runtime_output_spec.get("resume_signal") or {})
    s.assistance_contract = api.resume_contract(s.resume_signal)
    s.assistance_kind = str(s.assistance_contract.get("kind") or "")
    if (
        s.assistance_kind in {
            api.FORM_COMMIT_CATEGORY,
            api.FORM_EFFECT_VERIFY_CATEGORY,
            api.FORM_TASK_COMPLETION_CATEGORY,
        }
        and not s.current_obs.fresh
    ):
        s.reason = (
            "人工操作后无法读取最新页面，因此没有采纳旧页面状态，也不会重复保存/提交。"
            if s.lang == "zh" else
            "The live page could not be read after human action; stale state was not accepted and the commit will not be replayed."
        )
        s.recovery = s.terminal_recovery_plan(
            source=api.RESUME_RECONCILIATION_UNAVAILABLE,
            error=s.reason,
            preserved_handoff={"contract": s.assistance_contract},
        )
        if s.recovery_assistance_available(s.recovery):
            async for s.event in s.suspend_for_recovery(
                s.recovery,
                next_step=s.start_step,
            ):
                yield s.event
            s.terminal = True
            return
        yield {"type": "activity", "content": {"kind": "warning", "message": s.reason}}, {}
        yield {"type": "subagent_done", "content": {
            "subagent_id": s.subagent_id,
            "node_id": s.node.node_id,
            "status": "failed_terminal",
        }}, {"browser_receipt": s.browser_failure_receipt(error=s.reason, status="resume_reconciliation_unavailable")}
        s.terminal = True
        return
    s.human_commit_reconciliation = api.assess_human_commit_reconciliation(
        capability_id=s.action_capability_id,
        assistance_kind=s.assistance_kind,
        human_outcome=str(s.resume_signal.get("human_outcome") or ""),
        before_url=s.resume_checkpoint.current_url if s.resume_checkpoint else "",
        after=s.current_obs,
        form_state=s.form_transaction.export_state(),
        existing_receipts=s.effect_tracker.receipts(),
    )
    if s.human_commit_reconciliation.should_ask:
        s.confirmation = api.build_task_completion_confirmation_decision(
            reason=s.human_commit_reconciliation.reason,
            evidence=s.human_commit_reconciliation.evidence,
            lang=s.lang,
        )
        async for s.event in s.suspend_for_human_assistance(
            question=str(s.confirmation.args.get("question") or ""),
            next_step=s.start_step,
            category=api.FORM_TASK_COMPLETION_CATEGORY,
            handoff=dict(s.confirmation.args.get("handoff") or {}),
        ):
            yield s.event
        s.terminal = True
        return
    s.manual_receipt: api.EffectReceipt | None = None
    if s.assistance_kind == api.FORM_EFFECT_VERIFY_CATEGORY:
        s.outcome = api.resume_outcome(
            s.resume_signal,
            expected_kind=api.FORM_EFFECT_VERIFY_CATEGORY,
        )
        s.contract_key = str(
            dict(s.assistance_contract.get("payload") or {}).get("contract_key") or ""
        )
        s.previous_receipt = s.effect_tracker.receipt(s.contract_key)
        if s.outcome and s.previous_receipt is not None:
            s.manual_receipt = api.manual_effect_receipt(
                previous=s.previous_receipt,
                outcome=s.outcome,
                observation=s.current_obs,
            )
            s.effect_tracker.adopt_manual_receipt(s.manual_receipt)
    elif s.assistance_kind == api.FORM_COMMIT_CATEGORY:
        s.outcome = api.resume_outcome(
            s.resume_signal,
            expected_kind=api.FORM_COMMIT_CATEGORY,
        )
        if s.outcome == "completed":
            s.manual_receipt = api.manual_commit_receipt(
                contract=s.assistance_contract,
                observation=s.current_obs,
            )
            s.effect_tracker.adopt_manual_receipt(s.manual_receipt)
    elif s.assistance_kind == api.FORM_TASK_COMPLETION_CATEGORY:
        s.outcome = api.resume_outcome(
            s.resume_signal,
            expected_kind=api.FORM_TASK_COMPLETION_CATEGORY,
        )
        if s.outcome == "task_completed":
            s.manual_receipt = api.manual_commit_receipt(
                contract=s.assistance_contract,
                observation=s.current_obs,
            )
            s.effect_tracker.adopt_manual_receipt(s.manual_receipt)

    if s.manual_receipt is not None:
        s.business_actions.record(s.manual_receipt)
        s.form_transaction.after_effect(s.manual_receipt, s.current_obs)
        await s.persist_confirmed_effect(s.manual_receipt, s.current_obs)
        api.apply_effect_receipt(
            context=s.task_context,
            tracks_context_state=s.context_tracks_state,
            receipt=s.manual_receipt,
            observation=s.current_obs,
        )
        if s.manual_receipt.status == "confirmed_success":
            # Reuse the normal verified-effect completion path after one
            # fresh read, instead of duplicating result construction here.
            s.deferred_success_receipt = s.manual_receipt
            s.pending_resolved_decision = api.Decision(
                tool="browser_observe",
                args={},
                rationale="reconcile live page after human-confirmed form completion",
            )
        elif s.manual_receipt.status == "confirmed_failure":
            s._topology = (getattr(s.inputs, "output_spec", None) or {}).get("graph_topology") or []
            for s.failure_event in api.build_effect_business_failure_events(
                receipt=s.manual_receipt,
                objective=str(s.node.goal or ""),
                steps=len(s.history),
                lang=s.lang,
                result_data=api.project_verified_operation_result(
                    receipt=s.manual_receipt,
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
        else:
            # The human explicitly chose "uncertain". Preserve the replay
            # block and stop safely instead of asking the model to submit again.
            s.reason = (
                "人工确认结果仍不确定；为避免重复提交，任务已安全停止。"
                if s.lang == "zh" else
                "The outcome remains uncertain; the task stopped safely without replaying the commit."
            )
            yield {"type": "activity", "content": {"kind": "warning", "message": s.reason}}, {}
            yield {"type": "subagent_done", "content": {
                "subagent_id": s.subagent_id,
                "node_id": s.node.node_id,
                "status": "failed_terminal",
            }}, {"browser_receipt": s.browser_failure_receipt(error=s.reason, status="unknown_side_effect")}
            s.terminal = True
            return

    if s.assistance_kind in {
        api.FORM_COMMIT_CATEGORY,
        api.FORM_EFFECT_VERIFY_CATEGORY,
        api.FORM_TASK_COMPLETION_CATEGORY,
    }:
        s.outcome = str(s.resume_signal.get("human_outcome") or "").strip().lower()
        if s.outcome in {"unable", "uncertain"}:
            s.reason = (
                "人工协助后仍无法确认或完成该表单操作，任务已停止且不会重复提交。"
                if s.lang == "zh" else
                "The form action could not be completed or confirmed after assistance; it will not be replayed."
            )
            yield {"type": "activity", "content": {"kind": "warning", "message": s.reason}}, {}
            yield {"type": "subagent_done", "content": {
                "subagent_id": s.subagent_id,
                "node_id": s.node.node_id,
                "status": "failed_terminal",
            }}, {"browser_receipt": s.browser_failure_receipt(error=s.reason, status="human_assistance_unresolved")}
            s.terminal = True
            return

    s.step = s.start_step - 1
    s.execution_budget = api.BrowserExecutionBudget.start(
        float((s.inputs.output_spec or {}).get("execution_budget_seconds") or 270)
    )
    s.execution_budget_exhausted = False
    s.execution_budget_effect_unknown = False
    s.done_block_recovery = api.DoneBlockRecovery()
