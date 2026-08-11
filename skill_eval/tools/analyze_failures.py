#!/usr/bin/env python3
"""
Failure Root-Cause Analyzer for Skill Test Results.

Reads the results.db SQLite database, classifies every failed test run
into a root-cause category, and writes a Markdown report with:
  - Per-skill failure summaries with root causes
  - Per-client/model capability analysis
  - Grader-level failure heatmap
  - Actionable skill improvement suggestions

Usage:
    python tools/analyze_failures.py [OPTIONS]

Options:
    --db PATH           Path to results.db  (default: results.db)
    --run-ids ID,...     Comma-separated run_ids to analyze (default: all)
    --out PATH          Output Markdown file (default: reports/failure_analysis.md)
    --failures-only     Only include failed runs in the report
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class GraderFailure:
    grader_id: str
    grader_type: str
    score: float
    details: dict[str, Any]
    root_cause: str = ""


@dataclass
class TestFailure:
    test_id: int
    run_id: str
    skill_name: str
    case_id: str
    client: str
    model: str
    aggregate_score: float
    wall_clock_s: float
    prompt_tokens: int
    output_tokens: int
    error: str | None
    grader_failures: list[GraderFailure] = field(default_factory=list)
    grader_passes: list[str] = field(default_factory=list)
    root_cause: str = ""
    judge_grade: str = ""
    judge_rationale: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Root-cause classification
# ---------------------------------------------------------------------------

# Ordered by priority: first match wins.
ROOT_CAUSE_RULES: list[tuple[str, str]] = [
    ("AGENT_TIMEOUT",
     "Agent was killed or timed out before completing the task"),
    ("ZERO_TOKENS",
     "Agent produced zero output tokens -- likely a client launch or routing failure"),
    ("WORKSPACE_NAVIGATION",
     "Agent could not locate workspace files (ls/find returned empty)"),
    ("VIVADO_CRASH",
     "Vivado process crashed (segfault) during execution"),
    ("MCP_TIMEOUT",
     "MCP request was cancelled or timed out mid-execution"),
    ("STALE_SESSION",
     "Agent connected to a stale Vivado session from a different workspace"),
    ("ALL_ARTIFACTS_MISSING",
     "Agent produced none of the required output artifacts"),
    ("PARTIAL_ARTIFACTS",
     "Agent produced some artifacts but key ones are missing or incomplete"),
    ("WNS_REGRESSION",
     "Timing closure strategy made WNS worse (regression vs baseline)"),
    ("ORACLE_MISMATCH",
     "Oracle/diagnosis match failed -- agent's analysis diverged from expected"),
    ("VERIFY_STUB",
     "verify_by_rerun grader has no registered verifier (infrastructure gap)"),
    ("SCHEMA_PARTIAL",
     "Report schema checks partially passed -- format deviations"),
    ("NEAR_PASS",
     "Score >= 0.8 but failed on a strict grader (close to passing)"),
    ("UNKNOWN",
     "Could not classify -- manual inspection recommended"),
]


def _classify_failure(tf: TestFailure) -> str:
    """Assign a single root-cause label to a TestFailure."""
    if tf.error and ("killed" in tf.error.lower() or "timeout" in tf.error.lower()):
        return "AGENT_TIMEOUT"

    if (tf.prompt_tokens or 0) == 0 and (tf.output_tokens or 0) == 0:
        return "ZERO_TOKENS"

    details_blob = json.dumps(
        [g.details for g in tf.grader_failures], default=str
    ).lower()

    if "could not locate" in details_blob or "no output" in details_blob:
        return "WORKSPACE_NAVIGATION"

    rationale_blob = json.dumps(tf.judge_rationale, default=str).lower()
    if "segfault" in rationale_blob or "crash" in rationale_blob:
        return "VIVADO_CRASH"
    if "navigate" in rationale_blob and "failed" in rationale_blob:
        return "WORKSPACE_NAVIGATION"
    if "cancel" in rationale_blob or "timeout" in rationale_blob:
        return "MCP_TIMEOUT"
    if "stale session" in rationale_blob or "different workspace" in rationale_blob:
        return "STALE_SESSION"

    artifact_graders = [
        g for g in tf.grader_failures
        if g.grader_type in ("artifact_exists", "artifact_valid")
    ]
    artifact_passes = [
        gid for gid in tf.grader_passes
        if "exist" in gid.lower() or "parse" in gid.lower()
    ]

    if artifact_graders and not artifact_passes:
        return "ALL_ARTIFACTS_MISSING"

    wns_graders = [
        g for g in tf.grader_failures
        if "wns" in g.grader_id.lower() or "regress" in g.grader_id.lower()
    ]
    for g in wns_graders:
        val = g.details.get("value")
        if val is not None and float(val) < -0.05:
            return "WNS_REGRESSION"

    if artifact_graders and artifact_passes:
        return "PARTIAL_ARTIFACTS"

    verify_only = [
        g for g in tf.grader_failures
        if "verify_by_rerun" in g.grader_id
    ]
    oracle_only = [
        g for g in tf.grader_failures
        if "oracle" in g.grader_id
    ]

    if verify_only and len(verify_only) == len(tf.grader_failures):
        return "VERIFY_STUB"

    if oracle_only and len(oracle_only) == len(tf.grader_failures):
        return "ORACLE_MISMATCH"

    if tf.aggregate_score >= 0.8:
        return "NEAR_PASS"

    schema_graders = [
        g for g in tf.grader_failures
        if "schema" in g.grader_id.lower()
    ]
    if schema_graders and len(schema_graders) == len(tf.grader_failures):
        return "SCHEMA_PARTIAL"

    if len(tf.grader_failures) == 1 and "oracle" in tf.grader_failures[0].grader_id:
        return "ORACLE_MISMATCH"

    if tf.aggregate_score >= 0.8:
        return "NEAR_PASS"

    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_failures(db_path: str, run_ids: list[str] | None = None) -> list[TestFailure]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    where = "WHERE r.status = 'FAIL'"
    params: list[str] = []
    if run_ids:
        placeholders = ",".join("?" for _ in run_ids)
        where += f" AND r.run_id IN ({placeholders})"
        params = run_ids

    rows = conn.execute(f"""
        SELECT r.id, r.run_id, r.skill_name, r.case_id, r.client, r.model,
               r.aggregate_score, r.wall_clock_s,
               r.prompt_tokens, r.output_tokens, r.error
        FROM skill_test_results r
        {where}
        ORDER BY r.case_id, r.client, r.model
    """, params).fetchall()

    failures: list[TestFailure] = []
    for row in rows:
        tf = TestFailure(
            test_id=row["id"],
            run_id=row["run_id"],
            skill_name=row["skill_name"],
            case_id=row["case_id"],
            client=row["client"],
            model=row["model"],
            aggregate_score=row["aggregate_score"] or 0.0,
            wall_clock_s=row["wall_clock_s"] or 0.0,
            prompt_tokens=row["prompt_tokens"] or 0,
            output_tokens=row["output_tokens"] or 0,
            error=row["error"],
        )

        graders = conn.execute("""
            SELECT grader_id, grader_type, passed, score, details
            FROM skill_grader_results
            WHERE skill_test_id = ?
            ORDER BY id
        """, (row["id"],)).fetchall()

        for g in graders:
            details = {}
            if g["details"]:
                try:
                    details = json.loads(g["details"]) if isinstance(g["details"], str) else g["details"]
                except (json.JSONDecodeError, TypeError):
                    details = {"raw": str(g["details"])[:500]}

            if g["passed"]:
                tf.grader_passes.append(g["grader_id"])
            else:
                gf = GraderFailure(
                    grader_id=g["grader_id"],
                    grader_type=g["grader_type"] or "",
                    score=g["score"] or 0.0,
                    details=details,
                )
                tf.grader_failures.append(gf)

        judge = conn.execute("""
            SELECT letter_grade, rationale
            FROM skill_judge_results
            WHERE skill_test_id = ?
            ORDER BY id DESC LIMIT 1
        """, (row["id"],)).fetchone()

        if judge:
            tf.judge_grade = judge["letter_grade"] or ""
            rat = judge["rationale"] or ""
            if isinstance(rat, str) and rat.strip():
                try:
                    tf.judge_rationale = json.loads(rat)
                except (json.JSONDecodeError, TypeError):
                    tf.judge_rationale = {"raw": rat[:500]}

        tf.root_cause = _classify_failure(tf)
        for gf in tf.grader_failures:
            gf.root_cause = tf.root_cause

        failures.append(tf)

    conn.close()
    return failures


def load_passes(db_path: str, run_ids: list[str] | None = None) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    where = "WHERE r.status = 'PASS'"
    params: list[str] = []
    if run_ids:
        placeholders = ",".join("?" for _ in run_ids)
        where += f" AND r.run_id IN ({placeholders})"
        params = run_ids
    rows = conn.execute(f"""
        SELECT r.case_id, r.client, r.model, r.aggregate_score, r.wall_clock_s
        FROM skill_test_results r {where}
        ORDER BY r.case_id, r.client, r.model
    """, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

_CAUSE_DESCRIPTIONS = dict(ROOT_CAUSE_RULES)


def _model_short(model: str) -> str:
    if "/" in model:
        return model.rsplit("/", 1)[-1].split("-GGUF")[0]
    return model


def _pct(n: int, total: int) -> str:
    return f"{100 * n / total:.0f}%" if total else "n/a"


def generate_report(
    failures: list[TestFailure],
    passes: list[dict],
    out_path: str,
) -> str:
    lines: list[str] = []

    def w(text: str = "") -> None:
        lines.append(text)

    w("# Skill Test Failure Analysis Report")
    w()
    w(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    w()

    total_runs = len(failures) + len(passes)
    w("## Executive Summary")
    w()
    w(f"- **Total test executions analyzed:** {total_runs}")
    w(f"- **Passed:** {len(passes)} ({_pct(len(passes), total_runs)})")
    w(f"- **Failed:** {len(failures)} ({_pct(len(failures), total_runs)})")
    w()

    # Root-cause distribution
    cause_counts: Counter[str] = Counter()
    for tf in failures:
        cause_counts[tf.root_cause] += 1

    w("### Root-Cause Distribution")
    w()
    w("| Root Cause | Count | % of Failures | Description |")
    w("|---|---|---|---|")
    for cause, count in cause_counts.most_common():
        desc = _CAUSE_DESCRIPTIONS.get(cause, "")
        w(f"| {cause} | {count} | {_pct(count, len(failures))} | {desc} |")
    w()

    # ---- Per-skill breakdown ----
    w("---")
    w("## Per-Skill Failure Analysis")
    w()

    by_skill: dict[str, list[TestFailure]] = defaultdict(list)
    for tf in failures:
        by_skill[f"{tf.skill_name}/{tf.case_id}"].append(tf)

    pass_by_skill: dict[str, int] = Counter()
    for p in passes:
        pass_by_skill[f"?/{p['case_id']}"] += 1

    for skill_case in sorted(by_skill.keys()):
        skill_failures = by_skill[skill_case]
        skill_name = skill_failures[0].skill_name
        case_id = skill_failures[0].case_id

        w(f"### {skill_name} / {case_id}")
        w()

        skill_causes: Counter[str] = Counter()
        for tf in skill_failures:
            skill_causes[tf.root_cause] += 1

        w("**Failure summary:**")
        w()
        w("| Client | Model | Score | Root Cause | Judge | Wall Clock |")
        w("|---|---|---|---|---|---|")
        for tf in skill_failures:
            w(f"| {tf.client} | {_model_short(tf.model)} | {tf.aggregate_score:.3f} "
              f"| {tf.root_cause} | {tf.judge_grade or 'n/a'} "
              f"| {tf.wall_clock_s:.0f}s |")
        w()

        # Grader failure details
        grader_fails: Counter[str] = Counter()
        grader_details_agg: dict[str, list[str]] = defaultdict(list)
        for tf in skill_failures:
            for gf in tf.grader_failures:
                grader_fails[gf.grader_id] += 1
                reason = gf.details.get("reason", "")
                if not reason and not gf.details.get("present", True):
                    reason = "content not found"
                if not reason:
                    reason = _summarize_detail(gf.details)
                if reason and reason not in grader_details_agg[gf.grader_id]:
                    grader_details_agg[gf.grader_id].append(reason)

        w("**Failed grader checks:**")
        w()
        w("| Grader | Fail Count | Common Reason |")
        w("|---|---|---|")
        for gid, cnt in grader_fails.most_common():
            reasons = "; ".join(grader_details_agg[gid][:3])
            w(f"| `{gid}` | {cnt} | {reasons} |")
        w()

        # Judge rationale themes
        rationale_themes = _extract_rationale_themes(skill_failures)
        if rationale_themes:
            w("**Judge rationale themes:**")
            w()
            for theme in rationale_themes:
                w(f"- {theme}")
            w()

        # Skill improvement suggestions
        suggestions = _suggest_improvements(skill_name, case_id, skill_failures, skill_causes)
        w("**Suggested skill improvements:**")
        w()
        for i, suggestion in enumerate(suggestions, 1):
            w(f"{i}. {suggestion}")
        w()

    # ---- Per-client/model analysis ----
    w("---")
    w("## Client/Model Capability Analysis")
    w()

    model_results: dict[str, dict[str, int]] = defaultdict(lambda: {"pass": 0, "fail": 0})
    for p in passes:
        key = f"{p['client']} / {_model_short(p['model'])}"
        model_results[key]["pass"] += 1
    for tf in failures:
        key = f"{tf.client} / {_model_short(tf.model)}"
        model_results[key]["fail"] += 1

    w("| Client / Model | Pass | Fail | Pass Rate | Dominant Failure Mode |")
    w("|---|---|---|---|---|")
    for key in sorted(model_results.keys()):
        r = model_results[key]
        total = r["pass"] + r["fail"]
        rate = _pct(r["pass"], total)
        dominant = _dominant_cause_for_model(
            key.split(" / ")[0].strip(),
            key.split(" / ")[1].strip(),
            failures,
        )
        w(f"| {key} | {r['pass']} | {r['fail']} | {rate} | {dominant} |")
    w()

    # ---- Grader failure heatmap ----
    w("---")
    w("## Grader Failure Heatmap")
    w()
    w("Which grader checks fail most often across all skills:")
    w()

    all_grader_fails: Counter[str] = Counter()
    for tf in failures:
        for gf in tf.grader_failures:
            all_grader_fails[gf.grader_id] += 1

    w("| Grader Check | Total Failures | Skills Affected |")
    w("|---|---|---|")
    grader_to_skills: dict[str, set[str]] = defaultdict(set)
    for tf in failures:
        for gf in tf.grader_failures:
            grader_to_skills[gf.grader_id].add(tf.case_id)

    for gid, cnt in all_grader_fails.most_common(20):
        skills = ", ".join(sorted(grader_to_skills[gid]))
        w(f"| `{gid}` | {cnt} | {skills} |")
    w()

    # ---- Infrastructure issues ----
    infra_failures = [
        tf for tf in failures
        if tf.root_cause in ("ZERO_TOKENS", "VERIFY_STUB", "AGENT_TIMEOUT")
    ]
    if infra_failures:
        w("---")
        w("## Infrastructure Issues (Not Skill Defects)")
        w()
        w("These failures are caused by test infrastructure rather than skill quality:")
        w()
        for tf in infra_failures:
            w(f"- **{tf.case_id}** ({tf.client}/{_model_short(tf.model)}): "
              f"{_CAUSE_DESCRIPTIONS.get(tf.root_cause, tf.root_cause)}")
            if tf.error:
                w(f"  - Error: {tf.error[:200]}")
        w()

    # ---- Consolidated recommendations ----
    w("---")
    w("## Consolidated Improvement Recommendations")
    w()

    recs = _consolidated_recommendations(failures, cause_counts)
    for priority, rec in enumerate(recs, 1):
        w(f"### {priority}. {rec['title']}")
        w()
        w(f"**Impact:** {rec['impact']}")
        w()
        w(f"**Details:** {rec['details']}")
        w()
        if rec.get("action_items"):
            w("**Action items:**")
            w()
            for item in rec["action_items"]:
                w(f"- {item}")
            w()

    report = "\n".join(lines)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report)
    return report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _summarize_detail(details: dict) -> str:
    if "reason" in details:
        return str(details["reason"])
    if "missing" in details:
        items = details["missing"]
        if isinstance(items, list):
            return f"missing: {', '.join(str(i) for i in items[:3])}"
        return f"missing: {items}"
    if "value" in details and "threshold" in details:
        return f"value={details['value']} vs threshold={details['threshold']}"
    if details.get("present") is False:
        return "content not found"
    return ""


def _extract_rationale_themes(failures: list[TestFailure]) -> list[str]:
    themes: list[str] = []
    seen: set[str] = set()

    for tf in failures:
        for dimension, text in tf.judge_rationale.items():
            if not isinstance(text, str) or len(text) < 20:
                continue
            key_phrase = _extract_key_phrase(text)
            if key_phrase and key_phrase not in seen:
                seen.add(key_phrase)
                themes.append(f"**{dimension}:** {text[:150]}")

    return themes[:6]


def _extract_key_phrase(text: str) -> str:
    text_lower = text.lower()
    phrases = [
        "failed to locate", "never successfully", "could not",
        "did not produce", "never ran", "timed out",
        "crashed", "segfault", "stale session",
        "regressed", "made worse", "no improvement",
    ]
    for p in phrases:
        if p in text_lower:
            return p
    return text[:40] if len(text) > 40 else text


def _dominant_cause_for_model(
    client: str, model_short: str, failures: list[TestFailure],
) -> str:
    causes: Counter[str] = Counter()
    for tf in failures:
        if tf.client == client and _model_short(tf.model) == model_short:
            causes[tf.root_cause] += 1
    if not causes:
        return "n/a"
    top = causes.most_common(1)[0]
    return f"{top[0]} ({top[1]}x)"


def _suggest_improvements(
    skill_name: str,
    case_id: str,
    failures: list[TestFailure],
    cause_counts: Counter[str],
) -> list[str]:
    suggestions: list[str] = []
    causes = set(cause_counts.keys())

    if "ALL_ARTIFACTS_MISSING" in causes or "WORKSPACE_NAVIGATION" in causes:
        suggestions.append(
            "Add an explicit `## Workspace Layout` section to the SKILL.md that lists "
            "expected input file paths relative to the workspace root. Small models "
            "struggle to discover files without explicit directory guidance."
        )
        suggestions.append(
            "Consider adding a pre-check step to the skill that verifies input files "
            "exist before starting the main workflow, with clear error messages if not."
        )

    if "PARTIAL_ARTIFACTS" in causes:
        suggestions.append(
            "Break the skill into smaller, independently verifiable stages. "
            "Each stage should write its own artifact so partial progress is preserved."
        )

    if "WNS_REGRESSION" in causes:
        suggestions.append(
            "Add a guard-rail step that compares post-fix WNS against the baseline "
            "immediately after re-implementation. If WNS regresses, the skill should "
            "revert the constraint changes and try a more conservative strategy."
        )
        suggestions.append(
            "Include example XDC idioms in the skill instructions so the agent "
            "doesn't invent potentially harmful constraints."
        )

    if "ORACLE_MISMATCH" in causes or "NEAR_PASS" in causes:
        near_pass = [tf for tf in failures if tf.root_cause in ("ORACLE_MISMATCH", "NEAR_PASS")]
        if near_pass:
            avg_score = sum(tf.aggregate_score for tf in near_pass) / len(near_pass)
            suggestions.append(
                f"Scores average {avg_score:.2f} for ORACLE_MISMATCH/NEAR_PASS failures. "
                f"Consider relaxing the oracle tolerance or making the `met` field check "
                f"use a range instead of exact match. Also review the `verify_by_rerun` "
                f"grader stub -- registering a real verifier would add pass credit."
            )

    if "VERIFY_STUB" in causes:
        suggestions.append(
            "The `verify_by_rerun.apply` grader always fails because no verifier is "
            "registered. Either implement the Vivado MCP verifier or remove this "
            "grader from the grading spec to avoid penalizing runs that otherwise succeed."
        )

    if "ZERO_TOKENS" in causes:
        zero_clients = {
            tf.client for tf in failures if tf.root_cause == "ZERO_TOKENS"
        }
        suggestions.append(
            f"Client(s) {', '.join(zero_clients)} produced zero output tokens. "
            f"This is likely a client launch failure or MCP routing issue, not a skill "
            f"defect. Investigate the test harness integration for these clients."
        )

    if "MCP_TIMEOUT" in causes or "STALE_SESSION" in causes:
        suggestions.append(
            "Add `## Session Management` instructions to the skill: always start "
            "a new Vivado session (never reuse stale ones), and include retry logic "
            "for MCP timeouts with exponential backoff."
        )

    if case_id == "standard_export" and "ALL_ARTIFACTS_MISSING" in causes:
        suggestions.append(
            "The vivado-revision-control 5-step pipeline is too complex for a "
            "single-shot agent invocation. Consider: (a) providing a pre-written "
            "TCL template in the workspace that the agent fills in, (b) reducing "
            "the pipeline to fewer steps, or (c) providing step-by-step checkpoints."
        )

    if not suggestions:
        suggestions.append(
            "No specific automated suggestions. Review the judge rationales above "
            "for qualitative feedback on the skill execution."
        )

    return suggestions


def _consolidated_recommendations(
    failures: list[TestFailure],
    cause_counts: Counter[str],
) -> list[dict]:
    recs: list[dict] = []

    if cause_counts.get("VERIFY_STUB", 0) > 0:
        recs.append({
            "title": "Fix the `verify_by_rerun` grader stub",
            "impact": f"Would eliminate {cause_counts['VERIFY_STUB']} automatic failures "
                      f"and likely flip some NEAR_PASS runs to PASS",
            "details": "The `verify_by_rerun.apply` grader always returns score=0 "
                       "because no Vivado MCP verifier is registered. This unfairly "
                       "penalizes timing closure runs that otherwise produce valid artifacts.",
            "action_items": [
                "Register a `vivado_mcp` verifier in the grader framework, or",
                "Remove `verify_by_rerun.apply` from timing closure grading_spec.yaml files",
                "Re-run affected timing closure tests after fix to measure true pass rate",
            ],
        })

    zero_count = cause_counts.get("ZERO_TOKENS", 0)
    if zero_count > 0:
        zero_clients = sorted({
            f"{tf.client}/{_model_short(tf.model)}"
            for tf in failures if tf.root_cause == "ZERO_TOKENS"
        })
        recs.append({
            "title": "Fix client launch failures (zero-token runs)",
            "impact": f"{zero_count} test(s) never started -- these are wasted compute",
            "details": f"Clients {', '.join(zero_clients)} produced 0 prompt and 0 output "
                       f"tokens, meaning the agent never received the task or couldn't start.",
            "action_items": [
                "Check that each client binary is on PATH and properly configured",
                "Add a client health-check step before test execution",
                "Add timeout detection and retry logic in the test runner",
            ],
        })

    nav_count = cause_counts.get("WORKSPACE_NAVIGATION", 0) + cause_counts.get("ALL_ARTIFACTS_MISSING", 0)
    if nav_count > 0:
        recs.append({
            "title": "Improve workspace discoverability in skills",
            "impact": f"Would help {nav_count} failures where agents couldn't find inputs",
            "details": "Small local models (Gemma, Qwen) consistently fail to discover "
                       "workspace files. The skill instructions should provide explicit "
                       "paths and directory layouts rather than expecting the agent to "
                       "search for files.",
            "action_items": [
                "Add `## Workspace Layout` sections to each SKILL.md listing exact input paths",
                "Include a `find . -name '*.sv' -o -name '*.xdc'` example in the skill",
                "Consider adding an `inputs/README.txt` to each test case workspace "
                "that describes what files are present",
            ],
        })

    near_count = cause_counts.get("NEAR_PASS", 0) + cause_counts.get("ORACLE_MISMATCH", 0)
    if near_count > 0:
        near_scores = [
            tf.aggregate_score
            for tf in failures
            if tf.root_cause in ("NEAR_PASS", "ORACLE_MISMATCH")
        ]
        avg = sum(near_scores) / len(near_scores) if near_scores else 0
        recs.append({
            "title": "Tighten/relax oracle expectations for timing closure",
            "impact": f"{near_count} runs scored avg {avg:.2f} -- very close to passing",
            "details": "Many timing closure runs produce valid XDC and improve WNS, "
                       "but fail the oracle_diagnosis_matches check. The oracle's `met` "
                       "field and category matching may be too strict for stochastic "
                       "Vivado P&R results.",
            "action_items": [
                "Review expected_diagnosis.yaml -- consider accepting a wider WNS range",
                "Make `met` field a numeric threshold rather than boolean exact match",
                "Add tolerance for category ordering/naming variations",
            ],
        })

    wns_count = cause_counts.get("WNS_REGRESSION", 0)
    if wns_count > 0:
        recs.append({
            "title": "Add WNS regression guard-rails to timing closure skills",
            "impact": f"{wns_count} runs made timing worse",
            "details": "The agent applied constraints that regressed WNS. The skill "
                       "should include a validation step that reverts harmful changes.",
            "action_items": [
                "Add a post-implementation WNS check step to the skill",
                "If WNS regresses, revert to baseline and try fewer/different constraints",
                "Provide a curated list of safe constraint idioms in the skill instructions",
            ],
        })

    complex_skills = [
        tf.case_id for tf in failures
        if tf.case_id == "standard_export" and tf.root_cause == "ALL_ARTIFACTS_MISSING"
    ]
    if complex_skills:
        recs.append({
            "title": "Simplify the standard_export (revision control) skill pipeline",
            "impact": "0% pass rate across all clients -- fundamental skill design issue",
            "details": "The 5-step revision control pipeline (detect flow, analyze sources, "
                       "export, capture settings, generate build.tcl) is too complex for "
                       "single-shot agent execution. Even Opus fails to complete it.",
            "action_items": [
                "Provide a pre-written TCL template that the agent populates",
                "Split into separate sub-skills with checkpoint artifacts",
                "Add worked examples in the SKILL.md showing expected TCL output",
                "Consider providing the helper procedures as a ready-to-source TCL file",
            ],
        })

    if not recs:
        recs.append({
            "title": "No systemic issues found",
            "impact": "Individual failures may need case-by-case investigation",
            "details": "The failures don't cluster into obvious systemic patterns.",
        })

    return recs


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze skill test failures and generate a root-cause report",
    )
    parser.add_argument(
        "--db", default="results.db",
        help="Path to results.db (default: results.db)",
    )
    parser.add_argument(
        "--run-ids", default=None,
        help="Comma-separated run_ids to analyze (default: all)",
    )
    parser.add_argument(
        "--out", default="reports/failure_analysis.md",
        help="Output Markdown file (default: reports/failure_analysis.md)",
    )
    parser.add_argument(
        "--failures-only", action="store_true",
        help="Only show failure data (skip pass context)",
    )
    args = parser.parse_args()

    run_ids = args.run_ids.split(",") if args.run_ids else None

    print(f"Loading failures from {args.db}...", flush=True)
    failures = load_failures(args.db, run_ids)
    passes = [] if args.failures_only else load_passes(args.db, run_ids)

    if not failures:
        print("No failures found. Nothing to analyze.")
        sys.exit(0)

    print(f"Loaded {len(failures)} failures, {len(passes)} passes.", flush=True)
    print("Classifying root causes...", flush=True)

    cause_counts: Counter[str] = Counter(tf.root_cause for tf in failures)
    for cause, count in cause_counts.most_common():
        print(f"  {cause:30s} {count}", flush=True)

    print(f"\nGenerating report -> {args.out}", flush=True)
    report = generate_report(failures, passes, args.out)

    line_count = report.count("\n")
    print(f"Report written: {args.out} ({line_count} lines)", flush=True)


if __name__ == "__main__":
    main()
