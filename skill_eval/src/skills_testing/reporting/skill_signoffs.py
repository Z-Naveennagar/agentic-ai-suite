"""Versioned skill signoff packages written after ``skills-test run``.

These packages are durable inspection evidence for deciding whether a tested
skill can be promoted from ``staging/`` to production. For each skill in a
completed run, write to ``skill_signoffs_root/<skill_name>_summary/``:

- ``<skill_name>/`` -- the installed skill content (``SKILL.md``, ...) as
  it was actually tested, copied in directly -- always the latest
  snapshot, not versioned.
- ``report/`` -- everything *generated* by this module, kept out of the
  skill-content directory:
    - ``report.html`` (v1) / ``report_v2.html``, ``report_v3.html``, ...
      on repeat runs of the same skill -- one file per run, never
      overwritten.
    - ``README.md`` -- an environment block (client/model/Vivado version,
      from the latest run) plus a run-history table that gains one row
      per run.

See ``core/integration_runner.py`` (call site, ``--no-skill-signoffs``) and
``reporting/dashboard.py:render_skill_run_report`` (the report itself).
"""

from __future__ import annotations

import re
import shutil
import sqlite3
from pathlib import Path

from .dashboard import _per_run_rows_for_skill, render_skill_run_report

_VERSION_RE = re.compile(r"^report(?:_v(\d+))?\.html$")

# New header emitted by the 2026-08 redesign: aggregate_score replaces T2 mean
# and adds stddev. Old rows (with the T2 mean header) are preserved verbatim
# via ``_existing_table_rows`` -- they just appear under the new header block,
# which is fine since Markdown tables don't validate cell count.
_TABLE_HEADER = (
    "| Version | Run | Timestamp | Client / Model | Status | Pass rate"
    " | Score mean | Score σ | Cost | Tokens |\n"
    "|---|---|---|---|---|---|---|---|---|---|\n"
)

# Sentinel used to detect old-format README tables so their rows are still
# preserved even though the header changed.
_OLD_TABLE_HEADER_PREFIX = "| Version | Run | Timestamp |"


def _next_report_filename(report_dir: Path) -> tuple[int, str]:
    """Return (version, filename) for the next report in *report_dir*.

    v1 is unsuffixed (``report.html``); v2+ get ``report_v{N}.html``.
    Derived by scanning what's actually on disk rather than a stored
    counter, so a manually renamed/deleted file can't leave the next write
    pointing at a stale number.
    """
    highest = 0
    if report_dir.is_dir():
        for entry in report_dir.iterdir():
            m = _VERSION_RE.match(entry.name)
            if m:
                highest = max(highest, int(m.group(1)) if m.group(1) else 1)
    version = highest + 1
    filename = "report.html" if version == 1 else f"report_v{version}.html"
    return version, filename


def _copy_installed_skill(skill_name: str, claude_skills_dir: Path, dest_dir: Path) -> bool:
    """Overlay the installed (actually-tested) skill content into
    *dest_dir* -- always the latest snapshot, never versioned; history
    lives in report.html/README.md instead. Returns False without copying
    anything if the skill isn't installed there (e.g. install was skipped
    before this run)."""
    src = claude_skills_dir / skill_name
    if not src.is_dir():
        return False
    shutil.copytree(src, dest_dir, dirs_exist_ok=True)
    return True


def _aggregate(rows: list[sqlite3.Row]) -> dict:
    """Minimal metrics for the README -- deliberately not
    ``dashboard._aggregate``, which also computes power/hallucination
    breakdowns that report.html already renders in full.

    Uses ``aggregate_score`` as the primary signoff metric (COALESCE'd to
    ``t2_score`` in ``_per_run_rows``; this module receives those rows so
    the fallback is already baked in).
    """
    import statistics as _stats
    n = len(rows)
    n_pass = sum(1 for r in rows if r["status"] == "PASS")
    n_fail = sum(1 for r in rows if r["status"] in ("FAIL", "ERROR"))
    n_skip = sum(1 for r in rows if r["status"] == "SKIPPED")

    # aggregate_score is COALESCE(aggregate_score, t2_score) from _per_run_rows.
    score_vals: list[float] = []
    for r in rows:
        try:
            v = r["aggregate_score"]
        except (IndexError, KeyError):
            v = None
        if v is None:
            try:
                v = r["t2_score"]
            except (IndexError, KeyError):
                v = None
        if v is not None:
            score_vals.append(float(v))

    avg_score = (sum(score_vals) / len(score_vals)) if score_vals else None
    stdev_score = (
        _stats.pstdev(score_vals) if len(score_vals) > 1 else 0.0
    ) if score_vals else None

    return {
        "n": n, "n_pass": n_pass, "n_fail": n_fail, "n_skip": n_skip,
        "pr": (n_pass / n) if n else 0.0,
        "avg_score": avg_score,
        "stdev_score": stdev_score,
        # Keep legacy key so existing callers that read avg_t2 still work.
        "avg_t2": avg_score,
        "cost": sum((r["cost_usd"] or 0.0) for r in rows),
        "tokens": sum((r["prompt_tokens"] or 0) + (r["output_tokens"] or 0) for r in rows),
    }


