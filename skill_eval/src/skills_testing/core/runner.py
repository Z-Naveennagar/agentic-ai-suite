"""
Single-arm skill test runner.

For each (case, client, model) the runner:
    1. Gates on host capabilities (writes SKIPPED + skip_reason if unmet).
    2. Provisions a per-test workspace under the configured workspace_root.
    3. Calls cli.invoke(prompt, workspace_dir, ...) via the injected backend.
    4. Builds a GraderContext, runs every grader from grading_spec.yaml.
    5. Aggregates per-grader pass/fail into a t2_score and overall status.
    6. Runs the cleanup steps from manifest.cleanup.
    7. Persists everything via db_writer.write_skill_test_result /
       write_skill_grader_result.

A/B + replication is added in PR 6 by wrapping run_case in a loop over
arms and replication_index.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from skills_testing.core import db_writer
from skills_testing.core import session_log
from skills_testing.core.session_log import SessionLogConfig

from .case_loader import CaseSpec
from ..graders import GraderContext, get_grader
from ..runtime import memory_guard
from ..runtime.cleanup_manager import CleanupContext, CleanupManager
from ..runtime.power_meter import PowerMeter
from ..runtime.requirements_probe import case_can_run
from ..runtime.suite_lifecycle import GroupRegistry, GroupState, suite_key_for
from ..runtime.workspace import create_workspace

logger = logging.getLogger(__name__)

try:
    from skills_testing.core.cost_model import is_self_hosted as _is_self_hosted_model  # type: ignore
except Exception:  # pragma: no cover - cost_model is optional in some test envs
    def _is_self_hosted_model(_model: str) -> bool:
        return False


@dataclass
class RunOutcome:
    skill_test_id: int
    skill_name: str
    case_id: str
    client: str
    model: str
    status: str            # PASS | FAIL | ERROR | SKIPPED
    aggregate_score: float = 0.0
    t2_score: float = 0.0
    skip_reason: Optional[str] = None
    error: Optional[str] = None
    grader_summary: list[dict] = field(default_factory=list)
    # Hallucination signal: True iff any grader marked `mandatory: true`
    # failed. Mandatory graders are the anti-hallucination contract
    # (artifact_signature, tool_call_observed, claim_consistency, ...).
    # None for SKIPPED / ERROR rows.
    hallucination_detected: Optional[bool] = None


class SkillRunner:
    def __init__(
        self,
        *,
        cli_factory: Callable[[str, str], Any],
        cleanup_manager: CleanupManager,
        host_caps: dict,
        workspace_root: Path | str,
        baseline_lookup: Callable[..., Optional[float]] | None = None,
        llm_caller: Callable[[str], dict] | None = None,
        keep_tmp_on_failure: bool = False,
        capture_baseline: bool = False,
        verifiers: dict[str, Callable[..., dict]] | None = None,
        skills_root: Path | str | None = None,
        session_log_config: SessionLogConfig | None = None,
        mcp_server_aliases: dict | None = None,
        group_registry: GroupRegistry | None = None,
        pre_invoke_memory_headroom_gb: float = 0.0,
    ) -> None:
        self.cli_factory = cli_factory
        self.cleanup_manager = cleanup_manager
        self.host_caps = host_caps
        # Shared-workspace grouping for suites with a setup:/reset:/teardown:
        # action (see runtime/suite_lifecycle.py). None for callers that
        # never wire it up -- every case then runs the original,
        # fully-isolated-per-case path.
        self.group_registry = group_registry
        # Reactive backpressure: sharded shared-workspace suites (e.g.
        # ip-configurator under --parallel > 1) can run several concurrent
        # Vivado sessions -- something a single-session suite never did
        # before sharding existed. A suite whose cases vary widely in
        # weight can line up several of its heaviest cases running at
        # once, spiking real memory well above a single-session run and
        # (observed in practice) tripping the host's own limits, taking
        # the whole session down. <= 0 disables the check (the default;
        # see runtime/memory_guard.py).
        self.pre_invoke_memory_headroom_gb = pre_invoke_memory_headroom_gb
        self.workspace_root = Path(workspace_root).expanduser()
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.baseline_lookup = baseline_lookup
        self.llm_caller = llm_caller
        self.keep_tmp_on_failure = keep_tmp_on_failure
        self.capture_baseline = capture_baseline
        self.skills_root = Path(skills_root).resolve() if skills_root else None
        # Phase 2b: registry of `tool -> callable` used to apply the
        # skill's own fix artifact and produce a fresh artifact set in
        # the workspace. Each verifier is called as
        #   verifier(workspace_dir=ws.dir, tcl=str, env=dict|None,
        #            timeout_seconds=int) -> {"stdout": str, "stderr": str,
        #                                      "exit_code": int}.
        self.verifiers = dict(verifiers or {})
        # MCP server-family aliases used to match tool calls agnostic of which
        # backend produced them / which server exposed the tool. Config entries
        # are merged OVER the built-in defaults so customers can add servers
        # without dropping the shipped (Vivado) family mappings.
        from ..graders.trace import DEFAULT_MCP_SERVER_ALIASES
        self.mcp_server_aliases = {
            **DEFAULT_MCP_SERVER_ALIASES,
            **(mcp_server_aliases or {}),
        }
        # Per-session JSON monitoring logs. Disabled by default so existing
        # callers/tests that don't opt in keep their behaviour; the CLI wires
        # in an enabled config unless --no-json-log is passed.
        self.session_log_config = session_log_config or SessionLogConfig(enabled=False)
        # Capture the Vivado version once at startup so every row gets
        # the same string. The dashboard groups failures by version so
        # an engineer can spot when `rtl-assistant + 2027.1` goes bad.
        from ..runtime.requirements_probe import _vivado_version
        try:
            self.vivado_version = _vivado_version() or ""
        except Exception:
            self.vivado_version = ""

    # -- public API -------------------------------------------------------

    def run_case(
        self,
        case: CaseSpec,
        *,
        run_id: str,
        conn: sqlite3.Connection,
        with_skill: bool = True,
        replication_index: int = 0,
        reps_per_arm: int = 1,
        skip_predicate: Callable[[str, str, str, bool, int], bool] | None = None,
    ) -> list[RunOutcome]:
        # Expand into (client/model, replication_index) combos. reps_per_arm
        # lets the with-skill-only path run each (case, model) more than once
        # for consistency-across-iterations views -- previously only the A/B
        # path honoured reps. reps_per_arm=1 (the default) reproduces the old
        # single-rep behaviour exactly (range(1) == [0]). Each combo is
        # skip-filtered per rep so --resume still works.
        clients = case.invocation.get("clients", [])
        combos = [
            (entry, rep)
            for entry in clients
            for rep in range(int(reps_per_arm))
            if not (skip_predicate and skip_predicate(
                case.case_id, entry["name"], entry["model"],
                with_skill, rep))
        ]
        n = len(combos)
        if n <= 1:
            return [self._run_one(
                case, entry["name"], entry["model"],
                run_id=run_id, conn=conn,
                with_skill=with_skill, replication_index=rep,
            ) for entry, rep in combos]

        # Parallelise across (client, model, rep) combos. Each gets its own
        # ephemeral SQLite connection so writes don't serialise on the
        # caller's connection. Wall time becomes max(combo) instead of sum.
        # (Reps of the same shared-workspace model still serialise on that
        # group's lock inside _run_one, with a reset between them.)
        from concurrent.futures import ThreadPoolExecutor
        import sqlite3 as _sqlite3
        db_path = (conn.execute(
            "PRAGMA database_list").fetchone() or (0, "main", ""))[2]

        def _worker(combo: tuple) -> RunOutcome:
            entry, rep = combo
            tc = _sqlite3.connect(db_path, check_same_thread=False)
            try:
                return self._run_one(
                    case, entry["name"], entry["model"],
                    run_id=run_id, conn=tc,
                    with_skill=with_skill,
                    replication_index=rep,
                )
            finally:
                tc.close()

        with ThreadPoolExecutor(max_workers=n,
                                thread_name_prefix="armpool") as ex:
            return list(ex.map(_worker, combos))

    def run_one(
        self,
        case: CaseSpec,
        client: str,
        model: str,
        *,
        run_id: str,
        conn: sqlite3.Connection,
        with_skill: bool = True,
        replication_index: int = 0,
    ) -> RunOutcome:
        """Public single-combo entry point: run exactly one (case, client,
        model, with_skill, replication_index) combo, including
        shared-workspace group locking.

        This is what integration_runner.py schedules directly -- one Task
        per combo under the top-level Scheduler, so --parallel and the
        memory budget bound real concurrency instead of only case count.
        ``run_case`` remains available for tests and ad-hoc one-case callers.
        """
        return self._run_one(
            case, client, model, run_id=run_id, conn=conn,
            with_skill=with_skill, replication_index=replication_index,
        )

    # -- internals --------------------------------------------------------

    def _skills_root_for(self, client: str) -> Path | None:
        """Per-client skill SOURCE root to stage into the workspace.

        Delegates to ``cli_backends.resolve_skills_root_for_client`` -- the
        single source of truth for the ``.claude`` -> ``.opencode`` sibling
        swap, also used by ``integration_runner`` to print the root that
        will actually be staged, so the two never drift apart.
        """
        if self.skills_root is None:
            return None
        from ..cli_backends import resolve_skills_root_for_client
        return resolve_skills_root_for_client(self.skills_root, client)

    def _run_one(
        self, case: CaseSpec, client: str, model: str,
        *, run_id: str, conn: sqlite3.Connection,
        with_skill: bool, replication_index: int,
    ) -> RunOutcome:
        """Run one (case, client, model) combo.

        Suites with a shared-workspace setup:/reset:/teardown: action (see
        runtime/suite_lifecycle.py) serialize their group's members
        through GroupState.lock -- only one member touches the shared
        workspace/session at a time -- and defer teardown to whichever
        member's turn brings the group to zero. Everything else runs the
        original, fully-isolated-per-case path unchanged.
        """
        with_skill = True  # retained only in persisted/log formats for compatibility
        group = self._group_for(case, client, model, replication_index)
        if group is None:
            return self._run_one_body(
                case, client, model, run_id=run_id, conn=conn,
                with_skill=with_skill, replication_index=replication_index,
                group=None,
            )
        group_desc = f"{suite_key_for(case)}/{client}/{model}"
        if group.lock.locked():
            logger.debug("%s: waiting for group %s (case %s)",
                        case.case_id, group_desc, case.case_id)
        lock_wait_started = time.monotonic()
        with group.lock:
            lock_wait = time.monotonic() - lock_wait_started
            if lock_wait > 0.5:
                logger.debug("%s: acquired group %s after %.1fs wait",
                            case.case_id, group_desc, lock_wait)
            try:
                return self._run_one_body(
                    case, client, model, run_id=run_id, conn=conn,
                    with_skill=with_skill, replication_index=replication_index,
                    group=group,
                )
            finally:
                if group.decrement():
                    logger.info("group %s: last member (%s) finished, "
                               "tearing down", group_desc, case.case_id)
                    self._run_group_teardown(
                        case, group, client=client, model=model,
                        with_skill=True,
                    )

    def _group_for(
        self, case: CaseSpec, client: str, model: str, replication_index: int,
    ) -> GroupState | None:
        if self.group_registry is None:
            return None
        if not (case.setup_action or case.reset_action or case.teardown_action):
            return None
        base_key = (suite_key_for(case), client, model)
        shard_idx = self.group_registry.shard_for(
            base_key, case.case_id, replication_index)
        return self.group_registry.get((*base_key, shard_idx))

    def _run_one_body(
        self, case: CaseSpec, client: str, model: str,
        *, run_id: str, conn: sqlite3.Connection,
        with_skill: bool, replication_index: int,
        group: GroupState | None,
    ) -> RunOutcome:
        setup_action = case.setup_action
        reset_action = case.reset_action
        teardown_action = case.teardown_action

        # 1. requirements gate
        ok, reason = case_can_run(case.requirements, self.host_caps)
        if not ok:
            sid = db_writer.write_skill_test_result(conn, run_id, {
                "skill_name": case.skill_name,
                "skill_version": case.skill_version,
                "case_id": case.case_id,
                "client": client, "model": model,
                "with_skill": with_skill,
                "replication_index": replication_index,
                "status": "SKIPPED", "skip_reason": reason,
            })
            return RunOutcome(skill_test_id=sid, skill_name=case.skill_name,
                              case_id=case.case_id, client=client, model=model,
                              status="SKIPPED", skip_reason=reason)

        # 2. workspace -- created once per (suite, client, model) group and
        # reused by every later member when the suite declares a shared
        # setup:/reset:/teardown: action; otherwise (the common case) a fresh,
        # isolated workspace per case, exactly as before.
        if group is not None and group.workspace is not None:
            ws = group.workspace
            logger.debug("%s: reusing shared workspace %s", case.case_id, ws.dir)
        else:
            # Allowlist: when the manifest declares `invocation.skills:` we
            # stage only those skill bodies, so the agent doesn't pay for
            # 5 sibling sub-skills it never calls.
            skills_allowlist = (
                list(case.invocation.get("skills") or [])
                if with_skill else []
            )
            from ..cli_backends import skills_dir_for
            ws = create_workspace(
                f"{case.skill_name}_{case.case_id}",
                root=self.workspace_root,
                inputs_dir=case.inputs_dir,
                external_inputs=case.invocation.get("external_inputs") or [],
                # Stage the testing repo's skill tree into the workspace so
                # each CLI auto-discovers the project-local skills rather than
                # the user's home dir. Both the SOURCE and the destination
                # folder are client-specific: opencode links its own
                # `.opencode/skills` source into a `.opencode/skills`
                # workspace folder; other clients use `.claude/skills` for
                # both. This keeps opencode `.opencode` end-to-end, so a
                # skill writing back to its own dir (e.g. a learned cache)
                # never crosses into `.claude`.
                skills_root=self._skills_root_for(client),
                skills_allowlist=skills_allowlist,
                skills_dest=skills_dir_for(client),
                # Critical for A/B integrity: in the no-skill arm, drop any
                # external_inputs that would land inside .claude/skills/.
                # Without this, a manifest that smuggles SKILL.md trees in
                # via external_inputs makes the no-skill arm see (and use)
                # the skill anyway, which silently invalidates the contrast
                # between the two arms.
            )
            try:
                ws.populate()
            except FileNotFoundError as exc:
                sid = db_writer.write_skill_test_result(conn, run_id, {
                    "skill_name": case.skill_name, "skill_version": case.skill_version,
                    "case_id": case.case_id, "client": client, "model": model,
                    "with_skill": with_skill, "replication_index": replication_index,
                    "status": "ERROR", "error": f"input setup failed: {exc}",
                })
                ws.cleanup()
                return RunOutcome(skill_test_id=sid, skill_name=case.skill_name,
                                  case_id=case.case_id, client=client, model=model,
                                  status="ERROR", error=str(exc))

            if group is not None:
                # Persist the workspace for the rest of this group's
                # members BEFORE attempting the setup action, so a setup
                # failure still leaves something for the deferred
                # teardown to wipe.
                group.workspace = ws
                # One shard = one live Vivado session slot: reserve it
                # here, for the shard's whole lifetime, before the setup
                # action can start anything. Whichever member's turn
                # tears this shard down releases the same permit (see
                # _run_group_teardown) -- symmetric because both are
                # gated on "first/last member of this shard", each firing
                # exactly once. Blocks here (by design) when the run's
                # other shards/combos already hold every permit --
                # min(--parallel, vivado_mcp_session_cap) sessions may
                # ever be live at once, server-wide.
                if self.group_registry is not None and self.group_registry.session_semaphore is not None:
                    self.group_registry.session_semaphore.acquire()
                if setup_action:
                    logger.info("%s: running suite setup (kind=%s) in %s",
                               case.case_id, setup_action["kind"], ws.dir)
                    setup_started = time.monotonic()
                    setup_result = self._run_lifecycle_action(
                        setup_action, cli=self.cli_factory(client, model),
                        ws_dir=ws.dir,
                    )
                    setup_elapsed = time.monotonic() - setup_started
                    if setup_result["ok"]:
                        logger.info("%s: suite setup done in %.1fs",
                                   case.case_id, setup_elapsed)
                        group.session_ids = setup_result["vivado_session_ids"]
                    else:
                        logger.error("%s: suite setup failed after %.1fs: %s",
                                    case.case_id, setup_elapsed, setup_result["error"])
                        group.setup_error = setup_result["error"]

        # Either failure poisons the group: setup never built the shared
        # environment, or a reset left it dirty. Both mean this case would be
        # graded against something other than the baseline it assumes, so
        # record ERROR without spending an agent invocation on it.
        group_error = None
        if group is not None:
            if group.setup_error:
                group_error = f"suite setup failed: {group.setup_error}"
            elif group.reset_error:
                group_error = (
                    "suite reset failed for an earlier case in this group, so "
                    f"the shared design is not at baseline: {group.reset_error}")
        if group is not None and group_error:
            group.any_failed = True
            sid = db_writer.write_skill_test_result(conn, run_id, {
                "skill_name": case.skill_name, "skill_version": case.skill_version,
                "case_id": case.case_id, "client": client, "model": model,
                "with_skill": with_skill, "replication_index": replication_index,
                "status": "ERROR", "error": group_error,
            })
            return RunOutcome(skill_test_id=sid, skill_name=case.skill_name,
                              case_id=case.case_id, client=client, model=model,
                              status="ERROR", error=group_error)

        # Snapshot the freshly-populated workspace so the session logger can
        # later tell which files the agent *produced* (new or modified) from
        # the staged inputs. Cheap, best-effort.
        input_snapshot: dict = {}
        if self.session_log_config.enabled:
            try:
                input_snapshot = session_log.snapshot_workspace(ws.dir)
            except Exception:
                input_snapshot = {}

        # 3. CLI invocation
        cli = self.cli_factory(client, model)
        if not getattr(cli, "is_available", True):
            reason = f"client unavailable: {cli.unavailable_reason}"
            sid = db_writer.write_skill_test_result(conn, run_id, {
                "skill_name": case.skill_name,
                "skill_version": case.skill_version,
                "case_id": case.case_id,
                "client": client, "model": model,
                "with_skill": with_skill,
                "replication_index": replication_index,
                "status": "SKIPPED", "skip_reason": reason,
            })
            if group is None:
                self._cleanup(case, ws, vivado_session_ids=[], failed=False)
            return RunOutcome(
                skill_test_id=sid, skill_name=case.skill_name,
                case_id=case.case_id, client=client, model=model,
                status="SKIPPED", skip_reason=reason,
            )
        prompt = case.invocation.get("prompt") or _default_prompt(case)
        env: dict | None = None
        if self.skills_root is not None:
            # Pin skill discovery to the workspace copy, never the user's home.
            from ..runtime.skill_hider import redirect_skills_env
            env = redirect_skills_env(client, ws.dir / ws.skills_dest)
        timeout_seconds = int(case.invocation.get("timeout_seconds", 600))
        max_retries = int(case.invocation.get("retries", 0) or 0)

        # Pre-flight throughput check (Fix #2). Backends backed by a
        # slow on-prem inference engine probe the model first and can
        # short-circuit with a SKIPPED row if the prompt won't finish
        # in time, instead of waiting out the whole timeout for nothing.
        # ``cli_factory`` is an injection seam, so tolerate a double that
        # predates the SkillBackend interface and has no probe at all.
        probe = getattr(cli, "preflight_skip", None)
        try:
            pf_reason = probe(
                prompt=prompt, workspace_dir=ws.dir,
                timeout_seconds=timeout_seconds,
            ) if probe else None
        except Exception:
            pf_reason = None  # never let the probe break a real run
        if pf_reason:
            sid = db_writer.write_skill_test_result(conn, run_id, {
                "skill_name": case.skill_name,
                "skill_version": case.skill_version,
                "case_id": case.case_id,
                "client": client, "model": model,
                "with_skill": with_skill,
                "replication_index": replication_index,
                "status": "SKIPPED", "skip_reason": pf_reason,
            })
            if group is None:
                self._cleanup(case, ws, vivado_session_ids=[], failed=False)
            return RunOutcome(
                skill_test_id=sid, skill_name=case.skill_name,
                case_id=case.case_id, client=client, model=model,
                status="SKIPPED", skip_reason=pf_reason,
            )

        # Wrap self-hosted invocations with PowerMeter so cost_model can
        # bill the row at the *measured* watts instead of the static
        # avg_power_watts from config.yaml.  For hosted API models this
        # is a no-op so we skip the 5s post-test baseline overhead.
        power_metrics: dict | None = None
        meter = (
            PowerMeter(baseline_seconds=5.0)
            if _is_self_hosted_model(model) else None
        )
        try:
            if meter is not None:
                meter.start()
            # Retry-on-timeout loop. base.SkillCLIBackend.invoke does NOT
            # raise on timeout: it returns exit_code 124 with whatever partial
            # output it captured. A timed-out attempt is redone up to
            # `max_retries` times. To avoid orphaning the Vivado work the
            # killed attempt already did, the same MCP session is carried
            # forward -- the persistent MCP server keeps the session alive
            # after the CLI process is killed, so the next attempt is told to
            # resume that session_id instead of starting a fresh Vivado.
            # Seeded from the group's carried session (set by the suite's
            # setup action or a prior case in the same group), if any, so
            # this case's very first attempt already knows to reuse it.
            carried_session_ids: list[str] = (
                list(group.session_ids) if group is not None else []
            )
            attempt = 0
            # Reactive backpressure before starting the (possibly heavy)
            # agent invocation -- see pre_invoke_memory_headroom_gb above
            # and runtime/memory_guard.py. No-op unless configured. When a
            # session has multiple cases queued (a shared-workspace shard
            # finishing one case and about to load the next), this is
            # exactly the "session finished, about to load another case"
            # moment -- wait here until enough memory is actually free
            # rather than loading it immediately.
            memory_guard.wait_for_headroom(
                self.pre_invoke_memory_headroom_gb,
                label=f"{case.case_id} ({client}/{model})",
            )
            logger.info("%s: invoking %s/%s (%s, timeout=%ds) in %s",
                       case.case_id, client, model,
                       "with_skill" if with_skill else "no_skill",
                       timeout_seconds, ws.dir)
            invoke_started = time.monotonic()
            while True:
                attempt_prompt = (
                    _augment_prompt_reuse_session(
                        prompt, carried_session_ids,
                        # attempt 0 is reusing the suite/group's prepared
                        # session, not recovering from a timeout of its own.
                        after_timeout=attempt > 0)
                    if carried_session_ids else prompt
                )
                invocation = cli.invoke(
                    prompt=attempt_prompt, workspace_dir=ws.dir,
                    timeout_seconds=timeout_seconds,
                    env=env,
                )
                # Remember any Vivado session this attempt touched so a retry
                # resumes it rather than spawning a new one.
                seen_ids = invocation.get("vivado_session_ids") or []
                if seen_ids:
                    carried_session_ids = seen_ids
                timed_out = invocation.get("exit_code") == 124
                if not timed_out or attempt >= max_retries:
                    break
                attempt += 1
                logger.warning(
                    "%s (%s) timed out after %ds; retry %d/%d%s",
                    case.case_id, "skill" if with_skill else "no-skill",
                    timeout_seconds, attempt, max_retries,
                    f", reusing Vivado session {carried_session_ids[-1]}"
                    if carried_session_ids else "",
                )
            invoke_elapsed = time.monotonic() - invoke_started
            logger.info(
                "%s: %s/%s done in %.1fs (exit_code=%s, retries=%d)",
                case.case_id, client, model, invoke_elapsed,
                invocation.get("exit_code"), attempt,
            )
            if attempt:
                invocation["retry_count"] = attempt
            if meter is not None:
                meter.stop()
                power_metrics = meter.metrics
            if group is not None:
                # Hand the freshest known session id(s) to the next case
                # in this group.
                group.session_ids = carried_session_ids
        except Exception as exc:
            if meter is not None:
                try:
                    meter.stop()
                except Exception:
                    pass
                power_metrics = meter.metrics
            sid = db_writer.write_skill_test_result(conn, run_id, {
                "skill_name": case.skill_name, "skill_version": case.skill_version,
                "case_id": case.case_id, "client": client, "model": model,
                "with_skill": with_skill, "replication_index": replication_index,
                "status": "ERROR", "error": f"cli invoke raised: {exc}",
            })
            if group is not None:
                group.any_failed = True
            else:
                self._cleanup(case, ws, vivado_session_ids=[], failed=True)
            return RunOutcome(skill_test_id=sid, skill_name=case.skill_name,
                              case_id=case.case_id, client=client, model=model,
                              status="ERROR", error=str(exc))

        # 4. detect skill invocation
        invoked, _ = cli.detect_skill_invocation(
            invocation.get("stdout", ""), invocation.get("stderr", "")
        )

        # 5. grade
        grader_results = self._grade(
            case, ws.dir, invocation, with_skill=with_skill,
            session_ids=(group.session_ids if group is not None else None),
            client=client, model=model,
        )

        # 5b. Phase 2b: optional apply-and-rerun verification. Only
        # attempt if the primary graders all passed AND verify_by_rerun
        # is enabled in the manifest.
        primary_passed = all(g["passed"] for g in grader_results) and grader_results
        if (primary_passed and case.verify_by_rerun
                and case.verify_by_rerun.get("enabled")):
            verify_results = self._verify_by_rerun(
                case, ws.dir, invocation, client=client, model=model,
            )
            grader_results.extend(verify_results)

        n_total = len(grader_results)
        n_passed = sum(1 for g in grader_results if g["passed"])
        # Mandatory graders are pure Pass/Fail gates (see the hallucination
        # contract below) and are excluded from the scored aggregate — they
        # carry no weight and contribute no score. Only the soft graders
        # determine t2. When a case has ONLY mandatory graders, t2 defaults
        # to 1.0 so the verdict is driven entirely by the pass/fail gates.
        scored = [g for g in grader_results if not g.get("mandatory")]
        # Aggregate the soft (non-mandatory) results into the case score
        # (t2, on 0-1).
        #   weighted_sum -> sum(weight_i * score_i) / sum(weight_i)
        #   fraction     -> passed / total  (default, legacy behaviour)
        if getattr(case, "scoring_aggregation", "fraction") == "weighted_sum":
            total_w = sum(float(g.get("weight", 1.0)) for g in scored)
            t2 = (
                sum(float(g.get("weight", 1.0)) * float(g["score"])
                    for g in scored) / total_w
            ) if total_w else 1.0
        else:
            n_scored = len(scored)
            t2 = (
                sum(1 for g in scored if g["passed"]) / n_scored
            ) if n_scored else 1.0

        # Hallucination contract: a grader marked `mandatory: true` is
        # an anti-hallucination check (e.g. artifact_signature for a
        # real Vivado report header). If ANY such grader failed, the
        # row is hallucination_detected=1 regardless of the soft graders.
        mandatory_grs = [g for g in grader_results if g.get("mandatory")]
        any_mandatory = bool(mandatory_grs)
        hallucination_detected = (
            any(not g["passed"] for g in mandatory_grs) if any_mandatory
            else False
        )

        # A hallucinating run cannot pass, even if the soft graders are
        # all green. Conversely, missing mandatory graders is *not*
        # treated as hallucination (back-compat with cases that haven't
        # opted into the contract yet).
        if hallucination_detected:
            status = "FAIL"
        else:
            status = "PASS" if t2 >= case.pass_threshold else "FAIL"
        logger.info("%s: graded %s (t2=%.2f, threshold=%.2f, hallucination=%s)",
                   case.case_id, status, t2, case.pass_threshold,
                   hallucination_detected)

        # 6. write skill_test_results then per-grader rows
        sid = db_writer.write_skill_test_result(conn, run_id, {
            "skill_name": case.skill_name,
            "skill_version": case.skill_version,
            "case_id": case.case_id, "client": client, "model": model,
            "with_skill": with_skill,
            "replication_index": replication_index,
            "skill_invoked": invoked,
            "power_metrics": power_metrics,
            "wall_clock_s": invocation.get("wall_clock_s"),
            "prompt_tokens": invocation.get("prompt_tokens"),
            "output_tokens": invocation.get("output_tokens"),
            "total_tokens": invocation.get("total_tokens"),
            "cache_read_tokens": invocation.get("cache_read_tokens", 0),
            "cache_write_tokens": invocation.get("cache_write_tokens", 0),
            "t2_score": t2,
            "aggregate_score": t2,
            "status": status,
            "hallucination_detected": hallucination_detected,
            "vivado_version": self.vivado_version,
        })
        for g in grader_results:
            db_writer.write_skill_grader_result(conn, sid, {
                "grader_id":   g["id"],
                "grader_type": g["type"],
                "passed":      g["passed"],
                "score":       g["score"],
                "details":     json.dumps(g["details"], default=str),
                "mandatory":   bool(g.get("mandatory", False)),
                "weight":      g.get("weight"),
            })

        # 6a. Per-session JSON monitoring log: capture the prompt, raw
        # output, produced artifacts, and grader verdicts to
        # logs/<run_id>/ BEFORE cleanup wipes the workspace.
        if self.session_log_config.enabled:
            self._write_session_log(
                run_id=run_id, skill_test_id=sid, conn=conn, case=case,
                client=client, model=model, with_skill=with_skill,
                # The prompt as ACTUALLY SENT, not the case's base prompt:
                # attempt_prompt carries the session/retry notice the harness
                # appends. Logging the base prompt made the log misleading --
                # you couldn't tell from it whether the agent was ever handed a
                # session id, which is exactly what you go to the log to check.
                replication_index=replication_index, prompt=attempt_prompt,
                invocation=invocation, grader_results=grader_results,
                status=status, t2=t2,
                hallucination_detected=hallucination_detected,
                skill_invoked=invoked, ws_dir=ws.dir,
                input_snapshot=input_snapshot,
            )

        # 6b. optional: capture metrics into skill_baselines
        if self.capture_baseline and status == "PASS":
            from .baselines import capture_metrics_from_grader_results
            capture_metrics_from_grader_results(
                conn,
                skill_name=case.skill_name,
                skill_version=case.skill_version,
                case_id=case.case_id,
                grader_results=grader_results,
            )

        # 7. cleanup -- deferred to the group's last member (see
        # _run_group_teardown) when this case shares a workspace/session
        # with others in its suite; otherwise runs right here as before.
        failed = (status != "PASS")
        if group is not None:
            group.any_failed = group.any_failed or failed
            # Reset runs after every member EXCEPT the last -- it exists to
            # hand the next case a baseline shared workspace/session, and after
            # the last member there is no next case: teardown wipes the
            # workspace and stops the session moments later. `remaining` is
            # still pre-decrement here (group.decrement() runs in _run_one's
            # finally, after this body returns), and we hold group.lock, so
            # remaining <= 1 identifies the last member.
            is_last_member = group.remaining <= 1
            if reset_action and is_last_member:
                logger.debug("%s: skipping suite reset -- last member of the "
                            "group, teardown follows", case.case_id)
            elif reset_action:
                reset_started = time.monotonic()
                reset_result = self._run_lifecycle_action(
                    reset_action, cli=self.cli_factory(client, model),
                    ws_dir=ws.dir, session_ids=group.session_ids,
                )
                reset_elapsed = time.monotonic() - reset_started
                if reset_result["ok"]:
                    logger.info("%s: suite reset done in %.1fs",
                               case.case_id, reset_elapsed)
                    if reset_result["vivado_session_ids"]:
                        group.session_ids = reset_result["vivado_session_ids"]
                else:
                    # Fatal to the group, not a warning. A failed reset leaves
                    # the shared block design dirty (leftover cells, or a part
                    # still swapped by a case that needed a different one), and
                    # every later case then fails for reasons that have nothing
                    # to do with the skill -- attributed to the wrong case.
                    # Stopping loudly beats silent cross-case contamination.
                    logger.error(
                        "%s: suite reset failed after %.1fs for %s (%s/%s): %s "
                        "-- failing the rest of the group",
                        case.case_id, reset_elapsed, case.skill_name, client,
                        model, reset_result["error"],
                    )
                    group.reset_error = reset_result["error"]
                    group.any_failed = True
        else:
            vivado_session_ids = invocation.get("vivado_session_ids") or []
            self._cleanup(case, ws, vivado_session_ids=vivado_session_ids, failed=failed)

        return RunOutcome(
            skill_test_id=sid, skill_name=case.skill_name,
            case_id=case.case_id, client=client, model=model,
            status=status, aggregate_score=t2, t2_score=t2,
            grader_summary=grader_results,
            hallucination_detected=hallucination_detected,
        )

    # -- helpers ---------------------------------------------------------

    def _write_session_log(
        self,
        *,
        run_id: str,
        skill_test_id: int,
        conn: sqlite3.Connection,
        case: CaseSpec,
        client: str,
        model: str,
        with_skill: bool,
        replication_index: int,
        prompt: str,
        invocation: dict,
        grader_results: list[dict],
        status: str,
        t2: float,
        hallucination_detected: bool | None,
        skill_invoked: bool,
        ws_dir: Path,
        input_snapshot: dict,
    ) -> None:
        """Assemble and write the forensic per-test JSON log. Best-effort:
        a logging failure must never turn a completed run into a failure."""
        cfg = self.session_log_config
        try:
            # Reuse the timestamp the DB stored for this row as the record's
            # in-file `timestamp` (the filename itself carries no timestamp).
            row = conn.execute(
                "SELECT timestamp FROM skill_test_results WHERE id=?",
                (skill_test_id,),
            ).fetchone()
            row_ts = row[0] if row else None
            sdir = session_log.session_dir(run_id, conn, cfg)
            stem = session_log.test_log_stem(
                skill_name=case.skill_name, case_id=case.case_id,
                with_skill=with_skill, replication_index=replication_index,
                client=client, model=model,
            )
            copy_dir = session_log.artifacts_copy_dir(sdir, cfg, stem)
            artifacts = session_log.collect_artifacts(
                ws_dir, input_snapshot,
                size_cap=cfg.artifact_size_cap_bytes,
                copy_dir=copy_dir,
            )
            record = session_log.build_record(
                run_id=run_id,
                skill_name=case.skill_name,
                skill_version=case.skill_version,
                case_id=case.case_id,
                client=client, model=model,
                with_skill=with_skill,
                replication_index=replication_index,
                skill_invoked=skill_invoked,
                prompt=prompt,
                invocation=invocation,
                grader_results=grader_results,
                status=status,
                t2_score=t2,
                pass_threshold=case.pass_threshold,
                hallucination_detected=hallucination_detected,
                artifacts=artifacts,
                timestamp_iso=row_ts or session_log._utc_now_iso(),
                max_output_chars=cfg.max_output_chars,
            )
            session_log.write_test_log(record, session_dir=sdir)
        except Exception as exc:  # pragma: no cover - never break a real run
            sys.stderr.write(
                f"[session_log] failed for {case.skill_name}/{case.case_id}: {exc}\n")

    def _grade(
        self, case: CaseSpec, ws_dir: Path, invocation: dict,
        *, with_skill: bool = True, session_ids: list[str] | None = None,
        client: str | None = None, model: str | None = None,
    ) -> list[dict]:
        ctx = self._make_ctx(case, ws_dir, invocation, with_skill=with_skill,
                             session_ids=session_ids, client=client, model=model)
        return self._run_specs(case.grading, ctx, with_skill=with_skill)

    def _make_ctx(
        self, case: CaseSpec, ws_dir: Path, invocation: dict,
        *, with_skill: bool = True, session_ids: list[str] | None = None,
        client: str | None = None, model: str | None = None,
    ) -> GraderContext:
        return GraderContext(
            workspace_dir=ws_dir,
            stdout=invocation.get("stdout", ""),
            stderr=invocation.get("stderr", ""),
            case_dir=case.case_dir,
            parameters=dict(case.invocation.get("parameters") or {}),
            baseline_lookup=self.baseline_lookup,
            llm_caller=self.llm_caller,
            run_meta={
                "skill_name": case.skill_name,
                "skill_version": case.skill_version,
                "case_id": case.case_id,
                # Arm marker read by arm-aware graders (e.g. trigger).
                "with_skill": with_skill,
                # Which CLI backend/model produced stdout/stderr -- selects
                # the right transcript dialect in graders/trace.py
                # (extract_tool_calls / detect_skill_activation). Without
                # this, client-aware graders (trigger, discovery_first,
                # action_sequence, tool_call_observed) fall back to format
                # auto-detection, which doesn't recognize every backend's
                # transcript shape (e.g. Cursor's tool_call/*ToolCall JSONL).
                "client": client,
                "model": model,
                # Server-family aliases for backend-agnostic MCP tool matching
                # (consumed by action_sequence / tool_call_observed graders).
                "mcp_server_aliases": self.mcp_server_aliases,
                # The group's live Vivado session id(s), when this case is
                # part of a shared-workspace group (see runner.py's call
                # site for _grade) -- read by graders that need to act on
                # the still-running session before reset/teardown tear it
                # down (e.g. harness_script's {session_id} substitution).
                "vivado_session_ids": list(session_ids or []),
            },
        )

    def _run_specs(
        self, specs: list[dict], ctx: GraderContext,
        *, with_skill: bool = True,
    ) -> list[dict]:
        out: list[dict] = []
        for spec in specs:
            grader = get_grader(spec["type"])
            gid = spec.get("id", spec["type"])
            # Hallucination contract: a grader marked `mandatory: true`
            # is an anti-hallucination check. If it fails, the row is
            # marked hallucination_detected and counts toward the
            # release-gate hallucination_rate.
            mandatory = bool(spec.get("mandatory", False))
            weight = float(spec.get("weight", 1.0))
            try:
                r = grader.grade(spec, ctx)
                out.append({"id": gid, "type": spec["type"],
                            "mandatory": mandatory, "weight": weight,
                            "passed": r.passed, "score": r.score,
                            "details": r.details})
            except Exception as exc:
                out.append({"id": gid, "type": spec["type"],
                            "mandatory": mandatory, "weight": weight,
                            "passed": False, "score": 0.0,
                            "details": {"error": str(exc)}})
        return out

    def _verify_by_rerun(
        self, case: CaseSpec, ws_dir: Path, invocation: dict,
        *, client: str | None = None, model: str | None = None,
    ) -> list[dict]:
        """
        Phase 2b: apply the skill's own fix artifact (e.g. timing_fixes.xdc)
        via a registered verifier (e.g. Vivado MCP), then re-grade against
        verify_by_rerun.success_criteria.
        """
        verify = case.verify_by_rerun or {}
        apply_via = verify.get("apply_via") or {}
        tool = apply_via.get("tool")

        meta_id = "verify_by_rerun.apply"
        verifier = self.verifiers.get(tool)
        if verifier is None:
            return [{
                "id": meta_id, "type": "verify_by_rerun",
                "passed": False, "score": 0.0,
                "details": {"reason": "no_verifier_registered", "tool": tool},
            }]

        # Render {{ apply_artifact }} and other placeholders into the tcl
        # block. We re-use the schema_checks template engine so behaviour
        # matches ReportSchema / OracleMatch.
        from ..graders import schema_checks as _sc
        tvars = {
            "apply_artifact": verify.get("apply_artifact", ""),
            "parameters": dict(case.invocation.get("parameters") or {}),
        }
        tcl = _sc.render(apply_via.get("tcl", ""), tvars)
        env = apply_via.get("env") or None
        budget = int(verify.get("budget_seconds", 1800))

        try:
            apply_out = verifier(
                workspace_dir=ws_dir, tcl=tcl, env=env,
                timeout_seconds=budget,
            )
        except Exception as exc:
            return [{
                "id": meta_id, "type": "verify_by_rerun",
                "passed": False, "score": 0.0,
                "details": {"reason": "verifier_raised", "error": str(exc),
                            "tool": tool},
            }]

        exit_code = int(apply_out.get("exit_code", 0))
        apply_row = {
            "id": meta_id, "type": "verify_by_rerun",
            "passed": exit_code == 0, "score": 1.0 if exit_code == 0 else 0.0,
            "details": {"tool": tool, "exit_code": exit_code,
                        "stderr_tail": (apply_out.get("stderr") or "")[-512:]},
        }
        if exit_code != 0:
            return [apply_row]

        # Build a fresh context whose stdout/stderr come from the
        # verifier run, so success_criteria can grep the post-fix logs.
        rerun_invocation = {
            "stdout": apply_out.get("stdout", ""),
            "stderr": apply_out.get("stderr", ""),
        }
        rerun_ctx = self._make_ctx(case, ws_dir, rerun_invocation,
                                    client=client, model=model)
        criteria = verify.get("success_criteria") or []
        # Tag criterion ids so they don't collide with primary graders.
        tagged: list[dict] = []
        for c in criteria:
            cc = dict(c)
            cc["id"] = f"verify_by_rerun.{c.get('id', c['type'])}"
            tagged.append(cc)
        return [apply_row] + self._run_specs(tagged, rerun_ctx)

    def _cleanup(self, case: CaseSpec, ws, *, vivado_session_ids, failed: bool) -> None:
        if self.keep_tmp_on_failure and failed and "working_dir" in case.cleanup:
            steps = [s for s in case.cleanup if s != "working_dir"]
        else:
            steps = list(case.cleanup)
        ctx = CleanupContext(workspace=ws,
                             vivado_session_ids=list(vivado_session_ids),
                             notes={})
        self.cleanup_manager.run(steps, ctx)

    def _run_lifecycle_action(self, action: dict, *, cli, ws_dir: Path,
                              session_ids: list[str] | None = None) -> dict:
        """Execute a suite-level setup/reset/teardown action (case.setup_action
        / reset_action / teardown_action) and report the outcome as
        ``{"ok": bool, "error": str|None, "vivado_session_ids": list[str]}``.

        ``kind: prompt`` goes through the SAME ``cli.invoke()`` path as a
        real case -- so it's the agent, not the harness, that actually
        starts Vivado / opens the block design / sources the skill's TCL
        library, exactly as SKILL.md instructs it to for a real case.
        ``kind: python``/``kind: bash`` run directly via subprocess for
        actions that don't need an agent at all.
        """
        kind = action["kind"]
        timeout_seconds = int(action.get("timeout_seconds", 1800))
        if kind == "prompt":
            invocation = cli.invoke(
                prompt=action["prompt"], workspace_dir=ws_dir,
                timeout_seconds=timeout_seconds, env=None,
            )
            exit_code = invocation.get("exit_code")
            ok = exit_code in (0, None)
            error = None if ok else (
                f"exit_code={exit_code}: {(invocation.get('stderr') or '')[-500:]}")
            return {"ok": ok, "error": error,
                    "vivado_session_ids": invocation.get("vivado_session_ids") or []}

        import subprocess
        if kind == "bash":
            cmd: Any = action["command"]
            shell = True
        else:  # kind == "python"
            # Token substitution so a suite spec stays client-agnostic. The
            # staged skills dir is backend-specific -- opencode stages into
            # .opencode/skills while Claude Code/Copilot use .claude/skills
            # (see create_workspace's skills_dest=skills_dir_for(client)) -- so
            # a hardcoded path in runner_spec.yaml is right for one backend and
            # broken for the others.
            # {session_id} is the group's live Vivado session (whatever setup
            # printed via VIVADO_SESSION_ID:) -- a reset must act on THAT
            # session, not start its own. Empty when a group has none, which
            # runtime/vivado_session_reset.py treats as "discover by
            # working_dir" rather than an error.
            session_id = (session_ids or [""])[0]
            args = [
                a.replace("{skills_dir}", type(cli).workspace_skills_dir)
                 .replace("{workspace}", str(ws_dir))
                 .replace("{session_id}", session_id)
                for a in (action.get("args") or [])
            ]
            if action.get("module"):
                cmd = [sys.executable, "-m", action["module"], *args]
            else:
                cmd = [sys.executable, action["script"], *args]
            shell = False
        try:
            proc = subprocess.run(
                cmd, shell=shell, cwd=ws_dir, capture_output=True, text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            return {"ok": False,
                    "error": f"timed out after {timeout_seconds}s: {exc}",
                    "vivado_session_ids": []}
        ok = proc.returncode == 0
        error = None if ok else f"exit_code={proc.returncode}: {proc.stderr[-500:]}"
        # A script setup that started a shared Vivado session reports it by
        # printing "VIVADO_SESSION_ID:<id>" (see
        # runtime/vivado_session_setup.py). Without this the ids were dropped
        # on the floor for kind=python/bash, so group.session_ids stayed empty
        # and no case learned to reuse the session the setup had just built --
        # only kind=prompt could hand one over, via the agent's transcript.
        return {"ok": ok, "error": error,
                "vivado_session_ids": _parse_session_id_sentinels(proc.stdout)}

    def _run_group_teardown(
        self, case: CaseSpec, group: GroupState, *,
        client: str, model: str, with_skill: bool,
    ) -> None:
        """Run once, by whichever group member's turn brought it to zero:
        the suite's teardown action (if any), then the deferred per-case
        cleanup (e.g. the working_dir wipe every other suite runs after
        every single case)."""
        ws = group.workspace
        if ws is None:
            logger.debug("%s: group teardown -- nothing was ever set up",
                        case.case_id)
            return  # nothing was ever set up for this group -- no session
                    # permit was ever acquired either, so nothing to release
        try:
            teardown_action = case.teardown_action
            if teardown_action:
                teardown_started = time.monotonic()
                result = self._run_lifecycle_action(
                    teardown_action, cli=self.cli_factory(client, model),
                    ws_dir=ws.dir,
                )
                teardown_elapsed = time.monotonic() - teardown_started
                if result["ok"]:
                    logger.info("%s: suite teardown action done in %.1fs",
                               case.case_id, teardown_elapsed)
                else:
                    logger.warning(
                        "%s: suite teardown action failed after %.1fs for "
                        "%s (%s/%s): %s",
                        case.case_id, teardown_elapsed, case.skill_name, client,
                        model, result["error"],
                    )
            logger.info("%s: wiping shared workspace %s (any_failed=%s)",
                       case.case_id, ws.dir, group.any_failed)
            self._cleanup(case, ws, vivado_session_ids=list(group.session_ids),
                          failed=group.any_failed)
        finally:
            # Mirrors the acquire in _run_one_body's shard-init branch --
            # this shard's permit is released exactly once, here, whether
            # teardown/cleanup succeeded or raised, freeing the slot for
            # whichever other shard/combo is queued waiting for a session.
            if self.group_registry is not None and self.group_registry.session_semaphore is not None:
                self.group_registry.session_semaphore.release()


def _default_prompt(case: CaseSpec) -> str:
    return (
        f"Please run the {case.skill_name} skill on the inputs in the current "
        f"working directory. Case: {case.case_id}. {case.description}"
    )


#: Sentinel a ``kind: python``/``kind: bash`` lifecycle action prints to hand a
#: Vivado session it started back to the harness. Kept in sync with
#: ``runtime/vivado_session_setup.py:SESSION_ID_SENTINEL``.
_SESSION_ID_SENTINEL = "VIVADO_SESSION_ID:"


def _parse_session_id_sentinels(stdout: str) -> list[str]:
    """Collect ``VIVADO_SESSION_ID:<id>`` ids from a lifecycle script's stdout.

    Order-preserving and de-duplicated, so a script that prints the same id
    twice (or a wrapper that echoes its child) doesn't register it twice.
    """
    ids: list[str] = []
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line.startswith(_SESSION_ID_SENTINEL):
            continue
        sid = line[len(_SESSION_ID_SENTINEL):].strip()
        if sid and sid not in ids:
            ids.append(sid)
    return ids


def _augment_prompt_reuse_session(
    prompt: str, session_ids: list[str], *, after_timeout: bool = False,
) -> str:
    """Append a note telling the agent to use an existing Vivado MCP session
    instead of starting one.

    Two different situations need two different framings, and conflating them
    misinforms the agent:

    * ``after_timeout=True`` -- *this* case's previous attempt timed out and was
      killed, but the persistent MCP server kept its session alive. Reusing the
      ``session_id`` preserves the project/BD state that attempt built, so the
      retry continues instead of redoing device/IP discovery.
    * ``after_timeout=False`` (the default) -- the session came from the suite's
      ``setup:`` action or an earlier, *different* case in the same group. It is
      a shared, already-prepared session and nothing failed. Sending the retry
      wording here told the agent that "a previous attempt at this exact task
      timed out" on its very first attempt, and invited it to "continue from
      where the prior attempt left off" -- i.e. to go looking for a half-built
      cell belonging to another case.
    """
    sid = session_ids[-1]
    if after_timeout:
        return prompt + (
            "\n\n[HARNESS RETRY NOTICE] A previous attempt at this exact task "
            f"timed out and was terminated. The Vivado MCP session it created "
            f"({sid}) is still alive on the MCP server, with its project and "
            "block design intact. Resume that session: pass "
            f'session_id \"{sid}\" to vivado_execute / vivado_todos and '
            "continue from where the prior attempt left off. Do NOT start a "
            "new Vivado session with vivado_start unless "
            f'\"{sid}\" is no longer returned by vivado_list_sessions.\n'
        )
    return prompt + (
        "\n\n[HARNESS SESSION NOTICE] A prepared Vivado MCP session "
        f"({sid}) is already running on the MCP server for this test suite, "
        "with its project and block design open. It is shared by every task in "
        f'the suite. Use it: pass session_id \"{sid}\" to vivado_execute / '
        "vivado_todos. Do NOT start a new Vivado session with vivado_start "
        f'unless \"{sid}\" is no longer returned by vivado_list_sessions. '
        "Nothing has failed and no work on THIS task has been done yet -- do "
        "the task from the beginning, and leave the session open when done.\n"
    )
