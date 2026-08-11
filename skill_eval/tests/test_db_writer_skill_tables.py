"""
Tests for the skill-testing schema additions to db_writer.py.

Skill-testing tables:
  - skill_test_results        (one row per run x case x client x model x arm x rep)
  - skill_grader_results      (one row per grader per skill_test_results row)
  - skill_baselines           (one row per metric per skill_version per case)
  - skill_release_evaluations (one row per release per (skill, client, model))

Plus three new write helpers:
  - write_skill_test_result()       returns the new row id
  - write_skill_grader_result()
  - upsert_skill_baseline()
  - write_skill_release_evaluation()

These tests run against a fresh temp DB and never touch the production results.db.
"""

from __future__ import annotations

import sqlite3

import pytest


# -- schema shape ------------------------------------------------------------


def _table_columns(conn: sqlite3.Connection, table: str) -> dict[str, str]:
    """Return {column_name: type} for *table*."""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1]: row[2] for row in rows}


class TestSchemaShape:
    """The CREATE TABLE statements must produce exactly the expected columns."""

    def test_skill_test_results_columns(self, tmp_db):
        cols = _table_columns(tmp_db, "skill_test_results")
        # Identity / linkage
        assert "id" in cols
        assert "run_id" in cols
        assert "skill_name" in cols
        assert "skill_version" in cols
        assert "case_id" in cols
        assert "client" in cols
        assert "model" in cols
        # A/B + replication
        assert "with_skill" in cols
        assert "replication_index" in cols
        assert "skill_invoked" in cols
        # Cost / perf
        assert "wall_clock_s" in cols
        assert "prompt_tokens" in cols
        assert "output_tokens" in cols
        assert "total_tokens" in cols
        assert "cost_usd" in cols
        assert "mcp_call_count" in cols
        assert "mcp_total_latency_ms" in cols
        # Scoring + status
        assert "t2_score" in cols
        assert "aggregate_score" in cols
        assert "status" in cols
        assert "skip_reason" in cols
        assert "error" in cols
        assert "timestamp" in cols

    def test_skill_grader_results_columns(self, tmp_db):
        cols = _table_columns(tmp_db, "skill_grader_results")
        assert "id" in cols
        assert "skill_test_id" in cols
        assert "grader_id" in cols
        assert "grader_type" in cols
        assert "passed" in cols
        assert "score" in cols
        assert "details" in cols

    def test_skill_baselines_columns(self, tmp_db):
        cols = _table_columns(tmp_db, "skill_baselines")
        assert "skill_name" in cols
        assert "skill_version" in cols
        assert "case_id" in cols
        assert "metric_name" in cols
        assert "metric_value" in cols
        assert "captured_at" in cols

    def test_skill_release_evaluations_columns(self, tmp_db):
        cols = _table_columns(tmp_db, "skill_release_evaluations")
        assert "id" in cols
        assert "skill_name" in cols
        assert "skill_version" in cols
        assert "client" in cols
        assert "model" in cols
        assert "evaluated_at" in cols
        assert "n_cases" in cols
        assert "n_reps_per_arm" in cols
        assert "trigger_rate" in cols
        assert "t2_lift_pp" in cols
        assert "token_ratio" in cols
        assert "value_test_passed" in cols
        assert "lifecycle_state" in cols
        assert "state_transition_reason" in cols
        assert "prior_state" in cols


# -- db path resolution -------------------------------------------------------


class TestGetDbPath:
    """_get_db_path() must resolve a relative database.path the same way
    core/paths.py:resolve_project_path() does (database.path lives under
    _runtime/ at PROJECT_ROOT, not under the package), so every writer/reader
    in the harness agrees on one results.db file."""

    def test_relative_path_matches_resolve_project_path(self):
        from skills_testing.core import db_writer
        from skills_testing.core.paths import resolve_project_path

        resolved = db_writer._get_db_path({"database": {"path": "_runtime/results.db"}})
        assert resolved == resolve_project_path("_runtime/results.db")

    def test_absolute_path_passes_through(self, tmp_path):
        from skills_testing.core import db_writer

        abs_path = tmp_path / "somewhere" / "results.db"
        resolved = db_writer._get_db_path({"database": {"path": str(abs_path)}})
        assert resolved == abs_path