def _status_summary(agg: dict) -> str:
    if agg["n"] == 0:
        return "NO RESULTS"
    if agg["n_fail"] == 0 and agg["n_skip"] == 0:
        return "PASS"
    if agg["n_pass"] == 0:
        return "FAIL"
    return "MIXED"


def _environment_lines(rows: list[sqlite3.Row]) -> str:
    clients = sorted({r["client"] for r in rows if r["client"]})
    models = sorted({r["model"] for r in rows if r["model"]})
    vivado = sorted({r["vivado_version"] for r in rows if r["vivado_version"]})
    return (
        f"- **Client(s):** {', '.join(clients) or '—'}\n"
        f"- **Model(s):** {', '.join(models) or '—'}\n"
        f"- **Vivado version:** {', '.join(vivado) or '—'}"
    )


def _existing_table_rows(readme_path: Path) -> list[str]:
    """Prior '| ... |' data rows from an existing README's run-history
    table, oldest first, preserved verbatim across re-renders.

    Handles both the old (T2 mean) and new (Score mean / Score σ) header
    formats: any header line that starts with ``_OLD_TABLE_HEADER_PREFIX``
    and is followed by a separator line (`|---|...`) introduces the data
    rows we want to preserve.  The caller re-emits the new header above
    all preserved rows, so old rows survive header changes gracefully.
    """
    if not readme_path.is_file():
        return []
    text = readme_path.read_text()
    lines = text.splitlines()
    data_rows: list[str] = []

    # Fast path: exact new header match.
    if _TABLE_HEADER in text:
        after = text.split(_TABLE_HEADER, 1)[1]
        for line in after.splitlines():
            line = line.strip()
            if not line.startswith("|"):
                break
            data_rows.append(line)
        return data_rows

    # Slow path: scan for any header line that starts with the common prefix
    # (old format). Extract data rows that follow the separator line.
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith(_OLD_TABLE_HEADER_PREFIX):
            continue
        # Next non-empty line should be the separator (|---|---|...)
        sep_idx = i + 1
        while sep_idx < len(lines) and not lines[sep_idx].strip():
            sep_idx += 1
        if sep_idx >= len(lines):
            continue
        sep = lines[sep_idx].strip()
        if not (sep.startswith("|---") or sep.startswith("|:---")):
            continue
        # Collect data rows after the separator.
        for data_line in lines[sep_idx + 1:]:
            dl = data_line.strip()
            if not dl.startswith("|"):
                break
            data_rows.append(dl)
        break

    return data_rows


def _lifecycle_evidence(
    conn: sqlite3.Connection | None,
    skill_name: str,
) -> str:
    """Return a Markdown snippet with the latest lifecycle state for
    *skill_name* from ``skill_lifecycle_evaluations``, or an empty string
    when the table doesn't exist / has no row for this skill.

    Queried defensively -- the table is created by another agent's migration
    and may not exist yet.
    """
    if conn is None:
        return ""
    try:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table'"
            " AND name='skill_lifecycle_evaluations'"
        ).fetchone()
        if not exists:
            return ""
        row = conn.execute("""
            SELECT lifecycle_state, aggregate_score_mean, aggregate_score_stdev,
                   pass_rate, n_reps, transition_reason, evaluated_at
              FROM skill_lifecycle_evaluations
             WHERE skill_name = ?
             ORDER BY COALESCE(evaluated_at, '') DESC
             LIMIT 1
        """, (skill_name,)).fetchone()
        if not row:
            return ""
        state = row[0] or "—"
        mean = row[1]
        stdev = row[2]
        pr = row[3]
        n_reps = row[4]
        reason = row[5] or ""
        evat = (row[6] or "")[:19].replace("T", " ")
        score_txt = (
            f"{float(mean):.3f}"
            + (f" ± {float(stdev):.3f}" if stdev is not None else "")
            if mean is not None else "—"
        )
        pr_txt = f"{float(pr):.0%}" if pr is not None else "—"
        reps_txt = f"N={n_reps}" if n_reps is not None else ""
        parts = [f"score {score_txt}", f"pass {pr_txt}"]
        if reps_txt:
            parts.append(reps_txt)
        if reason:
            parts.append(reason)
        return (
            f"\n## Lifecycle\n\n"
            f"**{state}** ({evat}) — {', '.join(parts)}\n"
        )
    except Exception:
        return ""


