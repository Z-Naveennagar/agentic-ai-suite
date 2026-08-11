#!/usr/bin/env python3
"""
Driver for the Agent Skill test suite (PR 10).

Discovers test_cases under skills_testing/test_cases/, gates them on host
capabilities, schedules them with resource awareness, runs each one through the runner with the requested repetitions, and writes
results into the shared results.db via db_writer.

This script is intentionally callable both from run_all_tests.py and as a
standalone tool:

    python3 test_skill_integration.py                    # smoke (one repetition)
    python3 test_skill_integration.py --reps 3           # consistency evaluation
    python3 test_skill_integration.py --capture-baseline # populate baselines
    python3 test_skill_integration.py --tags smoke

If no CLI backend can be constructed (none of the CLIs are wired into the
factory yet), every case is recorded as SKIPPED with skip_reason
'no_cli_backend' so the dashboard still has a row to render.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import yaml

from skills_testing.core import db_writer
from skills_testing.core import session_log
from skills_testing.core.session_log import SessionLogConfig
from skills_testing.core.baselines import make_baseline_lookup
from skills_testing.core.case_loader import discover_cases, filter_cases
from skills_testing.core.logging_config import configure_logging
from skills_testing.core.paths import PROJECT_ROOT, REPORTS_DIR, default_workspace_root, resolve_project_path
from skills_testing.runtime.cleanup_manager import default_cleanup_manager
from skills_testing.runtime.suite_lifecycle import build_group_registry
from skills_testing.core.lifecycle import (
    PolicyConfig,
    aggregate_consistency_metrics,
    assess_consistency,
    history_streaks,
    next_state,
)
from skills_testing.runtime.requirements_probe import probe_host
from skills_testing.core.runner import SkillRunner
from skills_testing.core.scheduler import Scheduler, Task

logger = logging.getLogger(__name__)


def _load_config(config_path: str | None = None) -> dict:
    from skills_testing.core.paths import DEFAULT_CONFIG
    cfg_path = Path(config_path) if config_path else DEFAULT_CONFIG
    with open(cfg_path) as f:
        return yaml.safe_load(f) or {}


def _build_cli_factory(config: dict | None = None):
    """Return a (client, model) -> SkillCLIBackend factory.

    Uses the concrete backends in skills_testing.cli_backends, which fall
    back to NullSkillCLI when a binary isn't installed -- the runner still
    records a row so the dashboard has data.
    """
    from skills_testing.cli_backends import get as get_skill_cli

    def factory(client: str, model: str):
        return get_skill_cli(client, model, config=config)

    return factory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agent Skill test runner")
    parser.add_argument("--config", type=str, default=None,
                        help="Override config.yaml path")
    parser.add_argument("--reps", type=int, default=None,
                        help="Repeated attempts per case/client/model (default: 1)")
    parser.add_argument("--skills", nargs="+", default=None,
                        help="Only run the listed skill names")
    parser.add_argument("--cases", nargs="+", default=None,
                        help="Only run the listed case ids")
    parser.add_argument("--suite-id", nargs="+", default=None,
                        help="Only run cases belonging to the listed suite ids "
                             "(runner_spec.yaml suite_id, e.g. "
                             "hls-burst-inference_33). Suite-layout cases only "
                             "-- legacy per-case cases have no suite_id and "
                             "never match")
    parser.add_argument("--tags", nargs="+", default=None,
                        help="Only run cases with at least one matching tag")
    parser.add_argument("--client", type=str, default=None,
                        help="Override the client for every matched case, for this "
                             "invocation only -- outranks both the suite's own declared "
                             "clients and skill_testing.coding_agents. Must be paired "
                             "with --model. (Validated against installed backends by "
                             "the customer_cli.py 'run' wrapper before this is reached.)")
    parser.add_argument("--model", type=str, default=None,
                        help="Model id for --client. Required when --client is given")
    parser.add_argument("--capture-baseline", action="store_true")
    parser.add_argument("--keep-tmp-on-failure", action="store_true")
    parser.add_argument("--workspace-root", type=str, default=None)
    parser.add_argument("--parallel", type=int, default=None,
                        help="Override skill_testing.parallel_default")
    parser.add_argument("--resume", type=str, default=None, metavar="RUN_ID",
                        help="Resume a previous run instead of starting a new "
                             "one: reuses RUN_ID (must already exist in "
                             "test_runs) and skips every (case, client, "
                             "model, repetition) combo that already has a row "
                             "in skill_test_results for it, so an "
                             "interrupted large run doesn't restart from scratch. "
                             "Pass the same --skills/--cases/--reps filters as "
                             "the original invocation.")
    parser.add_argument("--no-refresh-dashboard", action="store_true",
                        help="Skip regenerating reports/index.html after the "
                             "suite finishes (default is to refresh so the "
                             "browser only needs a hard reload).")
    parser.add_argument("--no-skill-signoffs", action="store_true",
                        help="Skip writing per-skill signoff snapshots to "
                             "skill_signoffs_root/<skill_name>/ after the suite "
                             "finishes (default is to write one, versioned "
                             "on repeat runs of the same skill).")
    parser.add_argument("--no-json-log", action="store_true",
                        help="Disable per-session JSON monitoring logs "
                             "(default: write logs/<run_id>/ capturing each "
                             "test's output, artifacts and correctness).")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="DEBUG-level logging (lock waits, per-grader "
                             "detail). Default is INFO: case start/end, "
                             "group setup/reset/teardown firing, and how "
                             "long each took. Also settable via "
                             "SKILL_TEST_LOG_LEVEL.")
    args = parser.parse_args(argv)
    if bool(args.client) != bool(args.model):
        parser.error("--client and --model must be given together")

    configure_logging(verbose=args.verbose)
    cfg = _load_config(args.config)
    skill_cfg = cfg.get("skill_testing", {}) or {}
    cli_clients = [{"name": args.client, "model": args.model}] if args.client else None
    workspace_root = Path(
        args.workspace_root or skill_cfg.get("workspace_root") or default_workspace_root()
    ).expanduser()
    parallel = args.parallel or int(skill_cfg.get("parallel_default", 2))
    # Vivado-session sharding (see build_group_registry) is opt-in, not
    # tied to parallel_default: it only activates when the user explicitly
    # passes --parallel. Falling back to parallel_default silently would
    # change a plain `skills-test run`'s behaviour for every
    # shared-workspace suite (e.g. ip-configurator going from 1 shared
    # session to parallel_default sessions) with no flag asked for it.
    # An explicit `--parallel 1` also means exactly 1 shard, same as before.
    shard_parallel = args.parallel if args.parallel else 1
    # Hard ceiling on concurrent live Vivado MCP sessions, server-wide --
    # shared-workspace suites (setup:/reset:/teardown:) shard their cases
    # across min(shard_parallel, this) concurrent sessions instead of
    # always one. Optional: None leaves sharding capped only by
    # shard_parallel itself.
    vivado_mcp_session_cap = skill_cfg.get("vivado_mcp_session_cap")
    # Ordinary runs remain cheap; repetitions are explicit consistency evidence.
    reps = int(args.reps) if args.reps else 1

    test_cases_root = resolve_project_path(skill_cfg.get("test_cases_root", "_workspace"))
    cases = discover_cases(test_cases_root, config=cfg, cli_clients=cli_clients)
    cases = filter_cases(
        cases,
        allowlist=list(skill_cfg.get("allowlist") or []),
        denylist=list(skill_cfg.get("denylist") or []),
        tag_filter=args.tags,
    )
    if args.skills:
        wanted_skills = set(args.skills)
        cases = [c for c in cases if c.skill_name in wanted_skills]
    if args.cases:
        wanted_cases = set(args.cases)
        cases = [c for c in cases if c.case_id in wanted_cases]
    if args.suite_id:
        wanted_suites = set(args.suite_id)
        cases = [c for c in cases if getattr(c, "suite_id", None) in wanted_suites]
    if not cases:
        print("No skill test cases matched filters; nothing to do.")
        return 0
    skill_names_in_run = sorted({c.skill_name for c in cases})

    host_caps = probe_host(workspace_root=str(workspace_root))
    print(f"Host: vivado={host_caps['vivado']} vitis={host_caps['vitis']} "
          f"free_mem={host_caps['free_memory_gb']} GB "
          f"free_disk={host_caps['free_disk_gb_workspace']} GB on "
          f"{host_caps['workspace_root']}")
    print(f"Discovered {len(cases)} skill cases under {test_cases_root}")
    master_clients = skill_cfg.get("coding_agents")
    if master_clients:
        names = ", ".join(f"{e['name']}({e['model']})" for e in master_clients)
        print(f"Master override: skill_testing.coding_agents replacing clients "
              f"for all {len(cases)} case(s) -> {names}")
    if cli_clients:
        print(f"CLI override: --client/--model replacing clients for all "
              f"{len(cases)} case(s) -> {args.client}({args.model})")

    # Per-session JSON monitoring logs (always on unless --no-json-log).
    session_log_config = SessionLogConfig.from_config(cfg)
    if args.no_json_log:
        session_log_config.enabled = False

    conn = db_writer.init_db(cfg)
    from datetime import datetime, timezone
    started_at = datetime.now(timezone.utc).isoformat()
    completed_combos: set[tuple[str, str, str, bool, int]] = set()
    if args.resume:
        if not db_writer.run_exists(conn, args.resume):
            print(f"ERROR: --resume {args.resume!r} not found in test_runs "
                  f"-- nothing to resume.")
            return 1
        run_id = args.resume
        completed_combos = db_writer.completed_skill_test_combos(conn, run_id)
        print(f"Resuming run {run_id}: {len(completed_combos)} combo(s) "
              f"already completed, skipping those.")
    else:
        run_id = db_writer.create_run(conn, suite="skill_test",
                                      cli_backend="multi")
        print(f"Run id: {run_id}")
    if session_log_config.enabled:
        print(f"Session logs: {session_log.session_dir(run_id, conn, session_log_config)}")

    def _skip_predicate(case_id: str, client: str, model: str,
                        with_skill: bool, replication_index: int) -> bool:
        return (case_id, client, model, with_skill, replication_index) in completed_combos

    # Resolve to the same absolute path init_db() used, so worker-thread
    # connections and the dashboard refresh hit the schema-initialised DB
    # rather than a fresh empty file in the current working directory.
    db_path = str(db_writer._get_db_path(cfg))

    def _open_thread_conn():
        import sqlite3
        return sqlite3.connect(db_path, check_same_thread=False)

    # Skills come from the testing repo's local `.claude/skills/` tree
    # (not the user's home), so checked-in skill bodies are the single
    # source of truth for the test harness.
    skills_root = resolve_project_path(
        skill_cfg.get("skills_root", PROJECT_ROOT / ".claude" / "skills")
    )
    if not skills_root.exists():
        print(f"WARNING: skills_root {skills_root} does not exist; "
              f"falling back to per-CLI auto-discovery (~/.claude/skills/)")
        skills_root = None
    else:
        # `skills_root` above is only the *configured* source -- opencode
        # cases actually stage from the sibling `.opencode/skills` (see
        # cli_backends.resolve_skills_root_for_client). Printing the bare
        # configured root here was misleading for every opencode run: the
        # log said `.claude/skills` while the workspace was staged from
        # `.opencode/skills`. Resolve and print the real root per client
        # actually present in this run instead.
        from ..cli_backends import resolve_skills_root_for_client
        clients_in_run = sorted({
            entry["name"]
            for c in cases
            for entry in (c.invocation.get("clients") or [])
        })
        resolved_roots = {
            client: resolve_skills_root_for_client(skills_root, client)
            for client in clients_in_run
        }
        distinct_roots = set(resolved_roots.values())
        if len(distinct_roots) <= 1:
            resolved = next(iter(distinct_roots), skills_root)
            print(f"Skills root: {resolved}")
        else:
            for client, resolved in sorted(resolved_roots.items()):
                print(f"Skills root ({client}): {resolved}")

    # Build the llm_judge grader's caller from the same judge config the
    # frontier Answer Quality judge uses. None when no judge is configured,
    # in which case any `llm_judge` grader reports "no llm_caller".
    from ..graders.judge import make_llm_caller
    llm_caller = make_llm_caller(cfg)

    # Shared-workspace grouping for suites that declare a setup:/reset:/teardown:
    # action in runner_spec.yaml (e.g. ip-configurator's shared Vivado BD
    # session): grouped by (suite, client, model), sized once up front so
    # the group's last member reliably runs teardown regardless of
    # scheduling order. Suites with no such action are untouched -- see
    # runtime/suite_lifecycle.py. An explicit --parallel also sizes how
    # many shards (concurrent Vivado sessions) each combo gets, capped by
    # vivado_mcp_session_cap -- see build_group_registry's docstring.
    group_registry = build_group_registry(
        cases, repetitions=reps,
        parallel=shard_parallel, session_cap=vivado_mcp_session_cap,
    )
    group_sizes = group_registry.sizes()
    if group_sizes:
        for (suite, client, model, shard_idx), remaining in sorted(group_sizes.items()):
            logger.info(
                "shared-workspace group %s/%s/%s shard %d: %d member(s) expected",
                suite, client, model, shard_idx, remaining,
            )
    else:
        logger.debug("no shared-workspace groups for this run "
                     "(no suite declares setup:/reset:/teardown:)")

    runner_factory = lambda c: SkillRunner(
        cli_factory=_build_cli_factory(config=cfg),
        cleanup_manager=default_cleanup_manager(),
        host_caps=host_caps,
        workspace_root=workspace_root,
        baseline_lookup=make_baseline_lookup(c),
        llm_caller=llm_caller,
        keep_tmp_on_failure=args.keep_tmp_on_failure,
        capture_baseline=args.capture_baseline,
        skills_root=skills_root,
        session_log_config=session_log_config,
        mcp_server_aliases=(cfg.get("grading") or {}).get("mcp_server_aliases"),
        group_registry=group_registry,
        pre_invoke_memory_headroom_gb=float(
            skill_cfg.get("pre_invoke_memory_headroom_gb", 0.0)),
    )

    # Schedule one Task per (case, client, model, repetition) combo --
    # not one Task per case. A case's clients/repetitions used to fan out via
    # a private ThreadPoolExecutor inside runner.py,
    # invisible to this Scheduler's --parallel cap and memory budget: e.g.
    # --parallel 8 with 3 clients/case could actually run up to 24 agent
    # invocations at once. Building the task list at combo granularity here
    # means every individual agent invocation is admitted (and memory
    # accounted) by the same Scheduler, so --parallel bounds real
    # concurrency, not just case count.
    #
    # Per-case "starting"/"done in Xs -- client=STATUS, ..." logging is
    # still useful (it's the line this codebase's own diagnosis has leaned
    # on throughout), so it's reconstructed here across a case's now-
    # independent combo tasks: case_started/case_outcomes/case_lock track
    # when a case's first combo begins and log the aggregate once its last
    # combo (by count) finishes.
    import threading
    case_lock = threading.Lock()
    case_combo_total: dict[str, int] = {}
    case_started: dict[str, float] = {}
    case_outcomes: dict[str, list] = {}

    def _make_combo_task(case, entry, rep):
        client, model = entry["name"], entry["model"]
        case_name = f"{case.skill_name}/{case.case_id}"
        task_name = "/".join((case_name, client, model, f"rep{rep}"))

        def _run():
            with case_lock:
                if case.case_id not in case_started:
                    case_started[case.case_id] = time.monotonic()
                    logger.info("case %s: starting", case_name)
            tc = _open_thread_conn()
            try:
                runner = runner_factory(tc)
                outcome = runner.run_one(
                    case, client, model, run_id=run_id, conn=tc,
                    with_skill=True, replication_index=rep,
                )
            finally:
                tc.close()
            with case_lock:
                bucket = case_outcomes.setdefault(case.case_id, [])
                bucket.append(outcome)
                if len(bucket) >= case_combo_total[case.case_id]:
                    elapsed = time.monotonic() - case_started[case.case_id]
                    statuses = ", ".join(
                        f"{o.client}/{o.model}={o.status}" for o in bucket)
                    logger.info("case %s: done in %.1fs -- %s",
                               case_name, elapsed, statuses)
            return outcome
        mem = float((case.requirements or {}).get("min_memory_gb", 1.0))
        return Task(name=task_name, run=_run, estimated_memory_gb=mem)

    sched_tasks: list[Task] = []
    for case in cases:
        clients = case.invocation.get("clients", [])
        combos = [
            (entry, rep)
            for entry in clients
            for rep in range(int(reps))
            if not _skip_predicate(case.case_id, entry["name"], entry["model"], True, rep)
        ]
        case_combo_total[case.case_id] = len(combos)
        if not combos:
            logger.debug("case %s/%s: no combos (all skipped by --resume)",
                        case.skill_name, case.case_id)
            continue
        for entry, rep in combos:
            sched_tasks.append(_make_combo_task(case, entry, rep))

    sched = Scheduler(parallel=parallel,
                      memory_budget_gb=max(host_caps["free_memory_gb"], 2.0))
    results = sched.run_all(sched_tasks)

    # Summary
    n_pass = n_fail = n_skip = n_err = 0
    for tr in results:
        if tr.error:
            n_err += 1
            print(f"  [ERROR] {tr.name}: {tr.error}")
            continue
        o = tr.value
        if o is None:
            continue
        n_pass += (o.status == "PASS")
        n_fail += (o.status == "FAIL")
        n_skip += (o.status == "SKIPPED")
        n_err += (o.status == "ERROR")
    print(f"Skill suite done: PASS={n_pass} FAIL={n_fail} SKIP={n_skip} ERR={n_err}")

    # Per-session JSON summary: covers every row (PASS/FAIL/SKIPPED/ERROR)
    # and links each executed test to its forensic log file. Wrapped so a
    # logging failure never masks the suite exit status.
    if session_log_config.enabled:
        try:
            path = session_log.write_session_summary(
                run_id, conn, cfg=session_log_config,
                suite="skill_test", started_at=started_at)
            if path:
                print(f"Session summary: {path}")
        except Exception as exc:
            print(f"WARNING: session summary write failed: {exc}")

    # Every run writes an idempotent consistency lifecycle snapshot. One-rep
    # smoke runs remain UNASSESSED when they do not meet the evidence policy.
    _write_lifecycle(conn, skill_cfg, run_id=run_id, expected_reps=reps)

    # Refresh the static dashboard so the user can just hit Refresh in
    # their browser. Failure here must NOT mask the suite's exit status,
    # so we wrap it defensively.
    if not args.no_refresh_dashboard:
        _refresh_dashboard(db_path)
    if not args.no_skill_signoffs:
        _write_skill_signoffs(db_path, run_id, skill_names_in_run, skill_cfg)

    return 0 if n_err == 0 else 1


def _refresh_dashboard(db_path: str) -> None:
    """Regenerate ``reports/index.html`` from the live results.db."""
    try:
        from skills_testing.reporting import generate_report

        report_dir = REPORTS_DIR
        report_dir.mkdir(parents=True, exist_ok=True)
        out = report_dir / "index.html"
        html = generate_report.generate_html(db_path)
        out.write_text(html)
        print(f"Dashboard refreshed: {out} ({len(html):,} bytes)")
    except Exception as exc:
        print(f"WARNING: dashboard refresh failed: {exc}")


def _write_skill_signoffs(db_path: str, run_id: str, skill_names: list[str], skill_cfg: dict) -> None:
    """Write per-skill signoff snapshots to skill_signoffs_root/<skill_name>/.
    Failure here must NOT mask the suite's exit status, so it's wrapped
    defensively, same as ``_refresh_dashboard``."""
    try:
        from skills_testing.reporting.skill_signoffs import write_skill_signoffs

        # ``eval_output_root`` is accepted only as a migration fallback for
        # existing local configs. New configs and all generated packages use
        # the explicit staging-to-production review name.
        configured_root = skill_cfg.get("skill_signoffs_root")
        if configured_root is None:
            configured_root = skill_cfg.get("eval_output_root", "../skill-signoffs")
        skill_signoffs_root = resolve_project_path(configured_root)
        claude_skills_dir = PROJECT_ROOT / ".claude" / "skills"
        log = write_skill_signoffs(
            db_path, run_id, skill_names,
            skill_signoffs_root=skill_signoffs_root, claude_skills_dir=claude_skills_dir,
        )
        for line in log:
            print(f"Skill signoff: {line} -> {skill_signoffs_root}")
    except Exception as exc:
        print(f"WARNING: skill-signoffs snapshot failed: {exc}")


def _write_lifecycle(
    conn, skill_cfg: dict, *, run_id: str, expected_reps: int
) -> None:
    """Write one consistency snapshot per skill/client/model in *run_id*."""
    policy = skill_cfg.get("consistency_lifecycle") or {}
    cfg = PolicyConfig(**{
        name: policy.get(name, field.default)
        for name, field in PolicyConfig.__dataclass_fields__.items()
    })
    cells = conn.execute("""
        SELECT skill_name, skill_version, client, model
          FROM skill_test_results
         WHERE run_id=? AND with_skill=1
         GROUP BY skill_name, skill_version, client, model
    """, (run_id,)).fetchall()
    for skill, version, client, model in cells:
        result_rows = conn.execute("""
            SELECT id, case_id, replication_index, status, aggregate_score
              FROM skill_test_results
             WHERE run_id=? AND skill_name=? AND skill_version=?
               AND client=? AND model=? AND with_skill=1
        """, (run_id, skill, version, client, model)).fetchall()
        test_ids = [row[0] for row in result_rows]
        grader_rows = []
        if test_ids:
            marks = ",".join("?" for _ in test_ids)
            grader_rows = conn.execute(f"""
                SELECT passed, mandatory, weight, category
                  FROM skill_grader_results
                 WHERE skill_test_id IN ({marks})
            """, test_ids).fetchall()
        metrics = aggregate_consistency_metrics(
            [dict(zip(("id", "case_id", "replication_index", "status",
                       "aggregate_score"), row)) for row in result_rows],
            [dict(zip(("passed", "mandatory", "weight", "category"), row))
             for row in grader_rows],
            expected_reps=expected_reps,
        )
        sufficient, passed, failures = assess_consistency(metrics, cfg)
        history = conn.execute("""
            SELECT assessment_sufficient, consistency_passed, lifecycle_state
              FROM skill_lifecycle_evaluations
             WHERE skill_name=? AND skill_version=? AND client=? AND model=?
               AND run_id != ?
             ORDER BY evaluated_at
        """, (skill, version, client, model, run_id)).fetchall()
        history = [dict(zip(("assessment_sufficient", "consistency_passed",
                             "lifecycle_state"), row)) for row in history]
        prior_state = history[-1]["lifecycle_state"] if history else None
        fail_streak, deprecate_streak = history_streaks(history)
        state, reason = next_state(
            prior_state=prior_state,
            assessment_sufficient=sufficient,
            consistency_passed=passed,
            consecutive_failures=fail_streak + int(sufficient and not passed),
            releases_in_deprecate=deprecate_streak,
            cfg=cfg,
        )
        if failures:
            reason += ": " + "; ".join(failures)
        db_writer.upsert_skill_lifecycle_evaluation(conn, {
            "run_id": run_id, "skill_name": skill,
            "skill_version": version, "client": client, "model": model,
            "assessment_sufficient": sufficient,
            "consistency_passed": sufficient and passed,
            "lifecycle_state": state, "prior_state": prior_state,
            "transition_reason": reason,
            "n_cases": metrics["n_cases"], "n_reps": metrics["n_reps"],
            "n_results": metrics["n_results"],
            "coverage_rate": metrics["coverage_rate"],
            "pass_rate": metrics["pass_rate"],
            "fail_rate": metrics["n_fail"] / metrics["n_results"] if metrics["n_results"] else 0.0,
            "error_rate": metrics["error_rate"], "skip_rate": metrics["skip_rate"],
            "failed_case_rate": metrics["failed_case_rate"],
            "aggregate_score_mean": metrics["aggregate_score_mean"],
            "aggregate_score_stdev": metrics["max_case_score_stddev"],
            "flaky_case_rate": metrics["flaky_case_rate"],
            "variable_case_rate": metrics["variable_case_rate"],
            "mandatory_grader_total": metrics["mandatory_grader_total"],
            "mandatory_grader_fail_rate": metrics["mandatory_grader_fail_rate"],
            "weighted_grader_total": metrics["weighted_grader_total"],
            "weighted_grader_fail_rate": metrics["weighted_grader_fail_rate"],
            "diagnostic_grader_total": metrics["diagnostic_grader_total"],
            "diagnostic_grader_fail_rate": metrics["diagnostic_grader_fail_rate"],
        })


if __name__ == "__main__":
    sys.exit(main())
