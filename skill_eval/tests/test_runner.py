"""
Tests for the skill-test runner (single-arm; A/B added in PR 6).

Contract:
    SkillRunner(
        cli_factory: Callable[[client_name, model], CLIBackend],
        cleanup_manager: CleanupManager,
        host_caps: dict,
        workspace_root: Path,
    )
    .run_case(case: CaseSpec, run_id: str, conn) -> list[int]   # ids written

The runner uses the injected cli_factory so we never spawn a real
subprocess in unit tests. CLI backends in tests are FakeCLI instances
that pre-canned stdout/stderr and side-effect (e.g. write outputs/lint.rpt).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yaml

from skills_testing.core import db_writer
from skills_testing.core.case_loader import CaseSpec, load_case
from skills_testing.runtime.cleanup_manager import default_cleanup_manager
from skills_testing.runtime.suite_lifecycle import build_group_registry
from skills_testing.core.runner import RunOutcome, SkillRunner
from skills_testing.cli_backends.interface import SkillBackend
from skills_testing.graders import GraderContext


# -- fake CLI backend ----------------------------------------------------


@dataclass
class FakeCLI(SkillBackend):
    name: str
    model: str
    stdout: str = ""
    stderr: str = ""
    side_effect: Any = None  # callable(workspace_dir) -> None
    exit_code: int = 0
    prompt_tokens: int = 1000
    output_tokens: int = 500
    skill_invoked: bool = True
    invoked_skills: list[str] = field(default_factory=list)
    seen_prompts: list[str] = field(default_factory=list)

    def invoke(self, *, prompt, workspace_dir, timeout_seconds, env=None):
        self.seen_prompts.append(prompt)
        if self.side_effect is not None:
            self.side_effect(workspace_dir)
        return {
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "wall_clock_s": 0.01,
            "prompt_tokens": self.prompt_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.prompt_tokens + self.output_tokens,
        }

    def detect_skill_invocation(self, stdout: str, stderr: str):
        return self.skill_invoked, list(self.invoked_skills)

    def hide_skills_env_overrides(self):
        return None


# -- a complete on-disk case --------------------------------------------


def _write_case(tmp_path: Path) -> Path:
    case_dir = tmp_path / "rtl-assistant" / "rtl-lint"
    case_dir.mkdir(parents=True)
    (case_dir / "manifest.yaml").write_text(yaml.safe_dump({
        "skill_name": "rtl-assistant",
        "skill_version": "1.0.0",
        "case_id": "rtl-lint",
        "description": "lint",
        "invocation": {
            "clients": [{"name": "claude_code", "model": "opus"}],
            "parameters": {},
            "timeout_seconds": 30,
            "prompt": "lint please",
        },
        "requirements": {"vivado": False, "vitis": False,
                         "min_memory_gb": 1, "min_disk_gb": 1, "tags": ["smoke"]},
        "cleanup": ["working_dir"],
    }))
    (case_dir / "grading_spec.yaml").write_text(yaml.safe_dump({
        "graders": [
            {"id": "lint_report_exists", "type": "artifact_exists",
             "path": "outputs/lint.rpt"},
            {"id": "stdout_says_done", "type": "content_contains",
             "source": "stdout", "substring": "DONE"},
        ],
    }))
    (case_dir / "inputs").mkdir()
    (case_dir / "inputs" / "top.sv").write_text("module top; endmodule")
    return case_dir


# -- tests ---------------------------------------------------------------


def test_runner_records_pass(tmp_db, tmp_path):
    case = load_case(_write_case(tmp_path))

    def good(ws):
        (ws / "outputs").mkdir()
        (ws / "outputs" / "lint.rpt").write_text("found 0 issues")

    def factory(name, model):
        return FakeCLI(name=name, model=model, stdout="DONE", side_effect=good)

    run_id = db_writer.create_run(tmp_db, suite="skill_test", cli_backend="claude_code")
    runner = SkillRunner(
        cli_factory=factory,
        cleanup_manager=default_cleanup_manager(),
        host_caps={"vivado": True, "vitis": True, "free_memory_gb": 99,
                   "free_disk_gb_tmp": 99},
        workspace_root=tmp_path / "ws",
    )
    outcomes = runner.run_case(case, run_id=run_id, conn=tmp_db)
    assert len(outcomes) == 1
    o = outcomes[0]
    assert isinstance(o, RunOutcome)
    assert o.status == "PASS"
    assert o.aggregate_score == pytest.approx(1.0)

    row = tmp_db.execute(
        "SELECT status, t2_score, aggregate_score, skill_invoked "
        "FROM skill_test_results WHERE id = ?",
        (o.skill_test_id,),
    ).fetchone()
    assert row[0] == "PASS"
    assert row[1] == pytest.approx(1.0)
    assert row[2] == pytest.approx(1.0)
    assert row[3] == 1

    # one grader row per spec
    n = tmp_db.execute(
        "SELECT COUNT(*) FROM skill_grader_results WHERE skill_test_id = ?",
        (o.skill_test_id,),
    ).fetchone()[0]
    assert n == 2


def test_run_case_honours_reps_per_arm_without_ab(tmp_db, tmp_path):
    # The non-A/B path now runs each (case, client) reps_per_arm times, with
    # distinct replication_index values, so consistency-across-iterations
    # views have >1 rep even for with-skill-only runs.
    case = load_case(_write_case(tmp_path))

    def good(ws):
        (ws / "outputs").mkdir()
        (ws / "outputs" / "lint.rpt").write_text("found 0 issues")

    def factory(name, model):
        return FakeCLI(name=name, model=model, stdout="DONE", side_effect=good)

    run_id = db_writer.create_run(tmp_db, suite="skill_test", cli_backend="claude_code")
    runner = SkillRunner(
        cli_factory=factory,
        cleanup_manager=default_cleanup_manager(),
        host_caps={"vivado": True, "vitis": True, "free_memory_gb": 99,
                   "free_disk_gb_tmp": 99},
        workspace_root=tmp_path / "ws",
    )
    outcomes = runner.run_case(case, run_id=run_id, conn=tmp_db, reps_per_arm=3)
    assert len(outcomes) == 3
    reps = sorted(
        tmp_db.execute(
            "SELECT replication_index FROM skill_test_results "
            "WHERE run_id = ?", (run_id,)
        ).fetchall())
    assert [r[0] for r in reps] == [0, 1, 2]
    # default (no reps_per_arm) stays single-rep.
    run_id2 = db_writer.create_run(tmp_db, suite="skill_test", cli_backend="claude_code")
    assert len(runner.run_case(case, run_id=run_id2, conn=tmp_db)) == 1


def test_runner_records_fail_when_artifact_missing(tmp_db, tmp_path):
    case = load_case(_write_case(tmp_path))

    def factory(name, model):
        return FakeCLI(name=name, model=model, stdout="DONE")

    run_id = db_writer.create_run(tmp_db, suite="skill_test")
    runner = SkillRunner(
        cli_factory=factory,
        cleanup_manager=default_cleanup_manager(),
        host_caps={"free_memory_gb": 99, "free_disk_gb_tmp": 99},
        workspace_root=tmp_path / "ws",
    )
    outcomes = runner.run_case(case, run_id=run_id, conn=tmp_db)
    assert outcomes[0].status == "FAIL"
    grader_rows = tmp_db.execute(
        "SELECT grader_id, passed FROM skill_grader_results "
        "WHERE skill_test_id = ?",
        (outcomes[0].skill_test_id,),
    ).fetchall()
    by_id = dict(grader_rows)
    assert by_id["lint_report_exists"] == 0
    assert by_id["stdout_says_done"] == 1


def test_runner_skips_when_requirements_unmet(tmp_db, tmp_path):
    """Vivado is required but unavailable on host -> SKIPPED, no graders run."""
    case_dir = _write_case(tmp_path)
    # mutate manifest to require vivado
    m = yaml.safe_load((case_dir / "manifest.yaml").read_text())
    m["requirements"]["vivado"] = True
    (case_dir / "manifest.yaml").write_text(yaml.safe_dump(m))
    case = load_case(case_dir)

    cli_calls = {"n": 0}

    def factory(name, model):
        cli_calls["n"] += 1
        return FakeCLI(name=name, model=model)

    run_id = db_writer.create_run(tmp_db, suite="skill_test")
    runner = SkillRunner(
        cli_factory=factory,
        cleanup_manager=default_cleanup_manager(),
        host_caps={"vivado": False, "free_memory_gb": 99, "free_disk_gb_tmp": 99},
        workspace_root=tmp_path / "ws",
    )
    outcomes = runner.run_case(case, run_id=run_id, conn=tmp_db)
    assert outcomes[0].status == "SKIPPED"
    assert "vivado" in outcomes[0].skip_reason
    assert cli_calls["n"] == 0


def test_runner_runs_all_clients(tmp_db, tmp_path):
    """A case with 3 (client,model) entries -> 3 runs."""
    case_dir = _write_case(tmp_path)
    m = yaml.safe_load((case_dir / "manifest.yaml").read_text())
    m["invocation"]["clients"] = [
        {"name": "claude_code", "model": "opus"},
        {"name": "cursor",      "model": "claude-4.6-sonnet-medium-thinking"},
        {"name": "copilot",     "model": "gpt-5.2-codex"},
    ]
    (case_dir / "manifest.yaml").write_text(yaml.safe_dump(m))
    case = load_case(case_dir)

    def good(ws):
        (ws / "outputs").mkdir(exist_ok=True)
        (ws / "outputs" / "lint.rpt").write_text("ok")

    def factory(name, model):
        return FakeCLI(name=name, model=model, stdout="DONE", side_effect=good)

    run_id = db_writer.create_run(tmp_db, suite="skill_test")
    runner = SkillRunner(
        cli_factory=factory,
        cleanup_manager=default_cleanup_manager(),
        host_caps={"free_memory_gb": 99, "free_disk_gb_tmp": 99},
        workspace_root=tmp_path / "ws",
    )
    outcomes = runner.run_case(case, run_id=run_id, conn=tmp_db)
    clients = sorted(o.client for o in outcomes)
    assert clients == ["claude_code", "copilot", "cursor"]
    assert all(o.status == "PASS" for o in outcomes)


def test_runner_run_case_skip_predicate_resumes_only_incomplete_clients(tmp_db, tmp_path):
    """--resume support on the single-arm (non --ab) path: a (case, client,
    model, with_skill, rep) combo the skip_predicate reports as already
    completed must not be re-run."""
    case_dir = _write_case(tmp_path)
    m = yaml.safe_load((case_dir / "manifest.yaml").read_text())
    m["invocation"]["clients"] = [
        {"name": "claude_code", "model": "opus"},
        {"name": "cursor",      "model": "claude-4.6-sonnet-medium-thinking"},
        {"name": "copilot",     "model": "gpt-5.2-codex"},
    ]
    (case_dir / "manifest.yaml").write_text(yaml.safe_dump(m))
    case = load_case(case_dir)

    def good(ws):
        (ws / "outputs").mkdir(exist_ok=True)
        (ws / "outputs" / "lint.rpt").write_text("ok")

    def factory(name, model):
        return FakeCLI(name=name, model=model, stdout="DONE", side_effect=good)

    run_id = db_writer.create_run(tmp_db, suite="skill_test")
    runner = SkillRunner(
        cli_factory=factory,
        cleanup_manager=default_cleanup_manager(),
        host_caps={"free_memory_gb": 99, "free_disk_gb_tmp": 99},
        workspace_root=tmp_path / "ws",
    )
    already_done = {("rtl-lint", "cursor", "claude-4.6-sonnet-medium-thinking", True, 0)}
    outcomes = runner.run_case(
        case, run_id=run_id, conn=tmp_db,
        skip_predicate=lambda cid, cl, mo, ws, ri: (cid, cl, mo, ws, ri) in already_done,
    )
    clients = sorted(o.client for o in outcomes)
    assert clients == ["claude_code", "copilot"]


def test_runner_cleans_up_workspace_by_default(tmp_db, tmp_path):
    case = load_case(_write_case(tmp_path))

    captured: dict = {}

    def good(ws):
        captured["ws"] = ws
        (ws / "outputs").mkdir()
        (ws / "outputs" / "lint.rpt").write_text("ok")

    def factory(name, model):
        return FakeCLI(name=name, model=model, stdout="DONE", side_effect=good)

    run_id = db_writer.create_run(tmp_db, suite="skill_test")
    runner = SkillRunner(
        cli_factory=factory,
        cleanup_manager=default_cleanup_manager(),
        host_caps={"free_memory_gb": 99, "free_disk_gb_tmp": 99},
        workspace_root=tmp_path / "ws",
    )
    runner.run_case(case, run_id=run_id, conn=tmp_db)
    assert "ws" in captured
    assert not captured["ws"].exists()  # working_dir cleanup ran


# -- shared-workspace suite groups (setup:/teardown: actions) ------------


def _grouped_case(case_id: str, prompt: str, case_dir: Path, *,
                   suite_id: str = "grouped-suite",
                   setup_action: dict | None = None,
                   teardown_action: dict | None = None,
                   reset_action: dict | None = None,
                   setup_action_without_skill: dict | None = None,
                   teardown_action_without_skill: dict | None = None,
                   reset_action_without_skill: dict | None = None) -> CaseSpec:
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
        setup_action=setup_action,
        teardown_action=teardown_action,
        reset_action=reset_action,
        setup_action_without_skill=setup_action_without_skill,
        teardown_action_without_skill=teardown_action_without_skill,
        reset_action_without_skill=reset_action_without_skill,
        inputs_dir_is_set=True, inputs_dir_override=None,
    )


_PROMPT_SETUP = {"kind": "prompt", "prompt": "START SETUP", "script": None,
                 "command": None, "timeout_seconds": 60}


def test_runner_group_shares_workspace_setup_once_and_defers_teardown(tmp_db, tmp_path):
    case1 = _grouped_case("case_1", "CASE ONE", tmp_path, setup_action=_PROMPT_SETUP)
    case2 = _grouped_case("case_2", "CASE TWO", tmp_path, setup_action=_PROMPT_SETUP)

    fakes: dict[tuple, FakeCLI] = {}
    seen_ws: list[Path] = []

    def factory(name, model):
        fake = fakes.get((name, model))
        if fake is None:
            fake = FakeCLI(name=name, model=model, stdout="DONE",
                            side_effect=seen_ws.append)
            fakes[(name, model)] = fake
        return fake

    group_registry = build_group_registry([case1, case2])
    run_id = db_writer.create_run(tmp_db, suite="skill_test")
    runner = SkillRunner(
        cli_factory=factory,
        cleanup_manager=default_cleanup_manager(),
        host_caps={"free_memory_gb": 99, "free_disk_gb_tmp": 99},
        workspace_root=tmp_path / "ws",
        group_registry=group_registry,
    )

    o1 = runner.run_case(case1, run_id=run_id, conn=tmp_db)[0]
    assert o1.status == "PASS"
    # setup ran once, before case_1's own prompt -- and case_1 didn't get
    # its own fresh workspace, it reused the one setup just populated.
    fake = fakes[("claude_code", "opus")]
    assert fake.seen_prompts == ["START SETUP", "CASE ONE"]
    assert len(seen_ws) == 2 and seen_ws[0] == seen_ws[1]
    ws_dir = seen_ws[0]
    assert ws_dir.exists()  # deferred -- case_2 hasn't run yet

    o2 = runner.run_case(case2, run_id=run_id, conn=tmp_db)[0]
    assert o2.status == "PASS"
    # setup does NOT run again for case_2
    assert fake.seen_prompts == ["START SETUP", "CASE ONE", "CASE TWO"]
    assert seen_ws[2] == ws_dir
    assert not ws_dir.exists()  # last member's turn -- deferred cleanup ran


def test_runner_group_setup_failure_marks_every_member_error_and_still_tears_down(
    tmp_db, tmp_path,
):
    case1 = _grouped_case("case_1", "CASE ONE", tmp_path,
                          suite_id="grouped-suite-fail", setup_action=_PROMPT_SETUP)
    case2 = _grouped_case("case_2", "CASE TWO", tmp_path,
                          suite_id="grouped-suite-fail", setup_action=_PROMPT_SETUP)

    def factory(name, model):
        return FakeCLI(name=name, model=model, stdout="", stderr="boom", exit_code=1)

    group_registry = build_group_registry([case1, case2])
    run_id = db_writer.create_run(tmp_db, suite="skill_test")
    runner = SkillRunner(
        cli_factory=factory,
        cleanup_manager=default_cleanup_manager(),
        host_caps={"free_memory_gb": 99, "free_disk_gb_tmp": 99},
        workspace_root=tmp_path / "ws",
        group_registry=group_registry,
    )

    o1 = runner.run_case(case1, run_id=run_id, conn=tmp_db)[0]
    assert o1.status == "ERROR"
    assert "boom" in o1.error
    row = tmp_db.execute(
        "SELECT error FROM skill_test_results WHERE id = ?", (o1.skill_test_id,)
    ).fetchone()
    assert "suite setup failed" in row[0]

    ws_root = tmp_path / "ws"
    leftover = list(ws_root.glob("*"))
    assert len(leftover) == 1  # the one workspace setup created, not yet wiped

    o2 = runner.run_case(case2, run_id=run_id, conn=tmp_db)[0]
    assert o2.status == "ERROR"
    assert "boom" in o2.error
    assert not leftover[0].exists()  # last member's turn -- deferred cleanup ran


def test_runner_group_teardown_action_runs_once_before_deferred_cleanup(tmp_db, tmp_path):
    teardown_calls: list[str] = []
    teardown_action = {"kind": "bash", "prompt": None, "script": None,
                        "command": "true", "timeout_seconds": 60}

    case1 = _grouped_case("case_1", "CASE ONE", tmp_path,
                          suite_id="grouped-suite-teardown",
                          teardown_action=teardown_action)
    case2 = _grouped_case("case_2", "CASE TWO", tmp_path,
                          suite_id="grouped-suite-teardown",
                          teardown_action=teardown_action)

    def factory(name, model):
        return FakeCLI(name=name, model=model, stdout="DONE")

    group_registry = build_group_registry([case1, case2])
    run_id = db_writer.create_run(tmp_db, suite="skill_test")
    runner = SkillRunner(
        cli_factory=factory,
        cleanup_manager=default_cleanup_manager(),
        host_caps={"free_memory_gb": 99, "free_disk_gb_tmp": 99},
        workspace_root=tmp_path / "ws",
        group_registry=group_registry,
    )

    o1 = runner.run_case(case1, run_id=run_id, conn=tmp_db)[0]
    assert o1.status == "PASS"
    ws_root = tmp_path / "ws"
    leftover = list(ws_root.glob("*"))
    assert len(leftover) == 1
    assert leftover[0].exists()  # deferred -- case_2 hasn't run yet

    o2 = runner.run_case(case2, run_id=run_id, conn=tmp_db)[0]
    assert o2.status == "PASS"
    assert not leftover[0].exists()  # teardown action + deferred cleanup both ran


def test_runner_group_reset_runs_between_cases_but_not_after_the_last(tmp_db, tmp_path):
    """Reset exists to hand the NEXT case a baseline. After the last member
    there is no next case -- teardown wipes the workspace moments later -- so
    a reset there is pure waste (for ip-configurator, a whole Vivado
    close/reopen cycle per group)."""
    tally = tmp_path / "resets.txt"
    reset_action = {"kind": "bash", "prompt": None, "script": None,
                     "command": f"echo ran >> {tally}", "timeout_seconds": 60}
    case1 = _grouped_case("case_1", "CASE ONE", tmp_path,
                          suite_id="grouped-suite-reset", reset_action=reset_action)
    case2 = _grouped_case("case_2", "CASE TWO", tmp_path,
                          suite_id="grouped-suite-reset", reset_action=reset_action)
    case3 = _grouped_case("case_3", "CASE THREE", tmp_path,
                          suite_id="grouped-suite-reset", reset_action=reset_action)

    def factory(name, model):
        return FakeCLI(name=name, model=model, stdout="DONE")

    group_registry = build_group_registry([case1, case2, case3])
    run_id = db_writer.create_run(tmp_db, suite="skill_test")
    runner = SkillRunner(
        cli_factory=factory,
        cleanup_manager=default_cleanup_manager(),
        host_caps={"free_memory_gb": 99, "free_disk_gb_tmp": 99},
        workspace_root=tmp_path / "ws",
        group_registry=group_registry,
    )

    o1 = runner.run_case(case1, run_id=run_id, conn=tmp_db)[0]
    assert o1.status == "PASS"
    ws_root = tmp_path / "ws"
    leftover = list(ws_root.glob("*"))
    assert len(leftover) == 1
    assert leftover[0].exists()  # reset does not wipe the shared workspace

    o2 = runner.run_case(case2, run_id=run_id, conn=tmp_db)[0]
    assert o2.status == "PASS"
    assert leftover[0].exists()  # still alive after the second case's reset
    assert tally.read_text().count("ran") == 2  # after case 1 and case 2

    o3 = runner.run_case(case3, run_id=run_id, conn=tmp_db)[0]
    assert o3.status == "PASS"
    assert not leftover[0].exists()  # last case: deferred cleanup wipes it
    # Still 2: the last member skipped its reset.
    assert tally.read_text().count("ran") == 2


def test_runner_group_reset_failure_fails_the_rest_of_the_group(tmp_db, tmp_path):
    """A failed reset leaves the shared design in an unknown state (leftover
    cells, or a part a case swapped and never restored). Continuing would
    grade later cases against a contaminated environment and blame them for
    it, so the group stops loudly instead."""
    reset_action = {"kind": "bash", "prompt": None, "script": None,
                     "command": "false", "timeout_seconds": 60}
    case1 = _grouped_case("case_1", "CASE ONE", tmp_path,
                          suite_id="grouped-suite-reset-fail", reset_action=reset_action)
    case2 = _grouped_case("case_2", "CASE TWO", tmp_path,
                          suite_id="grouped-suite-reset-fail", reset_action=reset_action)
    case3 = _grouped_case("case_3", "CASE THREE", tmp_path,
                          suite_id="grouped-suite-reset-fail", reset_action=reset_action)

    invoked: list[str] = []

    def factory(name, model):
        return FakeCLI(name=name, model=model, stdout="DONE",
                        side_effect=lambda ws: invoked.append(str(ws)))

    group_registry = build_group_registry([case1, case2, case3])
    run_id = db_writer.create_run(tmp_db, suite="skill_test")
    runner = SkillRunner(
        cli_factory=factory,
        cleanup_manager=default_cleanup_manager(),
        host_caps={"free_memory_gb": 99, "free_disk_gb_tmp": 99},
        workspace_root=tmp_path / "ws",
        group_registry=group_registry,
    )

    o1 = runner.run_case(case1, run_id=run_id, conn=tmp_db)[0]
    # Case 1 itself is untouched -- it had already been graded when reset ran.
    assert o1.status == "PASS"

    o2 = runner.run_case(case2, run_id=run_id, conn=tmp_db)[0]
    assert o2.status == "ERROR"
    assert "reset failed" in (o2.error or "")
    o3 = runner.run_case(case3, run_id=run_id, conn=tmp_db)[0]
    assert o3.status == "ERROR"
    # And no agent was spent on the poisoned members: only case 1 invoked one.
    assert len(invoked) == 1


_BASH_TRUE = {"kind": "bash", "prompt": None, "script": None,
              "command": "true", "timeout_seconds": 60}


def test_run_specs_runs_all_declared_graders(tmp_path):
    """There is one skill-enabled path, so every declared grader runs."""
    runner = SkillRunner(
        cli_factory=lambda n, m: FakeCLI(name=n, model=m),
        cleanup_manager=default_cleanup_manager(),
        host_caps={"vivado": True, "vitis": True, "free_memory_gb": 99,
                   "free_disk_gb_tmp": 99},
        workspace_root=tmp_path / "ws",
    )
    ctx = GraderContext(workspace_dir=tmp_path, stdout="DONE", stderr="")
    specs = [
        {"id": "says_done", "type": "content_contains", "source": "stdout",
         "substring": "DONE"},
        {"id": "skill_fired", "type": "trigger", "skills": ["s"]},
        {"id": "contract", "type": "content_contains", "source": "stdout",
         "substring": "DONE", "skill_only": True},
    ]
    ids = {r["id"] for r in runner._run_specs(specs, ctx)}
    assert ids == {"says_done", "skill_fired", "contract"}


def test_make_ctx_populates_client_and_model_in_run_meta(tmp_path):
    """Client-aware graders (trigger, discovery_first, action_sequence,
    tool_call_observed) select their transcript-parsing dialect off
    ``ctx.run_meta["client"]``. If it's missing they silently fall back to
    format auto-detection, which doesn't recognize every backend's
    transcript shape (e.g. Cursor's tool_call/*ToolCall JSONL) -- a
    regression that made discovery_first/trigger grade Cursor runs off
    weaker or trivially-passing heuristics instead of the real transcript."""
    case = load_case(_write_case(tmp_path))
    runner = SkillRunner(
        cli_factory=lambda n, m: FakeCLI(name=n, model=m),
        cleanup_manager=default_cleanup_manager(),
        host_caps={"vivado": True, "vitis": True, "free_memory_gb": 99,
                   "free_disk_gb_tmp": 99},
        workspace_root=tmp_path / "ws",
    )
    ctx = runner._make_ctx(
        case, tmp_path, {"stdout": "", "stderr": ""},
        client="cursor", model="auto",
    )
    assert ctx.run_meta["client"] == "cursor"
    assert ctx.run_meta["model"] == "auto"
