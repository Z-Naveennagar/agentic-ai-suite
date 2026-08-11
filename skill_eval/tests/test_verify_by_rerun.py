"""
Tests for the SkillRunner verify_by_rerun (Phase 2b) hook.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yaml

from skills_testing.cli_backends.interface import SkillBackend
from skills_testing.core import db_writer
from skills_testing.core.case_loader import load_case
from skills_testing.runtime.cleanup_manager import default_cleanup_manager
from skills_testing.core.runner import SkillRunner


@dataclass
class FakeCLI(SkillBackend):
    name: str
    model: str
    stdout: str = ""
    stderr: str = ""
    side_effect: Any = None
    exit_code: int = 0
    prompt_tokens: int = 1
    output_tokens: int = 1
    skill_invoked: bool = True
    invoked_skills: list[str] = field(default_factory=list)

    def invoke(self, *, prompt, workspace_dir, timeout_seconds, env=None):
        if self.side_effect is not None:
            self.side_effect(workspace_dir)
        return {"stdout": self.stdout, "stderr": self.stderr,
                "exit_code": self.exit_code, "wall_clock_s": 0.01,
                "prompt_tokens": self.prompt_tokens,
                "output_tokens": self.output_tokens,
                "total_tokens": self.prompt_tokens + self.output_tokens}

    def detect_skill_invocation(self, stdout, stderr):
        return self.skill_invoked, list(self.invoked_skills)

    def hide_skills_env_overrides(self):
        return None


def _write_case_with_verify(tmp_path: Path) -> Path:
    case_dir = tmp_path / "skill_x" / "case_y"
    case_dir.mkdir(parents=True)
    (case_dir / "manifest.yaml").write_text(yaml.safe_dump({
        "skill_name": "skill_x",
        "skill_version": "1.0.0",
        "case_id": "case_y",
        "invocation": {
            "clients": [{"name": "claude_code", "model": "opus"}],
            "parameters": {"top_module": "u_top"},
            "timeout_seconds": 30,
            "prompt": "do it",
        },
        "requirements": {"vivado": False, "min_memory_gb": 1, "min_disk_gb": 1,
                         "tags": ["smoke"]},
        "cleanup": ["working_dir"],
        "verify_by_rerun": {
            "enabled": True,
            "apply_artifact": "outputs/fix.xdc",
            "apply_via": {
                "tool": "vivado_mcp",
                "tcl": "read_xdc {{ apply_artifact }}\nputs DONE",
            },
            "budget_seconds": 5,
            "success_criteria": [
                {"id": "post_fix_artifact",
                 "type": "artifact_exists",
                 "path": "outputs/post_fix.rpt"},
                {"id": "marker_in_log",
                 "type": "content_contains",
                 "source": "stdout",
                 "substring": "VERIFY_OK"},
            ],
        },
    }))
    (case_dir / "grading_spec.yaml").write_text(yaml.safe_dump({
        "graders": [
            {"id": "fix_xdc_exists", "type": "artifact_exists",
             "path": "outputs/fix.xdc"},
        ],
    }))
    return case_dir


def _make_skill_outputs(ws):
    (ws / "outputs").mkdir(exist_ok=True)
    (ws / "outputs" / "fix.xdc").write_text(
        "set_max_delay -from clk_a -to clk_b 5.0\n"
    )


def test_verify_by_rerun_runs_when_primary_passes(tmp_db, tmp_path):
    case = load_case(_write_case_with_verify(tmp_path))
    captured = {}

    def verifier(*, workspace_dir, tcl, env, timeout_seconds):
        captured["tcl"] = tcl
        captured["ws"] = workspace_dir
        (workspace_dir / "outputs" / "post_fix.rpt").write_text(
            "WNS(ns) THS(ns)\n0.05 0.10\n"
        )
        return {"stdout": "VERIFY_OK\n", "stderr": "", "exit_code": 0}

    def factory(name, model):
        return FakeCLI(name=name, model=model, stdout="ok",
                       side_effect=_make_skill_outputs)

    run_id = db_writer.create_run(tmp_db, suite="skill_test")
    runner = SkillRunner(
        cli_factory=factory,
        cleanup_manager=default_cleanup_manager(),
        host_caps={"free_memory_gb": 99, "free_disk_gb_tmp": 99},
        workspace_root=tmp_path / "ws",
        verifiers={"vivado_mcp": verifier},
    )
    outcomes = runner.run_case(case, run_id=run_id, conn=tmp_db)
    assert outcomes[0].status == "PASS"

    # template substitution into the apply tcl block actually ran.
    assert "read_xdc outputs/fix.xdc" in captured["tcl"]

    grader_ids = [g["id"] for g in outcomes[0].grader_summary]
    assert "fix_xdc_exists" in grader_ids
    assert "verify_by_rerun.apply" in grader_ids
    assert "verify_by_rerun.post_fix_artifact" in grader_ids
    assert "verify_by_rerun.marker_in_log" in grader_ids


def test_verify_by_rerun_skipped_when_primary_fails(tmp_db, tmp_path):
    case = load_case(_write_case_with_verify(tmp_path))
    calls = {"n": 0}

    def verifier(*, workspace_dir, tcl, env, timeout_seconds):
        calls["n"] += 1
        return {"stdout": "", "stderr": "", "exit_code": 0}

    def factory(name, model):
        # No side effect -> outputs/fix.xdc never created -> primary fails.
        return FakeCLI(name=name, model=model, stdout="ok")

    run_id = db_writer.create_run(tmp_db, suite="skill_test")
    runner = SkillRunner(
        cli_factory=factory,
        cleanup_manager=default_cleanup_manager(),
        host_caps={"free_memory_gb": 99, "free_disk_gb_tmp": 99},
        workspace_root=tmp_path / "ws",
        verifiers={"vivado_mcp": verifier},
    )
    outcomes = runner.run_case(case, run_id=run_id, conn=tmp_db)
    assert outcomes[0].status == "FAIL"
    assert calls["n"] == 0
    grader_ids = [g["id"] for g in outcomes[0].grader_summary]
    assert not any(g.startswith("verify_by_rerun") for g in grader_ids)


def test_verify_by_rerun_reports_when_no_verifier_registered(tmp_db, tmp_path):
    case = load_case(_write_case_with_verify(tmp_path))

    def factory(name, model):
        return FakeCLI(name=name, model=model, stdout="ok",
                       side_effect=_make_skill_outputs)

    run_id = db_writer.create_run(tmp_db, suite="skill_test")
    runner = SkillRunner(
        cli_factory=factory,
        cleanup_manager=default_cleanup_manager(),
        host_caps={"free_memory_gb": 99, "free_disk_gb_tmp": 99},
        workspace_root=tmp_path / "ws",
        verifiers={},  # no verifier registered for "vivado_mcp"
    )
    outcomes = runner.run_case(case, run_id=run_id, conn=tmp_db)
    assert outcomes[0].status == "FAIL"
    apply_row = next(g for g in outcomes[0].grader_summary
                     if g["id"] == "verify_by_rerun.apply")
    assert apply_row["passed"] is False
    assert apply_row["details"]["reason"] == "no_verifier_registered"


def test_case_loader_rejects_bad_verify_block(tmp_path):
    from skills_testing.core.case_loader import CaseSchemaError
    case_dir = tmp_path / "s" / "c"
    case_dir.mkdir(parents=True)
    (case_dir / "manifest.yaml").write_text(yaml.safe_dump({
        "skill_name": "s", "skill_version": "1.0.0", "case_id": "c",
        "invocation": {"clients": [{"name": "claude_code", "model": "opus"}],
                       "prompt": "x"},
        "verify_by_rerun": {
            "enabled": True,
            "apply_via": {},  # missing required tool
            "success_criteria": [],
        },
    }))
    (case_dir / "grading_spec.yaml").write_text(
        yaml.safe_dump({"graders": [{"id": "x", "type": "artifact_exists",
                                     "path": "x"}]})
    )
    with pytest.raises(CaseSchemaError):
        load_case(case_dir)
