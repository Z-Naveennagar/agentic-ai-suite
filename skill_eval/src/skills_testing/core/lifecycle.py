"""Consistency-based skill lifecycle policy.

The lifecycle evaluates repeated skill-enabled runs only.  It intentionally
contains no A/B, baseline-arm, T2-lift, or token-ratio logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean, pstdev
from typing import Iterable, Optional


@dataclass(frozen=True)
class PolicyConfig:
    min_reps: int = 3
    min_coverage_rate: float = 1.0
    min_pass_rate: float = 0.80
    max_failed_case_rate: float = 0.20
    max_error_rate: float = 0.0
    max_skip_rate: float = 0.0
    max_case_score_stddev: float = 0.05
    max_flaky_case_rate: float = 0.0
    max_mandatory_grader_fail_rate: float = 0.0
    max_weighted_grader_fail_rate: float = 0.20
    consecutive_fails_to_deprecate: int = 2
    releases_in_deprecate_to_remove: int = 2


def grader_category(row: dict) -> str:
    """Derive the lifecycle category from persisted grader attributes."""
    if row.get("mandatory"):
        return "mandatory"
    weight = row.get("weight")
    if weight is None:
        category = row.get("category")
        return category if category in {"weighted", "diagnostic"} else "unclassified"
    return "weighted" if float(weight) > 0 else "diagnostic"


def aggregate_consistency_metrics(
    rows: Iterable[dict], grader_rows: Iterable[dict] = (), *, expected_reps: int
) -> dict:
    """Aggregate one run's rows for one skill/client/model lifecycle cell."""
    rows = list(rows)
    grader_rows = list(grader_rows)
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(str(row.get("case_id") or ""), []).append(row)

    counts = {
        status: sum(1 for row in rows if row.get("status") == status)
        for status in ("PASS", "FAIL", "ERROR", "SKIPPED")
    }
    attempted = counts["PASS"] + counts["FAIL"] + counts["ERROR"]
    total = len(rows)
    pass_rate = counts["PASS"] / attempted if attempted else 0.0
    error_rate = counts["ERROR"] / attempted if attempted else 0.0
    skip_rate = counts["SKIPPED"] / total if total else 0.0

    expected_reps = max(1, int(expected_reps))
    observed_reps = [len(recs) for recs in groups.values()]
    min_observed_reps = min(observed_reps, default=0)
    expected_rows = len(groups) * expected_reps
    coverage_rate = min(1.0, total / expected_rows) if expected_rows else 0.0

    case_stddevs: list[float] = []
    flaky = variable = failed_groups = 0
    all_scores: list[float] = []
    case_metrics: dict[str, dict] = {}
    for case_id, recs in groups.items():
        statuses = [r.get("status") for r in recs]
        scores = [float(r["aggregate_score"]) for r in recs
                  if r.get("aggregate_score") is not None]
        all_scores.extend(scores)
        score_stddev = pstdev(scores) if len(scores) > 1 else 0.0
        case_stddevs.append(score_stddev)
        has_pass = "PASS" in statuses
        has_nonpass = any(s in ("FAIL", "ERROR") for s in statuses)
        is_flaky = has_pass and has_nonpass
        is_variable = not is_flaky and score_stddev > 0
        flaky += int(is_flaky)
        variable += int(is_variable)
        failed_groups += int(has_nonpass)
        case_metrics[case_id] = {
            "n_reps": len(recs),
            "pass_rate": statuses.count("PASS") / len(recs) if recs else 0.0,
            "score_mean": fmean(scores) if scores else None,
            "score_stddev": score_stddev if scores else None,
            "flaky": is_flaky,
        }

    n_groups = len(groups)
    grader_stats: dict[str, dict[str, int | float]] = {}
    for category in ("mandatory", "weighted", "diagnostic"):
        selected = [r for r in grader_rows if grader_category(r) == category]
        failures = sum(1 for r in selected if not r.get("passed"))
        grader_stats[category] = {
            "total": len(selected),
            "failures": failures,
            "fail_rate": failures / len(selected) if selected else 0.0,
        }

    return {
        "n_cases": n_groups,
        "n_reps": min_observed_reps,
        "n_results": total,
        "coverage_rate": coverage_rate,
        "n_pass": counts["PASS"],
        "n_fail": counts["FAIL"],
        "n_error": counts["ERROR"],
        "n_skip": counts["SKIPPED"],
        "pass_rate": pass_rate,
        "error_rate": error_rate,
        "skip_rate": skip_rate,
        "failed_case_rate": failed_groups / n_groups if n_groups else 0.0,
        "aggregate_score_mean": fmean(all_scores) if all_scores else None,
        "max_case_score_stddev": max(case_stddevs, default=0.0),
        "flaky_case_rate": flaky / n_groups if n_groups else 0.0,
        "variable_case_rate": variable / n_groups if n_groups else 0.0,
        "mandatory_grader_total": grader_stats["mandatory"]["total"],
        "mandatory_grader_fail_rate": grader_stats["mandatory"]["fail_rate"],
        "weighted_grader_total": grader_stats["weighted"]["total"],
        "weighted_grader_fail_rate": grader_stats["weighted"]["fail_rate"],
        "diagnostic_grader_total": grader_stats["diagnostic"]["total"],
        "diagnostic_grader_fail_rate": grader_stats["diagnostic"]["fail_rate"],
        "case_metrics": case_metrics,
    }


