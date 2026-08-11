"""
Regression test for the combo-level scheduling fix in integration_runner.py.

Before the fix, integration_runner.main() scheduled one Task per CASE under
the top-level Scheduler, and SkillRunner.run_case() fanned out a case's own
clients/reps concurrently via a second, private ThreadPoolExecutor -- fully
invisible to the Scheduler's --parallel cap and memory budget. A case with
N clients could run all N combos at once regardless of --parallel, so real
concurrency was parallel_cases * combos_per_case, not --parallel.

This test builds one case with 4 clients and runs it through the real
integration_runner.main() with --parallel 2 and a fake CLI backend that
records how many invocations are ever concurrently in flight. It asserts
peak concurrency never exceeds 2 -- i.e. --parallel now bounds real,
per-combo concurrency, not just case count.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest
import yaml

import skills_testing.cli_backends as cli_backends_pkg
from skills_testing.cli_backends.interface import SkillBackend
from skills_testing.core import db_writer
from skills_testing.core import integration_runner
from skills_testing.core.case_loader import CaseSpec
from skills_testing.core.runner import SkillRunner
from skills_testing.core.scheduler import Scheduler, Task
from skills_testing.runtime.cleanup_manager import default_cleanup_manager
from skills_testing.runtime.suite_lifecycle import build_group_registry


class _ConcurrencyTrackingCLI(SkillBackend):
    """Fake backend: records concurrent invoke() calls across ALL clients
    via shared, test-owned counters, and holds each invocation open for a
    short time so overlapping calls are actually observable."""

    def __init__(self, name, model, *, lock, state, hold_seconds=0.15):
        self.name = name
        self.model = model
        self._lock = lock
        self._state = state  # {"current": int, "peak": int}
        self._hold_seconds = hold_seconds

    def invoke(self, *, prompt, workspace_dir, timeout_seconds, env=None):
        with self._lock:
            self._state["current"] += 1
            self._state["peak"] = max(self._state["peak"], self._state["current"])
        time.sleep(self._hold_seconds)
        with self._lock:
            self._state["current"] -= 1
        return {
            "stdout": "DONE", "stderr": "", "exit_code": 0,
            "wall_clock_s": self._hold_seconds,
            "prompt_tokens": 1, "output_tokens": 1, "total_tokens": 2,
        }

    def detect_skill_invocation(self, stdout, stderr):
        return True, []

    def hide_skills_env_overrides(self):
        return None


def _write_multi_client_case(root: Path, n_clients: int) -> None:
    case_dir = root / "fake-skill" / "fake-case"
    case_dir.mkdir(parents=True)
    clients = [{"name": "claude_code", "model": f"m{i}"} for i in range(n_clients)]
    (case_dir / "manifest.yaml").write_text(yaml.safe_dump({
        "skill_name": "fake-skill",
        "skill_version": "1.0.0",
        "case_id": "fake-case",
        "description": "scheduling concurrency test",
        "invocation": {
            "clients": clients,
            "parameters": {},
            "timeout_seconds": 30,
            "prompt": "do the thing",
        },
        "requirements": {"vivado": False, "vitis": False,
                         "min_memory_gb": 1, "min_disk_gb": 0, "tags": []},
        "cleanup": ["working_dir"],
    }))
    (case_dir / "grading_spec.yaml").write_text(yaml.safe_dump({
        "graders": [
            {"id": "stdout_says_done", "type": "content_contains",
             "source": "stdout", "substring": "DONE"},
        ],
    }))
    (case_dir / "inputs").mkdir()
    (case_dir / "inputs" / "x.txt").write_text("x")


def test_parallel_bounds_real_combo_concurrency_not_case_count(tmp_path, monkeypatch):
    test_cases_root = tmp_path / "test_cases_root"
    _write_multi_client_case(test_cases_root, n_clients=4)

    lock = threading.Lock()
    state = {"current": 0, "peak": 0}

    def fake_get(client, model, config=None):
        return _ConcurrencyTrackingCLI(client, model, lock=lock, state=state)

    monkeypatch.setattr(cli_backends_pkg, "get", fake_get)

    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump({
        "skill_testing": {
            "test_cases_root": str(test_cases_root),
            "workspace_root": str(tmp_path / "workspace"),
        },
        "database": {"path": str(tmp_path / "results.db")},
    }))

    rc = integration_runner.main([
        "--config", str(cfg_path),
        "--parallel", "2",
        "--no-json-log",
        "--no-refresh-dashboard",
        "--no-skill-signoffs",
    ])

    assert rc == 0
    # The whole point of the fix: with 4 combos (one case, 4 clients) and
    # --parallel 2, at most 2 may ever be concurrently in flight. Before the
    # fix, run_case's own inner ThreadPoolExecutor ran all 4 at once,
    # invisible to the outer Scheduler -- this would have observed peak==4.
    assert state["peak"] <= 2, (
        f"expected --parallel=2 to bound concurrency, but saw "
        f"{state['peak']} simultaneous invocations")
    assert state["peak"] >= 1  # sanity: work actually ran


def test_case_level_progress_log_still_reports_all_combos(tmp_path, monkeypatch, caplog):
    """The per-case 'starting' / 'done in Xs -- client=STATUS, ...' log line
    is reconstructed across a case's now-independent combo tasks -- verify
    it still fires once, after ALL of a case's combos finish, listing every
    one of them."""
    test_cases_root = tmp_path / "test_cases_root"
    _write_multi_client_case(test_cases_root, n_clients=3)

    lock = threading.Lock()
    state = {"current": 0, "peak": 0}

    def fake_get(client, model, config=None):
        return _ConcurrencyTrackingCLI(client, model, lock=lock, state=state,
                                        hold_seconds=0.01)

    monkeypatch.setattr(cli_backends_pkg, "get", fake_get)

    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump({
        "skill_testing": {
            "test_cases_root": str(test_cases_root),
            "workspace_root": str(tmp_path / "workspace"),
        },
        "database": {"path": str(tmp_path / "results.db")},
    }))

    import logging
    from skills_testing.core.logging_config import configure_logging

    # Pin down the capture path so this test does not depend on where it lands
    # in the run order.
    #
    # configure_logging() sets propagate=False on the `skills_testing` logger
    # (deliberately -- it installs its own stderr handler and does not want
    # duplicate lines) and, being guarded by a module-level flag, only ever
    # runs once per process. pytest decides where to put its capture handler
    # when the test *starts*: on the root logger, plus on any logger that is
    # already non-propagating. One that becomes non-propagating later is
    # missed -- pytest's catching_logs() says so outright ("will miss loggers
    # that *become* non-propagating after the __enter__").
    #
    # main() calls configure_logging() below, so the flip's timing decided the
    # result: first test in the process -> flip lands mid-test, pytest never
    # attached to this logger, caplog.records empty. Later test -> pytest had
    # attached, records captured. Green in a full run, red alone.
    #
    # So: force the setup up front (making main()'s call a no-op), keep
    # propagation OFF, and attach caplog's own handler straight to the logger.
    # addHandler() ignores a handler it already holds, so this is exactly one
    # capture path whether or not pytest already attached the same object --
    # and with propagation off, the root handler cannot double-count it.
    # Re-enabling propagation instead does double-count, which is how the
    # first attempt at this fix broke the whole-file run.
    configure_logging()
    pkg_logger = logging.getLogger("skills_testing")
    pkg_logger.propagate = False
    pkg_logger.addHandler(caplog.handler)

    with caplog.at_level(logging.INFO, logger="skills_testing.core.integration_runner"):
        rc = integration_runner.main([
            "--config", str(cfg_path),
            "--parallel", "3",
            "--no-json-log",
            "--no-refresh-dashboard",
            "--no-skill-signoffs",
        ])
    assert rc == 0

    done_lines = [
        r.message for r in caplog.records
        if r.name == "skills_testing.core.integration_runner" and "done in" in r.message
    ]
    assert len(done_lines) == 1, f"expected exactly one aggregate line, got {done_lines}"
    line = done_lines[0]
    assert "fake-skill/fake-case" in line
    for i in range(3):
        assert f"claude_code/m{i}=PASS" in line


# ---------------------------------------------------------------------------
# Shared-workspace group serialization under combo-level scheduling
#
# The riskiest interaction with this fix: ip-configurator-style suites rely
# on GroupState.lock (suite_lifecycle.py) to serialize different CASES that
# share one (suite, client, model, with_skill, shard) workspace/Vivado
# session -- only one member may touch it at a time. Before this fix, cases
# were scheduled one-Task-per-case, so at most `parallel` cases (and hence
# at most `parallel` group members) ever raced for that lock at once. Now
# that scheduling happens at combo granularity, MORE independent Tasks can
# be simultaneously admitted by the Scheduler for cases belonging to the
# very same group. group.lock is supposed to make that safe regardless (see
# runner.py:_run_one) -- this test proves it actually is, by driving real
# concurrent Scheduler-submitted Tasks (not sequential run_case calls, which
# both existing test_runner.py group tests and this one's fix use).
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_group_db(tmp_path):
    conn = db_writer.init_db({"database": {"path": str(tmp_path / "results.db")}})
    try:
        yield conn
    finally:
        conn.close()


@dataclass
class _GroupFakeCLI(SkillBackend):
    # intervals/intervals_lock first (genuinely required, no default) --
    # name/model get explicit defaults below rather than bare annotations,
    # since SkillBackend already declares plain class attributes
    # name="" / model="": a bare `name: str` here would make dataclasses
    # silently inherit that "" as its default via getattr(cls, "name"),
    # which then makes any truly-required field declared after it error
    # out as "non-default argument follows default argument".
    intervals: list
    intervals_lock: threading.Lock
    name: str = ""
    model: str = ""
    hold_seconds: float = 0.05
    seen_prompts: list = field(default_factory=list)

    def invoke(self, *, prompt, workspace_dir, timeout_seconds, env=None):
        self.seen_prompts.append(prompt)
        start = time.monotonic()
        time.sleep(self.hold_seconds)
        end = time.monotonic()
        with self.intervals_lock:
            self.intervals.append((prompt, start, end))
        return {
            "stdout": "DONE", "stderr": "", "exit_code": 0,
            "wall_clock_s": self.hold_seconds,
            "prompt_tokens": 1, "output_tokens": 1, "total_tokens": 2,
        }

    def detect_skill_invocation(self, stdout, stderr):
        return True, []

    def hide_skills_env_overrides(self):
        return None


def _grouped_case(case_id: str, prompt: str, case_dir: Path, *, suite_id: str) -> CaseSpec:
    return CaseSpec(
        skill_name="ip-configurator", skill_version="1.0.0", case_id=case_id,
        case_dir=case_dir,
        invocation={"clients": [{"name": "claude_code", "model": "opus"}],
                    "timeout_seconds": 30, "prompt": prompt,
                    "external_inputs": []},
        requirements={"tags": ["smoke"]},
        cleanup=["working_dir"],
        grading=[{"id": "ok", "type": "content_contains",
                  "source": "stdout", "substring": ""}],
        suite_id=suite_id,
        setup_action={"kind": "prompt", "prompt": "START SETUP", "script": None,
                     "command": None, "timeout_seconds": 60},
        inputs_dir_is_set=True, inputs_dir_override=None,
    )


def _intervals_overlap(a, b):
    _, a_start, a_end = a
    _, b_start, b_end = b
    return a_start < b_end and b_start < a_end


def test_group_lock_still_serializes_members_under_real_scheduler_concurrency(
    tmp_group_db, tmp_path,
):
    tmp_db = tmp_group_db
    cases = [
        _grouped_case(f"case_{i}", f"CASE {i}", tmp_path, suite_id="grouped-suite")
        for i in range(4)
    ]
    group_registry = build_group_registry(cases)

    intervals: list = []
    intervals_lock = threading.Lock()
    fake = _GroupFakeCLI(name="claude_code", model="opus",
                         intervals=intervals, intervals_lock=intervals_lock)

    def factory(name, model):
        return fake  # same shared backend/session for every case, like a real group

    run_id = db_writer.create_run(tmp_db, suite="skill_test")
    runner = SkillRunner(
        cli_factory=factory,
        cleanup_manager=default_cleanup_manager(),
        host_caps={"free_memory_gb": 99, "free_disk_gb_tmp": 99},
        workspace_root=tmp_path / "ws",
        group_registry=group_registry,
    )

    # Exactly what integration_runner.py now does: one Task per combo,
    # submitted to ONE real Scheduler with enough parallel slots that all 4
    # cases COULD run at once if nothing serialized them.
    def _make_run(case):
        def _run():
            conn = db_writer.init_db({"database": {"path": str(tmp_path / "results.db")}})
            try:
                return runner.run_one(case, "claude_code", "opus", run_id=run_id,
                                       conn=conn, with_skill=True, replication_index=0)
            finally:
                conn.close()
        return _run

    tasks = [Task(name=case.case_id, run=_make_run(case)) for case in cases]

    sched = Scheduler(parallel=4, memory_budget_gb=99)
    results = sched.run_all(tasks)

    for r in results:
        assert r.error is None, f"{r.name}: {r.error}"
        assert r.value.status == "PASS", f"{r.name}: {r.value.status}"

    # The core claim: even though the Scheduler tried to run all 4 combo
    # Tasks at once, group.lock forced them to actually execute one at a
    # time -- no two invoke() calls (the shared setup action, plus each
    # case's own invocation -- 5 total) ever overlapped in wall-clock time.
    assert len(intervals) == 5
    for i in range(len(intervals)):
        for j in range(i + 1, len(intervals)):
            assert not _intervals_overlap(intervals[i], intervals[j]), (
                f"group members ran concurrently: {intervals[i]} vs {intervals[j]}")

    # Setup ran exactly once (shared across the whole group), not once per case.
    assert fake.seen_prompts.count("START SETUP") == 1
    assert fake.seen_prompts.count("CASE 0") == 1
    assert fake.seen_prompts.count("CASE 3") == 1
