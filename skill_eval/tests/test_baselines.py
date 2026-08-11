"""
Tests for skills_testing.core.baselines - the bridge between grader output,
the skill_baselines table, and the baseline_delta grader.
"""

from __future__ import annotations

from skills_testing.cli_backends.interface import SkillBackend
from skills_testing.core import db_writer
from skills_testing.core.baselines import (
    capture_metrics_from_grader_results,
    make_baseline_lookup,
)


def test_lookup_returns_value(tmp_db):
    db_writer.upsert_skill_baseline(tmp_db, dict(
        skill_name="rtl-assistant", skill_version="1.0",
        case_id="lint", metric_name="violations", metric_value=12.0,
    ))
    lookup = make_baseline_lookup(tmp_db)
    assert lookup("rtl-assistant", "1.0", "lint", "violations") == 12.0


def test_lookup_missing_returns_none(tmp_db):
    lookup = make_baseline_lookup(tmp_db)
    assert lookup("x", "1", "y", "metric") is None


def test_capture_metrics_writes_baselines(tmp_db):
    grader_results = [
        {"id": "g1", "type": "metric_threshold", "passed": True, "score": 1.0,
         "details": {"metric": "wns_ns", "value": 0.215}},
        {"id": "g2", "type": "artifact_valid", "passed": True, "score": 1.0,
         "details": {"validator": "vivado_methodology_report_parser",
                     "total_violations": 8, "warnings": 5,
                     "critical_warnings": 1, "advisories": 2}},
        {"id": "g3", "type": "content_contains", "passed": True, "score": 1.0,
         "details": {"present": True}},   # no metric -> skipped
    ]
    n = capture_metrics_from_grader_results(
        tmp_db,
        skill_name="rtl-assistant",
        skill_version="1.0",
        case_id="lint",
        grader_results=grader_results,
    )
    assert n >= 2  # wns_ns and several methodology metrics

    rows = tmp_db.execute(
        "SELECT metric_name, metric_value FROM skill_baselines "
        "WHERE skill_name=? AND case_id=? ORDER BY metric_name",
        ("rtl-assistant", "lint"),
    ).fetchall()
    metrics = dict(rows)
    assert metrics["wns_ns"] == 0.215
    assert metrics["total_violations"] == 8
    assert metrics["critical_warnings"] == 1


def test_runner_capture_baseline_mode_writes_table(tmp_db, tmp_path):
    """End-to-end: runner with capture_baseline=True populates skill_baselines."""
    import yaml
    from skills_testing.core.case_loader import load_case
    from skills_testing.runtime.cleanup_manager import default_cleanup_manager
    from skills_testing.core.runner import SkillRunner

    case_dir = tmp_path / "rtl-assistant" / "lint"
    case_dir.mkdir(parents=True)
    (case_dir / "manifest.yaml").write_text(yaml.safe_dump({
        "skill_name": "rtl-assistant", "skill_version": "1.0",
        "case_id": "lint", "description": "x",
        "invocation": {"clients": [{"name": "claude_code", "model": "opus"}],
                       "parameters": {}, "timeout_seconds": 30,
                       "prompt": "go"},
        "requirements": {"vivado": False, "vitis": False,
                         "min_memory_gb": 1, "min_disk_gb": 1, "tags": ["smoke"]},
        "cleanup": ["working_dir"],
    }))
    (case_dir / "grading_spec.yaml").write_text(yaml.safe_dump({
        "graders": [
            {"id": "wns", "type": "metric_threshold", "metric": "wns_ns",
             "value": 0.215, "op": ">=", "threshold": 0.0},
        ],
    }))
    (case_dir / "inputs").mkdir()

    case = load_case(case_dir)

    class FakeCLI(SkillBackend):
        def __init__(self, name, model): self.name, self.model = name, model
        def invoke(self, **kw):
            return {"stdout": "DONE", "stderr": "", "exit_code": 0,
                    "wall_clock_s": 0.01, "prompt_tokens": 100,
                    "output_tokens": 50, "total_tokens": 150}
        def detect_skill_invocation(self, *a): return True, []
        def hide_skills_env_overrides(self): return None

    run_id = db_writer.create_run(tmp_db, suite="skill_test")
    runner = SkillRunner(
        cli_factory=lambda n, m: FakeCLI(n, m),
        cleanup_manager=default_cleanup_manager(),
        host_caps={"free_memory_gb": 99, "free_disk_gb_tmp": 99},
        workspace_root=tmp_path / "ws",
        capture_baseline=True,
    )
    runner.run_case(case, run_id=run_id, conn=tmp_db)

    row = tmp_db.execute(
        "SELECT metric_value FROM skill_baselines "
        "WHERE skill_name='rtl-assistant' AND case_id='lint' "
        "AND metric_name='wns_ns'"
    ).fetchone()
    assert row is not None
    assert row[0] == 0.215


def test_capture_skips_failed_graders(tmp_db):
    grader_results = [
        {"id": "g1", "type": "metric_threshold", "passed": False, "score": 0.0,
         "details": {"metric": "wns_ns", "value": -0.5}},
    ]
    n = capture_metrics_from_grader_results(
        tmp_db, skill_name="rtl-assistant", skill_version="1.0",
        case_id="lint", grader_results=grader_results,
    )
    assert n == 0
    rows = tmp_db.execute(
        "SELECT COUNT(*) FROM skill_baselines"
    ).fetchone()[0]
    assert rows == 0
