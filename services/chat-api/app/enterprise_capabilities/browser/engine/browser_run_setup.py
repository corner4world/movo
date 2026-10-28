from __future__ import annotations

from . import desktop_agent_executor as api


async def prepare_request(s):
    s.lang = api._detect_language(s.inputs)
    s.goal = api._extract_goal(s.node, s.inputs)
    s.resume_checkpoint = s.executor.checkpoint_session.checkpoint if s.executor.checkpoint_session else None
    s.subagent_id = s.executor.checkpoint_session.subagent_id if s.executor.checkpoint_session else f"sa_{api.uuid.uuid4().hex[:12]}"

    # Prepend composite_task site knowledge so the planner LLM starts
    # with auth / navigation / entry-URL hints already in context,
    # instead of rediscovering them via trial-and-error.
    s.site_context = (s.node.meta or {}).get("site_context") if isinstance(s.node.meta, dict) else None
    if isinstance(s.site_context, dict):
        s.site_hints_block = api.format_site_hints_for_goal(s.site_context)
        if s.site_hints_block:
            s.goal = f"{s.site_hints_block}\n\n{s.goal}" if s.goal else s.site_hints_block

    # Multi-node data-flow context. Every graph node's LLM needs three
    # things in addition to its own step goal:
    #   1. the user's original request (so it knows the global intent)
    #   2. actual data the upstream nodes produced (not just artifact
    #      ids — real values; empty values get an explicit warning so
    #      the LLM doesn't pretend work is done)
    #   3. what downstream consumers expect (so browser_done.data is
    #      shaped to serve the next node, not just literally close
    #      out this step)
    # This is the "blood flow" between graph nodes — without it the
    # graph is just a skeleton and each node delivers its narrow
    # subgoal regardless of whether the overall request is served.
    s.original_user_request = api._extract_original_user_request(s.inputs)
    s.runtime_output_spec = getattr(s.inputs, "output_spec", None) or {}
    s.input_context = api.BrowserInputContext.from_runtime(
        original_request=s.original_user_request,
        node=s.node,
        output_spec=s.runtime_output_spec,
    )
    s.authoritative_form_values = s.input_context.authoritative_form_values()
    s.requires_authoritative_form_input = bool(s.authoritative_form_values)
    s.has_form_handoff_payload = bool(
        s.requires_authoritative_form_input
        or any(item.value_kind == "file" for item in s.input_context.candidates)
    )
    # Load visible site profiles up front so we can extract entry-URL
    # candidates from them (names the user mentioned in the request)
    # and render the candidate list into the prompt below. Same profiles
    # are reused further down as `enterprise_sites` for the planner.
    try:
        s.visible_sites = await api.site_profile_service.list_for_user(s.executor.user_id)
    except Exception as exc:
        api.logger.warning("site profiles load failed", extra={"event": "browser.site_profiles_load_failed", "error": str(exc)})
        s.visible_sites = []
    s.site_resolution = api.resolve_business_site_scope(
        s.node,
        original_request=s.original_user_request,
        visible_sites=s.visible_sites,
    )
    s.node = api.scope_node(s.node, s.site_resolution)
    s.resolved_site_id = api.site_id_for_node(s.node, input_context=s.input_context)
    api.logger.info(
        "browser business site resolved",
        extra={
            "event": "browser.business_site_resolved",
            "site_id": s.resolved_site_id,
            "source": s.site_resolution.source,
            "confidence": s.site_resolution.confidence,
        },
    )
    # Task context — picks form / scrape / general based on the
    # content_task_spec.schema.category enum. The executor only talks
    # to the BrowserTaskContext ABC from here on; each category's
    # behaviour lives in its own contexts/*.py file.
    s.task_context = api.context_factory.maybe_init(
        node=s.node,
        output_spec=getattr(s.inputs, "output_spec", None) or {},
        original_user_request=s.original_user_request,
        goal=s.goal,
        lang=s.lang,
        input_context=s.input_context,
    )
    if s.resume_checkpoint and s.resume_checkpoint.context_state:
        s.task_context.restore_checkpoint_state(s.resume_checkpoint.context_state)
    s.context_tracks_state = bool(
        s.task_context.active or getattr(s.task_context, "stateful", False)
    )
    s.candidate_entries = api.extract_candidate_entries(
        s.original_user_request,
        s.visible_sites,
        expected_site=s.resolved_site_id,
        target_url=str(
            (
                (s.node.meta or {}).get("semantic_config")
                if isinstance((s.node.meta or {}).get("semantic_config"), dict)
                else {}
            ).get("targetUrl")
            or ""
        ),
    )
    s.candidate_block = api._format_candidate_entries(s.candidate_entries, s.lang)
    api.logger.debug(
        "browser candidate entries resolved",
        extra={"event": "browser.candidate_entries", "count": len(s.candidate_entries), "request_len": len(s.original_user_request or ""), "preview": [(c.get("source"), c.get("url")) for c in s.candidate_entries[:3]]},
    )
    s.upstream_context = api._format_upstream_artifacts(s.node, s.inputs, s.lang)
    s.downstream_block = api._format_downstream_expectations(s.node, s.lang)
    # Per-capability produce contract: the planner picks a capability
    # per browser step (browser.read / submit / modify / …); each has
    # a declared produce shape we'll validate against at browser_done
    # time. Show it to the LLM so it knows exactly what to put in data.
    s.action_capability_id = str((s.node.meta or {}).get("capability_id") or "").strip().lower()
    s.contract_hint = api.action_contract_describe_for_agent(s.action_capability_id, s.lang)
    api.logger.debug(
        "browser node capability resolved",
        extra={"event": "browser.node_capability", "capability_id": s.action_capability_id or "<untyped>", "hint_injected": bool(s.contract_hint)},
    )

    # Remember the narrow step goal separately from the augmented
    # prompt. The UI banner / activity messages should show the
    # human-meaningful "what this step does" text, not the full
    # context envelope we feed the planner LLM.
    s.step_goal_for_display = s.goal

    s.goal_sections: api.List[str] = []
    if s.original_user_request and s.original_user_request != s.goal:
        s.header = "USER'S ORIGINAL REQUEST (shared by all graph nodes):" if s.lang == "zh" \
                 else "USER'S ORIGINAL REQUEST (shared by all graph nodes):"
        s.goal_sections.append(f"{s.header}\n{s.original_user_request}")
    if s.candidate_block:
        s.goal_sections.append(s.candidate_block)
    if s.upstream_context:
        s.goal_sections.append(s.upstream_context)
    elif api._upstream_is_empty(s.node, s.upstream_context):
        # Plan-A soft fallback: upstream declared deps but left no data.
        # Tell the LLM honestly so it re-fetches instead of assuming
        # the work was already done.
        s.warn = ("⚠ Upstream nodes produced no concrete data. Do not assume the work is done; fetch from scratch."
                if s.lang == "zh"
                else "⚠ Upstream nodes produced no concrete data — don't assume it's done; fetch from scratch.")
        s.goal_sections.append(s.warn)
    if s.downstream_block:
        s.goal_sections.append(s.downstream_block)
    # Capability contract hint sits right before the step goal so the
    # LLM reads "you're doing a READ / SUBMIT / etc., data must look
    # like this" immediately before deciding its first action.
    if s.contract_hint:
        s.goal_sections.append(s.contract_hint)
    if s.goal_sections:
        # The step goal goes last so the LLM sees context first, then
        # the specific action it should take now.
        s.goal_sections.append(
            ("THIS STEP:\n" + s.goal) if s.lang == "zh" else ("THIS STEP:\n" + s.goal)
        )
        s.goal = "\n\n".join(s.goal_sections)

    if not s.goal:
        yield {"type": "activity", "content": {
            "kind": "error",
            "message": ("浏览器任务缺少目标描述" if s.lang == "zh" else "Missing task goal"),
        }}, {}
        yield {"type": "subagent_done", "content": {
            "subagent_id": s.subagent_id, "node_id": s.node.node_id, "status": "failed_terminal",
        }}, {}
        s.terminal = True
        return

    # Signal the desktop workspace before the Skill fast path runs. This
    # event deliberately contains no screenshot: desktop clients connect
    # to the sidecar's local CDP screencast, while web clients may use the
    # existing backend stream as a compatibility fallback.
    yield {"type": "browser.preview", "content": {
        "mode": "local",
        "transport": "native_cdp",
        "session_id": s.executor.session_id,
    }}, {}

    s.fast_path_seed: api.Dict[str, api.Any] | None = None
    s.fast_path_request = None if s.resume_checkpoint else api.prepare_skill_fast_path(
        node=s.node,
        inputs=s.inputs,
        goal=s.goal,
    )
    s.fast_path = None
    # An unavailable sidecar means there is no real dispatch to present;
    # preserve the existing model fallback without a synthetic failure.
    if s.fast_path_request is not None and s.executor.bridge.available():
        yield {"type": "tool_requested", "content": {
            "tool": "browser_execute_workflow",
            "args": s.fast_path_request.args,
        }}, {}
        s.fast_path = await api.execute_skill_fast_path(
            bridge=s.executor.bridge,
            request=s.fast_path_request,
        )
        yield {"type": "tool_completed", "content": {
            "tool": "browser_execute_workflow",
            "ok": bool(s.fast_path and s.fast_path.completed),
            "result": s.fast_path.result if s.fast_path is not None else {},
            **({"error": "local browser agent unavailable"} if s.fast_path is None else {}),
        }}, {}
    if s.fast_path is not None:
        if s.fast_path.completed:
            s.fast_path_artifacts = s.fast_path.artifacts(
                str((s.node.meta or {}).get("capability_id") or "")
            )
            yield {"type": "activity", "content": {
                "kind": "complete",
                "message": (
                    "浏览器 Skill 已通过本地规则完成，未调用模型"
                    if s.lang == "zh"
                    else "Browser Skill completed by local rules without a model"
                ),
            }}, {}
            yield {"type": "subagent_done", "content": {
                "subagent_id": s.subagent_id,
                "node_id": s.node.node_id,
                "status": "succeeded",
            }}, {
                "browser_receipt": {
                    "status": "ok",
                    "summary": "skill_fast_path_completed",
                    "steps": int(s.fast_path.result.get("completed_actions") or 0),
                },
                "browser_result": api.build_browser_result(
                    objective=str(s.node.goal or s.goal or ""),
                    summary="skill_fast_path_completed",
                    data={"workflow_result": s.fast_path.result, **s.fast_path_artifacts},
                ),
                **s.fast_path_artifacts,
            }
            s.terminal = True
            return
        yield {"type": "activity", "content": {
            "kind": "analyze",
            "message": (
                "本地 Skill/DOM 规则遇到未知状态，转入模型探索"
                if s.lang == "zh"
                else "Local Skill/DOM rules reached an unknown state; escalating to model exploration"
            ),
        }}, {}
        s.fast_path_seed = s.fast_path.result

    yield {"type": "activity", "content": {
        "kind": "analyze",
        "message": (
            (f"继续浏览器任务：{s.step_goal_for_display[:80]}" if s.resume_checkpoint else
             f"开始浏览器任务：{s.step_goal_for_display[:80]}")
            if s.lang == "zh"
            else (f"Resuming browser task: {s.step_goal_for_display[:80]}" if s.resume_checkpoint else
                  f"Starting browser task: {s.step_goal_for_display[:80]}")
        ),
    }}, {}


