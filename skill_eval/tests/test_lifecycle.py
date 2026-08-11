"""Tests for repetition-based consistency lifecycle policy."""

import pytest

from skills_testing.core.lifecycle import (
    PolicyConfig,
    aggregate_consistency_metrics,
    assess_consistency,
    grader_category,
    history_streaks,
    next_state,
)


def _rows(statuses, scores=None, case_id="c1"):
    scores = scores or [1.0] * len(statuses)
    return [
        {"case_id": case_id, "replication_index": i, "status": status,
         "aggregate_score": score}
        for i, (status, score) in enumerate(zip(statuses, scores))
    ]


def test_aggregate_status_score_and_grader_categories():
    rows = _rows(["PASS", "FAIL", "PASS"], [1.0, 0.4, 0.9])
    graders = [
        {"passed": False, "mandatory": True, "weight": None},
        {"passed": True, "mandatory": False, "weight": 1.0},
        {"passed": False, "mandatory": False, "weight": 0.0},
    ]
    metrics = aggregate_consistency_metrics(rows, graders, expected_reps=3)
    assert metrics["pass_rate"] == pytest.approx(2 / 3)
    assert metrics["coverage_rate"] == 1.0
    assert metrics["flaky_case_rate"] == 1.0
    assert metrics["max_case_score_stddev"] > 0
    assert metrics["mandatory_grader_fail_rate"] == 1.0
    assert metrics["weighted_grader_fail_rate"] == 0.0
    assert metrics["diagnostic_grader_fail_rate"] == 1.0


def test_all_skipped_is_insufficient():
    metrics = aggregate_consistency_metrics(
        _rows(["SKIPPED", "SKIPPED", "SKIPPED"]), expected_reps=3)
    sufficient, passed, reasons = assess_consistency(metrics, PolicyConfig())
    assert not sufficient and not passed
    assert "no attempted results" in reasons


def test_single_rep_is_insufficient():
    metrics = aggregate_consistency_metrics(_rows(["PASS"]), expected_reps=1)
    sufficient, passed, reasons = assess_consistency(metrics, PolicyConfig())
    assert not sufficient and not passed
    assert any("minimum repetitions" in reason for reason in reasons)


def test_consistent_passing_run_passes_policy():
    metrics = aggregate_consistency_metrics(
        _rows(["PASS", "PASS", "PASS"]),
        [{"passed": True, "mandatory": False, "weight": 1.0}],
        expected_reps=3,
    )
    assert assess_consistency(metrics, PolicyConfig()) == (True, True, [])


def test_diagnostic_failures_do_not_gate():
    metrics = aggregate_consistency_metrics(
        _rows(["PASS", "PASS", "PASS"]),
        [{"passed": False, "mandatory": False, "weight": 0.0}],
        expected_reps=3,
    )
    sufficient, passed, _ = assess_consistency(metrics, PolicyConfig())
    assert sufficient and passed


def test_grader_category_derivation():
    assert grader_category({"mandatory": True}) == "mandatory"
    assert grader_category({"mandatory": False, "weight": 1}) == "weighted"
    assert grader_category({"mandatory": False, "weight": 0}) == "diagnostic"
    assert grader_category({"mandatory": None, "weight": None}) == "unclassified"


def test_history_streaks_ignore_unassessed():
    history = [
        {"assessment_sufficient": True, "consistency_passed": False,
         "lifecycle_state": "WATCH"},
        {"assessment_sufficient": False, "consistency_passed": False,
         "lifecycle_state": "WATCH"},
        {"assessment_sufficient": True, "consistency_passed": False,
         "lifecycle_state": "DEPRECATE"},
    ]
    assert history_streaks(history) == (2, 1)


@pytest.mark.parametrize(
    "prior,sufficient,passed,failures,deprecations,expected",
    [
        (None, False, False, 0, 0, "UNASSESSED"),
        (None, True, True, 0, 0, "KEEP"),
        (None, True, False, 1, 0, "WATCH"),
        ("KEEP", True, False, 1, 0, "WATCH"),
        ("WATCH", True, False, 2, 0, "DEPRECATE"),
        ("WATCH", True, True, 0, 0, "KEEP"),
        ("DEPRECATE", True, True, 0, 1, "WATCH"),
        ("DEPRECATE", True, False, 3, 1, "REMOVE"),
        ("REMOVE", True, True, 0, 0, "REMOVE"),
    ],
)
def test_state_transitions(prior, sufficient, passed, failures, deprecations, expected):
    state, _ = next_state(
        prior_state=prior, assessment_sufficient=sufficient,
        consistency_passed=passed, consecutive_failures=failures,
        releases_in_deprecate=deprecations, cfg=PolicyConfig(),
    )
    assert state == expected


def test_insufficient_evidence_preserves_prior_state():
    state, reason = next_state(
        prior_state="KEEP", assessment_sufficient=False,
        consistency_passed=False, consecutive_failures=0,
        releases_in_deprecate=0, cfg=PolicyConfig(),
    )
    assert state == "KEEP"
    assert "preserved" in reason
