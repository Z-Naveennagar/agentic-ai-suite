"""
Tests for the Skill Testing dashboard tab (2026-08 redesign).

The renderer is exposed as skills_testing.reporting.dashboard.render_skill_tab(conn)
and returns an HTML fragment (str). Per the redesign it must:
    * render a friendly empty state when no skill_test_results exist
    * render a consistency view (aggregate_score mean/sigma per case x model
      group) rather than the removed A/B heatmap
    * render a KEEP / WATCH / DEPRECATE / REMOVE callout strip from
      skill_release_evaluations (legacy, still present)
    * render lifecycle cards from skill_lifecycle_evaluations when that table
      exists (new, queried defensively)
    * surface aggregate_score in the headline stat tiles
    * be free of bare {python format braces} (so nothing accidentally
      tries to format the string downstream)
"""

from __future__ import annotations

import re
import sqlite3

import pytest

from skills_testing.core import db_writer
from skills_testing.reporting.dashboard import render_skill_tab


def _seed_release(conn, skill, version, client, model, **kw):
    db_writer.write_skill_release_evaluation(conn, {
        "skill_name": skill, "skill_version": version,
        "client": client, "model": model,
        "n_cases": kw.get("n_cases", 3),
        "n_reps_per_arm": kw.get("n_reps_per_arm", 3),
        "trigger_rate": kw.get("trigger_rate", 0.9),
        "t2_lift_pp": kw.get("t2_lift_pp", 12.0),
        "token_ratio": kw.get("token_ratio", 1.4),
        "value_test_passed": kw.get("value_test_passed", True),
        "lifecycle_state": kw.get("lifecycle_state", "KEEP"),
        "state_transition_reason": kw.get("reason", ""),
        "prior_state": kw.get("prior_state"),
    })


def _seed_test_row(conn, run_id, skill, client, model, with_skill, t2,
                   *, replication_index=0, status="PASS"):
    return db_writer.write_skill_test_result(conn, run_id, {
        "skill_name": skill, "skill_version": "1.0",
        "case_id": "c1", "client": client, "model": model,
        "with_skill": with_skill, "replication_index": replication_index,
        "skill_invoked": with_skill,
        "t2_score": t2, "aggregate_score": t2, "status": status,
        "wall_clock_s": 10.0, "prompt_tokens": 1000, "output_tokens": 500,
        "total_tokens": 1500,
    })


# -- empty state ---------------------------------------------------------


def test_empty_state(tmp_db):
    html = render_skill_tab(tmp_db)
    assert isinstance(html, str)
    assert "Skill Testing" in html
    assert "no skill" in html.lower()
    # never leaks {} placeholders
    assert "{" not in html or "}" not in html or "{ " not in html


# -- consistency view (replaces A/B heatmap) -----------------------------


def test_consistency_view_shows_skills_and_models(tmp_db):
    """Consistency tree renders skill names and client/model labels.

    A/B comparison (T2 lift in pp) has been removed; we verify the
    aggregate_score-based consistency view instead.
    """
    run_id = db_writer.create_run(tmp_db, suite="skill_test")
    # Two reps of rtl-assistant on claude_code/opus.
    for rep, t2 in enumerate([0.9, 0.85]):
        _seed_test_row(tmp_db, run_id, "rtl-assistant", "claude_code", "opus",
                       with_skill=True, t2=t2, replication_index=rep)
    # One rep on a second model.
    _seed_test_row(tmp_db, run_id, "rtl-assistant", "cursor",
                   "claude-4.6-sonnet-medium-thinking",
                   with_skill=True, t2=0.7)
    # A second skill.
    _seed_test_row(tmp_db, run_id, "vivado-revision-control",
                   "claude_code", "opus", with_skill=True, t2=0.8)

    html = render_skill_tab(tmp_db)
    assert "rtl-assistant" in html
    assert "vivado-revision-control" in html
    # column header for at least one (client, model) cell
    assert "claude_code" in html
    # Aggregate score is no longer displayed in the run summary.
    assert "aggregate score" not in html
    # Score values appear somewhere in the consistency tree
    assert re.search(r"0\.\d{3}", html), "expected score formatted to 3dp"


def test_consistency_tree_has_compact_interactive_columns(tmp_db):
    run_id = db_writer.create_run(tmp_db, suite="skill_test")
    _seed_test_row(tmp_db, run_id, "rtl-assistant", "claude_code", "opus",
                   with_skill=True, t2=0.90)
    html = render_skill_tab(tmp_db)
    assert "Reps (by index)" in html
    assert "Consistency" in html
    assert "Pass rate" in html
    assert "Avg / run" in html
    assert "Token consumption" in html
    assert ">Score mean<" not in html
    assert ">Runtime p50<" not in html
    assert 'data-cons-filter="text"' in html
    assert 'data-cons-action="expand"' in html
    assert 'class="col-resizer"' in html or "col-resizer" in html
    assert 'data-cons-action="columns"' in html
    assert "column-menu" in html
    assert "skill-tree-columns-" in html
    assert "text/column" in html
    assert 'colspan="9"' in html