def _write_readme(
    readme_path: Path, *, skill_name: str, version: int, run_id: str,
    rows: list[sqlite3.Row], agg: dict,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Write (or update) the run-history README.

    The new header uses ``Score mean`` and ``Score σ`` instead of
    ``T2 mean``.  Old rows written under the previous header are preserved
    verbatim via ``_existing_table_rows``, which recognises both formats.
    A lifecycle evidence block is appended when ``conn`` is provided and the
    ``skill_lifecycle_evaluations`` table is present.
    """
    ts = (rows[0]["timestamp"] if rows else "") or ""
    clients_models = ", ".join(sorted({
        f"{r['client']}/{r['model']}" for r in rows if r["client"] or r["model"]
    })) or "—"
    pass_rate = f"{agg['pr']:.0%} ({agg['n_pass']}/{agg['n']})" if agg["n"] else "—"
    score_mean = f"{agg['avg_score']:.3f}" if agg.get("avg_score") is not None else "—"
    score_stdev = (
        f"{agg['stdev_score']:.3f}" if agg.get("stdev_score") is not None else "—"
    )
    cost = f"${agg['cost']:.4f}" if agg["cost"] else "—"
    tokens = f"{agg['tokens']:,}" if agg["n"] else "—"
    new_row = (
        f"| v{version} | `{run_id[:8]}` | {ts[:19].replace('T', ' ')} | "
        f"{clients_models} | {_status_summary(agg)} | {pass_rate}"
        f" | {score_mean} | {score_stdev} | {cost} | {tokens} |"
    )
    prior_rows = _existing_table_rows(readme_path)
    lifecycle_section = _lifecycle_evidence(conn, skill_name)
    content = (
        f"# {skill_name} — signoff history\n\n"
        f"## Environment (latest run)\n\n{_environment_lines(rows)}\n"
        + lifecycle_section +
        f"\n## Run history\n\n{_TABLE_HEADER}"
        + "\n".join(prior_rows + [new_row]) + "\n"
    )
    readme_path.write_text(content)


def write_skill_signoffs(
    db_path: str, run_id: str, skill_names: list[str], *,
    skill_signoffs_root: Path, claude_skills_dir: Path,
) -> list[str]:
    """Write one review-ready package for each evaluated skill in *run_id*.

    Each package preserves the tested skill snapshot, a versioned report, and
    cumulative run history used for staging-to-production promotion review.
    Returns one human-readable log line per
    skill actually written (mirrors ``skill_repo.install_reports``); a
    skill with zero rows for this run (e.g. every case SKIPPED before a DB
    write) is left alone -- there's nothing to snapshot.
    """
    log: list[str] = []
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        for skill_name in sorted(skill_names):
            rows = _per_run_rows_for_skill(conn, run_id, skill_name)
            if not rows:
                continue
            summary_dir = Path(skill_signoffs_root) / f"{skill_name}_summary"
            content_dir = summary_dir / skill_name
            report_dir = summary_dir / "report"
            report_dir.mkdir(parents=True, exist_ok=True)

            version, filename = _next_report_filename(report_dir)
            html = render_skill_run_report(conn, skill_name, run_id)
            (report_dir / filename).write_text(html)

            copied = _copy_installed_skill(skill_name, Path(claude_skills_dir), content_dir)

            _write_readme(
                report_dir / "README.md", skill_name=skill_name, version=version,
                run_id=run_id, rows=rows, agg=_aggregate(rows),
                conn=conn,
            )

            note = "" if copied else " (skill content not installed -- snapshot skipped)"
            log.append(f"{skill_name}: {filename}{note}")
    finally:
        conn.close()
    return log
