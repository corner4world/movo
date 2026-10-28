from __future__ import annotations

from . import desktop_agent_executor as api


async def plan_step(s):
    if s.execution_budget.expired:
        s.execution_budget_exhausted = True
        s.break_step = True
        return
    if s.resume_checkpoint and s.current_obs.fresh and not s.driver_resume_reconciled:
        api.apply_driver_resume_signal(s.planner, s.resume_signal, s.current_obs)
        s.driver_resume_reconciled = True
    if not s.current_obs.fresh:
        s.pending_resolved_decision = api.Decision(
            tool="browser_observe",
            args={},
            rationale="system freshness barrier: refresh DOM before the next decision",
        )
    # Stateful contexts may inject a synthetic record before planning.
    if s.context_tracks_state and s.current_obs.fresh:
        s.injected = s.task_context.before_decision(s.history, s.current_obs)
        if s.injected is not None:
            s.history.append(s.injected)
            s._msg = s.task_context.timeline_for_record(s.injected) or str(s.injected.result_digest or '')[:180]
            for s._line in [x.strip() for x in str(s._msg or "").splitlines() if x.strip()]:
                yield {"type": "activity", "content": {
                    "kind": "analyze",
                    "message": s._line,
                }}, {}
            s.continue_step = True
            return

    # First-step short-circuit: if we're sitting on about:blank and
    # exactly one entry URL candidate was resolved (either a user-
    # typed URL or a named-site from the profile registry), navigate
    # there directly instead of letting the planner potentially ask
    # the user for a URL we already know. Only fires on step 1 and
    # only when there's no ambiguity — multi-candidate cases go
    # through the planner so it can pick by user-request semantics.
    s.forced_decision = s.pending_resolved_decision
    s.pending_resolved_decision = None
    if s.forced_decision is None:
        s.forced_decision = api.recovery_decision_after_guard_failure(
            s.history,
            s.current_obs,
            lang=s.lang,
        )
    s.forced_url = api.initial_entry_url(
        step=s.step,
        candidates=s.candidate_entries,
        current_url=s.current_obs.url,
        resuming=bool(s.resume_checkpoint),
    )
    if s.forced_decision is None and s.forced_url:
        try:
            s.forced_domain = api.urlparse(s.forced_url).hostname or ""
        except Exception:
            s.forced_domain = ""
        s.forced_decision = api.Decision(
            tool="browser_navigate",
            args={"url": s.forced_url, "domain": s.forced_domain},
            rationale=(
                "auto-navigate from single resolved entry "
                f"(source={s.candidate_entries[0].get('source')})"
            ),
        )
        api.logger.info("browser first step short-circuit", extra={"event": "browser.first_step_short_circuit", "url": s.forced_url, "source": s.candidate_entries[0].get("source")})

    # A resumed run can restore the history policy while the browser
    # is still on a target completed by an earlier run. Recover before
    # page-specific rules or another planner turn can operate on it.
    await s.target_history.synchronize(
        store=s.action_receipt_store,
        actor_id=s.executor.user_id,
        recovery=s.alternative_target_recovery,
    )
    if s.forced_decision is None and s.target_history.excludes_completed:
        s.forced_decision = s.completed_target_recovery.recovery_decision(
            observation=s.current_obs,
            history=s.history,
            candidate_entries=s.candidate_entries,
            recovery=s.alternative_target_recovery,
        )
        if s.forced_decision is not None:
            api.logger.info(
                "browser completed current target recovery selected",
                extra={
                    "event": "browser.completed_target_recovery",
                    "operation": s.target_history.operation,
                    "current_url": s.current_obs.url,
                    "recovery_url": str(s.forced_decision.args.get("url") or ""),
                },
            )
    # System-owned navigation: when the flow requires a known
    # page (e.g. after create lands on a detail route and the
    # next sub-phase needs the list), let the context synthesize
    # the navigate decision instead of hoping the LLM figures it
    # out. Preempts the planner call entirely.
    if s.context_tracks_state and s.forced_decision is None:
        try:
            s.nav = s.task_context.maybe_force_navigation(s.current_obs)
        except Exception:
            s.nav = None
        if s.nav is not None:
            s.forced_decision = s.nav
            yield {"type": "activity", "content": {
                "kind": "analyze",
                "message": s.task_context.timeline_text("forced_nav"),
            }}, {}

    # Rules layer: before paying for an LLM turn, try to resolve
    # the current phase's action from deterministic rules. A
    # unique candidate → auto-click; ambiguous / missing → fall
    # through to the planner with the usual ledger context.
    if s.context_tracks_state and s.forced_decision is None:
        try:
            s.rule_observation = s.alternative_target_recovery.planning_observation(s.current_obs)
            s.rule_observation = s.interaction_target_recovery.planning_observation(s.rule_observation)
            s.rule_dec = s.task_context.suggest_next_action(s.rule_observation)
        except Exception:
            s.rule_dec = None
        if s.rule_dec is not None:
            s.forced_decision = s.rule_dec
            api.logger.info(
                "browser context rule auto execution",
                extra={"event": "browser.context_rule_autoexec", "tool": s.rule_dec.tool, "ref": str((s.rule_dec.args or {}).get("ref") or ""), "rationale": s.rule_dec.rationale[:120]},
            )
            if hasattr(s, "nav") and s.nav is not None:
                api.logger.info("browser context forced navigation", extra={"event": "browser.context_forced_navigation", "url": str(s.nav.args.get("url") or "")})
    # pass the state ledger to the planner every turn.
    # The LLM reads an authoritative "where are we / what's next /
    # what's off-limits" card instead of inferring from history.
    s._ledger = None
    try:
        s._ledger = s.task_context.build_state_ledger(s.current_obs) if s.context_tracks_state else None
    except Exception:
        s._ledger = None
    s.scope_state = s.form_transaction.interaction_scope_state(s.current_obs)
    if s.scope_state is not None:
        s._ledger = dict(s._ledger or {})
        s.constraints = list(s._ledger.get("action_constraints") or [])
        s.constraints.append(s.scope_state["constraint"])
        s.notes = list(s._ledger.get("notes") or [])
        s.notes.append(s.scope_state["note"])
        s.pinned_refs = list(s._ledger.get("pinned_refs") or [])
        s.pinned_refs.extend(s.scope_state["allowed_refs"])
        s._ledger.update({
            "action_constraints": s.constraints,
            "notes": s.notes,
            "pinned_refs": list(dict.fromkeys(s.pinned_refs)),
        })
    s._ledger = s.alternative_target_recovery.augment_state_ledger(s._ledger)
    s.planning_obs = s.alternative_target_recovery.planning_observation(s.current_obs)
    s.quarantined_refs = s.interaction_target_recovery.quarantined_refs(s.planning_obs)
    s.planning_obs = s.interaction_target_recovery.planning_observation(s.planning_obs)
    s._ledger = s.interaction_target_recovery.augment_state_ledger(s._ledger)
    if s.quarantined_refs:
        api.logger.info(
            "browser quarantined failed interaction targets from planning",
            extra={
                "event": "browser.interaction_targets_quarantined",
                "refs": list(s.quarantined_refs),
                "url": str(s.current_obs.url or "")[:1000],
            },
        )
    s.decision_is_system_owned = s.forced_decision is not None
    s.decision = s.forced_decision or await s.planner.next_step(
        s.goal, s.history, s.planning_obs, state_ledger=s._ledger,
    )
    await s.target_history.synchronize(
        store=s.action_receipt_store,
        actor_id=s.executor.user_id,
        recovery=s.alternative_target_recovery,
        decision=s.decision,
    )
    s.completed_recovery_decision = (
        s.completed_target_recovery.recovery_decision(
            observation=s.current_obs,
            history=s.history,
            candidate_entries=s.candidate_entries,
            recovery=s.alternative_target_recovery,
        )
        if s.target_history.excludes_completed else None
    )
    if s.completed_recovery_decision is not None:
        s.model_history_hint = (
            "The current page already has the requested business action; "
            "returning through a grounded candidate entry to choose another target."
        )
        s.history_hint = (
            "当前页面已完成本次要求的业务操作，正在返回可信候选入口并改选其他目标。"
            if s.lang == "zh" else
            s.model_history_hint
        )
        s.history.append(api.StepRecord(
            observation=s.current_obs,
            decision=s.decision,
            ok=False,
            error=s.model_history_hint,
            result_digest="completed current target recovered before dispatch",
        ))
        yield {"type": "activity", "content": {
            "kind": "analyze", "message": s.history_hint,
        }}, {}
        api.logger.info(
            "browser completed current target recovery selected",
            extra={
                "event": "browser.completed_target_recovery",
                "operation": s.target_history.operation,
                "current_url": s.current_obs.url,
                "recovery_url": str(
                    s.completed_recovery_decision.args.get("url") or ""
                ),
            },
        )
        s.decision = s.completed_recovery_decision
        s.decision_is_system_owned = True
    s.blocked_target_ref = s.target_history.blocked_selection_ref(
        s.decision,
        s.current_obs,
        s.alternative_target_recovery,
    )
    if s.blocked_target_ref:
        s.model_history_hint = "This candidate already has the requested business action; it was excluded before navigation."
        s.history_hint = (
            "该候选已完成当前要求的业务操作，已在选择阶段排除并改选其他目标。"
            if s.lang == "zh" else
            s.model_history_hint
        )
        s.history.append(api.StepRecord(
            observation=s.current_obs,
            decision=s.decision,
            ok=False,
            error=s.model_history_hint,
            result_digest=f"excluded_ref={s.blocked_target_ref}",
        ))
        yield {"type": "activity", "content": {
            "kind": "analyze", "message": s.history_hint,
        }}, {}
        api.logger.info(
            "browser completed target excluded before selection",
            extra={
                "event": "browser.target_history_selection_blocked",
                "policy": s.target_history.policy,
                "operation": s.target_history.operation,
                "ref": s.blocked_target_ref,
            },
        )
        s.consecutive_failures = 0
        s.continue_step = True
        return
    s.done_block_recovery.record_action(s.decision)
    # Reuse an immediately preceding screenshot when the page and
    # capture scope are unchanged. This runs before timeline emission,
    # so a planner retry does not become another visible/tool step.
    s.visual_reuse = api.redundant_visual_observation(
        s.decision,
        current=s.current_obs,
        history=s.history,
    )
    if s.visual_reuse.blocked:
        s.history.append(api.StepRecord(
            observation=s.current_obs,
            decision=s.decision,
            ok=False,
            error=s.visual_reuse.reason,
            result_digest="existing screenshot retained",
        ))
        api.logger.info(
            "duplicate visual observation reused",
            extra={
                "event": "browser.visual_observation_reused",
                "tool": s.decision.tool,
                "url": s.current_obs.url,
                "state_fingerprint": s.current_obs.state_fingerprint,
            },
        )
        s.continue_step = True
        return

    # Xiaohongshu creator console is a JS-heavy SPA and the root
    # /login /new/home entry often yields empty observations before
    # hydration. For publish flows, jump straight to the resolved
    # publish URL (user-supplied > yaml default) instead of letting
    # the planner guess.
    if (
        s.is_xhs_publish_goal
        and s.xhs_publish_url
        and s.decision.tool == "browser_navigate"
        and str(s.decision.args.get("url") or "").strip().rstrip("/") in api._XHS_LANDING_URLS
    ):
        s.decision = api.Decision(
            tool=s.decision.tool,
            args={**dict(s.decision.args or {}), "url": s.xhs_publish_url},
            rationale=(s.decision.rationale or "") + " | rewritten to resolved xiaohongshu publish route",
        )
        api.logger.info("xiaohongshu navigate rewritten", extra={"event": "browser.xhs_navigate_rewritten", "url": s.xhs_publish_url})

    # Only model exploration is provenance-gated. Context-owned
    # routing, recorded skill steps and auth recovery carry their own
    # authoritative URL source; browser redirects never create a
    # Decision and therefore never reach this gate.
    if s.decision.tool in ("browser_navigate", "browser_tab_new"):
        s.skill_owned = str(s.decision.rationale or "").startswith("[skill_driver]")
        s.provenance = api.assess_navigation_provenance(
            target_url=str(s.decision.args.get("url") or "").strip(),
            current_observation=s.current_obs,
            history_observations=(record.observation for record in s.history),
            original_user_request=s.original_user_request,
            site_profiles=s.visible_sites,
            trusted_urls=(s.xhs_publish_url,) if s.xhs_publish_url else (),
            system_owned=s.decision_is_system_owned or s.skill_owned,
        )
        if s.provenance.audit_only:
            api.logger.warning(
                "browser URL provenance audit",
                extra={
                    "event": "browser.url_provenance_audit",
                    "url": str(s.decision.args.get("url") or "")[:160],
                    "reason": s.provenance.reason,
                },
            )
        if not s.provenance.allowed:
            s.model_hint = "The target URL is not grounded: do not invent a site route from button text; click an observed link or use an explicit user/site URL."
            s.hint = (
                "目标 URL 没有可靠来源：不要根据按钮文字猜站内路径；请点击页面中已观察到的链接，或使用用户/站点设置给出的完整 URL。"
                if s.lang == "zh" else
                s.model_hint
            )
            s.history.append(api.StepRecord(
                observation=s.current_obs,
                decision=s.decision,
                ok=False,
                error=f"{s.model_hint} ({s.provenance.reason})",
                result_digest="",
            ))
            api.notify_driver_rejection(
                s.planner,
                s.decision,
                s.current_obs,
                category="navigation_provenance",
                reason=s.provenance.reason,
            )
            yield {"type": "activity", "content": {
                "kind": "warning",
                "message": s.hint,
            }}, {}
            api.logger.warning(
                "browser URL provenance blocked",
                extra={
                    "event": "browser.url_provenance_blocked",
                    "url": str(s.decision.args.get("url") or "")[:160],
                    "reason": s.provenance.reason,
                },
            )
            s.consecutive_failures += 1
            if s.consecutive_failures >= api.MAX_CONSECUTIVE_FAILURES:
                s.break_step = True
                return
            s.continue_step = True
            return

    s.visible_tool_step += 1
    yield {"type": "activity", "content": {
        "kind": "analyze",
        "message": (f"步骤 {s.visible_tool_step}: {s.decision.tool}" if s.lang == "zh"
                    else f"Step {s.visible_tool_step}: {s.decision.tool}"),
        "visibility": "debug",
    }}, {}

    if (
        not s.replay_guard_emitted
        and api.action_contract_blocks_whole_node_replay(s.action_capability_id)
        and s.decision.tool in {
            "browser_fill", "browser_type_at", "browser_select",
            "browser_click", "browser_click_at", "browser_press",
            "browser_upload_file", "browser_paste_image",
            "browser_execute_workflow",
            "browser_execute_plan",
        }
    ):
        s.replay_guard_emitted = True
        yield {"type": "runtime_status", "content": {
            "side_effect_guard": {
                "status": "mutation_started",
                "blocks_replay": True,
                "capability_id": s.action_capability_id,
                "reason": "browser write mission has started; resume or verify instead of replaying the whole node",
            },
        }}, {}

    # Terminal / control tools
