"""
Bridge between grader outputs, the skill_baselines table, and the
baseline_delta grader.

In normal A/B mode the runner is constructed with a baseline_lookup
returned by make_baseline_lookup(conn). The baseline_delta grader uses
that closure to compare new metric values against stored baselines.

In --capture-baseline mode the runner instead calls
capture_metrics_from_grader_results() after each successful run, which
writes any *numeric* fields it finds in grader details into the
skill_baselines table.
"""

from __future__ import annotations

import sqlite3
from typing import Callable, Iterable, Optional

from skills_testing.core import db_writer

# Detail keys we never want to mistake for a metric.
_DETAIL_BLACKLIST = {
    "validator", "path", "reason", "regex", "match",
    "metric", "op", "threshold", "rationale",  # carry context, not values
    "missing_baseline", "present", "by_rule",
}


def make_baseline_lookup(conn: sqlite3.Connection) -> Callable[..., Optional[float]]:
    """Return a closure (skill, version, case, metric) -> value | None."""

    def _lookup(skill: str, version: str, case: str, metric: str) -> Optional[float]:
        row = conn.execute(
            "SELECT metric_value FROM skill_baselines "
            "WHERE skill_name=? AND skill_version=? AND case_id=? "
            "AND metric_name=?",
            (skill, version, case, metric),
        ).fetchone()
        return None if row is None else float(row[0])

    return _lookup


def _numeric_metrics_from_details(details: dict) -> dict[str, float]:
    out: dict[str, float] = {}
    metric_name = details.get("metric")
    if metric_name and isinstance(details.get("value"), (int, float)):
        out[str(metric_name)] = float(details["value"])

    for k, v in details.items():
        if k in _DETAIL_BLACKLIST:
            continue
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            out[str(k)] = float(v)
    return out


def capture_metrics_from_grader_results(
    conn: sqlite3.Connection,
    *,
    skill_name: str,
    skill_version: str,
    case_id: str,
    grader_results: Iterable[dict],
) -> int:
    """Write numeric fields from passing graders into skill_baselines.

    Returns the number of metrics written.
    """
    written = 0
    for g in grader_results:
        if not g.get("passed"):
            continue
        details = g.get("details") or {}
        if not isinstance(details, dict):
            continue
        for metric_name, value in _numeric_metrics_from_details(details).items():
            db_writer.upsert_skill_baseline(conn, dict(
                skill_name=skill_name, skill_version=skill_version,
                case_id=case_id, metric_name=metric_name, metric_value=value,
            ))
            written += 1
    return written