class TestResumeHelpers:
    """run_exists()/completed_skill_test_combos() back --resume (see
    integration_runner.py) -- resuming a long run across thousands of skills
    without restarting it from scratch when interrupted partway through."""

    def test_run_exists(self, tmp_db):
        from skills_testing.core import db_writer

        run_id = _make_run(tmp_db)
        assert db_writer.run_exists(tmp_db, run_id) is True
        assert db_writer.run_exists(tmp_db, "not-a-real-run-id") is False

    def test_completed_skill_test_combos_reflects_written_rows(self, tmp_db):
        from skills_testing.core import db_writer

        run_id = _make_run(tmp_db)
        assert db_writer.completed_skill_test_combos(tmp_db, run_id) == set()

        db_writer.write_skill_test_result(tmp_db, run_id, {
            "skill_name": "hls-flattenable", "skill_version": "1.0",
            "case_id": "flattenable_01", "client": "opencode", "model": "azure/gpt-5.4",
            "with_skill": True, "replication_index": 0, "status": "PASS",
        })
        db_writer.write_skill_test_result(tmp_db, run_id, {
            "skill_name": "hls-flattenable", "skill_version": "1.0",
            "case_id": "flattenable_01", "client": "opencode", "model": "azure/gpt-5.4",
            "with_skill": False, "replication_index": 0, "status": "PASS",
        })
        combos = db_writer.completed_skill_test_combos(tmp_db, run_id)
        assert combos == {
            ("flattenable_01", "opencode", "azure/gpt-5.4", True, 0),
            ("flattenable_01", "opencode", "azure/gpt-5.4", False, 0),
        }

        # A different run_id's rows must never leak into this one's set.
        other_run = _make_run(tmp_db)
        assert db_writer.completed_skill_test_combos(tmp_db, other_run) == set()


# -- baselines uniqueness ----------------------------------------------------


class TestBaselinesPrimaryKey:
    """The (skill_name, skill_version, case_id, metric_name) tuple must be unique."""

    def test_pk_enforced(self, tmp_db):
        tmp_db.execute(
            "INSERT INTO skill_baselines "
            "(skill_name, skill_version, case_id, metric_name, metric_value, captured_at) "
            "VALUES ('rtl-assistant', '1.0', 'lint_smoke', 'pass_rate', 0.9, '2026-04-24')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            tmp_db.execute(
                "INSERT INTO skill_baselines "
                "(skill_name, skill_version, case_id, metric_name, metric_value, captured_at) "
                "VALUES ('rtl-assistant', '1.0', 'lint_smoke', 'pass_rate', 0.95, '2026-04-25')"
            )


# -- write helpers -----------------------------------------------------------


def _make_run(conn):
    from skills_testing.core import db_writer

    return db_writer.create_run(conn, suite="skill_test", cli_backend="claude_code")


class TestWriteSkillTestResult:
    """write_skill_test_result inserts and returns the new row id."""

    def test_basic_insert_returns_id(self, tmp_db):
        from skills_testing.core import db_writer

        run_id = _make_run(tmp_db)
        new_id = db_writer.write_skill_test_result(
            tmp_db,
            run_id,
            {
                "skill_name": "rtl-assistant",
                "skill_version": "1.0",
                "case_id": "lint_smoke",
                "client": "claude_code",
                "model": "opus",
                "with_skill": True,
                "replication_index": 0,
                "skill_invoked": True,
                "wall_clock_s": 12.4,
                "prompt_tokens": 1200,
                "output_tokens": 800,
                "total_tokens": 2000,
                "mcp_call_count": 3,
                "mcp_total_latency_ms": 240,
                "t2_score": 0.85,
                "aggregate_score": 0.85,
                "status": "PASS",
            },
        )
        assert isinstance(new_id, int) and new_id > 0

        row = tmp_db.execute(
            "SELECT skill_name, with_skill, replication_index, skill_invoked, "
            "       t2_score, status FROM skill_test_results WHERE id = ?",
            (new_id,),
        ).fetchone()
        assert row[0] == "rtl-assistant"
        assert row[1] == 1
        assert row[2] == 0
        assert row[3] == 1
        assert abs(row[4] - 0.85) < 1e-9
        assert row[5] == "PASS"

    def test_skipped_status_records_skip_reason(self, tmp_db):
        from skills_testing.core import db_writer

        run_id = _make_run(tmp_db)
        new_id = db_writer.write_skill_test_result(
            tmp_db,
            run_id,
            {
                "skill_name": "vitis-vpp-link",
                "skill_version": "1.4.0",
                "case_id": "vck190_link",
                "client": "claude_code",
                "model": "opus",
                "with_skill": True,
                "replication_index": 0,
                "status": "SKIPPED",
                "skip_reason": "vitis_not_available",
            },
        )
        row = tmp_db.execute(
            "SELECT status, skip_reason FROM skill_test_results WHERE id = ?",
            (new_id,),
        ).fetchone()
        assert row == ("SKIPPED", "vitis_not_available")

    def test_cost_annotated_when_usage_present(self, tmp_db):
        """If usage tokens + model are present, cost_usd should be populated."""
        from skills_testing.core import db_writer

        run_id = _make_run(tmp_db)
        new_id = db_writer.write_skill_test_result(
            tmp_db,
            run_id,
            {
                "skill_name": "rtl-assistant",
                "skill_version": "1.0",
                "case_id": "lint_smoke",
                "client": "claude_code",
                "model": "claude-opus-4.6",
                "with_skill": True,
                "replication_index": 0,
                "prompt_tokens": 100_000,
                "output_tokens": 10_000,
                "total_tokens": 110_000,
                "wall_clock_s": 30.0,
                "status": "PASS",
            },
        )
        cost = tmp_db.execute(
            "SELECT cost_usd FROM skill_test_results WHERE id = ?",
            (new_id,),
        ).fetchone()[0]
        # 100k input @ $5/Mtok + 10k output @ $25/Mtok = $0.50 + $0.25 = $0.75
        assert cost is not None
        assert 0.6 < cost < 0.9