async def prepare_session(s):
    # Site profiles were loaded earlier (for candidate extraction);
    # reuse them here as the planner's enterprise_sites map. Site
    # knowledge is unconditional — the LLM should know where the
    # user's intranet systems live even when no composite skill was
    # selected for this turn.
    s.enterprise_sites = api._build_enterprise_sites_map(s.visible_sites)
    api.logger.debug(
        "enterprise sites injected",
        extra={"event": "browser.enterprise_sites_injected", "count": len(s.enterprise_sites), "names": list(s.enterprise_sites.keys())[:8]},
    )

    # Driver selection — picks SkillDriver if upstream resolved a
    # composite_task skill with replayable steps, otherwise the
    # plain ExplorationDriver (LLM planner). Variable kept as
    # ``planner`` for minimal call-site diff; it remains a drop-in
    # replacement at the .next_step interface.
    s.planner = api.select_driver(
        lang=s.lang,
        enterprise_sites=s.enterprise_sites or None,
        output_spec=s.runtime_output_spec,
        input_context=s.input_context,
        capability_id=s.action_capability_id,
    )
    if s.resume_checkpoint and s.resume_checkpoint.driver_state:
        s.planner.restore_checkpoint_state(s.resume_checkpoint.driver_state)
    api.logger.info(
        "browser driver selected",
        extra={
            "event": "browser.driver_selected",
            "driver": s.planner.kind,
        },
    )
    s.history: api.List[api.StepRecord] = s.resume_checkpoint.restore_history() if s.resume_checkpoint else []
    s.learning_trace = api.WorkflowLearningTrace.restore(
        s.resume_checkpoint.learning_trace if s.resume_checkpoint else None,
        history_size=len(s.history),
    )
    s.active_human_recording_id = str(
        (
            (s.resume_checkpoint.browser_runtime_state or {})
            if s.resume_checkpoint else {}
        ).get("human_recording_id") or ""
    )
    s.current_obs = api.Observation(
        url=s.resume_checkpoint.current_url if s.resume_checkpoint else "about:blank",
        title=s.resume_checkpoint.current_title if s.resume_checkpoint else "",
        elements=[],
        revision=s.resume_checkpoint.current_revision if s.resume_checkpoint else "",
        fresh=False,
    )
    if isinstance(s.fast_path_seed, dict):
        s.seed_observation = s.fast_path_seed.get("observation")
        if isinstance(s.seed_observation, dict):
            s.seed_payload = dict(s.seed_observation)
            if s.fast_path_seed.get("screenshot"):
                s.seed_payload["screenshot"] = s.fast_path_seed.get("screenshot")
            s.current_obs = api._obs_from_payload(s.seed_payload) or s.current_obs
    # Cross-node state handoff: probe the browser for whatever page the
    # previous graph node left behind. Without this, every new browser
    # node starts with current_obs==about:blank, so the planner LLM
    # sees "I'm on a blank page" and re-navigates from the enterprise
    # site map — undoing any progress an upstream node made (e.g.
    # landed on an authenticated portal, next node restarts from the entry page).
    # A no-domain browser_observe falls through to getLastActivePage
    # on the agent side, returning the actual tab state if one exists.
    s.initial_probe = await api.acquire_initial_observation(
        s.current_obs,
        dispatch=s.executor._dispatch,
        parse_observation=api._obs_from_payload,
    )
    if s.initial_probe.adopted:
        s.current_obs = s.initial_probe.observation
        api.logger.info(
            "browser initial probe succeeded",
            extra={
                "event": "browser.initial_probe",
                "url": s.current_obs.url,
                "elements": len(s.current_obs.elements or []),
                "page_text_len": len(s.current_obs.page_text or ""),
                "attempts": s.initial_probe.attempts,
            },
        )
    else:
        api.logger.warning(
            "browser initial probe failed",
            extra={
                "event": "browser.initial_probe_failed",
                "error": s.initial_probe.error,
                "attempts": s.initial_probe.attempts,
            },
        )
    if s.active_human_recording_id:
        # Stop only after the fresh probe so the last human-side DOM/effect
        # transition is available to the recorder. Events are durable and
        # are merged before any resumed Agent action can run.
        try:
            await s.executor.bridge.send_command(
                "recording_stop",
                recording_id=s.active_human_recording_id,
            )
            s.stopped = await api.human_recording_store.wait_stopped(
                s.active_human_recording_id,
            )
            s.recorded_events = await api.human_recording_store.list(
                s.active_human_recording_id,
            )
            s.learning_trace.capture_recorded(
                s.recorded_events,
                input_context=s.input_context,
            )
            await api.human_recording_store.purge(s.active_human_recording_id)
            api.logger.info(
                "browser human recording merged",
                extra={
                    "event": "browser.human_recording_merged",
                    "recording_id": s.active_human_recording_id,
                    "events": len(s.recorded_events),
                    "stopped": bool(s.stopped),
                },
            )
        except Exception as exc:
            api.logger.warning(
                "browser human recording merge failed",
                extra={
                    "event": "browser.human_recording_merge_failed",
                    "recording_id": s.active_human_recording_id,
                    "error": str(exc),
                },
            )
        s.active_human_recording_id = ""
    s.driver_resume_reconciled = not bool(s.resume_checkpoint)
    if s.resume_checkpoint and s.current_obs.fresh:
        # Human interaction can change the page, active form and refs.
        # Reconcile the signal only after the live tab has been observed.
        api.apply_driver_resume_signal(
            s.planner,
            dict(s.runtime_output_spec.get("resume_signal") or {}),
            s.current_obs,
        )
        s.driver_resume_reconciled = True

    s.consecutive_failures = s.resume_checkpoint.consecutive_failures if s.resume_checkpoint else 0
    # Soft-recovery flag: when consecutive_failures hits the ceiling for
    # the first time, we inject one fresh browser_observe to re-ground
    # the LLM on the current DOM (stale refs are the most common cause
    # of a triple-click miss) instead of terminating the whole node.
    # Only granted once per run so a genuinely stuck flow still exits.
    s.soft_recovery_used = s.resume_checkpoint.soft_recovery_used if s.resume_checkpoint else False
    # Stagnation detector: tools can return ok=True while the page makes
    # no observable progress — a dispatched click on a disabled or
    # non-interactive target can still report success, so `ok` alone doesn't catch
    # "I clicked 5 times and nothing happened" loops. We track a cheap
    # page-state signature (url, element count, page_text hash) across
    # progress-expected tool calls; if the signature is identical for
    # too many consecutive turns we inject a synthetic StepRecord with
    # a "page didn't change" hint so the planner LLM switches tactics
    # (fill required fields, re-scan attributes for disabled state,
    # etc.) instead of spinning.
    s.last_progress_signature: tuple[api.Any, ...] | None = (
        tuple(s.resume_checkpoint.last_progress_signature)  # type: ignore[arg-type]
        if s.resume_checkpoint and s.resume_checkpoint.last_progress_signature
        else None
    )
    s.no_progress_streak = s.resume_checkpoint.no_progress_streak if s.resume_checkpoint else 0
    s.stagnation_notices = 0
    s.stagnation_budget = api.StagnationBudget(max_notices=3)
    s.click_outcome_policy = api.ClickOutcomePolicy()
    s.interaction_target_recovery = api.InteractionTargetRecovery()
    s.NO_PROGRESS_STREAK_LIMIT = 3
    # the primary fix for "LLM spams wait_for on same
    # text" lives in the agent: wait_for now returns the matched ref
    # so the LLM can click immediately instead of re-waiting. This
    # counter is the safety net — if the LLM keeps invoking
    # wait_for on the same text (regardless of ok status), redirect
    # it. Count INVOCATIONS, not failures, because the real bad
    # pattern is "already confirmed the text is there but still
    # calling wait_for instead of using the returned ref".
    s.wait_for_text_calls: api.Dict[str, int] = dict(s.resume_checkpoint.wait_for_text_calls) if s.resume_checkpoint else {}
    # Cache of (text → clickable_ref) populated from every successful
    # browser_wait_for. Enables P1-hard: when LLM re-waits on the same
    # text and we already know the ref, we auto-rewrite the decision
    # into browser_click(ref=…) in-place. Eliminates the loop entirely.
    s.current_refs = {
        str(item.get("ref") or "")
        for item in list(s.current_obs.elements or [])
        if isinstance(item, dict) and str(item.get("ref") or "")
    }
    s.checkpoint_url = s.resume_checkpoint.current_url if s.resume_checkpoint else ""
    s.wait_for_text_refs: api.Dict[str, str] = {
        str(text): str(ref)
        for text, ref in dict(s.resume_checkpoint.wait_for_text_refs if s.resume_checkpoint else {}).items()
        if str(ref) in s.current_refs and s.current_obs.url == s.checkpoint_url
    }
    # Rich metadata is intentionally not restored from checkpoints: refs
    # are observation-local and must be freshly rule-confirmed after resume.
    s.wait_for_click_targets: api.Dict[str, api.WaitForClickTarget] = {}
    s.WAIT_FOR_TEXT_MAX_CALLS = 2
    s.is_xhs_publish_goal = api._is_xiaohongshu_publish_goal(s.goal)
    # Resolve once per run: user-supplied URL (in goal) wins over the
    # yaml default. Empty string means "no default available — skip
    # the landing-page rewrite entirely and trust the planner".
    s.xhs_publish_url = api._resolve_xiaohongshu_publish_url(s.goal) if s.is_xhs_publish_goal else ""
    # Track the last URL the LLM explicitly asked to navigate to.
    # If login is detected, we return here after the user logs in.
    # Never set to a login-like URL (would poison the resume URL and
    # trap the login wait loop polling /login against itself).
    s.last_navigate_target: str | None = s.resume_checkpoint.last_navigate_target if s.resume_checkpoint else None
    # Session-scoped auth fact table. Once a domain successfully exits
    # the login wait loop (user completed sign-in) we mark it here.
    # Any later login signal on the same domain is treated as a false
    # positive (stale URL match, transient DOM glitch, or LLM-driven
    # re-navigation to a login URL) and gets redirected to the last
    # safe URL instead of re-entering the login flow.
    s.authenticated_domains: api.Set[str] = set(s.resume_checkpoint.authenticated_domains) if s.resume_checkpoint else set()
    s.auth_tracker = api.AuthTransitionTracker()
    # Per-domain last known non-login URL. Used as the resume target
    # after login completes, and as the recovery target when a
    # spurious login signal fires on an authenticated domain.
    s.last_safe_url_by_domain: api.Dict[str, str] = dict(s.resume_checkpoint.last_safe_url_by_domain) if s.resume_checkpoint else {}
    # Per-domain counter of consecutive safe-URL recovery attempts
    # against a login signal on an already-authenticated domain. When
    # this hits MAX_LOGIN_RECOVERY_ATTEMPTS we treat the domain as
    # truly re-authentication-needed: drop it from authenticated_domains
    # and fall through to the real login flow. Reset whenever we
    # observe a healthy non-login page for that domain.
    s.login_recovery_failures: api.Dict[str, int] = dict(s.resume_checkpoint.login_recovery_failures) if s.resume_checkpoint else {}
    # Most recent DOM-level loginDetected flag from an executed dispatch.
    # Used by the ask_user branch to distinguish URL-only matches (stale
    # sub-string hits like /login-history) from genuine login forms.
    s.last_dom_login_flag: bool = False
    # A wait-for resolution is consumed before the planner on the next
    # loop. This keeps locate -> click free of another planning turn while
    # still routing the click through the executor's normal validation,
    # context policy, accounting, failure recovery, and activity pipeline.
    s.pending_resolved_decision: api.Decision | None = None
    s.effect_tracker = api.EffectTracker(
        goal=s.step_goal_for_display,
        capability_id=s.action_capability_id,
        lang=s.lang,
        original_request=s.original_user_request,
    )
    from app.infrastructure.runtime_services import action_receipt_store
    s.action_receipt_store = action_receipt_store
    s.action_history = api.BrowserActionHistory(
        actor_id=s.executor.user_id,
        attempt_id=(
            f"{str(s.runtime_output_spec.get('run_id') or '')}:"
            f"{s.node.node_id}:{s.subagent_id}"
        ),
        store=s.action_receipt_store,
        goal=s.step_goal_for_display,
        original_request=s.original_user_request,
        lang=s.lang,
    )
    s.alternative_target_recovery = api.AlternativeTargetRecovery()
    s.completed_target_recovery = api.CompletedTargetRecovery()
    s.target_history = api.TargetHistoryState()
    s.business_actions = api.BusinessActionLedger()
    s.form_transaction = api.FormTransactionTracker()
    s.fill_retry_policy = api.FillRetryPolicy()
    s.runtime_checkpoint_state = (
        dict(s.resume_checkpoint.browser_runtime_state or {})
        if s.resume_checkpoint else {}
    )
    s.automatic_assistance_counts = {
        str(key): max(0, int(value))
        for key, value in dict(
            s.runtime_checkpoint_state.get("automatic_assistance_counts") or {}
        ).items()
    }
    s.business_actions.restore_state(
        dict(s.runtime_checkpoint_state.get("business_actions") or {}),
    )
    s.effect_tracker.restore_state(
        dict(s.runtime_checkpoint_state.get("effect_tracker") or {}),
    )
    s.form_transaction.restore_state(
        dict(s.runtime_checkpoint_state.get("form_transaction") or {}),
    )
    s.fill_retry_policy.restore_state(
        dict(s.runtime_checkpoint_state.get("fill_retry_policy") or {}),
    )
    s.alternative_target_recovery.restore_state(
        dict(s.runtime_checkpoint_state.get("alternative_target_recovery") or {}),
    )
    s.completed_target_recovery.restore_state(
        dict(s.runtime_checkpoint_state.get("completed_target_recovery") or {}),
    )
    s.target_history.restore_state(
        dict(s.runtime_checkpoint_state.get("target_history") or {}),
    )
    s.deferred_payload = s.runtime_checkpoint_state.get("deferred_success_receipt")
    s.deferred_success_receipt: api.Any | None = (
        api.EffectReceipt.model_validate(s.deferred_payload)
        if isinstance(s.deferred_payload, dict) else None
    )
    s.replay_guard_emitted = False

    def browser_failure_receipt(*, error: str, status: str = "failed") -> api.Dict[str, api.Any]:
        return api.build_effect_failure(
            error=error,
            receipts=s.effect_tracker.receipts(),
            status=status,
        )
    s.browser_failure_receipt = browser_failure_receipt

    async def persist_confirmed_effect(receipt: api.Any, observation: api.Observation) -> None:
        try:
            source_url = s.alternative_target_recovery.source_url_from_history(
                history=s.history,
                target_id=observation.url,
            )
            persisted = await s.action_history.record(
                receipt,
                observation,
                source_url=source_url,
            )
            if persisted is not None:
                api.logger.info(
                    "browser action history persisted",
                    extra={
                        "event": "browser.action_history_persisted",
                        "business_key": persisted.business_key,
                        "operation": persisted.operation_id,
                        "target": persisted.target_id,
                        "target_alias_count": len(persisted.target_aliases),
                    },
                )
        except Exception as exc:
            # The action has already happened and was independently
            # verified. History storage must not turn it into a failure.
            api.logger.warning(
                "browser action history persist failed",
                extra={"event": "browser.action_history_persist_failed", "error": str(exc)},
            )
    s.persist_confirmed_effect = persist_confirmed_effect

    s.visible_tool_step = s.resume_checkpoint.visible_tool_step if s.resume_checkpoint else 0
    s.start_step = s.resume_checkpoint.next_step if s.resume_checkpoint else 1

    s.entry_preflight = api.assess_entry_preflight(
        current_url=s.current_obs.url,
        candidates=s.candidate_entries,
    )
    api.logger.info(
        "browser entry preflight completed",
        extra={
            "event": "browser.entry_preflight",
            "ready": s.entry_preflight.ready,
            "code": s.entry_preflight.code,
            "current_url": s.current_obs.url,
            "candidate_count": len(s.candidate_entries),
        },
    )
    if not s.entry_preflight.ready:
        s.message = (
            "浏览器当前处于空白或错误页，且任务没有可信入口地址。"
            "请使用 target_url 重新发起 browser_task；这不是需要人工处理的网页状态。"
            if s.lang == "zh" else
            "The browser is on a blank/error page and the task has no grounded entry URL. "
            "Reissue browser_task with target_url; this is not a human-assistance state."
        )
        s.failure = s.browser_failure_receipt(
            error=s.entry_preflight.reason,
            status=s.entry_preflight.code,
        )
        s.failure.update({
            "code": s.entry_preflight.code,
            "retryable": True,
            "required_argument": "target_url",
        })
        api.logger.warning(
            "browser entry preflight rejected ungrounded blank page",
            extra={
                "event": "browser.entry_preflight_rejected",
                "code": s.entry_preflight.code,
                "current_url": s.current_obs.url,
            },
        )
        yield {"type": "activity", "content": {
            "kind": "error",
            "message": s.message,
        }}, {}
        yield {"type": "subagent_done", "content": {
            "subagent_id": s.subagent_id,
            "node_id": s.node.node_id,
            "status": "failed_terminal",
        }}, {
            "browser_receipt": s.failure,
            "browser_result": api.build_browser_result(
                objective=s.step_goal_for_display,
                summary=s.message,
                data={
                    "code": s.entry_preflight.code,
                    "retryable": True,
                    "required_argument": "target_url",
                },
                status=s.entry_preflight.code,
            ),
        }
        s.terminal = True
        return