def assess_consistency(metrics: dict, cfg: PolicyConfig) -> tuple[bool, bool, list[str]]:
    """Return ``(sufficient, passed, reasons)`` for one lifecycle snapshot."""
    insufficiency: list[str] = []
    if metrics.get("n_results", 0) == 0 or (
        metrics.get("n_pass", 0) + metrics.get("n_fail", 0) + metrics.get("n_error", 0)
    ) == 0:
        insufficiency.append("no attempted results")
    if metrics.get("n_reps", 0) < cfg.min_reps:
        insufficiency.append(
            f"minimum repetitions {metrics.get('n_reps', 0)} < {cfg.min_reps}"
        )
    if metrics.get("coverage_rate", 0.0) < cfg.min_coverage_rate:
        insufficiency.append(
            f"coverage {metrics.get('coverage_rate', 0.0):.0%} < {cfg.min_coverage_rate:.0%}"
        )
    if metrics.get("skip_rate", 0.0) > cfg.max_skip_rate:
        insufficiency.append(
            f"skip rate {metrics.get('skip_rate', 0.0):.0%} > {cfg.max_skip_rate:.0%}"
        )
    if insufficiency:
        return False, False, insufficiency

    failures: list[str] = []
    gates = (
        ("pass rate", metrics.get("pass_rate", 0.0), cfg.min_pass_rate, ">="),
        ("failed-case rate", metrics.get("failed_case_rate", 0.0), cfg.max_failed_case_rate, "<="),
        ("error rate", metrics.get("error_rate", 0.0), cfg.max_error_rate, "<="),
        ("score stddev", metrics.get("max_case_score_stddev", 0.0), cfg.max_case_score_stddev, "<="),
        ("flaky-case rate", metrics.get("flaky_case_rate", 0.0), cfg.max_flaky_case_rate, "<="),
        ("mandatory grader fail rate", metrics.get("mandatory_grader_fail_rate", 0.0), cfg.max_mandatory_grader_fail_rate, "<="),
        ("weighted grader fail rate", metrics.get("weighted_grader_fail_rate", 0.0), cfg.max_weighted_grader_fail_rate, "<="),
    )
    for label, actual, threshold, relation in gates:
        failed = actual < threshold if relation == ">=" else actual > threshold
        if failed:
            failures.append(f"{label} {actual:.1%} {relation} {threshold:.1%} required")
    return True, not failures, failures


def history_streaks(history: Iterable[dict]) -> tuple[int, int]:
    """Return trailing sufficient failure and deprecation streak lengths."""
    assessed = [h for h in history if h.get("assessment_sufficient")]
    failures = 0
    for row in reversed(assessed):
        if row.get("consistency_passed"):
            break
        failures += 1
    deprecated = 0
    for row in reversed(assessed):
        if row.get("lifecycle_state") != "DEPRECATE":
            break
        deprecated += 1
    return failures, deprecated


def next_state(
    *, prior_state: Optional[str], assessment_sufficient: bool,
    consistency_passed: bool, consecutive_failures: int,
    releases_in_deprecate: int, cfg: PolicyConfig,
) -> tuple[str, str]:
    """Apply the consistency lifecycle state machine."""
    if not assessment_sufficient:
        state = prior_state or "UNASSESSED"
        return state, "insufficient evidence; prior state preserved"
    if prior_state in (None, "UNASSESSED"):
        return (("KEEP", "first sufficient assessment passes")
                if consistency_passed else
                ("WATCH", "first sufficient assessment fails"))
    if prior_state == "KEEP":
        return (("KEEP", "consistency assessment passes")
                if consistency_passed else
                ("WATCH", "first sufficient failure"))
    if prior_state == "WATCH":
        if consistency_passed:
            return "KEEP", "recovered: consistency assessment passes"
        if consecutive_failures >= cfg.consecutive_fails_to_deprecate:
            return "DEPRECATE", f"{consecutive_failures} consecutive sufficient failures"
        return "WATCH", "still failing; below deprecation threshold"
    if prior_state == "DEPRECATE":
        if consistency_passed:
            return "WATCH", "probationary recovery"
        if releases_in_deprecate + 1 >= cfg.releases_in_deprecate_to_remove:
            return "REMOVE", f"{releases_in_deprecate + 1} evaluations in deprecate"
        return "DEPRECATE", "still failing in deprecate"
    if prior_state == "REMOVE":
        return "REMOVE", "already removed"
    return "WATCH", f"unknown prior state {prior_state!r}; defaulting to WATCH"