class TestWriteSkillGraderResult:
    def test_links_to_skill_test_result(self, tmp_db):
        from skills_testing.core import db_writer

        run_id = _make_run(tmp_db)
        skill_test_id = db_writer.write_skill_test_result(
            tmp_db,
            run_id,
            {
                "skill_name": "rtl-assistant",
                "skill_version": "1.0",
                "case_id": "lint_smoke",
                "client": "claude_code",
                "model": "opus",
                "with_skill": True,
                "replication_index": 0,
                "status": "PASS",
            },
        )
        db_writer.write_skill_grader_result(
            tmp_db,
            skill_test_id,
            {
                "grader_id": "lint_report_exists",
                "grader_type": "artifact_exists",
                "passed": True,
                "score": 1.0,
                "details": '{"path": "outputs/lint.rpt"}',
            },
        )
        rows = tmp_db.execute(
            "SELECT grader_id, passed, score FROM skill_grader_results "
            "WHERE skill_test_id = ?",
            (skill_test_id,),
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "lint_report_exists"
        assert rows[0][1] == 1
        assert rows[0][2] == 1.0


class TestUpsertSkillBaseline:
    def test_insert_then_update(self, tmp_db):
        from skills_testing.core import db_writer

        db_writer.upsert_skill_baseline(
            tmp_db,
            {
                "skill_name": "rtl-assistant",
                "skill_version": "1.0",
                "case_id": "lint_smoke",
                "metric_name": "pass_rate",
                "metric_value": 0.80,
            },
        )
        # Same key, new value: must overwrite, not raise.
        db_writer.upsert_skill_baseline(
            tmp_db,
            {
                "skill_name": "rtl-assistant",
                "skill_version": "1.0",
                "case_id": "lint_smoke",
                "metric_name": "pass_rate",
                "metric_value": 0.92,
            },
        )
        rows = tmp_db.execute(
            "SELECT metric_value FROM skill_baselines "
            "WHERE skill_name=? AND skill_version=? AND case_id=? AND metric_name=?",
            ("rtl-assistant", "1.0", "lint_smoke", "pass_rate"),
        ).fetchall()
        assert len(rows) == 1
        assert abs(rows[0][0] - 0.92) < 1e-9


class TestWriteSkillReleaseEvaluation:
    def test_insert_with_lifecycle_state(self, tmp_db):
        from skills_testing.core import db_writer

        db_writer.write_skill_release_evaluation(
            tmp_db,
            {
                "skill_name": "rtl-assistant",
                "skill_version": "1.0",
                "client": "claude_code",
                "model": "opus",
                "n_cases": 3,
                "n_reps_per_arm": 3,
                "trigger_rate": 0.85,
                "t2_lift_pp": 12.5,
                "token_ratio": 1.2,
                "value_test_passed": True,
                "lifecycle_state": "KEEP",
                "state_transition_reason": "first release; passes value test",
                "prior_state": None,
            },
        )
        row = tmp_db.execute(
            "SELECT trigger_rate, t2_lift_pp, token_ratio, "
            "       value_test_passed, lifecycle_state "
            "FROM skill_release_evaluations "
            "WHERE skill_name=? AND skill_version=?",
            ("rtl-assistant", "1.0"),
        ).fetchone()
        assert abs(row[0] - 0.85) < 1e-9
        assert abs(row[1] - 12.5) < 1e-9
        assert abs(row[2] - 1.2) < 1e-9
        assert row[3] == 1
        assert row[4] == "KEEP"
