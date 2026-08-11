"""End-to-end smoke runs for shipped skill test cases.

These tests intentionally use real case directories from
`skills_testing/test_cases/` instead of synthetic manifests. They keep the CLI
side deterministic so the unit suite does not require agent credentials or a
Vivado installation, but they exercise the real manifests, inputs, skill
staging, workspace population, graders, DB writes, and cleanup path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pytest

from skills_testing.cli_backends.interface import SkillBackend
from skills_testing.core import db_writer
from skills_testing.core.case_loader import load_case
from skills_testing.core.runner import SkillRunner
from skills_testing.runtime.cleanup_manager import default_cleanup_manager


from skills_testing.core.paths import TEST_CASES_ROOT

pytestmark = pytest.mark.skip(
    reason="rtl-assistant seed cases were removed from "
           "src/skills_testing/test_cases/ during the tests/ (formerly "
           "vivado_skills_repo) migration, with no replacement suite authored "
           "yet. Re-enable once a real tests/ suite exists for "
           "rtl-assistant."
)

# Tests need repo root for .claude/skills/ — distinct from package root
_TEST_REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = _TEST_REPO_ROOT / ".claude" / "skills"


# Real Vivado text-report header. The hallucination-contract graders
# (`artifact_signature: vivado_text_report`) check for this verbatim,
# so the seed fixture has to reproduce it exactly. If the regex in
# ARTIFACT_SIGNATURES changes you will need to update this preamble.
_VIVADO_REPORT_HEADER = (
    "Copyright 1986-2026 Xilinx, Inc. All Rights Reserved.\n"
    "----------------------------------------------------------------------------------\n"
    "| Tool Version : Vivado v.2026.2.0 (lin64) Build 1234567 Sat May 17 15:00:00 2026\n"
    "| Date         : Wed May 27 16:00:00 2026\n"
    "| Host         : ci-runner\n"
    "----------------------------------------------------------------------------------\n"
)


def _stub_vivado_invocation_evidence(workspace: Path) -> None:
    """
    Simulate the side-effect of a `vivado_start` + `vivado_execute` pair:
    creates the `.vivado-ai/` working directory plus a log + journal so
    the `tool_call_observed` grader can confirm Vivado actually ran.
    """
    vai = workspace / ".vivado-ai"
    vai.mkdir(parents=True, exist_ok=True)
    (vai / "vivado_seed.log").write_text(
        "# Vivado seed-case stub log; real runs emit one of these per session\n"
    )
    (vai / "vivado_seed.jou").write_text("# stub journal\n")


@dataclass
class DeterministicSeedCaseCLI(SkillBackend):
    # ``name``/``model`` inherit their "" defaults from SkillBackend, so every
    # field below needs one too; all call sites pass these by keyword anyway.
    name: str = ""
    model: str = ""
    stdout: str = ""
    side_effect: Callable[[Path], None] = None

    def invoke(self, *, prompt, workspace_dir, timeout_seconds, env=None):
        self.side_effect(Path(workspace_dir))
        return {
            "stdout": self.stdout,
            "stderr": "",
            "exit_code": 0,
            "wall_clock_s": 0.01,
            "prompt_tokens": 100,
            "output_tokens": 25,
            "total_tokens": 125,
        }

    def detect_skill_invocation(self, stdout, stderr):
        return True, ["rtl-assistant"]

    def hide_skills_env_overrides(self):
        return None


def _run_seed_case(tmp_db, tmp_path, monkeypatch, *, skill: str, case_id: str,
                   side_effect: Callable[[Path], None], stdout: str):
    case = load_case(TEST_CASES_ROOT / skill / case_id)
    run_id = db_writer.create_run(tmp_db, suite="skill_test_seed_case")

    # Avoid power-meter overhead for lemonade models in multi-client manifests.
    import skills_testing.core.runner as runner_mod
    monkeypatch.setattr(runner_mod, "_is_self_hosted_model", lambda _model: False)

    def factory(name, model):
        return DeterministicSeedCaseCLI(
            name=name,
            model=model,
            stdout=stdout,
            side_effect=side_effect,
        )

    runner = SkillRunner(
        cli_factory=factory,
        cleanup_manager=default_cleanup_manager(),
        host_caps={
            "vivado": True,
            "vitis": True,
            "xsdb": True,
            "free_memory_gb": 128,
            "free_disk_gb_workspace": 1024,
            "free_disk_gb_tmp": 1024,
            "workspace_root": str(tmp_path / "ws"),
            "available_hardware": [],
        },
        workspace_root=tmp_path / "ws",
        skills_root=SKILLS_ROOT,
    )
    outcomes = runner.run_case(case, run_id=run_id, conn=tmp_db)
    assert outcomes, "seed case produced no outcomes"
    assert {outcome.status for outcome in outcomes} == {"PASS"}

    rows = tmp_db.execute(
        "SELECT status, skill_invoked FROM skill_test_results WHERE run_id = ?",
        (run_id,),
    ).fetchall()
    assert len(rows) == len(case.invocation["clients"])
    assert all(row == ("PASS", 1) for row in rows)
    return outcomes


def test_full_seed_case_rtl_lint_runs_real_manifest(tmp_db, tmp_path, monkeypatch):
    def make_lint_outputs(workspace: Path) -> None:
        assert (workspace / "top.sv").exists(), "case inputs were not copied"
        assert (
            workspace / ".claude" / "skills" / "rtl-assistant" / "SKILL.md"
        ).exists(), "parent skill was not staged"
        assert (
            workspace / ".claude" / "skills" / "rtl-assistant" / "rtl-lint" / "SKILL.md"
        ).exists(), "rtl-lint subskill was not staged"

        _stub_vivado_invocation_evidence(workspace)
        out = workspace / "outputs"
        out.mkdir(exist_ok=True)
        (out / "lint.rpt").write_text(
            _VIVADO_REPORT_HEADER
            + "Vivado RTL lint report for top\n"
            + "Top module: top\n"
            + "Severity summary: INFO=1 WARNING=0 ERROR=0\n"
            + "No lint findings requiring action.\n"
        )

    _run_seed_case(
        tmp_db,
        tmp_path,
        monkeypatch,
        skill="rtl-assistant",
        case_id="rtl-lint",
        side_effect=make_lint_outputs,
        stdout="lint severity summary for top: no findings",
    )


def test_full_seed_case_report_methodology_runs_real_manifest(tmp_db, tmp_path, monkeypatch):
    def make_methodology_outputs(workspace: Path) -> None:
        assert (workspace / "top.sv").exists(), "case inputs were not copied"
        assert (
            workspace / ".claude" / "skills" / "rtl-assistant" / "SKILL.md"
        ).exists(), "rtl-assistant skill was not staged"
        assert (
            workspace / ".claude" / "skills" / "rtl-assistant" / "report_methodology" / "SKILL.md"
        ).exists(), "report_methodology subskill was not staged"

        _stub_vivado_invocation_evidence(workspace)
        out = workspace / "outputs"
        out.mkdir(exist_ok=True)
        report = "\n".join([
            "Vivado Methodology Report",
            "| Rule ID | Severity | Description | Count |",
            "| TIMING-1 | Critical Warning | Synthetic seed-case check | 0 |",
            "| XDC-1 | Warning | Synthetic seed-case check | 0 |",
            "Summary: total violations 0",
        ])
        (out / "methodology.rpt").write_text(
            _VIVADO_REPORT_HEADER + report + "\n" + ("#" * 256)
        )

    _run_seed_case(
        tmp_db,
        tmp_path,
        monkeypatch,
        skill="rtl-assistant",
        case_id="report_methodology",
        side_effect=make_methodology_outputs,
        stdout="CRITICAL_WARNING severity summary: 0 methodology violations",
    )