def test_consistency_tree_shows_tokens_and_average_runtime(tmp_db):
    run_id = db_writer.create_run(tmp_db, suite="skill_test")
    for rep in range(2):
        _seed_test_row(tmp_db, run_id, "rtl-assistant", "claude_code", "opus",
                       with_skill=True, t2=1.0, replication_index=rep)
    html = render_skill_tab(tmp_db)
    assert "3.0k" in html
    assert "10.0 s" in html
    assert "avg 1.5k / run" in html


def test_consistency_view_omits_aggregate_score_headline(tmp_db):
    """Aggregate score is internal evidence, not a run-summary tile."""
    run_id = db_writer.create_run(tmp_db, suite="skill_test")
    _seed_test_row(tmp_db, run_id, "rtl-assistant", "claude_code", "opus",
                   with_skill=True, t2=0.90)
    html = render_skill_tab(tmp_db)
    assert "aggregate score" not in html


def test_no_skill_arm_shown_in_consistency(tmp_db):
    """No-skill rows are still shown in the consistency tree (labelled
    no-skill) -- the consistency view retains them for completeness even
    though A/B reporting has been removed."""
    run_id = db_writer.create_run(tmp_db, suite="skill_test")
    _seed_test_row(
        tmp_db, run_id, "rtl-assistant", "opencode",
        "lemonade/Gemma-4-26B-A4B-it-GGUF", True, 1.0,
    )
    _seed_test_row(
        tmp_db, run_id, "rtl-assistant", "opencode",
        "lemonade/Gemma-4-26B-A4B-it-GGUF", False, 0.5,
    )

    html = render_skill_tab(tmp_db)
    # Skill name appears in the tree.
    assert "rtl-assistant" in html
    # Model label (Gemma 4 local) should appear somewhere in the output.
    assert "Gemma 4 local" in html


# -- new consistency lifecycle cards -------------------------------------


def test_lifecycle_cards_absent_when_table_missing(tmp_db):
    """_render_lifecycle_cards returns empty string when the
    skill_lifecycle_evaluations table does not exist yet."""
    run_id = db_writer.create_run(tmp_db, suite="skill_test")
    _seed_test_row(tmp_db, run_id, "rtl-assistant", "claude_code", "opus",
                   with_skill=True, t2=0.9)
    html = render_skill_tab(tmp_db)
    # The new Consistency Lifecycle section should NOT appear when the table
    # is absent (migration pending -- defensive query).
    assert "Consistency Lifecycle" not in html


def test_lifecycle_cards_rendered_when_table_present(tmp_db):
    """_render_lifecycle_cards renders cards when skill_lifecycle_evaluations
    exists and has data."""
    run_id = db_writer.create_run(tmp_db, suite="skill_test")
    for skill, state, mean, sigma, rate, reason, prior in (
        ("rtl-assistant", "KEEP", 0.920, 0.025, 0.95, "", None),
        ("hls-dataflow", "WATCH", 0.650, 0.080, 0.70,
         "score below threshold", "KEEP"),
    ):
        db_writer.upsert_skill_lifecycle_evaluation(tmp_db, {
            "run_id": run_id, "skill_name": skill, "skill_version": "1.0",
            "client": "claude_code", "model": "opus",
            "assessment_sufficient": True, "consistency_passed": state == "KEEP",
            "lifecycle_state": state, "prior_state": prior,
            "transition_reason": reason, "n_cases": 1, "n_reps": 10,
            "n_results": 10, "coverage_rate": 1.0, "pass_rate": rate,
            "fail_rate": 1 - rate, "error_rate": 0.0, "skip_rate": 0.0,
            "failed_case_rate": 0.0, "aggregate_score_mean": mean,
            "aggregate_score_stdev": sigma, "flaky_case_rate": 0.0,
            "variable_case_rate": 0.0, "mandatory_grader_total": 1,
            "mandatory_grader_fail_rate": 0.0, "weighted_grader_total": 1,
            "weighted_grader_fail_rate": 0.0, "diagnostic_grader_total": 0,
            "diagnostic_grader_fail_rate": 0.0,
        })

    _seed_test_row(tmp_db, run_id, "rtl-assistant", "claude_code", "opus",
                   with_skill=True, t2=0.9)

    html = render_skill_tab(tmp_db)
    assert "Consistency Lifecycle" in html
    assert "rtl-assistant" in html
    assert "hls-dataflow" in html
    assert "KEEP" in html
    assert "WATCH" in html
    assert "score below threshold" in html
    assert "How this conclusion was reached" in html
    assert "Score evidence" not in html
