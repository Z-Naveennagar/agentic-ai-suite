"""
Skill Testing dashboard tab renderer.

Pure HTML emitted as a string; embedded directly into the static
generate_report.py output. The renderer reads from the skill_test_results,
skill_grader_results, and skill_release_evaluations tables and gracefully
degrades to a friendly empty state when the harness has not yet run any
skill cases.

Layout
------
    [ Run selector and PASS/FAIL/SKIP/cost/runtime summary ]
    [ Interactive consistency tree: skill -> case x client x model ]
    [ Per-repetition prompt, tool, response, and grader details ]
    [ Consistency heatmap and client/model cost comparison ]
    [ Lifecycle decisions with expandable policy evidence ]

The primary view uses repeated skill-enabled runs. Historical database fields
remain readable, but the active dashboard does not present A/B comparisons.

All styling reuses the existing dark-theme CSS classes from
``generate_report.py`` (``.run-selector``, ``.summary``, ``.stat``, plain
``<table>``) plus a small block of skill-tab-local CSS for the tree-view
chrome only. There are no light-on-light inline styles.
"""

from __future__ import annotations

import html as _html
import json
import re
import sqlite3
import statistics
from collections import defaultdict
from urllib.parse import quote

from ..core import session_log as _session_log
from ..graders.trace import tool_calls_detailed as _tool_calls_detailed
from ..graders.trace import final_response_text as _final_response_text


# Palette tokens from generate_report.py's main stylesheet.
_BG       = "#0d1117"
_SURFACE  = "#161b22"
_BORDER   = "#30363d"
_TEXT     = "#e6edf3"
_MUTED    = "#8b949e"
_ACCENT   = "#58a6ff"
_GREEN    = "#2ea043"
_RED      = "#f85149"
_AMBER    = "#d29922"
_GREY     = "#6e7681"


_STATE_COLORS = {
    "KEEP":      _GREEN,
    "WATCH":     _AMBER,
    "DEPRECATE": _RED,
    "REMOVE":    _GREY,
}

_STATUS_FG = {
    "PASS":    _GREEN,
    "FAIL":    _RED,
    "ERROR":   _RED,
    "SKIPPED": _AMBER,
}


# --------------------------------------------------------------- helpers


def _esc(s: object) -> str:
    return _html.escape(str(s if s is not None else ""))


def _fmt_tokens(n: float | int | None) -> str:
    if not n:
        return "0"
    n = float(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return f"{int(n)}"


def _fmt_cost(c: float | None) -> str:
    if c is None or c <= 0:
        return "—"
    # Below $1, 2-decimal rounding loses too much of the value to add up
    # across rows (e.g. per-case costs of $0.011-$0.02 all collapse to
    # "$0.01"/"$0.02" and no longer sum to the displayed run total).
    if c < 1:
        return f"${c:.4f}"
    return f"${c:.2f}"


def _fmt_secs(s: float | None) -> str:
    if not s:
        return "—"
    if s >= 60:
        return f"{int(s // 60)}m {int(s % 60):02d}s"
    return f"{s:.1f} s"


def _model_label(model: str | None) -> str:
    """Compact but recognizable labels for the Skill Testing table."""
    raw = str(model or "")
    lower = raw.lower()
    if "gemma-4" in lower:
        return "Gemma 4 local"
    if "qwen3.5" in lower or "qwen3-5" in lower:
        return "Qwen3.5 local"
    if raw.startswith("lemonade/"):
        return raw.split("/", 1)[1].replace("-GGUF", "")
    return raw


def _fmt_method(method: str | None, power_metrics: dict | None = None) -> str:
    """Human label for the cost traceability tag stored in results.db.

    When ``method`` is the new ``local_measured:<machine>`` tag, the label
    embeds the actual sampled active/idle watts from ``power_metrics`` so
    the dashboard tells you how much of the bill came from real draw vs
    the post-test idle floor.
    """
    if not method:
        return "—"
    if method.startswith("local_measured:"):
        machine = method.split(":", 1)[1].replace("_", " ").title()
        if isinstance(power_metrics, dict):
            avg_w = power_metrics.get("avg_active_w")
            base_w = power_metrics.get("baseline_w")
            peak_w = power_metrics.get("peak_w")
            parts = []
            if avg_w is not None:
                parts.append(f"active {avg_w:.1f} W")
            if base_w is not None:
                parts.append(f"idle {base_w:.1f} W")
            if peak_w is not None:
                parts.append(f"peak {peak_w:.1f} W")
            if parts:
                return f"{machine} measured power ({', '.join(parts)})"
        return f"{machine} measured power"
    if method == "local_calendar_amortized:strix_halo":
        return "Strix Halo local amortized cost (config fallback)"
    if method.startswith("local_calendar_amortized:"):
        machine = method.split(":", 1)[1].replace("_", " ").title()
        return f"{machine} local amortized cost (config fallback)"
    if method == "api_priced_with_cache":
        return "repo pricing with prompt-cache rates"
    if method == "api_priced":
        return "repo pricing per input/output token"
    if method == "cloud_equivalent_amortized_unknown_model":
        return "repo fallback for unknown model pricing"
    if method == "cloud_equivalent_amortized":
        return "cloud-equivalent amortized placeholder"
    return method.replace("_", " ")


def _heatmap_color(lift_pp: float | None) -> str:
    """Translucent green/amber/red for use on the dark surface."""
    if lift_pp is None:
        return "transparent"
    if lift_pp >= 8.0:
        return "rgba(46,160,67,0.20)"   # green
    if lift_pp >= 0.0:
        return "rgba(210,153,34,0.20)"  # amber
    return "rgba(248,81,73,0.20)"       # red


def _status_pill(status: str, count_text: str = "") -> str:
    fg = _STATUS_FG.get(status, _MUTED)
    extra = (
        f' <span style="color:{_MUTED}; font-size:11px; font-weight:400;">'
        f'{_esc(count_text)}</span>' if count_text else ''
    )
    return (
        f'<span style="display:inline-block; padding:1px 8px; '
        f'border:1px solid {fg}; color:{fg}; '
        f'border-radius:10px; font-size:11px; font-weight:600; '
        f'letter-spacing:.5px;">{_esc(status)}</span>{extra}'
    )


def _parse_jsonish(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    text = str(value)
    try:
        return json.loads(text)
    except Exception:
        return text


def _fmt_plain_detail(value: object, *, max_len: int = 220) -> str:
    parsed = _parse_jsonish(value)
    if isinstance(parsed, dict):
        bits: list[str] = []
        for key, val in _detail_items(parsed):
            if isinstance(val, (dict, list)):
                val = json.dumps(val, default=str)
            if isinstance(val, bool):
                val = "Yes" if val else "No"
            bits.append(f"{key}: {val}")
        text = "; ".join(bits)
    elif isinstance(parsed, list):
        text = "; ".join(str(x) for x in parsed[:6])
        if len(parsed) > 6:
            text += f"; ... +{len(parsed) - 6} more"
    else:
        text = str(parsed or "")
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text


def _expandable(text: object, *, limit: int = 220) -> str:
    """Render ``text`` with an inline "more/less" toggle when it is long.

    Returns escaped HTML. Text at or below ``limit`` characters is returned
    inline unchanged; longer text becomes a pure-CSS ``<details>`` disclosure
    whose summary shows a truncated preview + "more", expanding in place to the
    full text + "less" (no JavaScript required).
    """
    s = str(text or "")
    if len(s) <= limit:
        return _esc(s)
    preview = s[:limit].rstrip()
    return (
        '<details class="expand"><summary>'
        f'<span class="short">{_esc(preview)}…</span>'
        f'<span class="full">{_esc(s)}</span>'
        '<span class="tog"></span></summary></details>'
    )


_SESSION_LOG_CFG = _session_log.SessionLogConfig()


def _load_session_log(conn: sqlite3.Connection, rec: sqlite3.Row) -> dict | None:
    """Load the per-test session-log JSON for *rec*, if one was written.

    The path is fully reconstructible from columns already on the
    skill_test_results row -- no new capture/copy needed. Returns None for
    older runs, session_log-disabled runs, or any read/parse failure (the
    dashboard degrades gracefully rather than erroring the whole tab).
    """
    try:
        sdir = _session_log.session_dir(rec["run_id"], conn, _SESSION_LOG_CFG)
        stem = _session_log.test_log_stem(
            skill_name=rec["skill_name"], case_id=rec["case_id"],
            with_skill=bool(rec["with_skill"]),
            replication_index=rec["replication_index"],
            client=rec["client"], model=rec["model"],
        )
        log_path = sdir / f"{stem}.json"
        if not log_path.is_file():
            return None
        data = json.loads(log_path.read_text())
        if isinstance(data, dict):
            # Path relative to the session-log root, for the download link
            # (served by generate_report's /logs/<rel> route).
            data["_log_rel"] = f"{sdir.name}/{stem}.json"
        return data
    except Exception:
        return None


def _detail_items(parsed: dict) -> list[tuple[str, object]]:
    """Keep grader details compact and useful in a narrow dashboard cell."""
    items: list[tuple[str, object]] = []

    if "actual_size" in parsed:
        items.append(("size", _fmt_bytes(parsed.get("actual_size"))))
    if "min_size_bytes" in parsed:
        items.append(("min", _fmt_bytes(parsed.get("min_size_bytes"))))

    # `path` is often an enormous scratch absolute path. It is rarely the
    # interesting part of the grader result, so show only a repo-like suffix.
    path = parsed.get("path")
    if path and not items:
        items.append(("file", _short_path(str(path))))

    for key in ("present", "match", "substring", "pattern", "reason"):
        if key in parsed:
            items.append((key, parsed[key]))

    if items:
        return items
    return list(parsed.items())[:5]


def _fmt_bytes(value: object) -> str:
    try:
        n = float(value)
    except Exception:
        return str(value)
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{int(n)} B"


def _short_path(path: str) -> str:
    for marker in ("/outputs/", "/inputs/"):
        if marker in path:
            return marker.strip("/") + "/" + path.split(marker, 1)[1]
    parts = [p for p in path.split("/") if p]
    if len(parts) <= 3:
        return path
    return ".../" + "/".join(parts[-3:])


# ---------------------------------------------------------------- runs


def _list_runs(conn: sqlite3.Connection) -> list[tuple[str, str, int]]:
    return conn.execute("""
        SELECT run_id, MAX(timestamp) AS ts, COUNT(*) AS n
          FROM skill_test_results
         GROUP BY run_id
         ORDER BY ts DESC
    """).fetchall()


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """True if *table*.*column* is present in the live SQLite schema."""
    try:
        cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.OperationalError:
        return False
    # PRAGMA rows are (cid, name, type, notnull, dflt, pk)
    return any((row[1] if not isinstance(row, sqlite3.Row) else row["name"])
               == column for row in cols)


# ============================================================ entrypoint


def render_skill_tab(conn: sqlite3.Connection) -> str:
    """Return an HTML fragment (no <html> wrapper). Always non-empty.

    Layout (single tab -- A/B comparison removed per 2026-08 redesign):

        [ Run selector ]
        [ Headline stat tiles: pass/fail/skip/halluc/cost/wall/aggregate-score ]
        [ Consistency tree: skill → case × model groups, each aggregated
          over replications into pass-rate + aggregate_score mean/σ/status ]
        [ Consistency heatmap + model-comparison chart ]
        [ Lifecycle cards: skill_lifecycle_evaluations (defensive) ]
        [ Lifecycle callouts: skill_release_evaluations ]
    """
    # Local row-factory so column-name access works regardless of caller.
    conn.row_factory = sqlite3.Row

    parts: list[str] = ['<h2>Skill Testing</h2>']

    n_results = conn.execute(
        "SELECT COUNT(*) FROM skill_test_results"
    ).fetchone()[0]
    n_release = conn.execute(
        "SELECT COUNT(*) FROM skill_release_evaluations"
    ).fetchone()[0]

    if n_results == 0 and n_release == 0:
        parts.append(_render_empty_state())
        return "\n".join(parts)

    runs = _list_runs(conn)

    parts.append(_render_local_css())

    # Single view: Consistency across iterations & models.
    # A/B tab is removed -- the with-skill-only consistency view is the
    # canonical signoff signal per the 2026-08 redesign.
    cons: list[str] = []
    cons.append(_render_consistency_intro())
    cons.append(_render_run_selector(
        runs, select_id="consistency-run-select",
        onchange="consistencySelectRun"))
    for i, (run_id, ts, n_rows) in enumerate(runs):
        cons.append(_render_consistency_run_panel(conn, run_id, ts, n_rows,
                                                  hidden=(i != 0)))
    # Heatmap + model-comparison chart, both scoped to the selected run and
    # both placed after the tree. They live in their own run-keyed divs (a
    # separate attribute from data-consistency-run) purely so they can sit
    # below the tree in the DOM while still switching with the one run
    # selector above (see consistencySelectRun in _render_skill_switcher_js).
    for i, (run_id, ts, n_rows) in enumerate(runs):
        rows = _per_run_rows(conn, run_id)
        style = ' style="display:none;"' if i != 0 else ''
        cons.append(
            f'<div data-cmp-chart-run="{_esc(run_id)}"{style}>'
            f'{_render_consistency_heatmap(conn, run_id=run_id)}'
            f'{_render_model_comparison_chart(rows)}</div>'
        )
    parts.extend(cons)

    # Lifecycle cards from the new skill_lifecycle_evaluations table (queried
    # defensively -- the table may not exist yet if the migration hasn't run).
    parts.append(_render_lifecycle_cards(conn))

    # Legacy lifecycle callouts from skill_release_evaluations (A/B-era table
    # still populated by lifecycle.py; rendered as a secondary section until
    # the new table replaces it completely).

    parts.append(_render_skill_switcher_js())
    return "\n".join(parts)


def _render_tab_bar() -> str:
    # A/B Comparison tab is intentionally hidden: the current suites run the
    # with-skill arm only (no no-skill arm to compare against), so the
    # Consistency-across-iterations-&-models view is the sole meaningful tab
    # and is shown by default. To restore A/B, re-add its button here and flip
    # the default-visible divs in render_skill_tab().
    return (
        '<div class="skill-tabs">'
        '<button class="skill-tab-btn active" data-tab-target="consistency" '
        'onclick="skillShowTab(\'consistency\')">'
        'Consistency across iterations &amp; models</button>'
        '</div>'
    )


# --------------------------------------------------------- empty state


def _render_empty_state() -> str:
    return (
        f'<div style="padding:1.5em; border:1px dashed {_BORDER}; '
        f'border-radius:8px; color:{_MUTED}; background:{_SURFACE};">'
        f'There are no skill_test_results yet. Run '
        f'<code>make skill-smoke</code> or '
        f'<code>python3 test_skill_integration.py</code> '
        f'to populate this tab.'
        f'</div>'
    )


# ------------------------------------------------------------- local css


def _render_local_css() -> str:
    """Tree-view chrome only. Everything else reuses the global dark theme."""
    return f"""
<style>
  .skill-tree-wrap {{ height: 70vh; min-height: 260px; max-height: none;
                       resize: vertical; overflow: auto;
                       border: 1px solid {_BORDER}; border-radius: 8px; }}
  .tree-resize-hint {{ color:{_MUTED}; font-size:11px; margin:-3px 0 7px;
                       text-align:right; }}
  .lifecycle-evidence {{ margin-top:7px; border:1px solid {_BORDER};
                         border-radius:5px; background:{_BG}; }}
  .lifecycle-evidence > summary {{ cursor:pointer; padding:5px 7px;
                                   color:{_ACCENT}; font-size:11px; }}
  .lifecycle-evidence .body {{ padding:0 8px 8px; font-size:11px;
                              color:{_MUTED}; line-height:1.55; }}
  .lifecycle-evidence-grid {{ display:grid;
      grid-template-columns:repeat(auto-fit,minmax(145px,1fr)); gap:4px 10px; }}
  .lifecycle-evidence .gate-pass {{ color:{_GREEN}; }}
  .lifecycle-evidence .gate-fail {{ color:{_RED}; }}
  .skill-tree {{ width: 100%; min-width: 980px; table-layout: fixed;
                  border-collapse: collapse; background: {_SURFACE};
                  font-variant-numeric: tabular-nums; }}
  .skill-tree th {{ position: relative; overflow: hidden; }}
  .col-resizer {{ position:absolute; top:0; right:-3px; width:7px; height:100%;
                   cursor:col-resize; user-select:none; z-index:2; }}
  .cell-sub {{ display:block; color:{_MUTED}; font-size:10px;
               white-space:nowrap; margin-top:2px; }}
  .skill-tree th {{ background: {_SURFACE}; color: {_MUTED};
                    padding: 10px 12px; text-align: left;
                    border-bottom: 2px solid {_BORDER};
                    font-weight: 600; font-size: 0.85em; position: sticky;
                    top: 0; z-index: 1; }}
  .skill-tree td {{ padding: 8px 12px; border-bottom: 1px solid {_BORDER};
                    color: {_TEXT}; font-size: 0.88em; vertical-align: top; }}
  .skill-tree tr:last-child td {{ border-bottom: none; }}
  .skill-tree .num {{ text-align: right; }}
  .skill-tree .ctr {{ text-align: center; }}

  .skill-tree .skill-row {{ cursor: pointer; background: {_BG}; }}
  .skill-tree .skill-row:hover {{ background: {_SURFACE}; }}
  .skill-tree .skill-row td {{ font-weight: 600; }}
  .skill-tree .skill-row .name {{ color: {_TEXT}; }}

  .skill-tree .arm-row {{ display: none; background: {_SURFACE}; }}
  .skill-tree .arm-row.open {{ display: table-row; }}
  .skill-tree .arm-row td.arm-name {{ padding-left: 36px; color: {_MUTED}; }}
  .skill-tree .arm-row td.arm-name .case {{ color: {_TEXT}; font-weight: 500; }}

  .skill-tree .grader-row {{ display: none; background: {_BG}; }}
  .skill-tree .grader-row.open {{ display: table-row; }}
  .skill-tree .grader-row > td {{ padding: 0 12px 12px 56px; }}
  .skill-tree .grader-row > td > div {{ max-height: 60vh; min-height: 140px;
                                       resize: vertical; overflow: auto; }}
  .cons-filter-bar {{ display:flex; gap:8px; align-items:center; flex-wrap:wrap;
                      margin:8px 0; padding:8px; background:{_SURFACE};
                      border:1px solid {_BORDER}; border-radius:8px; }}
  .cons-filter-bar input, .cons-filter-bar select, .cons-filter-bar button {{
      background:{_BG}; color:{_TEXT}; border:1px solid {_BORDER};
      border-radius:5px; padding:5px 8px; font:12px inherit; }}
  .cons-filter-bar input {{ min-width:210px; flex:1; }}
  .cons-filter-bar button {{ cursor:pointer; }}
  .cons-filter-count {{ color:{_MUTED}; font-size:11px; margin-left:auto; }}
  .column-picker {{ position:relative; }}
  .column-menu {{ display:none; position:absolute; right:0; top:calc(100% + 5px);
                  z-index:20; min-width:230px; padding:8px; background:{_BG};
                  border:1px solid {_BORDER}; border-radius:7px;
                  box-shadow:0 8px 24px rgba(0,0,0,.35); }}
  .column-menu.open {{ display:block; }}
  .column-item {{ display:grid; grid-template-columns:18px minmax(0, 1fr) 72px;
                  align-items:center; column-gap:8px; min-height:32px; padding:4px 6px;
                  border-radius:4px; cursor:grab; color:{_TEXT}; font-size:12px; }}
  .column-item:hover {{ background:{_SURFACE}; }}
  .column-item.dragging {{ opacity:.45; }}
  .column-item input[type="checkbox"] {{ appearance:auto; width:14px; height:14px;
                                          margin:0; justify-self:center; }}
  .column-item span {{ line-height:18px; text-align:left; white-space:nowrap; }}
  .column-item input[type="number"] {{ width:68px; min-width:0; padding:3px 4px;
                                        text-align:right; font-size:11px; }}
  .column-menu-actions {{ display:flex; justify-content:flex-end; padding:6px 4px 0;
                          margin-top:4px; border-top:1px solid {_BORDER}; }}
  .column-menu-actions button {{ font-size:11px; padding:3px 7px; }}
  .skill-tree th[draggable="true"] {{ cursor:grab; }}
  .skill-tree th.col-drag-over {{ box-shadow:inset 3px 0 {_ACCENT}; }}

  .skill-tree .caret {{ display: inline-block; width: 12px;
                         color: {_MUTED}; margin-right: 6px;
                         transition: transform 0.15s; }}
  .skill-tree .open > td .caret {{ transform: rotate(90deg); }}
  .skill-tree .arm-row.expandable {{ cursor: pointer; }}
  .skill-tree .arm-row .arm-caret {{ display: inline-block; width: 10px;
                                     color: {_MUTED}; margin-right: 4px; }}
  .skill-tree .arm-row.open .arm-caret {{ color: {_ACCENT}; }}

  .grader-table {{ width: 100%; border-collapse: collapse;
                    background: {_SURFACE}; border: 1px solid {_BORDER};
                    border-radius: 6px; overflow: hidden;
                    margin-top: 4px; }}
  .grader-table th {{ background: {_SURFACE}; color: {_MUTED};
                       padding: 6px 10px; text-align: left;
                       border-bottom: 1px solid {_BORDER};
                       font-size: 12px; font-weight: 600; position: static; }}
  .grader-table td {{ padding: 6px 10px; border-bottom: 1px solid {_BORDER};
                       color: {_TEXT}; font-size: 12px; }}
  .grader-table tr:last-child td {{ border-bottom: none; }}
  .grader-table code {{ background: {_BG}; padding: 1px 4px;
                         border-radius: 3px; font-size: 11px; color: {_TEXT}; }}
  .grader-error {{ color: {_RED}; padding: 6px 0; font-size: 12px; }}
  .grader-skip  {{ color: {_AMBER}; padding: 6px 0; font-size: 12px; }}
  /* Inline "more/less" disclosure for long grader details. */
  .expand {{ display: inline; }}
  .expand > summary {{ display: inline; cursor: pointer; list-style: none; }}
  .expand > summary::-webkit-details-marker {{ display: none; }}
  .expand > summary::marker {{ content: ""; }}
  .expand .full {{ display: none; }}
  .expand[open] .short {{ display: none; }}
  .expand[open] .full {{ display: inline; }}
  .expand .tog {{ color: {_ACCENT}; font-weight: 600; white-space: nowrap;
                  margin-left: 4px; user-select: none; }}
  .expand .tog::after {{ content: "more"; }}
  .expand[open] .tog::after {{ content: "less"; }}
  /* Whole-block collapse (Prompt / LLM Judge / Full session log) --
     distinct from .expand's inline text-toggle use above. */
  .section {{ margin-top: 8px; border: 1px solid {_BORDER}; border-radius: 6px; }}
  .section > summary {{ cursor: pointer; padding: 6px 10px; font-size: 12px;
                         font-weight: 600; color: {_TEXT}; list-style: none; }}
  .section > summary::-webkit-details-marker {{ display: none; }}
  .section > summary::before {{ content: "▸"; margin-right: 6px; color: {_MUTED}; }}
  .section[open] > summary::before {{ content: "▾"; }}
  .section .body {{ padding: 0 10px 10px; }}
  .section pre {{ margin: 0; padding: 8px; background: {_BG};
                   border: 1px solid {_BORDER}; border-radius: 4px;
                   font-size: 11px; color: {_TEXT}; overflow-x: auto;
                   white-space: pre-wrap; word-break: break-word; }}

  /* Rep tab strip -- lets a multi-rep group's detail panel show any one
     replication on demand instead of only the default (first-failing) rep. */
  .rep-tab-strip {{ margin-bottom: 6px; }}
  .rep-tab-btn {{ background: transparent; border: 1px solid {_BORDER};
                   color: {_MUTED}; border-radius: 4px; padding: 2px 8px;
                   font-size: 11px; margin: 0 4px 4px 0; cursor: pointer;
                   font-family: inherit; }}
  .rep-tab-btn:hover {{ color: {_TEXT}; }}
  .rep-tab-btn.active {{ background: {_BG}; color: {_TEXT}; font-weight: 600; }}
  .rep-tab-btn .dot {{ display: inline-block; width: 7px; height: 7px;
                        border-radius: 50%; margin-right: 4px; }}
  .rep-panel {{ display: none; }}
  .rep-panel.active {{ display: block; }}

  /* Top-level tab bar (A/B vs Consistency). */
  .skill-tabs {{ display: flex; gap: 4px; margin: 14px 0 4px;
                  border-bottom: 1px solid {_BORDER}; }}
  .skill-tab-btn {{ background: transparent; border: none;
                     border-bottom: 2px solid transparent; color: {_MUTED};
                     padding: 8px 16px; cursor: pointer; font-size: 0.9em;
                     font-weight: 600; font-family: inherit; }}
  .skill-tab-btn:hover {{ color: {_TEXT}; }}
  .skill-tab-btn.active {{ color: {_ACCENT}; border-bottom-color: {_ACCENT}; }}

  /* Consistency-view stability verdict pill. */
  .cons-badge {{ display: inline-block; padding: 1px 8px; border-radius: 10px;
                  font-size: 11px; font-weight: 600; letter-spacing: .5px; }}

  /* Model-comparison paired bars. A categorical row per model, so the
     layout is immune to label collision at any model count -- no SVG text
     measurement, no overflow, no horizontal scroll. */
  .cmp-table {{ width: 100%; border-collapse: collapse; font-size: 0.88em;
                 background: {_SURFACE}; border: 1px solid {_BORDER};
                 border-radius: 8px; overflow: hidden; margin: 8px 0 6px; }}
  .cmp-table th {{ background: {_SURFACE}; color: {_MUTED};
                    padding: 9px 12px; text-align: left;
                    border-bottom: 2px solid {_BORDER};
                    font-weight: 600; font-size: 12px; position: static; }}
  .cmp-table td {{ padding: 8px 12px; border-bottom: 1px solid {_BORDER};
                    color: {_TEXT}; vertical-align: middle; }}
  .cmp-table tr:last-child td {{ border-bottom: none; }}
  .cmp-table .cmp-name {{ font-weight: 600; white-space: nowrap;
                           width: 1%; }}
  .cmp-table .cmp-n {{ text-align: right; white-space: nowrap; width: 1%;
                        font-variant-numeric: tabular-nums;
                        font-size: 12px; }}
  .cmp-bar {{ display: flex; align-items: center; gap: 10px; }}
  /* Recessive track; the fill is square at the baseline and rounded at the
     data-end, per the shared mark spec. */
  .cmp-track {{ flex: 1; min-width: 70px; height: 14px; background: {_BG};
                 border: 1px solid {_BORDER}; border-radius: 3px;
                 overflow: hidden; }}
  .cmp-fill {{ height: 100%; border-radius: 0 3px 3px 0; }}
  .cmp-val {{ min-width: 66px; text-align: right; font-size: 12px;
               color: {_TEXT}; font-variant-numeric: tabular-nums; }}

  /* Tool timeline: full-width fixed layout. Width is handled by WRAPPING
     (never a horizontal scroll / chop); height is capped by clamping tall
     cells to 3 lines with a trailing ellipsis. */
  .tl {{ table-layout: fixed; width: 100%; max-width: 100%;
          border-collapse: collapse; font-size: 12px; margin: 0 0 10px; }}
  .tl td, .tl th {{ padding: 2px 8px; vertical-align: top;
                     overflow-wrap: anywhere; word-break: break-word; }}
  .tl-clamp {{ display: -webkit-box; -webkit-line-clamp: 3; line-clamp: 3;
                -webkit-box-orient: vertical; overflow: hidden; }}
  .tl-args {{ display: block; }}
  .tl-args > summary {{ list-style: none; cursor: pointer; color: {_MUTED}; }}
  .tl-args > summary::-webkit-details-marker {{ display: none; }}
  .tl-args > summary::marker {{ content: ""; }}
  .tl-args[open] .tl-clamp {{ display: block; -webkit-line-clamp: unset;
                               overflow: visible; }}
</style>
"""


# ------------------------------------------------------------- selector


def _render_run_selector(
    runs: list[tuple[str, str, int]],
    *,
    select_id: str = "skill-run-select",
    onchange: str = "skillSelectRun",
) -> str:
    if not runs:
        return ''
    out = [
        '<div class="run-selector">',
        '  <label>Run:</label>',
        f'  <select id="{_esc(select_id)}" '
        f'onchange="{_esc(onchange)}(this.value)">',
    ]
    for run_id, ts, n_rows in runs:
        ts_short = (ts or "")[:19].replace("T", " ")
        out.append(
            f'    <option value="{_esc(run_id)}">'
            f'{_esc(ts_short)} &nbsp;|&nbsp; {_esc(run_id[:8])} '
            f'&nbsp;|&nbsp; {n_rows} rows'
            f'</option>'
        )
    out.append('  </select>')
    out.append('</div>')
    return "\n".join(out)


def _render_skill_switcher_js() -> str:
    return """
<script>
(function () {
  // Run selectors: one per tab, each scoped by its panel data-attribute(s).
  // Pass an array when a second, separately-positioned element (e.g. the
  // model-comparison chart's own divs, placed after the heatmap rather than
  // inside the run panel) needs to switch in lockstep with the same run id.
  function makeSelector(attrs) {
    attrs = Array.isArray(attrs) ? attrs : [attrs];
    return function (runId) {
      attrs.forEach(function (attr) {
        document.querySelectorAll('[' + attr + ']').forEach(function (el) {
          el.style.display = (el.getAttribute(attr) === runId) ? '' : 'none';
        });
      });
    };
  }
  window.skillSelectRun = makeSelector('data-skill-run');
  window.consistencySelectRun =
    makeSelector(['data-consistency-run', 'data-cmp-chart-run']);

  // Hide all but the first per-run panel on initial load (both tabs).
  function hideAllButFirst(attr) {
    var panels = document.querySelectorAll('[' + attr + ']');
    for (var i = 1; i < panels.length; i++) panels[i].style.display = 'none';
  }
  hideAllButFirst('data-skill-run');
  hideAllButFirst('data-consistency-run');
  hideAllButFirst('data-cmp-chart-run');

  function applyConsistencyFilter(bar) {
    var tableId = bar.getAttribute('data-filter-for');
    var wrap = document.querySelector('[data-cons-table="' + CSS.escape(tableId) + '"]');
    if (!wrap) return;
    var value = function (name) {
      var el = bar.querySelector('[data-cons-filter="' + name + '"]');
      return el ? el.value.toLowerCase().trim() : '';
    };
    var text = value('text'), client = value('client'), model = value('model');
    var consistency = value('consistency'), outcome = value('outcome');
    var visible = 0;
    wrap.querySelectorAll('.arm-row').forEach(function (row) {
      var show = (!text || (row.dataset.filterText || '').includes(text)) &&
        (!client || row.dataset.filterClient === client) &&
        (!model || row.dataset.filterModel === model) &&
        (!consistency || row.dataset.filterConsistency === consistency) &&
        (!outcome || row.dataset.filterOutcome === outcome);
      row.dataset.filterVisible = show ? '1' : '0';
      row.style.display = show && row.classList.contains('open') ? 'table-row' : 'none';
      if (!show) {
        var detail = wrap.querySelector('.grader-row[data-parent-arm="' +
          CSS.escape(row.dataset.armKey) + '"]');
        if (detail) detail.classList.remove('open');
      } else visible++;
    });
    wrap.querySelectorAll('.skill-row').forEach(function (skill) {
      var key = skill.dataset.skillKey;
      var matches = Array.from(wrap.querySelectorAll('.arm-row[data-parent="' +
        CSS.escape(key) + '"]')).some(function (r) { return r.dataset.filterVisible === '1'; });
      skill.style.display = matches ? 'table-row' : 'none';
    });
    var count = bar.querySelector('.cons-filter-count');
    if (count) count.textContent = visible + ' case group' + (visible === 1 ? '' : 's');
  }

  document.querySelectorAll('.cons-filter-bar').forEach(function (bar) {
    bar.querySelectorAll('[data-cons-filter]').forEach(function (el) {
      el.addEventListener(el.tagName === 'INPUT' ? 'input' : 'change', function () {
        applyConsistencyFilter(bar);
      });
    });
    bar.addEventListener('click', function (ev) {
      var action = ev.target.getAttribute('data-cons-action');
      if (!action) return;
      var tableId = bar.getAttribute('data-filter-for');
      var wrap = document.querySelector('[data-cons-table="' + CSS.escape(tableId) + '"]');
      if (action === 'reset') {
        bar.querySelectorAll('[data-cons-filter]').forEach(function (el) { el.value = ''; });
        applyConsistencyFilter(bar);
      } else if (wrap) {
        wrap.querySelectorAll('.skill-row').forEach(function (r) {
          r.classList.toggle('open', action === 'expand');
        });
        wrap.querySelectorAll('.arm-row').forEach(function (r) {
          var open = action === 'expand' && r.dataset.filterVisible !== '0';
          r.classList.toggle('open', open);
          r.style.display = open ? 'table-row' : 'none';
        });
        if (action === 'collapse') wrap.querySelectorAll('.grader-row').forEach(function (r) {
          r.classList.remove('open');
        });
      }
    });
    applyConsistencyFilter(bar);
  });

  // Column visibility, order, and widths are local browser preferences.
  document.querySelectorAll('.skill-tree').forEach(function (table, tableIndex) {
    var wrap = table.closest('[data-cons-table]');
    var tableKey = wrap ? wrap.getAttribute('data-cons-table') : String(tableIndex);
    var prefKey = 'skill-tree-columns-' + tableKey;
    var widthKey = 'skill-tree-widths-' + tableKey;
    var headers = table.tHead && table.tHead.rows.length
      ? Array.from(table.tHead.rows[0].cells) : [];
    if (!headers.length || headers.some(function (th) { return !th.dataset.colKey; })) return;
    var defaultOrder = headers.map(function (th) { return th.dataset.colKey; });
    var prefs = { order: defaultOrder, hidden: [] };
    try { prefs = Object.assign(prefs, JSON.parse(localStorage.getItem(prefKey) || '{}')); } catch (_) {}
    prefs.order = prefs.order.filter(function (key) { return defaultOrder.includes(key); });
    prefs.hidden = (prefs.hidden || []).filter(function (key) { return defaultOrder.includes(key); });
    defaultOrder.forEach(function (key) { if (!prefs.order.includes(key)) prefs.order.push(key); });

    function moveColumn(from, to) {
      if (from === to) return;
      table.querySelectorAll('tr').forEach(function (row) {
        var cells = row.children;
        if (cells.length !== defaultOrder.length) return;
        var cell = cells[from];
        row.insertBefore(cell, to > from ? cells[to].nextSibling : cells[to]);
      });
      var cols = table.querySelector('colgroup');
      if (cols && cols.children[from]) {
        var col = cols.children[from];
        cols.insertBefore(col, to > from ? cols.children[to].nextSibling : cols.children[to]);
      }
    }
    prefs.order.forEach(function (key, target) {
      var current = headers.findIndex(function (th) {
        return th.dataset.colKey === key;
      });
      if (current >= 0) moveColumn(current, target);
    });

    function applyHidden() {
      headers.forEach(function (th, index) {
        var hidden = prefs.hidden.includes(th.dataset.colKey);
        table.querySelectorAll('tr').forEach(function (row) {
          if (row.children.length === defaultOrder.length && row.children[index])
            row.children[index].style.display = hidden ? 'none' : '';
        });
      });
      table.querySelectorAll('.grader-row td[colspan]').forEach(function (td) {
        td.colSpan = defaultOrder.length - prefs.hidden.length;
      });
    }

    var bar = wrap && wrap.previousElementSibling;
    var menu = bar && bar.querySelector('.column-menu');
    function savePrefs() { try { localStorage.setItem(prefKey, JSON.stringify(prefs)); } catch (_) {} }
    function renderMenu() {
      if (!menu) return;
      menu.innerHTML = '';
      var currentCols = Array.from(table.querySelectorAll('col'));
      prefs.order.forEach(function (key, displayIndex) {
        var th = headers.find(function (h) { return h.dataset.colKey === key; });
        if (!th) return;
        var item = document.createElement('label'); item.className = 'column-item';
        item.draggable = true; item.dataset.colKey = key;
        var label = th.dataset.colLabel || key;
        var checkbox = document.createElement('input');
        checkbox.type = 'checkbox'; checkbox.checked = !prefs.hidden.includes(key);
        var labelText = document.createElement('span'); labelText.textContent = label;
        var widthInput = document.createElement('input'); widthInput.type = 'number';
        widthInput.min = '70'; widthInput.max = '600'; widthInput.step = '10';
        widthInput.title = 'Column width in pixels'; widthInput.setAttribute('aria-label', label + ' width in pixels');
        widthInput.value = Math.round(th.getBoundingClientRect().width || 100);
        item.appendChild(checkbox); item.appendChild(labelText); item.appendChild(widthInput);
        checkbox.addEventListener('change', function (e) {
          if (!e.target.checked && prefs.order.length - prefs.hidden.length <= 1) { e.target.checked = true; return; }
          prefs.hidden = e.target.checked ? prefs.hidden.filter(function (x) { return x !== key; }) : prefs.hidden.concat(key);
          savePrefs(); applyHidden();
        });
        widthInput.addEventListener('mousedown', function (e) { e.stopPropagation(); });
        widthInput.addEventListener('dragstart', function (e) { e.preventDefault(); e.stopPropagation(); });
        widthInput.addEventListener('change', function (e) {
          var width = Math.max(70, Math.min(600, Number(e.target.value) || 100));
          e.target.value = String(width);
          var liveHeaders = Array.from(table.tHead.rows[0].cells);
          var liveIndex = liveHeaders.findIndex(function (h) { return h.dataset.colKey === key; });
          var liveCols = table.querySelectorAll('col');
          if (liveIndex >= 0 && liveCols[liveIndex]) liveCols[liveIndex].style.width = width + 'px';
          try { localStorage.setItem(widthKey, JSON.stringify(Array.from(liveCols).map(function (c) { return c.style.width; }))); } catch (_) {}
        });
        item.addEventListener('dragstart', function (e) {
          if (e.target === widthInput || e.target === checkbox) { e.preventDefault(); return; }
          item.classList.add('dragging');
        });
        item.addEventListener('dragend', function () { item.classList.remove('dragging'); });
        item.addEventListener('dragover', function (e) { e.preventDefault(); });
        item.addEventListener('drop', function (e) {
          e.preventDefault(); var source = menu.querySelector('.column-item.dragging');
          if (!source || source === item) return;
          var from = prefs.order.indexOf(source.dataset.colKey), to = prefs.order.indexOf(key);
          prefs.order.splice(from, 1); prefs.order.splice(to, 0, source.dataset.colKey);
          moveColumn(from, to); savePrefs(); renderMenu(); applyHidden();
        });
        menu.appendChild(item);
      });
      var actions = document.createElement('div'); actions.className = 'column-menu-actions';
      var resetWidths = document.createElement('button'); resetWidths.type = 'button';
      resetWidths.textContent = 'Reset widths';
      resetWidths.addEventListener('click', function (e) {
        e.preventDefault(); e.stopPropagation();
        Array.from(table.querySelectorAll('col')).forEach(function (col) { col.style.width = ''; });
        try { localStorage.removeItem(widthKey); } catch (_) {}
        renderMenu();
      });
      actions.appendChild(resetWidths); menu.appendChild(actions);
    }
    if (bar) bar.addEventListener('click', function (ev) {
      if (ev.target.getAttribute('data-cons-action') === 'columns' && menu) {
        var open = !menu.classList.contains('open'); menu.classList.toggle('open', open);
        ev.target.setAttribute('aria-expanded', open ? 'true' : 'false');
      }
    });
    renderMenu(); applyHidden();

    var cols = table.querySelectorAll('col');
    headers.forEach(function (th, index) {
      th.draggable = true;
      th.addEventListener('dragstart', function (ev) { ev.dataTransfer.setData('text/column', th.dataset.colKey); });
      th.addEventListener('dragover', function (ev) { ev.preventDefault(); th.classList.add('col-drag-over'); });
      th.addEventListener('dragleave', function () { th.classList.remove('col-drag-over'); });
      th.addEventListener('drop', function (ev) {
        ev.preventDefault(); th.classList.remove('col-drag-over');
        var sourceKey = ev.dataTransfer.getData('text/column');
        var from = prefs.order.indexOf(sourceKey), to = prefs.order.indexOf(th.dataset.colKey);
        if (from >= 0 && to >= 0) { prefs.order.splice(from, 1); prefs.order.splice(to, 0, sourceKey); moveColumn(from, to); savePrefs(); renderMenu(); applyHidden(); }
      });
      var handle = document.createElement('span'); handle.className = 'col-resizer'; th.appendChild(handle);
      handle.addEventListener('mousedown', function (ev) {
        ev.preventDefault(); ev.stopPropagation(); var startX = ev.clientX; var startW = th.offsetWidth;
        function move(e) { if (cols[index]) cols[index].style.width = Math.max(70, startW + e.clientX - startX) + 'px'; }
        function up() { document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up);
          try { localStorage.setItem(widthKey, JSON.stringify(Array.from(cols).map(function (c) { return c.style.width; }))); } catch (_) {} }
        document.addEventListener('mousemove', move); document.addEventListener('mouseup', up);
      });
    });
    try { JSON.parse(localStorage.getItem(widthKey) || '[]').forEach(function (width, index) {
      if (cols[index] && width) cols[index].style.width = width;
    }); } catch (_) {}
  });

  // Top-level tab switching (A/B vs. Consistency).
  window.skillShowTab = function (name) {
    document.querySelectorAll('[data-skill-tab]').forEach(function (el) {
      el.style.display =
        (el.getAttribute('data-skill-tab') === name) ? '' : 'none';
    });
    document.querySelectorAll('.skill-tab-btn').forEach(function (b) {
      b.classList.toggle('active',
        b.getAttribute('data-tab-target') === name);
    });
  };

  // Tree-view toggling.
  //   Skill row  -> toggles every .arm-row whose data-parent matches.
  //                 When collapsing, also closes any open grader-row.
  //   Arm row    -> toggles its own .grader-row sibling (FAILs only).
  document.addEventListener('click', function (ev) {
    if (!ev.target.closest) return;

    // Rep tab strip: swap which replication's detail panel is visible
    // within this one group, without touching any other group's tabs.
    var tb = ev.target.closest('.rep-tab-btn');
    if (tb) {
      var grp = tb.getAttribute('data-rep-group');
      var idx = tb.getAttribute('data-rep-index');
      document.querySelectorAll(
        '.rep-tab-btn[data-rep-group="' + CSS.escape(grp) + '"]'
      ).forEach(function (b) {
        b.classList.toggle('active', b === tb);
      });
      document.querySelectorAll(
        '.rep-panel[data-rep-group="' + CSS.escape(grp) + '"]'
      ).forEach(function (p) {
        p.classList.toggle('active', p.getAttribute('data-rep-index') === idx);
      });
      return;
    }

    var sk = ev.target.closest('.skill-row');
    if (sk) {
      var key = sk.getAttribute('data-skill-key');
      var nowOpen = !sk.classList.contains('open');
      sk.classList.toggle('open', nowOpen);
      document.querySelectorAll(
        '.arm-row[data-parent="' + CSS.escape(key) + '"]'
      ).forEach(function (row) {
        var rowOpen = nowOpen && row.dataset.filterVisible !== '0';
        row.classList.toggle('open', rowOpen);
        row.style.display = rowOpen ? 'table-row' : 'none';
        if (!nowOpen) {
          var aKey = row.getAttribute('data-arm-key');
          var det = document.querySelector(
            '.grader-row[data-parent-arm="' + CSS.escape(aKey) + '"]');
          if (det) det.classList.remove('open');
        }
      });
      return;
    }

    var ar = ev.target.closest('.arm-row.expandable');
    if (ar) {
      var aKey = ar.getAttribute('data-arm-key');
      var det = document.querySelector(
        '.grader-row[data-parent-arm="' + CSS.escape(aKey) + '"]');
      if (det) {
        var nowOpen = !det.classList.contains('open');
        det.classList.toggle('open', nowOpen);
      }
    }
  });
})();
</script>
"""


# --------------------------------------------------------- per-run panel


def _per_run_rows(conn: sqlite3.Connection, run_id: str) -> list[sqlite3.Row]:
    # `hallucination_detected`, `vivado_version`, and `aggregate_score` are
    # additive columns; older DBs may not have them. We materialise NULL in
    # that case so the rest of the renderer doesn't have to branch.
    has_halluc = _column_exists(conn, "skill_test_results", "hallucination_detected")
    has_vivver = _column_exists(conn, "skill_test_results", "vivado_version")
    has_agg = _column_exists(conn, "skill_test_results", "aggregate_score")
    halluc_col = (
        "str.hallucination_detected" if has_halluc
        else "NULL AS hallucination_detected"
    )
    vivver_col = (
        "str.vivado_version" if has_vivver
        else "NULL AS vivado_version"
    )
    # aggregate_score is the primary signoff metric; fall back to t2_score for
    # rows written before the column was added.
    agg_col = (
        "COALESCE(str.aggregate_score, str.t2_score) AS aggregate_score"
        if has_agg else
        "str.t2_score AS aggregate_score"
    )
    return conn.execute(f"""
        SELECT str.id, str.run_id, str.skill_name, str.case_id, str.client, str.model,
               str.with_skill, str.replication_index,
               str.wall_clock_s, str.prompt_tokens, str.output_tokens,
               str.cache_read_tokens, str.cache_write_tokens,
               str.cost_usd, str.cost_method, str.power_metrics,
               str.t2_score, {agg_col}, str.status, str.error, str.skip_reason,
               str.timestamp, {halluc_col}, {vivver_col}
          FROM skill_test_results AS str
         WHERE run_id = ?
         ORDER BY skill_name, case_id, client, model, with_skill DESC,
                  replication_index
    """, (run_id,)).fetchall()


def _per_run_rows_for_skill(
    conn: sqlite3.Connection, run_id: str, skill_name: str,
) -> list[sqlite3.Row]:
    """Same rows as ``_per_run_rows``, scoped to one skill within the run --
    the slice ``reporting/skill_signoffs.py`` snapshots into skill-signoffs/."""
    return [r for r in _per_run_rows(conn, run_id) if r["skill_name"] == skill_name]


# CSS for a standalone single-skill report page. `_render_local_css()`
# supplies only tree-view chrome (see its own docstring) -- everything else
# a fragment like `_render_headline`'s `.stat`/`.summary` classes need is
# normally the surrounding dashboard page's job (generate_report.py). A
# standalone skill-signoffs report has no such surrounding page, so it needs
# its own minimal copy of that base chrome.
_STANDALONE_PAGE_CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       background: #0d1117; color: #e6edf3; padding: 20px; }
h1 { font-size: 1.8em; margin-bottom: 8px; color: #58a6ff; }
h3 { font-size: 1.1em; margin: 20px 0 10px 0; color: #8b949e; }
.subtitle { color: #8b949e; margin-bottom: 20px; font-size: 0.9em; }
.summary { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 16px 0; }
.stat { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; text-align: center; }
.stat .value { font-size: 1.8em; font-weight: bold; color: #58a6ff; }
.stat .label { font-size: 0.85em; color: #8b949e; margin-top: 4px; }
table { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 0.85em; }
th { background: #161b22; color: #8b949e; padding: 10px 12px; text-align: left; border-bottom: 2px solid #30363d; }
td { padding: 8px 12px; border-bottom: 1px solid #21262d; }
tr:hover td { background: #161b22; }
"""


def render_skill_run_report(conn: sqlite3.Connection, skill_name: str, run_id: str) -> str:
    """Self-contained HTML page for one skill's slice of one run --
    ``reporting/skill_signoffs.py``'s ``report.html``/``report_vN.html``.

    Reuses the same aggregation/rendering helpers as the main dashboard
    (headline tiles, consistency tree) rather than a separate template, just
    scoped to one (skill, run) pair instead of every run in the DB.
    """
    conn.row_factory = sqlite3.Row
    rows = _per_run_rows_for_skill(conn, run_id, skill_name)
    ts = rows[0]["timestamp"] if rows else ""
    ts_short = (ts or "")[:19].replace("T", " ")

    body = [_render_local_css(), _render_headline(rows, run_id, ts)]
    body.append(_render_consistency_tree(conn, rows, run_id))
    body.append(_render_consistency_heatmap(conn, skill_name, run_id))
    body.append(_render_model_comparison_chart(rows))
    body.append(_render_lifecycle_cards(conn, skill_name=skill_name, run_id=run_id))
    # Without this, the tree/rep-tab click handlers never attach and every
    # row's expand caret is dead -- the markup renders but nothing toggles
    # its "open" class. Pure event-delegation, no dependency on the
    # multi-run selector or tab bar this page doesn't have, so it's safe
    # to include verbatim.
    body.append(_render_skill_switcher_js())

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(skill_name)} &middot; {_esc(run_id)}</title>
<style>{_STANDALONE_PAGE_CSS}</style>
</head>
<body>
<h1>{_esc(skill_name)}</h1>
<p class="subtitle">run {_esc(run_id)} &middot; {_esc(ts_short)}</p>
{chr(10).join(body)}
</body>
</html>"""


def _render_run_panel(
    conn: sqlite3.Connection,
    run_id: str,
    ts: str,
    n_rows: int,
    *,
    hidden: bool,
) -> str:
    rows = _per_run_rows(conn, run_id)
    style = ' style="display:none;"' if hidden else ''
    out = [f'<div data-skill-run="{_esc(run_id)}"{style}>']
    out.append(_render_headline(rows, run_id, ts))
    out.append(_render_tree(conn, rows, run_id))
    out.append('</div>')
    return "\n".join(out)


# ---- headline -----------------------------------------------------------


def _render_headline(rows: list[sqlite3.Row], run_id: str, ts: str) -> str:
    n_pass = sum(1 for r in rows if r["status"] == "PASS")
    n_fail = sum(1 for r in rows if r["status"] in ("FAIL", "ERROR"))
    n_skip = sum(1 for r in rows if r["status"] == "SKIPPED")
    total_cost = sum((r["cost_usd"] or 0.0) for r in rows)
    total_wall = sum((r["wall_clock_s"] or 0.0) for r in rows)

    cells = [
        (str(n_pass),               'PASS',      _GREEN if n_pass else None),
        (str(n_fail),               'FAIL',      _RED   if n_fail else None),
        (str(n_skip),               'SKIP',      _AMBER if n_skip else None),
        (_fmt_cost(total_cost),     'run cost',  None),
        (_fmt_secs(total_wall),     'wall clock', None),
    ]
    chips = []
    for value, label, color in cells:
        color = color or _ACCENT
        chips.append(
            f'<div class="stat">'
            f'<div class="value" style="color:{color};">{_esc(value)}</div>'
            f'<div class="label">{_esc(label)}</div>'
            f'</div>'
        )
    ts_short = (ts or "")[:19].replace("T", " ")
    return (
        f'<h3 style="margin-top:14px;">Run summary '
        f'<span style="color:{_MUTED}; font-weight:400; font-size:0.8em;">'
        f'&middot; {_esc(run_id[:8])} &middot; {_esc(ts_short)}'
        f'</span></h3>'
        f'<div class="summary">'
        + "".join(chips) +
        '</div>'
    )


# ---- tree view ----------------------------------------------------------


def _grader_rows(conn: sqlite3.Connection, skill_test_id: int) -> list[sqlite3.Row]:
    has_mandatory = _column_exists(conn, "skill_grader_results", "mandatory")
    has_weight = _column_exists(conn, "skill_grader_results", "weight")
    mandatory_col = "mandatory" if has_mandatory else "NULL AS mandatory"
    # ``weight`` column distinguishes weighted (soft) graders from diagnostic
    # (always=true but weight=0 or NULL) ones. Absent in older DBs -> NULL.
    weight_col = "weight" if has_weight else "NULL AS weight"
    # Mandatory + failing graders surface first (the hallucination signal).
    # Then non-mandatory failures, then passing rows by grader_id.
    return conn.execute(f"""
        SELECT grader_id, grader_type, passed, score, details,
               {mandatory_col}, {weight_col}
          FROM skill_grader_results
         WHERE skill_test_id = ?
         ORDER BY (CASE WHEN {mandatory_col if has_mandatory else 'NULL'} = 1 AND passed = 0 THEN 0
                        WHEN passed = 0 THEN 1
                        ELSE 2 END),
                  grader_id
    """, (skill_test_id,)).fetchall()


def _grader_category(g: sqlite3.Row) -> str:
    """Return 'mandatory', 'weighted', or 'diagnostic' for a grader row.

    - mandatory: ``mandatory=1`` -- anti-hallucination contract; failure marks
      the row hallucination_detected=1.
    - weighted: non-mandatory grader with an explicit weight > 0 (or weight
      absent/NULL, treated as weight=1.0 by the runner).
    - diagnostic: grader always run but contributing zero weight to the score
      (weight=0.0 explicitly).  These are observational probes -- important
      to surface but not score-gating.
    """
    try:
        mand = g["mandatory"]
    except (IndexError, KeyError):
        mand = None
    if mand:
        return "mandatory"
    try:
        w = g["weight"]
    except (IndexError, KeyError):
        w = None
    if w is not None and float(w) == 0.0:
        return "diagnostic"
    return "weighted"


def _render_tree(
    conn: sqlite3.Connection,
    rows: list[sqlite3.Row],
    run_id: str,
) -> str:
    if not rows:
        return ''

    by_skill: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for r in rows:
        by_skill[r["skill_name"]].append(r)

    out = [
        '<h3>Results by skill '
        f'<span style="color:{_MUTED}; font-weight:400; font-size:0.8em;">'
        '(click a skill to expand A/B runs; click a run to see grader '
        'detail)</span></h3>',
        '<div class="table-wrap"><table class="skill-tree">',
        '<thead><tr>',
        '<th>Skill / case</th>',
        '<th>CLI</th>',
        '<th>Model</th>',
        '<th class="ctr">Status<br><span style="font-weight:400;">skill / no skill</span></th>',
        '<th class="ctr">Halluc<br><span style="font-weight:400;">skill / no skill</span></th>',
        '<th class="num">Runtime<br><span style="font-weight:400;">skill / no skill</span></th>',
        '<th class="num">Cost<br><span style="font-weight:400;">skill / no skill</span></th>',
        '<th class="num">T2 score<br><span style="font-weight:400;">skill</span></th>',
        '<th class="num">T2 score<br><span style="font-weight:400;">no skill</span></th>',
        '<th class="num">T2 Δ</th>',
        '<th class="num">Tokens<br><span style="font-weight:400;">in/out/cache</span></th>',
        '<th>Method</th>',
        '</tr></thead><tbody>',
    ]

    for skill in sorted(by_skill):
        rs = by_skill[skill]
        skill_key = f"{run_id}:{skill}"
        out.append(_render_skill_parent_row(skill, skill_key, rs))
        arm_groups: dict[tuple, list[sqlite3.Row]] = defaultdict(list)
        for r in rs:
            arm_groups[(r["case_id"], r["client"], r["model"])].append(r)
        for (case, client, model), recs in sorted(arm_groups.items()):
            out.append(_render_ab_child_row(conn, skill_key, case, client,
                                            model, recs))

    out.append('</tbody></table></div>')
    return "\n".join(out)


def _aggregate(recs: list[sqlite3.Row]) -> dict:
    n = len(recs)
    n_pass = sum(1 for r in recs if r["status"] == "PASS")
    n_fail = sum(1 for r in recs if r["status"] in ("FAIL", "ERROR"))
    n_skip = sum(1 for r in recs if r["status"] == "SKIPPED")
    pr = (n_pass / n) if n else 0.0
    t2_vals = [r["t2_score"] for r in recs if r["t2_score"] is not None]
    avg_t2 = (sum(t2_vals) / len(t2_vals)) if t2_vals else 0.0
    cost = sum((r["cost_usd"] or 0.0) for r in recs)
    cpp = (cost / n_pass) if n_pass else None
    walls = [r["wall_clock_s"] for r in recs if r["wall_clock_s"]]
    p50 = statistics.median(walls) if walls else None
    wall_total = sum(walls) if walls else None
    methods = sorted({r["cost_method"] for r in recs if r["cost_method"]})
    # Aggregate power across rows that recorded a measurement so the
    # method-column tooltip can show *this group's* mean active/idle watts
    # rather than just the per-row blob from an arbitrary record.
    pm_objs: list[dict] = []
    for r in recs:
        try:
            raw = r["power_metrics"]
        except (IndexError, KeyError):
            raw = None
        if not raw:
            continue
        parsed = _parse_jsonish(raw)
        if isinstance(parsed, dict):
            pm_objs.append(parsed)
    agg_pm: dict | None = None
    if pm_objs:
        actives = [p["avg_active_w"] for p in pm_objs if isinstance(p.get("avg_active_w"), (int, float))]
        peaks   = [p["peak_w"]       for p in pm_objs if isinstance(p.get("peak_w"),       (int, float))]
        bases   = [p["baseline_w"]   for p in pm_objs if isinstance(p.get("baseline_w"),   (int, float))]
        agg_pm = {
            "avg_active_w": (sum(actives) / len(actives)) if actives else None,
            "peak_w":       max(peaks) if peaks else None,
            "baseline_w":   (sum(bases) / len(bases)) if bases else None,
            "rows_with_power": len(pm_objs),
        }
    # Hallucination rate (hallucination_detected/total). Rows that
    # predate the column return NULL → excluded from the denominator
    # so historical runs render as "—" instead of falsely-clean "0%".
    h_vals: list[int] = []
    for r in recs:
        try:
            v = r["hallucination_detected"]
        except (IndexError, KeyError):
            v = None
        if v is None:
            continue
        h_vals.append(1 if int(v) else 0)
    h_rate = (sum(h_vals) / len(h_vals)) if h_vals else None
    h_count = sum(h_vals)

    return {
        "n": n, "n_pass": n_pass, "n_fail": n_fail, "n_skip": n_skip,
        "pr": pr, "avg_t2": avg_t2,
        "live_in":  sum((r["prompt_tokens"]      or 0) for r in recs),
        "live_out": sum((r["output_tokens"]      or 0) for r in recs),
        "cache_r":  sum((r["cache_read_tokens"]  or 0) for r in recs),
        "cost": cost, "cost_per_pass": cpp, "p50_wall": p50,
        "wall_total": wall_total, "methods": methods,
        "power_metrics": agg_pm,
        # Hallucination signal (None when no row carried the column).
        "h_rate": h_rate,
        "h_count": h_count,
        "h_total": len(h_vals),
    }


def _aggregate_method_label(methods: list[str], power_metrics: dict | None = None) -> str:
    if not methods:
        return "—"
    if len(methods) == 1:
        return _fmt_method(methods[0], power_metrics)
    return f"mixed ({len(methods)} methods)"


def _split_arms(recs: list[sqlite3.Row]) -> tuple[list[sqlite3.Row], list[sqlite3.Row]]:
    return (
        [r for r in recs if r["with_skill"]],
        [r for r in recs if not r["with_skill"]],
    )


def _t2_avg(recs: list[sqlite3.Row]) -> float | None:
    vals = [
        float(r["t2_score"]) for r in recs
        if r["t2_score"] is not None
    ]
    return (sum(vals) / len(vals)) if vals else None


def _t2_cell(recs: list[sqlite3.Row]) -> str:
    score = _t2_avg(recs)
    if score is None:
        return "—"
    pct = score * 100
    color = _GREEN if score >= 0.9 else (_AMBER if score >= 0.5 else _RED)
    return f'<span style="color:{color}; font-weight:600;">{pct:.0f}%</span>'


def _t2_delta(skill_recs: list[sqlite3.Row], no_skill_recs: list[sqlite3.Row]) -> str:
    s = _t2_avg(skill_recs)
    n = _t2_avg(no_skill_recs)
    if s is None or n is None:
        return "—"
    delta_pp = (s - n) * 100
    color = _GREEN if delta_pp > 0 else (_RED if delta_pp < 0 else _MUTED)
    sign = "+" if delta_pp > 0 else ""
    return f'<span style="color:{color}; font-weight:600;">{sign}{delta_pp:.0f} pp</span>'


def _status_pair(skill_recs: list[sqlite3.Row], no_skill_recs: list[sqlite3.Row]) -> str:
    return (
        f'{_arm_status(skill_recs)} '
        f'<span style="color:{_MUTED};">/</span> '
        f'{_arm_status(no_skill_recs)}'
    )


def _halluc_cell(recs: list[sqlite3.Row]) -> str:
    """
    Compact hallucination indicator for the skill tree. Renders as
    "n/N" with red foreground when n > 0, green when n == 0, dashed
    grey when the rows predate the column.
    """
    if not recs:
        return f'<span style="color:{_MUTED};">—</span>'
    a = _aggregate(recs)
    if a["h_rate"] is None:
        return f'<span style="color:{_MUTED};">—</span>'
    n = a["h_count"]
    total = a["h_total"]
    color = _RED if n else _GREEN
    label = f"{n}/{total}"
    if n:
        # Loud icon when something hallucinated, so a customer scanning
        # the table can't miss it.
        return (
            f'<span style="display:inline-block; padding:1px 8px; '
            f'border:1px solid {color}; color:{color}; '
            f'border-radius:10px; font-size:11px; font-weight:600; '
            f'letter-spacing:.5px;" '
            f'title="{n} of {total} runs flagged hallucination_detected=1">'
            f'⚠ {label}</span>'
        )
    return (
        f'<span style="color:{color}; font-variant-numeric:tabular-nums;" '
        f'title="0 of {total} runs flagged hallucination_detected=1">'
        f'{label}</span>'
    )


def _halluc_pair(
    skill_recs: list[sqlite3.Row], no_skill_recs: list[sqlite3.Row],
) -> str:
    return (
        f'{_halluc_cell(skill_recs)} '
        f'<span style="color:{_MUTED};">/</span> '
        f'{_halluc_cell(no_skill_recs)}'
    )


def _arm_status(recs: list[sqlite3.Row]) -> str:
    if not recs:
        return f'<span style="color:{_MUTED};">missing</span>'
    a = _aggregate(recs)
    status = (
        "PASS" if a["n_pass"] and not a["n_fail"] and not a["n_skip"]
        else "FAIL" if a["n_fail"]
        else "SKIPPED" if a["n_skip"]
        else (recs[0]["status"] if recs else "--")
    )
    count_text = f'({a["n_pass"]}/{a["n"]})' if a["n"] > 1 else ""
    return _status_pill(status, count_text)


def _runtime_pair(skill_recs: list[sqlite3.Row], no_skill_recs: list[sqlite3.Row]) -> str:
    return f'{_fmt_secs(_aggregate(skill_recs)["wall_total"])} / {_fmt_secs(_aggregate(no_skill_recs)["wall_total"])}'


def _cost_pair(skill_recs: list[sqlite3.Row], no_skill_recs: list[sqlite3.Row]) -> str:
    return f'{_fmt_cost(_aggregate(skill_recs)["cost"])} / {_fmt_cost(_aggregate(no_skill_recs)["cost"])}'


def _tokens_pair(skill_recs: list[sqlite3.Row], no_skill_recs: list[sqlite3.Row]) -> str:
    s = _aggregate(skill_recs)
    n = _aggregate(no_skill_recs)
    s_txt = f'{_fmt_tokens(s["live_in"])}/{_fmt_tokens(s["live_out"])}/{_fmt_tokens(s["cache_r"])}'
    n_txt = f'{_fmt_tokens(n["live_in"])}/{_fmt_tokens(n["live_out"])}/{_fmt_tokens(n["cache_r"])}'
    return f'{s_txt}<br><span style="color:{_MUTED};">{n_txt}</span>'


def _render_skill_parent_row(
    skill: str, skill_key: str, recs: list[sqlite3.Row],
) -> str:
    skill_recs, no_skill_recs = _split_arms(recs)
    a = _aggregate(skill_recs or recs)
    n_arms = len({(r["case_id"], r["client"], r["model"]) for r in recs})
    clients = sorted({str(r["client"]) for r in recs if r["client"]})
    models = sorted({str(r["model"]) for r in recs if r["model"]})
    client_label = clients[0] if len(clients) == 1 else f"{len(clients)} CLIs"
    model_label = (
        _model_label(models[0]) if len(models) == 1
        else f"{len(models)} models"
    )
    return (
        f'<tr class="skill-row" data-skill-key="{_esc(skill_key)}">'
        f'<td class="name">'
        f'<span class="caret">&#9656;</span>'
        f'{_esc(skill)} '
        f'<span style="color:{_MUTED}; font-weight:400; font-size:0.85em;">'
        f'({n_arms} test{"s" if n_arms != 1 else ""})</span>'
        f'</td>'
        f'<td>{_esc(client_label)}</td>'
        f'<td>{_esc(model_label)}</td>'
        f'<td class="ctr">{_status_pair(skill_recs, no_skill_recs)}</td>'
        f'<td class="ctr">{_halluc_pair(skill_recs, no_skill_recs)}</td>'
        f'<td class="num">{_esc(_runtime_pair(skill_recs, no_skill_recs))}</td>'
        f'<td class="num">{_esc(_cost_pair(skill_recs, no_skill_recs))}</td>'
        f'<td class="num">{_t2_cell(skill_recs)}</td>'
        f'<td class="num">{_t2_cell(no_skill_recs)}</td>'
        f'<td class="num">{_t2_delta(skill_recs, no_skill_recs)}</td>'
        f'<td class="num">{_tokens_pair(skill_recs, no_skill_recs)}</td>'
        f'<td>{_esc(_aggregate_method_label(a["methods"], a.get("power_metrics")))}</td>'
        f'</tr>'
    )


def _render_ab_child_row(
    conn: sqlite3.Connection,
    skill_key: str,
    case: str,
    client: str,
    model: str,
    recs: list[sqlite3.Row],
) -> str:
    skill_recs, no_skill_recs = _split_arms(recs)
    a = _aggregate(skill_recs or recs)
    arm_key = f'{skill_key}:{case}:{client}:{model}'
    classes = "arm-row expandable"
    caret = '<span class="arm-caret">&#9656;</span>'

    arm_html = (
        f'<tr class="{classes}" data-parent="{_esc(skill_key)}" '
        f'data-arm-key="{_esc(arm_key)}">'
        f'<td class="arm-name">'
        f'{caret}'
        f'<span class="case">{_esc(case)}</span>'
        f'</td>'
        f'<td>{_esc(client)}</td>'
        f'<td title="{_esc(model)}">{_esc(_model_label(model))}</td>'
        f'<td class="ctr">{_status_pair(skill_recs, no_skill_recs)}</td>'
        f'<td class="ctr">{_halluc_pair(skill_recs, no_skill_recs)}</td>'
        f'<td class="num">{_esc(_runtime_pair(skill_recs, no_skill_recs))}</td>'
        f'<td class="num">{_esc(_cost_pair(skill_recs, no_skill_recs))}</td>'
        f'<td class="num">{_t2_cell(skill_recs)}</td>'
        f'<td class="num">{_t2_cell(no_skill_recs)}</td>'
        f'<td class="num">{_t2_delta(skill_recs, no_skill_recs)}</td>'
        f'<td class="num">{_tokens_pair(skill_recs, no_skill_recs)}</td>'
        f'<td>{_esc(_aggregate_method_label(a["methods"], a.get("power_metrics")))}</td>'
        f'</tr>'
    )

    detail_html = _render_ab_detail_block(conn, skill_recs, no_skill_recs, arm_key)
    grader_row = (
        f'<tr class="grader-row" data-parent-arm="{_esc(arm_key)}">'
        f'<td colspan="12">{detail_html}</td>'
        f'</tr>'
    )
    return arm_html + grader_row


def _render_ab_detail_block(
    conn: sqlite3.Connection,
    skill_recs: list[sqlite3.Row],
    no_skill_recs: list[sqlite3.Row],
    arm_key: str,
) -> str:
    return (
        '<div style="display:grid; grid-template-columns: repeat(auto-fit, '
        'minmax(320px, 1fr)); gap:12px;">'
        f'{_render_arm_detail(conn, "Skill test", skill_recs, f"{arm_key}:skill")}'
        f'{_render_arm_detail(conn, "No-skill test", no_skill_recs, f"{arm_key}:noskill")}'
        '</div>'
    )


def _render_arm_detail(
    conn: sqlite3.Connection,
    title: str,
    recs: list[sqlite3.Row],
    group_id: str,
) -> str:
    if not recs:
        return (
            f'<div style="border:1px solid {_BORDER}; border-radius:6px; '
            f'padding:10px; color:{_MUTED}; background:{_SURFACE};">'
            f'<strong style="color:{_TEXT};">{_esc(title)}</strong><br>'
            'No run recorded for this test.</div>'
        )

    ordered = sorted(recs, key=lambda r: (r["replication_index"] or 0))

    # Default tab: first FAILing/ERRORing rep, else rep 0 -- same rule the
    # dashboard used before there was a picker, so the panel that's open on
    # load is the one that explains the status shown in the row above.
    default_rec = next(
        (r for r in ordered if r["status"] in ("FAIL", "ERROR")), ordered[0]
    )

    # When reps disagree, disclose the pass spread next to the title.
    summary = ""
    if len(ordered) > 1:
        n_pass = sum(1 for r in ordered if r["status"] == "PASS")
        summary = (
            f' <span style="color:{_MUTED}; font-weight:400; font-size:11px;">'
            f'({n_pass}/{len(ordered)} reps passed)</span>'
        )

    tabs_html = (
        _render_rep_tabs(ordered, default_rec, group_id)
        if len(ordered) > 1 else ""
    )
    panels_html = "".join(
        _render_rep_panel(conn, r, group_id, active=(r is default_rec))
        for r in ordered
    )

    return (
        f'<div style="border:1px solid {_BORDER}; border-radius:6px; '
        f'padding:10px; background:{_SURFACE};">'
        f'<div style="font-weight:600; color:{_TEXT}; margin-bottom:6px;">'
        f'{_esc(title)}{summary}</div>'
        f'{tabs_html}'
        f'{panels_html}'
        '</div>'
    )


def _render_rep_tabs(
    ordered: list[sqlite3.Row], default_rec: sqlite3.Row, group_id: str,
) -> str:
    """Clickable tab strip, one per replication, so a multi-rep group's
    detail panel can show any single rep on demand instead of only the
    one _render_arm_detail defaults to. Colour-by-status dot mirrors
    _rep_dots' at-a-glance convention; the click handler that swaps the
    visible .rep-panel lives in _render_skill_switcher_js."""
    btns = []
    for r in ordered:
        idx = r["replication_index"]
        active = " active" if r is default_rec else ""
        color = _STATUS_FG.get(r["status"], _MUTED)
        btns.append(
            f'<button type="button" class="rep-tab-btn{active}" '
            f'data-rep-group="{_esc(group_id)}" data-rep-index="{_esc(idx)}" '
            f'title="rep {_esc(idx)}: {_esc(r["status"])}">'
            f'<span class="dot" style="background:{color};"></span>'
            f'Rep {_esc(idx)}</button>'
        )
    return f'<div class="rep-tab-strip">{"".join(btns)}</div>'


def _render_rep_panel(
    conn: sqlite3.Connection, rec: sqlite3.Row, group_id: str, *, active: bool,
) -> str:
    """One replication's Prompt/Timeline/Final response/Grader/Call-summary
    content, hidden unless *active* -- the rep-tab click handler toggles
    which panel in a group is visible via the shared data-rep-group/
    data-rep-index attributes."""
    graders = _grader_rows(conn, rec["id"])
    log_data = _load_session_log(conn, rec)
    timeline = (log_data or {}).get("output", {}).get("tool_timeline") or []
    cls = "rep-panel active" if active else "rep-panel"
    return (
        f'<div class="{cls}" data-rep-group="{_esc(group_id)}" '
        f'data-rep-index="{_esc(rec["replication_index"])}">'
        + _render_prompt_section(log_data)
        + _render_timeline_section(log_data, rec["client"])
        + _render_final_response_section(log_data)
        + _render_grader_section(graders, rec)
        + _render_call_summary_section(timeline)
        + '</div>'
    )


def _section(title: str, body: str, *, open_: bool = False) -> str:
    """A collapsible ``.section`` block; empty body -> nothing rendered."""
    if not body or not body.strip():
        return ""
    op = " open" if open_ else ""
    return (
        f'<details class="section"{op}><summary>{_esc(title)}</summary>'
        f'<div class="body">{body}</div></details>'
    )


def _render_timeline_section(log_data: dict | None, client: str | None) -> str:
    output = (log_data or {}).get("output") or {}
    timeline = output.get("tool_timeline") or []
    if timeline:
        body = _render_tool_timeline(timeline)
    else:
        # Fallback for older logs / backends without a captured timeline:
        # the plain ordered tool-call list mined from the transcript.
        calls = _tool_calls_detailed(
            output.get("stdout") or "", output.get("stderr") or "",
            client=client)
        if not calls:
            return ""
        items = "".join(
            f'<li><span style="color:{_MUTED};">{_tool_icon(n)}</span> '
            f'<code>{_esc(n)}</code>'
            f'{(" " + _expandable(c, limit=160)) if c else ""}</li>'
            for n, c in calls
        )
        body = (f'<ol style="margin:0 0 4px 18px; padding:0; '
                f'font-size:12px;">{items}</ol>')
    return _section("Timeline", body)


def _session_log_download(log_data: dict | None) -> str:
    """Download link pointing at the saved session-log JSON on disk.

    Uses ``../logs/<rel>`` so it resolves both ways: served (the report
    server's ``/logs/<rel>`` route serves the file) and static (relative to
    ``_runtime/reports/index.html`` -> ``_runtime/logs/<rel>``). No inline
    embedding, so it doesn't bloat the dashboard."""
    rel = (log_data or {}).get("_log_rel")
    if not rel:
        return ""
    href = "../logs/" + quote(rel, safe="/")
    return (
        f'<a href="{_esc(href)}" download '
        f'style="display:inline-block; padding:3px 10px; border:1px solid '
        f'{_ACCENT}; color:{_ACCENT}; border-radius:6px; font-size:12px; '
        f'text-decoration:none; font-weight:600;">'
        f'&#8681; Download session log (.json)</a>'
    )


def _render_final_response_section(log_data: dict | None) -> str:
    output = (log_data or {}).get("output") or {}
    # Prefer the final answer captured at run time (survives stdout truncation);
    # fall back to extracting it from the stored (possibly truncated) stdout.
    final = output.get("final_response")
    if final is None:
        final = _final_response_text(output.get("stdout") or "",
                                     output.get("stderr") or "")
    final = (final or "").strip()

    download = _session_log_download(log_data)
    if not final and not download:
        return ""

    body = []
    if download:
        body.append(f'<div style="margin-bottom:8px;">{download}</div>')
    if final:
        body.append(f'<pre>{_expandable(final, limit=600)}</pre>')
    else:
        body.append(
            f'<div style="color:{_MUTED}; font-size:12px;">No final answer text '
            f'was captured — download the session log for the full transcript.</div>'
        )
    return _section("Final response", "".join(body))


def _render_grader_section(graders: list, rec: sqlite3.Row) -> str:
    body = _render_grader_block(graders, rec)
    n = len(graders or [])
    n_pass = sum(1 for g in (graders or []) if g["passed"])
    headline = f' — {n_pass}/{n} passed' if n else ''
    return _section(f'Grader score{headline}', body)


def _call_token_breakdown(r: dict) -> tuple[dict, bool, bool]:
    """Per-call token split -> ({in,out,cin,cout}, has_cache, estimated).

    Real usage when the backend reports it; otherwise base's len/4 heuristic
    over the per-call text (args -> input, result -> output), no cache split."""
    if any(r.get(k) is not None
           for k in ("tokens_in", "tokens_out", "cache_read", "cache_write")):
        return ({"in": r.get("tokens_in") or 0, "out": r.get("tokens_out") or 0,
                 "cin": r.get("cache_read") or 0, "cout": r.get("cache_write") or 0},
                True, False)
    args_len = len(str(r.get("args") or ""))
    rc = r.get("result_chars")
    return ({"in": -(-args_len // _CHARS_PER_TOKEN) if args_len else 0,
             "out": -(-rc // _CHARS_PER_TOKEN) if rc else 0, "cin": 0, "cout": 0},
            False, True)


def _tok_txt(v: int, est: bool) -> str:
    return (("~" if est else "") + _fmt_tokens(v)) if v else "—"


def _passfail_cell(ok: int, fail: int) -> str:
    """Render a per-tool ``pass/fail`` cell, e.g. ``16/2``.

    Three distinct states, because conflating the last two is how a report
    lies: ``16/2`` (measured, some failed), ``16/0`` (measured, none
    failed), and ``—`` (*no per-call status in this transcript at all*).
    Only the anthropic stream-json recognizer records ``is_error``
    (tool_timing.py:_from_stream_json), so an opencode or cursor run has no
    per-call outcome to report -- showing it as "0 fails" would present
    missing instrumentation as a clean result.
    """
    if not ok and not fail:
        return f'<span style="color:{_MUTED};" title="no per-call status in this transcript">—</span>'
    fail_part = (f'<span style="color:{_RED}; font-weight:600;">{fail}</span>'
                 if fail else f'<span style="color:{_MUTED};">0</span>')
    return (f'<span style="font-variant-numeric:tabular-nums;">'
            f'{ok}<span style="color:{_MUTED};">/</span>{fail_part}</span>')


def _render_call_summary_section(timeline: list[dict]) -> str:
    """Per-tool rollup: count, total token utilization, time, pass/fail."""
    if not timeline:
        return ""
    agg: dict[str, dict] = {}
    order: list[str] = []
    for r in timeline:
        is_skill = (r.get("kind") == "skill"
                    or str(r.get("name") or "").strip().lower() == "skill")
        key = f'skill: {_skill_label(r)}' if is_skill else str(r.get("name") or "")
        a = agg.get(key)
        if a is None:
            a = {"count": 0, "in": 0, "out": 0, "cin": 0, "cout": 0,
                 "has_cache": False, "est": False,
                 "time": 0.0, "has_time": False, "fail": 0, "ok": 0}
            agg[key] = a
            order.append(key)
        a["count"] += 1
        bd, has_cache, est = _call_token_breakdown(r)
        for k in ("in", "out", "cin", "cout"):
            a[k] += bd[k]
        a["has_cache"] = a["has_cache"] or has_cache
        a["est"] = a["est"] or est
        d = r.get("duration_s")
        if d is not None:
            a["time"] += d
            a["has_time"] = True
        # Track passes explicitly rather than deriving them as count-fail:
        # `is_error` is only ever set by the anthropic stream-json recognizer
        # (tool_timing.py:_from_stream_json), so on an opencode/cursor
        # transcript every call is neither ok nor fail. Deriving pass as
        # count-fail would report those as "all passed" -- an absent signal
        # rendered as a clean bill of health. Keeping them separate lets the
        # renderer tell "0 failures" apart from "no failure data".
        if r.get("is_error"):
            a["fail"] += 1
        elif "is_error" in r:
            a["ok"] += 1

    def _num_td(inner: str) -> str:
        return (f'<td style="padding:3px 8px; text-align:right; '
                f'font-variant-numeric:tabular-nums;">{inner}</td>')

    def _cache_txt(v: int, present: bool) -> str:
        return _fmt_tokens(v) if present else "—"

    rows = []
    tot = {"count": 0, "in": 0, "out": 0, "cin": 0, "cout": 0,
           "time": 0.0, "fail": 0, "ok": 0}
    any_est = any_cache = False
    for key in order:
        a = agg[key]
        for k in ("count", "in", "out", "cin", "cout", "time", "fail", "ok"):
            tot[k] += a[k]
        any_est = any_est or a["est"]
        any_cache = any_cache or a["has_cache"]
        fail_txt = _passfail_cell(a["ok"], a["fail"])
        rows.append(
            f'<tr>'
            f'<td class="tool" style="padding:3px 8px;"><code>{_esc(key)}</code></td>'
            + _num_td(str(a["count"]))
            + _num_td(_tok_txt(a["in"], a["est"]))
            + _num_td(_tok_txt(a["out"], a["est"]))
            + _num_td(_cache_txt(a["cin"], a["has_cache"]))
            + _num_td(_cache_txt(a["cout"], a["has_cache"]))
            + _num_td(_esc(_fmt_secs(a["time"]) if a["has_time"] else "—"))
            + f'<td style="padding:3px 8px; text-align:center;">{fail_txt}</td>'
            + '</tr>'
        )
    rows.append(
        f'<tr style="border-top:2px solid {_BORDER}; font-weight:600;">'
        f'<td style="padding:3px 8px; color:{_MUTED};">TOTAL '
        f'({len(order)} tool{"s" if len(order) != 1 else ""})</td>'
        + _num_td(str(tot["count"]))
        + _num_td(_tok_txt(tot["in"], any_est))
        + _num_td(_tok_txt(tot["out"], any_est))
        + _num_td(_cache_txt(tot["cin"], any_cache))
        + _num_td(_cache_txt(tot["cout"], any_cache))
        + _num_td(_esc(_fmt_secs(tot["time"])))
        + f'<td style="padding:3px 8px; text-align:center;">'
        f'{_passfail_cell(tot["ok"], tot["fail"])}</td>'
        + '</tr>'
    )
    body = (
        f'<table class="tl"><colgroup><col>'
        f'<col style="width:42px;"><col style="width:50px;">'
        f'<col style="width:50px;"><col style="width:58px;">'
        f'<col style="width:58px;"><col style="width:54px;">'
        f'<col style="width:44px;"></colgroup>'
        f'<thead><tr style="color:{_MUTED}; font-size:10px; '
        f'text-transform:uppercase; letter-spacing:.04em;">'
        f'<th style="text-align:left; padding:3px 8px;">tool</th>'
        f'<th style="text-align:right; padding:3px 8px;">count</th>'
        f'<th style="text-align:right; padding:3px 8px;">in</th>'
        f'<th style="text-align:right; padding:3px 8px;">out</th>'
        f'<th style="text-align:right; padding:3px 8px;">cache&nbsp;in</th>'
        f'<th style="text-align:right; padding:3px 8px;">cache&nbsp;out</th>'
        f'<th style="text-align:right; padding:3px 8px;">time</th>'
        f'<th style="text-align:center; padding:3px 8px;">pass&#8202;/&#8202;fail</th>'
        f'</tr></thead><tbody>' + "".join(rows) + '</tbody></table>'
    )
    return _section("Summary", body)


def _render_prompt_section(log_data: dict | None) -> str:
    """Collapsible "Prompt" section sourced from the session-log JSON.

    Omitted entirely (not an empty toggle) when no session log was found --
    e.g. an older run, or one with session_log.enabled=false.
    """
    prompt = (log_data or {}).get("prompt")
    if not prompt:
        return ""
    return (
        '<details class="section"><summary>Prompt</summary>'
        f'<div class="body">{_expandable(prompt, limit=400)}</div>'
        '</details>'
    )


_LOGFMT_LINE = re.compile(
    r'^timestamp=(?P<ts>\S+)\s+level=(?P<level>\S+)\s+'
    r'(?:run=\S+\s+)?message=(?:"(?P<qmsg>(?:[^"\\]|\\.)*)"|(?P<msg>\S+))'
)
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
# Bootstrap/config-loading noise that dwarfs the signal in every opencode
# run and carries no debugging value (dozens of near-identical lines).
_NOISY_MESSAGE_PREFIXES = ("loading",)
# opencode's internal event-loop bookkeeping: fires dozens of times per run
# and carries no debugging signal (vs. one-off lifecycle/tool/file events,
# which are kept). WARN/ERROR-level lines are always kept regardless of
# message, on the theory that a warning is worth seeing even if terse.
_NOISY_MESSAGES = {
    "init", "all LSPs are disabled", "all formatters are disabled",
    "stream", "llm runtime selected", "evaluated", "loop", "process",
    "stream error", "formatting", "resolved path",
}


def _tool_icon(name: str) -> str:
    if name.startswith("mcp__"):
        return "⚙"
    if name in ("Bash", "shell"):
        return "$"
    if name == "Skill":
        return "◆"
    return "→"


def _activity_timeline(stderr: str) -> list[tuple[str, str, str]]:
    """Best-effort chronological (time, level, message) events mined from a
    logfmt-style stderr stream (opencode's runtime log). Filters out
    high-volume bootstrap noise. Returns [] for non-logfmt backends -- their
    stderr just won't match and every line is silently skipped."""
    events: list[tuple[str, str, str]] = []
    for raw in stderr.splitlines():
        line = _ANSI_RE.sub("", raw).strip()
        m = _LOGFMT_LINE.match(line)
        if not m:
            continue
        msg = (m.group("qmsg") or m.group("msg") or "").strip()
        level = m.group("level")
        is_noisy = not msg or msg in _NOISY_MESSAGES or msg.startswith(_NOISY_MESSAGE_PREFIXES)
        if is_noisy and level not in ("WARN", "ERROR"):
            continue
        ts = m.group("ts")
        time_part = ts.split("T", 1)[1].rstrip("Z") if "T" in ts else ts
        events.append((time_part, level, msg))
    return events


def _fmt_offset(s: float | int | None) -> str:
    """Format a seconds-since-start offset as ``t+12.3s`` / ``t+1m03s``."""
    if s is None:
        return "—"
    s = float(s)
    if s >= 60:
        return f"t+{int(s // 60)}m{int(s % 60):02d}s"
    return f"t+{s:.1f}s"


def _render_tool_timeline(timeline: list[dict]) -> str:
    """Chronological chain of tool calls with a duration bar per call.

    ``timeline`` rows are ``{seq, name, args, t_start, duration_s}`` as produced
    by ``cli_backends.tool_timing``. Bars are scaled to the longest call so the
    slowest tool reads at a glance; a call with unknown duration shows no bar.
    """
    if not timeline:
        return ""
    durs = [r.get("duration_s") for r in timeline if r.get("duration_s") is not None]
    max_dur = max(durs) if durs else 0.0
    total_dur = sum(durs) if durs else 0.0

    rows = []
    for r in timeline:
        name = str(r.get("name") or "")
        dur = r.get("duration_s")
        t_start = r.get("t_start")
        args = r.get("args") or ""
        # Duration bar (green→amber→red by share of the slowest call).
        if dur is not None and max_dur > 0:
            pct = max(2.0, 100.0 * dur / max_dur)
            share = dur / max_dur
            bar_color = (_RED if share >= 0.75 else
                         _AMBER if share >= 0.4 else _GREEN)
            bar = (
                f'<div style="background:{_BG}; border-radius:3px; '
                f'min-width:60px; height:12px; position:relative;">'
                f'<div style="width:{pct:.1f}%; height:100%; '
                f'background:{bar_color}; opacity:.55; border-radius:3px;"></div>'
                f'</div>'
            )
        else:
            bar = f'<span style="color:{_MUTED};">—</span>'
        dur_txt = _fmt_secs(dur) if dur is not None else "—"
        # Wraps to fit the column width; clamped to 3 lines with a trailing
        # "…" so rows stay short. Click to expand the clamp (CSS-only).
        args_html = (
            f'<details class="tl-args"><summary title="{_esc(args)}">'
            f'<span class="tl-clamp">{_esc(args)}</span></summary></details>'
            if args else ""
        )
        stats_html = _timeline_stats_cell(r)

        # `kind`/`skill` are tagged at capture time; fall back to name-sniffing
        # so timelines captured before that tagging still show the trigger.
        is_skill = (r.get("kind") == "skill"
                    or str(name).strip().lower() == "skill")
        if is_skill:
            # Skill activation: highlight the row and label it as the trigger
            # that opened the tool chain below it.
            skill_name = _skill_label(r)
            row_style = (
                f' style="background:rgba(88,166,255,0.10);'
                f' border-left:3px solid {_ACCENT};"'
            )
            tool_cell = (
                f'<td class="tool" style="padding:2px 8px;">'
                f'<span style="color:{_ACCENT};">&#9670;</span> '
                f'<span style="display:inline-block; padding:0 6px; '
                f'border:1px solid {_ACCENT}; color:{_ACCENT}; border-radius:8px; '
                f'font-size:10px; font-weight:600; letter-spacing:.5px;">SKILL</span> '
                f'<code style="color:{_ACCENT};">{_esc(skill_name)}</code></td>'
            )
        else:
            row_style = ''
            tool_cell = (
                f'<td class="tool" style="padding:2px 8px;">'
                f'<span style="color:{_MUTED};">{_tool_icon(name)}</span> '
                f'<code>{_esc(name)}</code></td>'
            )
        rows.append(
            f'<tr{row_style}>'
            f'<td style="color:{_MUTED}; text-align:right; padding:2px 8px;">'
            f'{r.get("seq", "")}</td>'
            f'<td style="color:{_MUTED}; font-variant-numeric:tabular-nums; '
            f'white-space:nowrap; padding:2px 8px;">{_esc(_fmt_offset(t_start))}</td>'
            f'{tool_cell}'
            f'<td style="padding:2px 8px;">{bar}</td>'
            f'<td style="text-align:right; font-variant-numeric:tabular-nums; '
            f'white-space:nowrap; padding:2px 8px;">{_esc(dur_txt)}</td>'
            f'<td style="padding:2px 8px; line-height:1.7;">{stats_html}</td>'
            f'<td style="padding:2px 8px;">{args_html}</td>'
            f'</tr>'
        )

    n_skill = sum(
        1 for r in timeline
        if r.get("kind") == "skill" or str(r.get("name") or "").strip().lower() == "skill"
    )
    skill_note = f' &middot; {n_skill} skill trigger{"s" if n_skill != 1 else ""}' if n_skill else ''
    out_total = sum(r.get("tokens_out") or 0 for r in timeline)
    out_note = f' &middot; {_fmt_tokens(out_total)} out' if out_total else ''
    total_note = (
        f' &middot; {_fmt_secs(total_dur)} in tools' if total_dur else ''
    )
    # Legend for the token/stat glyphs used in the "tokens / result" column.
    legend = (
        f'<div style="color:{_MUTED}; font-size:10px; margin:0 0 4px; '
        f'line-height:1.6;">tokens/call &mdash; '
        f'&#8593; input &middot; &#8595; output &middot; '
        f'&#8853; cache-write (new input) &middot; '
        f'&#9211; cache-read (from cache) &middot; '
        f'&#8618; result size (chars) &middot; '
        f'<span style="font-style:italic;">~</span> estimated &middot; '
        f'bar = duration</div>'
    )
    return (
        f'<div style="font-weight:600; color:{_TEXT}; font-size:11px; '
        f'text-transform:uppercase; letter-spacing:.04em; margin:2px 0 2px;">'
        f'Tool timeline ({len(timeline)} calls{skill_note}{out_note}{total_note})</div>'
        + legend +
        f'<table class="tl">'
        f'<colgroup>'
        f'<col style="width:30px;"><col style="width:58px;">'
        f'<col style="width:22%;"><col style="width:14%;">'
        f'<col style="width:48px;"><col style="width:24%;">'
        f'<col>'
        f'</colgroup>'
        f'<thead><tr style="color:{_MUTED}; font-size:10px; '
        f'text-transform:uppercase; letter-spacing:.04em;">'
        f'<th style="text-align:right; padding:2px 8px;">#</th>'
        f'<th style="text-align:left; padding:2px 8px;">start</th>'
        f'<th style="text-align:left; padding:2px 8px;">tool</th>'
        f'<th style="text-align:left; padding:2px 8px;">duration</th>'
        f'<th style="text-align:right; padding:2px 8px;"></th>'
        f'<th style="text-align:left; padding:2px 8px;">tokens / result</th>'
        f'<th style="text-align:left; padding:2px 8px;">args</th>'
        f'</tr></thead><tbody>' + "".join(rows) + '</tbody></table>'
    )


_CHARS_PER_TOKEN = 4  # base's len/4 heuristic, reused for per-call estimates


def _skill_label(r: dict) -> str:
    """Bare skill name for a skill-trigger row, cleaning older timelines that
    stored the raw JSON input (``{"skill": "x", ...}``) as the label."""
    s = str(r.get("skill") or r.get("args") or "").strip()
    if s.startswith("{"):
        try:
            obj = json.loads(s)
        except (json.JSONDecodeError, ValueError):
            obj = None
        if isinstance(obj, dict):
            for k in ("skill", "name", "command"):
                if isinstance(obj.get(k), str) and obj[k].strip():
                    return obj[k].strip()
    return s.strip('"').strip("'").strip() or "skill"


def _timeline_stats_cell(r: dict) -> str:
    """Per-call stats chips: token usage (in/out/cache), result size, and an
    error pill.

    Real per-call usage exists only where the transcript reports it (Claude
    Code's stream-json ``usage`` block). When it does not (e.g. opencode), we
    fall back to base's ``len/4`` heuristic over the per-call text we do have --
    the args blob (input) and result size (output) -- and mark it ``~`` /
    italic so an estimate is never mistaken for a measured value.
    """
    chips: list[str] = []
    # Status chip. Previously only failures were chipped, which left a
    # successful call and a call with *no status data* rendering
    # identically (both blank) -- so a reader could not tell "this tool
    # succeeded" from "this backend doesn't report tool outcomes". Emit an
    # explicit OK for a measured success and stay blank only when the
    # recognizer never set `is_error` at all (opencode/cursor today; see
    # tool_timing.py:_from_stream_json, the only writer of that key).
    if r.get("is_error"):
        chips.append(
            f'<span style="display:inline-block; padding:0 6px; '
            f'border:1px solid {_RED}; color:{_RED}; border-radius:8px; '
            f'font-size:10px; font-weight:600;">ERROR</span>'
        )
    elif "is_error" in r:
        chips.append(
            f'<span style="display:inline-block; padding:0 6px; '
            f'border:1px solid {_GREEN}; color:{_GREEN}; border-radius:8px; '
            f'font-size:10px; font-weight:600;">OK</span>'
        )

    t_in, t_out = r.get("tokens_in"), r.get("tokens_out")
    estimated = False
    if t_in is None and t_out is None:
        args_len = len(str(r.get("args") or ""))
        rc = r.get("result_chars")
        t_in = -(-args_len // _CHARS_PER_TOKEN) if args_len else None
        t_out = -(-rc // _CHARS_PER_TOKEN) if rc else None
        estimated = t_in is not None or t_out is not None

    tok_parts: list[str] = []
    pfx = "~" if estimated else ""
    if t_in is not None:
        tok_parts.append(f'{pfx}&#8593;{_fmt_tokens(t_in)}')
    if t_out is not None:
        tok_parts.append(f'{pfx}&#8595;{_fmt_tokens(t_out)}')
    if tok_parts:
        title = (
            "estimated from per-call text length (chars/4); this backend "
            "reports no per-call token usage"
            if estimated else
            "input (context) / output (generated) tokens for the turn that "
            "issued this call"
        )
        style = f'color:{_MUTED};' + (' font-style:italic;' if estimated else '')
        chips.append(
            f'<span title="{title}" style="{style}">{" ".join(tok_parts)}</span>'
        )

    cache_w = r.get("cache_write")
    if cache_w:
        chips.append(
            f'<span title="prompt-cache write: new input tokens processed and '
            f'cached this turn" style="color:{_MUTED};">'
            f'&#8853;{_fmt_tokens(cache_w)}</span>'
        )
    cache_r = r.get("cache_read")
    if cache_r:
        chips.append(
            f'<span title="prompt-cache read: input tokens served from cache '
            f'this turn" style="color:{_MUTED};">'
            f'&#9211;{_fmt_tokens(cache_r)}</span>'
        )
    rc = r.get("result_chars")
    if rc:
        chips.append(
            f'<span title="tool result size (characters returned)" '
            f'style="color:{_MUTED};">&#8618;{_fmt_tokens(rc)} ch</span>'
        )
    if not chips:
        return f'<span style="color:{_MUTED};">—</span>'
    return ' '.join(chips)


def _render_session_log_section(log_data: dict | None, client: str | None) -> str:
    """Collapsible "Conversation" section: the tool-call sequence the agent
    actually ran (mined via graders.trace, the same parser the
    action_sequence/trigger graders use for grading -- not a re-implementation),
    a best-effort timestamped activity timeline, and the final response text.
    Omitted entirely when there is no session log or it recorded no output.
    """
    if not log_data:
        return ""
    output = log_data.get("output") or {}
    stdout = output.get("stdout") or ""
    stderr = output.get("stderr") or ""
    if not stdout and not stderr:
        return ""

    parts = []

    # Preferred: the chronological tool-call chain with per-call durations,
    # captured at run time. Older runs / backends without it fall back to the
    # plain ordered list mined from the transcript.
    timeline = (log_data.get("output") or {}).get("tool_timeline") or []
    if timeline:
        parts.append(_render_tool_timeline(timeline))
    else:
        calls = _tool_calls_detailed(stdout, stderr, client=client)
        if calls:
            items = []
            for name, command in calls:
                cmd_html = f' {_expandable(command, limit=160)}' if command else ""
                items.append(
                    f'<li><span style="color:{_MUTED};">{_tool_icon(name)}</span> '
                    f'<code>{_esc(name)}</code>{cmd_html}</li>'
                )
            parts.append(
                f'<div style="font-weight:600; color:{_TEXT}; font-size:11px; '
                f'text-transform:uppercase; letter-spacing:.04em; margin:2px 0 4px;">'
                f'Tool calls ({len(calls)})</div>'
                f'<ol style="margin:0 0 10px 18px; padding:0; font-size:12px;">'
                + "".join(items) + '</ol>'
            )

    events = _activity_timeline(stderr)
    if events:
        items = [
            f'<li><span style="color:{_MUTED}; font-variant-numeric:tabular-nums;">'
            f'{_esc(t)}</span> '
            f'<span style="color:{_RED if lvl == "ERROR" else _AMBER if lvl == "WARN" else _MUTED};">'
            f'{_esc(lvl)}</span> {_esc(msg)}</li>'
            for t, lvl, msg in events
        ]
        parts.append(
            f'<details class="expand" style="display:block;">'
            f'<summary><span class="tog">activity timeline ({len(events)} events)</span></summary>'
            f'<ol style="margin:6px 0 10px 18px; padding:0; font-size:11px; '
            f'font-family:ui-monospace,monospace;">' + "".join(items) + '</ol>'
            '</details>'
        )

    if stdout:
        parts.append(
            f'<div style="font-weight:600; color:{_TEXT}; font-size:11px; '
            f'text-transform:uppercase; letter-spacing:.04em; margin:6px 0 4px;">'
            f'Final response</div>'
            f'<pre>{_expandable(stdout, limit=300)}</pre>'
        )
    if stderr:
        parts.append(
            '<details class="expand" style="display:block; margin-top:6px;">'
            '<summary><span class="tog">raw stderr</span></summary>'
            f'<pre style="margin-top:4px;">{_esc(stderr)}</pre>'
            '</details>'
        )

    if not parts:
        return ""
    return (
        '<details class="section"><summary>Conversation</summary>'
        f'<div class="body">{"".join(parts)}</div>'
        '</details>'
    )


def _render_contract_detail(details_raw: object) -> str:
    """Render the output_contract_match verdict: golden-vs-generated JSON, with
    each anomaly (mismatch / missing / extra) called out. Clean match -> a green
    'exact match' note."""
    d = _parse_jsonish(details_raw)
    if not isinstance(d, dict):
        return _expandable(_fmt_plain_detail(details_raw, max_len=10**9))

    if not d.get("extracted", True):
        return (f'<span style="color:{_RED};">no JSON result extracted</span> '
                f'<span style="color:{_MUTED};">— {_esc(d.get("feedback", ""))}</span>')

    matched = d.get("matched", 0)
    total = d.get("total", 0)
    mismatches = d.get("mismatches") or []
    missing = d.get("missing") or []
    extra = d.get("extra") or []
    allow_extra = d.get("allow_extra", True)
    # Allowed extras are not anomalies -- they don't affect the verdict and are
    # shown only as an informational footnote. Only disallowed extras are rows.
    hard_extra = [] if allow_extra else extra

    # An informational note listing the agent's allowed extra fields.
    extra_note = ""
    if allow_extra and extra:
        shown = ", ".join(extra[:12]) + ("…" if len(extra) > 12 else "")
        extra_note = (f'<div style="color:{_MUTED}; font-size:11px; margin-top:3px;">'
                      f'+{len(extra)} allowed extra field(s): {_esc(shown)}</div>')

    # LLM-judge verdicts for semantic fields (e.g. notes): show score+rationale
    # for each, green when it cleared the bar, red when it didn't, muted skips.
    semantic = d.get("semantic") or []
    sem_lines = []
    for s in semantic:
        score = s.get("score")
        if s.get("skipped"):
            col, tag = _MUTED, "skipped"
        else:
            col = _GREEN if s.get("passed") else _RED
            tag = f"{score:.0f}/100" if isinstance(score, (int, float)) else "?"
        rat = _esc(s.get("rationale", ""))
        sem_lines.append(
            f'<div style="color:{col}; font-size:11px; margin-top:2px;">'
            f'&#9878; <code>{_esc(s.get("path"))}</code> judged {tag}'
            + (f' — {rat}' if rat else '') + '</div>')
    sem_note = "".join(sem_lines)

    head_color = _GREEN if (not mismatches and not missing
                            and not hard_extra) else _RED
    head = (f'<div style="margin-bottom:4px;"><strong style="color:{head_color};">'
            f'output contract</strong> '
            f'<span style="color:{_MUTED};">{matched}/{total} fields match</span></div>')

    if not mismatches and not missing and not hard_extra:
        clean = " exactly" if not extra else " (extra fields allowed)"
        return head + (f'<div style="color:{_GREEN}; font-size:12px;">'
                       f'&#10003; generated result matches golden{clean}</div>'
                       + sem_note + extra_note)

    rows = []
    for m in mismatches[:50]:
        # Semantic (LLM-judged) mismatches are labelled distinctly and carry
        # the judge's rationale in the generated cell.
        if m.get("semantic"):
            label = "JUDGE&#9878;"
            got = _esc(m.get("got"))
            rat = _esc(m.get("rationale", ""))
            got_cell = got + (f'<div style="color:{_MUTED}; font-size:10px;">'
                              f'{rat}</div>' if rat else '')
        else:
            label = "MISMATCH"
            got_cell = _esc(m.get("got"))
        rows.append(
            f'<tr><td style="padding:2px 8px;"><code>{_esc(m.get("path"))}</code></td>'
            f'<td style="padding:2px 8px; color:{_AMBER};">{label}</td>'
            f'<td style="padding:2px 8px; color:{_MUTED};">{_esc(m.get("expected"))}</td>'
            f'<td style="padding:2px 8px; color:{_RED};">{got_cell}</td></tr>'
        )
    for p in missing[:50]:
        rows.append(
            f'<tr><td style="padding:2px 8px;"><code>{_esc(p)}</code></td>'
            f'<td style="padding:2px 8px; color:{_RED};">MISSING</td>'
            f'<td style="padding:2px 8px; color:{_MUTED};">(expected)</td>'
            f'<td style="padding:2px 8px; color:{_RED};">&mdash;</td></tr>'
        )
    for p in hard_extra[:50]:
        rows.append(
            f'<tr><td style="padding:2px 8px;"><code>{_esc(p)}</code></td>'
            f'<td style="padding:2px 8px; color:{_AMBER};">EXTRA</td>'
            f'<td style="padding:2px 8px; color:{_MUTED};">&mdash;</td>'
            f'<td style="padding:2px 8px; color:{_AMBER};">(not allowed)</td></tr>'
        )
    table = (
        f'<table class="tl" style="margin-top:2px;"><colgroup><col>'
        f'<col style="width:84px;"><col style="width:30%;">'
        f'<col style="width:30%;"></colgroup>'
        f'<thead><tr style="color:{_MUTED}; font-size:10px; '
        f'text-transform:uppercase; letter-spacing:.04em;">'
        f'<th style="text-align:left; padding:2px 8px;">field</th>'
        f'<th style="text-align:left; padding:2px 8px;">anomaly</th>'
        f'<th style="text-align:left; padding:2px 8px;">golden</th>'
        f'<th style="text-align:left; padding:2px 8px;">generated</th>'
        f'</tr></thead><tbody>' + "".join(rows) + '</tbody></table>'
    )
    return head + table + sem_note + extra_note


_GRADER_CATEGORY_COLORS = {
    "mandatory":  (_RED,    "MANDATORY",  "Anti-hallucination contract; failure marks hallucination_detected=1."),
    "weighted":   (_ACCENT, "WEIGHTED",   "Soft grader contributing to the aggregate score."),
    "diagnostic": (_MUTED,  "DIAGNOSTIC", "Always-run observational probe; zero weight in score."),
}


def _render_grader_block(
    graders: list[sqlite3.Row], rec: sqlite3.Row,
) -> str:
    """Render the grader results table with mandatory/weighted/diagnostic
    category badges and a per-category summary header above the table."""
    out = []
    if rec["error"]:
        out.append(
            f'<div class="grader-error">'
            f'<strong>error:</strong> '
            f'<code>{_esc(str(rec["error"])[:300])}</code>'
            f'</div>'
        )
    if rec["skip_reason"]:
        out.append(
            f'<div class="grader-skip">'
            f'<strong>skip:</strong> {_esc(rec["skip_reason"])}'
            f'</div>'
        )
    if graders:
        # Category summary: count pass/fail per category before rendering rows.
        cat_stats: dict[str, dict] = {
            "mandatory": {"pass": 0, "fail": 0},
            "weighted":  {"pass": 0, "fail": 0},
            "diagnostic": {"pass": 0, "fail": 0},
        }
        for g in graders:
            cat = _grader_category(g)
            if cat not in cat_stats:
                cat_stats[cat] = {"pass": 0, "fail": 0}
            if g["passed"]:
                cat_stats[cat]["pass"] += 1
            else:
                cat_stats[cat]["fail"] += 1

        # Compact category summary strip above the table.
        summary_chips = []
        for cat in ("mandatory", "weighted", "diagnostic"):
            st = cat_stats.get(cat, {"pass": 0, "fail": 0})
            total = st["pass"] + st["fail"]
            if total == 0:
                continue
            base_color, label, _ = _GRADER_CATEGORY_COLORS[cat]
            chip_color = _RED if st["fail"] and cat != "diagnostic" else (
                _AMBER if st["fail"] and cat == "diagnostic" else base_color
            )
            chip_title = f"{_esc(label)}: {st['pass']}/{total} passed"
            summary_chips.append(
                f'<span style="display:inline-block; padding:1px 8px; '
                f'border:1px solid {chip_color}; color:{chip_color}; '
                f'border-radius:10px; font-size:10px; font-weight:600; '
                f'margin-right:6px; letter-spacing:.3px;" '
                f'title="{chip_title}">'
                f'{_esc(label)} {st["pass"]}/{total}</span>'
            )
        if summary_chips:
            out.append(
                f'<div style="margin-bottom:6px;">{"".join(summary_chips)}</div>'
            )

        out.append('<table class="grader-table">')
        out.append(
            '<thead><tr>'
            '<th>grader</th><th>category</th><th>type</th>'
            '<th class="ctr" style="text-align:center;">pass</th>'
            '<th style="text-align:right;">score</th>'
            '<th>detail</th>'
            '</tr></thead><tbody>'
        )
        for g in graders:
            passed = bool(g["passed"])
            color = _GREEN if passed else _RED
            mark = 'PASS' if passed else 'FAIL'
            if g["grader_type"] == "output_contract_match":
                detail_html = _render_contract_detail(g["details"])
            else:
                detail_html = _expandable(
                    _fmt_plain_detail(g["details"], max_len=10**9))

            cat = _grader_category(g)
            cat_color, cat_label, cat_title = _GRADER_CATEGORY_COLORS.get(
                cat, (_MUTED, cat.upper(), ""))
            # Failing mandatory grader is the hallucination signal -- make it loud.
            if cat == "mandatory" and not passed:
                badge_color = _RED
            elif cat == "mandatory":
                badge_color = _AMBER
            else:
                badge_color = cat_color

            badge = (
                f'<span style="display:inline-block; '
                f'padding:0 5px; margin-left:4px; '
                f'border:1px solid {badge_color}; color:{badge_color}; '
                f'border-radius:8px; font-size:10px; font-weight:600; '
                f'letter-spacing:.3px;" title="{_esc(cat_title)}">'
                f'{_esc(cat_label)}</span>'
            )

            out.append(
                f'<tr>'
                f'<td><code>{_esc(g["grader_id"])}</code></td>'
                f'<td>{badge}</td>'
                f'<td style="color:{_MUTED};">{_esc(g["grader_type"])}</td>'
                f'<td style="text-align:center; color:{color}; '
                f'font-weight:600;">{mark}</td>'
                f'<td style="text-align:right;">'
                f'{(g["score"] or 0):.2f}</td>'
                f'<td style="color:{_MUTED};">{detail_html}</td>'
                f'</tr>'
            )
        out.append('</tbody></table>')
    elif not rec["error"] and not rec["skip_reason"]:
        out.append(
            f'<div style="color:{_MUTED}; font-size:12px;">'
            f'No grader rows recorded for this test.</div>'
        )
    return "\n".join(out)


# ------------------------------------------ lifecycle cards (new table)

# Column names the new skill_lifecycle_evaluations table is expected to have.
# Queried defensively: if the table or column is absent, the section is
# silently omitted rather than raising an error (another agent owns the
# migration).
_LIFECYCLE_EVT_COLS = (
    "skill_name", "client", "model", "lifecycle_state", "evaluated_at",
    "assessment_sufficient", "consistency_passed", "n_cases", "n_reps",
    "n_results", "coverage_rate", "pass_rate", "fail_rate", "error_rate",
    "skip_rate", "failed_case_rate", "aggregate_score_mean",
    "aggregate_score_stdev", "flaky_case_rate", "variable_case_rate",
    "mandatory_grader_total", "mandatory_grader_fail_rate",
    "weighted_grader_total", "weighted_grader_fail_rate",
    "diagnostic_grader_total", "diagnostic_grader_fail_rate",
    "transition_reason", "prior_state",
)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    """True if *table* exists in the live SQLite schema."""
    try:
        result = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        return result is not None
    except sqlite3.OperationalError:
        return False


def _render_lifecycle_cards(
    conn: sqlite3.Connection,
    *,
    skill_name: str | None = None,
    run_id: str | None = None,
) -> str:
    """Consistency lifecycle cards from the new ``skill_lifecycle_evaluations``
    table.  Gracefully degrades to an empty string when:
    - the table hasn't been created yet (migration pending), or
    - expected columns are absent (schema version mismatch), or
    - the table is empty (no lifecycle evaluations have been written).

    Design: one card per skill showing the latest lifecycle state, aggregate
    score mean/σ, pass-rate, replication count, and the transition reason.
    Cards are grouped by state (KEEP → WATCH → DEPRECATE → REMOVE) so the
    at-a-glance view matches the old ``_render_callouts`` layout but carries
    the richer aggregate-score evidence the new table provides.
    """
    if not _table_exists(conn, "skill_lifecycle_evaluations"):
        return ""

    # Probe which of the expected columns actually exist (migration-safe).
    present_cols: set[str] = set()
    try:
        pragma = conn.execute(
            "PRAGMA table_info(skill_lifecycle_evaluations)"
        ).fetchall()
        for row in pragma:
            present_cols.add(row["name"] if isinstance(row, sqlite3.Row)
                             else row[1])
    except sqlite3.OperationalError:
        return ""

    # Must have at minimum skill_name + lifecycle_state to render anything.
    if not {"skill_name", "lifecycle_state"}.issubset(present_cols):
        return ""

    # Build SELECT projection -- NULL for every absent optional column so
    # downstream code can always reference them by name.
    def _col(name: str) -> str:
        return name if name in present_cols else f"NULL AS {name}"

    select_cols = ", ".join(_col(c) for c in _LIFECYCLE_EVT_COLS)
    try:
        # Latest record per skill/client/model cell. Different clients are
        # independent lifecycle decisions and must not hide one another.
        order_col = "evaluated_at" if "evaluated_at" in present_cols else "id"
        client_match = "COALESCE(s2.client, '') = COALESCE(skill_lifecycle_evaluations.client, '')" if "client" in present_cols else "1=1"
        model_match = "COALESCE(s2.model, '') = COALESCE(skill_lifecycle_evaluations.model, '')" if "model" in present_cols else "1=1"
        filters: list[str] = []
        params: list[str] = []
        if skill_name is not None:
            filters.append("skill_lifecycle_evaluations.skill_name = ?")
            params.append(skill_name)
        if run_id is not None:
            filters.append("skill_lifecycle_evaluations.run_id = ?")
            params.append(run_id)
        outer_filter = " AND " + " AND ".join(filters) if filters else ""
        rows = conn.execute(f"""
            SELECT {select_cols}
              FROM skill_lifecycle_evaluations
             WHERE {order_col} = (
                 SELECT MAX(s2.{order_col})
                   FROM skill_lifecycle_evaluations AS s2
                  WHERE s2.skill_name = skill_lifecycle_evaluations.skill_name
                    AND {client_match}
                    AND {model_match}
             )
             {outer_filter}
             ORDER BY skill_name, client, model
        """, tuple(params)).fetchall()
    except sqlite3.OperationalError:
        return ""

    if not rows:
        return ""

    by_state: dict[str, list] = {s: [] for s in ("UNASSESSED", "KEEP", "WATCH", "DEPRECATE", "REMOVE")}
    for r in rows:
        state = (r["lifecycle_state"] or "").upper()
        if state not in by_state:
            by_state[state] = []
        by_state[state].append(r)

    out = [
        '<h3>Consistency Lifecycle</h3>',
        '<div style="display:flex; gap:12px; flex-wrap:wrap; margin-bottom:12px;">',
    ]
    for state in ("UNASSESSED", "KEEP", "WATCH", "DEPRECATE", "REMOVE"):
        items = by_state.get(state, [])
        color = _STATE_COLORS.get(state, _GREY)
        out.append(
            f'<div style="flex:1 1 220px; min-width:220px; '
            f'border-left:4px solid {color}; padding:10px 14px; '
            f'background:{_SURFACE}; border:1px solid {_BORDER}; '
            f'border-left-width:4px; border-radius:6px;">'
            f'<div style="font-weight:600; color:{color}; '
            f'letter-spacing:.5px;">{_esc(state)} '
            f'<span style="color:{_MUTED}; font-weight:400">'
            f'({len(items)})</span></div>'
        )
        if not items:
            out.append(f'<div style="color:{_MUTED};">none</div>')
        else:
            out.append('<ul style="margin:6px 0 0 16px; padding:0;">')
            for r in items[:10]:
                mean = r["aggregate_score_mean"]
                stdev = r["aggregate_score_stdev"]
                pr = r["pass_rate"]
                n_reps = r["n_reps"]
                reason = r["transition_reason"] or ""
                prior = r["prior_state"] or ""

                score_txt = (
                    f"{float(mean):.3f}"
                    + (f" &plusmn; {float(stdev):.3f}" if stdev is not None else "")
                    if mean is not None else "—"
                )
                pr_txt = f"{float(pr):.0%}" if pr is not None else "—"
                reps_txt = f"N={n_reps}" if n_reps is not None else ""
                transition_txt = (
                    f" &larr; {_esc(prior)}" if prior else ""
                )
                sufficient = bool(r["assessment_sufficient"])
                passed = bool(r["consistency_passed"])
                decision_class = "gate-pass" if passed else "gate-fail"
                pct = lambda v: f"{float(v):.1%}" if v is not None else "—"
                evidence = [
                    ("Coverage", pct(r["coverage_rate"])),
                    ("Results", f'{r["n_results"] or 0} ({r["n_cases"] or 0} cases × {r["n_reps"] or 0} reps)'),
                    ("Pass / fail", f'{pct(r["pass_rate"])} / {pct(r["fail_rate"])}'),
                    ("Error / skip", f'{pct(r["error_rate"])} / {pct(r["skip_rate"])}'),
                    ("Failed cases", pct(r["failed_case_rate"])),
                    ("Flaky / variable", f'{pct(r["flaky_case_rate"])} / {pct(r["variable_case_rate"])}'),
                    ("Mandatory grader fails", f'{pct(r["mandatory_grader_fail_rate"])} ({r["mandatory_grader_total"] or 0} checks)'),
                    ("Weighted grader fails", f'{pct(r["weighted_grader_fail_rate"])} ({r["weighted_grader_total"] or 0} checks)'),
                    ("Diagnostic grader fails", f'{pct(r["diagnostic_grader_fail_rate"])} ({r["diagnostic_grader_total"] or 0} checks)'),
                ]
                evidence_html = "".join(
                    f'<div><strong>{_esc(label)}:</strong> {_esc(value)}</div>'
                    for label, value in evidence
                )
                out.append(
                    f'<li><strong style="color:{_TEXT};">'
                    f'{_esc(r["skill_name"])} · {_esc(r["client"] or "—")} / '
                    f'{_esc(_model_label(r["model"] or "—"))}</strong>'
                    f'{transition_txt}<br>'
                    f'<span style="color:{_MUTED}; font-size:90%;">'
                    f'pass {pr_txt}{" &middot; " + reps_txt if reps_txt else ""}'
                    f' &middot; <span class="{decision_class}">'
                    f'{"policy passed" if passed else "policy failed"}</span>'
                    f'{" &middot; insufficient evidence" if not sufficient else ""}'
                    f'</span>'
                    f'<details class="lifecycle-evidence"><summary>How this conclusion was reached</summary>'
                    f'<div class="body"><div class="lifecycle-evidence-grid">{evidence_html}</div>'
                    f'<div style="margin-top:6px;"><strong>Decision:</strong> {_esc(reason or "No transition reason recorded")}</div>'
                    f'</div></details></li>'
                )
            if len(items) > 10:
                out.append(
                    f'<li style="color:{_MUTED};">... '
                    f'{len(items) - 10} more</li>'
                )
            out.append('</ul>')
        out.append('</div>')
    out.append('</div>')
    return "\n".join(out)


# ---------------------------------------------------- lifecycle callouts


# ================================ Consistency view (reps x models) ======
#
# Everything below renders the same skill run repeatedly (replications)
# across models -- a determinism/stability view. Unlike the A/B tree it does
# NOT need a no-skill arm; it groups by (case x client x model) and collapses
# the replications into pass-rate + T2 mean/sigma/range + a stability verdict.

# T2 is a 0..1 score. A group whose reps all agree on PASS/FAIL but whose
# score wobbles by more than this is flagged "variable"; below it, "stable".
_CONSISTENCY_SIGMA_VARIABLE = 0.05


def _render_consistency_intro() -> str:
    return (
        f'<p style="color:{_MUTED}; margin-top:10px;">Determinism view: the same '
        'skill run multiple times (replications) across one or more models. Each '
        'row aggregates one case/model combination into repetition outcomes, '
        'consistency, pass rate, average runtime, cost, and token consumption. '
        'Expand a case to inspect every repetition.</p>'
    )


def _consistency_stats(recs: list[sqlite3.Row]) -> dict:
    """Collapse a group of replications into determinism metrics.

    Uses ``aggregate_score`` as the primary signoff metric (the column added
    after the initial t2_score design).  ``aggregate_score`` is already
    COALESCE(aggregate_score, t2_score) in ``_per_run_rows``, so rows written
    before the column existed degrade gracefully to their t2 value.
    """
    n = len(recs)
    n_pass = sum(1 for r in recs if r["status"] == "PASS")
    n_fail = sum(1 for r in recs if r["status"] in ("FAIL", "ERROR"))
    n_skip = sum(1 for r in recs if r["status"] == "SKIPPED")
    pr = (n_pass / n) if n else 0.0

    # Use aggregate_score; fall back to t2_score key if the column was not
    # selected (shouldn't happen after the _per_run_rows change, but be safe).
    def _score(r: sqlite3.Row) -> float | None:
        try:
            v = r["aggregate_score"]
        except (IndexError, KeyError):
            v = None
        if v is not None:
            return float(v)
        try:
            v2 = r["t2_score"]
        except (IndexError, KeyError):
            v2 = None
        return float(v2) if v2 is not None else None

    t2 = [s for r in recs if (s := _score(r)) is not None]
    mean = (sum(t2) / len(t2)) if t2 else None
    if len(t2) > 1:
        stdev = statistics.pstdev(t2)
    elif t2:
        stdev = 0.0
    else:
        stdev = None
    tmin = min(t2) if t2 else None
    tmax = max(t2) if t2 else None

    # Determinism verdict. Reps that disagree on PASS vs FAIL are "flaky" --
    # the worst outcome for a signoff harness. SKIPPED rows are excluded from
    # the agreement test (a skip is not a behavioural disagreement).
    graded = n_pass + n_fail
    unanimous = graded == 0 or n_pass == 0 or n_pass == graded
    if n < 2:
        cls = "single"
    elif not unanimous:
        cls = "flaky"
    elif stdev is not None and stdev > _CONSISTENCY_SIGMA_VARIABLE:
        cls = "variable"
    else:
        cls = "stable"

    attempted = [r for r in recs if r["status"] != "SKIPPED"]
    walls = [r["wall_clock_s"] for r in attempted if r["wall_clock_s"]]
    p50 = statistics.median(walls) if walls else None
    avg_wall = (sum(walls) / len(walls)) if walls else None
    cost = sum((r["cost_usd"] or 0.0) for r in attempted)
    avg_cost = (cost / len(attempted)) if attempted else None
    prompt_tokens = sum((r["prompt_tokens"] or 0) for r in attempted)
    output_tokens = sum((r["output_tokens"] or 0) for r in attempted)
    cache_read_tokens = sum((r["cache_read_tokens"] or 0) for r in attempted)
    cache_write_tokens = sum((r["cache_write_tokens"] or 0) for r in attempted)
    total_tokens = prompt_tokens + output_tokens
    avg_tokens = (total_tokens / len(attempted)) if attempted else None

    return {
        "n": n, "n_pass": n_pass, "n_fail": n_fail, "n_skip": n_skip,
        "pr": pr, "mean": mean, "stdev": stdev, "tmin": tmin, "tmax": tmax,
        "cls": cls, "p50": p50, "avg_wall": avg_wall,
        "cost": cost, "avg_cost": avg_cost,
        "prompt_tokens": prompt_tokens, "output_tokens": output_tokens,
        "cache_read_tokens": cache_read_tokens,
        "cache_write_tokens": cache_write_tokens,
        "total_tokens": total_tokens, "avg_tokens": avg_tokens,
    }


_CONSISTENCY_BADGE = {
    "stable":   (_GREEN, "stable"),
    "variable": (_AMBER, "variable"),
    "flaky":    (_RED,   "flaky"),
    "single":   (_GREY,  "1 rep"),
}


def _consistency_badge(cls: str) -> str:
    color, label = _CONSISTENCY_BADGE.get(cls, (_GREY, "—"))
    return (
        f'<span class="cons-badge" style="border:1px solid {color}; '
        f'color:{color};">{_esc(label)}</span>'
    )


def _consistency_color(cls: str) -> str:
    """Translucent cell fill for the consistency heatmap."""
    return {
        "stable":   "rgba(46,160,67,0.20)",
        "variable": "rgba(210,153,34,0.20)",
        "flaky":    "rgba(248,81,73,0.20)",
    }.get(cls, "transparent")


_CONSISTENCY_ORDER = ("flaky", "variable", "stable", "single")


def _worst_class(classes: list[str]) -> str:
    for c in _CONSISTENCY_ORDER:
        if c in classes:
            return c
    return "single"


def _pr_html(pr: float, n_pass: int, n: int) -> str:
    color = _GREEN if pr >= 1.0 else (_RED if pr <= 0.0 else _AMBER)
    return (
        f'<span style="color:{color}; font-weight:600;">{pr:.0%}</span> '
        f'<span style="color:{_MUTED}; font-size:11px;">{n_pass}/{n}</span>'
    )


def _score_cell(mean: float | None) -> str:
    """Colour-coded aggregate_score mean for a group of replications."""
    if mean is None:
        return f'<span style="color:{_MUTED};">—</span>'
    color = _GREEN if mean >= 0.9 else (_AMBER if mean >= 0.5 else _RED)
    return f'<span style="color:{color}; font-weight:600;">{mean:.3f}</span>'


def _stdev_cell(stdev: float | None) -> str:
    """Colour-coded score σ (population std dev across replications)."""
    if stdev is None:
        return f'<span style="color:{_MUTED};">—</span>'
    # High σ (> _CONSISTENCY_SIGMA_VARIABLE) is amber; very high (> 0.15) red.
    color = (
        _RED if stdev > 0.15 else
        _AMBER if stdev > _CONSISTENCY_SIGMA_VARIABLE else
        _MUTED
    )
    return f'<span style="color:{color}; font-variant-numeric:tabular-nums;">{stdev:.3f}</span>'


def _tokens_cell(st: dict) -> str:
    total = st.get("total_tokens") or 0
    if not total:
        return f'<span style="color:{_MUTED};">—</span>'
    avg = st.get("avg_tokens")
    title = (
        f'prompt {st.get("prompt_tokens", 0):,}; '
        f'output {st.get("output_tokens", 0):,}; '
        f'cache read {st.get("cache_read_tokens", 0):,}; '
        f'cache write {st.get("cache_write_tokens", 0):,}'
    )
    avg_html = (
        f'<span class="cell-sub">avg {_fmt_tokens(avg)} / run</span>'
        if avg is not None else ""
    )
    return f'<span title="{_esc(title)}">{_fmt_tokens(total)}</span>{avg_html}'


def _cost_cell(st: dict) -> str:
    avg = st.get("avg_cost")
    avg_html = (
        f'<span class="cell-sub">avg {_fmt_cost(avg)} / run</span>'
        if avg is not None else ""
    )
    return f'{_fmt_cost(st.get("cost"))}{avg_html}'


def _avg_run_cell(st: dict) -> str:
    return _fmt_secs(st.get("avg_wall"))


def _rep_dots(recs: list[sqlite3.Row]) -> str:
    """One coloured dot per replication, ordered by index -- a compact
    at-a-glance strip showing exactly which reps passed/failed."""
    dots = []
    for r in sorted(recs, key=lambda x: (x["replication_index"] or 0)):
        c = _STATUS_FG.get(r["status"], _MUTED)
        dots.append(
            f'<span title="rep {_esc(r["replication_index"])}: '
            f'{_esc(r["status"])}" style="display:inline-block; width:9px; '
            f'height:9px; border-radius:50%; background:{c}; '
            f'margin-right:3px;"></span>'
        )
    return f'<span style="white-space:nowrap;">{"".join(dots)}</span>'


def _render_model_comparison_chart(rows: list[sqlite3.Row]) -> str:
    """Sorted paired-bar comparison, one row per (client, model) in *rows*:
    pass-rate beside avg cost per test, best model first. Always rendered
    (never behind a click) so the cost/quality trade-off across models is
    readable without expanding anything.

    Deliberately bars-on-a-categorical-axis rather than the cost-vs-pass-rate
    scatter this replaced. Real model costs span two orders of magnitude
    ($0.001 to $0.21 in one observed run), so a linear scatter crushed every
    cheap model into the left edge and its direct labels collided there no
    matter how the placement was tuned -- the geometry was fighting the data.
    One categorical row per model cannot collide or clip at any label length
    or model count, and keeps the two measures on their own scales rather
    than forcing a shared axis (never a dual axis).
    """
    groups: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
    for r in rows:
        groups[(str(r["client"] or "\u2014"), str(r["model"] or "\u2014"))].append(r)
    if not groups:
        return ''

    items = []
    for (client, model), recs in groups.items():
        # SKIPPED rows never reached the agent (runner.py's requirements gate
        # and unavailable-CLI paths write them with no tokens and no cost), so
        # they belong in neither denominator: counting them would drag avg
        # cost toward $0 and pass-rate toward 0% purely because the host was
        # missing Vivado / a CLI binary / disk. Same convention as
        # _consistency_stats -- a skip is not a behavioural result. FAIL and
        # ERROR rows DO count: they spent real tokens, and their cost is part
        # of what the model actually charges you per attempt.
        attempted = [r for r in recs if r["status"] != "SKIPPED"]
        n_att = len(attempted)
        n_skip = len(recs) - n_att
        n_pass = sum(1 for r in attempted if r["status"] == "PASS")
        pass_rate = (n_pass / n_att * 100) if n_att else 0.0
        avg_cost = (
            sum((r["cost_usd"] or 0.0) for r in attempted) / n_att
        ) if n_att else 0.0
        items.append({
            "label": f"{client} / {_model_label(model)}",
            "pass_rate": pass_rate, "avg_cost": avg_cost,
            "n_att": n_att, "n_pass": n_pass, "n_skip": n_skip,
        })

    # Best-first: highest pass-rate, then cheapest -- so the top row is the
    # recommendation and the reader needs no further scanning to find it.
    # Groups with nothing attempted sort last; they carry no verdict at all.
    items.sort(key=lambda i: (i["n_att"] == 0, -i["pass_rate"], i["avg_cost"]))
    max_cost = max((i["avg_cost"] for i in items), default=0.0)
    total_skipped = sum(i["n_skip"] for i in items)

    out = [
        '<h3>Model comparison '
        f'<span style="color:{_MUTED}; font-weight:400; font-size:0.8em;">'
        '(pass-rate vs. avg cost per test, per client/model, this run '
        '&mdash; best first)</span></h3>',
        '<table class="cmp-table">',
        '<thead><tr>'
        '<th>Client / model</th>'
        '<th>Pass rate</th>'
        '<th>Avg cost / test</th>'
        '<th class="cmp-n">Pass / total</th>'
        '</tr></thead><tbody>',
    ]

    for i in items:
        skip_note = (
            f' <span style="color:{_AMBER}; font-size:11px;" '
            f'title="{i["n_skip"]} run(s) skipped -- never invoked the agent, '
            f'so excluded from both figures">+{i["n_skip"]} skip</span>'
            if i["n_skip"] else ''
        )

        # Nothing attempted -- every run skipped. Rendering 0% / $0 here would
        # read as a total failure at zero cost; it is really "no verdict".
        if i["n_att"] == 0:
            out.append(
                f'<tr>'
                f'<td class="cmp-name">{_esc(i["label"])}</td>'
                f'<td colspan="2" style="color:{_MUTED};">'
                f'not run &mdash; all {i["n_skip"]} run(s) skipped</td>'
                f'<td class="cmp-n"><span style="color:{_MUTED};">&mdash;</span>'
                f'</td>'
                f'</tr>'
            )
            continue

        pr = i["pass_rate"]
        color = _GREEN if pr >= 90 else (_AMBER if pr >= 50 else _RED)
        # Cost is a magnitude, not a verdict -- cheap is not "good" on its
        # own, so the cost bar stays a neutral accent rather than borrowing
        # the status palette the pass-rate bar uses.
        cost_pct = (i["avg_cost"] / max_cost * 100) if max_cost > 0 else 0.0
        # With a 200x spread between cheapest and dearest model (real, not
        # hypothetical), a true-to-scale bar for the cheapest rounds to a
        # sliver that reads as missing data rather than "nearly free". Floor
        # any nonzero cost to a visible stub; the exact figure sits beside it.
        if i["avg_cost"] > 0:
            cost_pct = max(cost_pct, 1.5)
        cost_txt = _fmt_cost(i["avg_cost"]) if i["avg_cost"] > 0 else "$0"
        out.append(
            f'<tr>'
            f'<td class="cmp-name">{_esc(i["label"])}{skip_note}</td>'
            f'<td><div class="cmp-bar">'
            f'<div class="cmp-track"><div class="cmp-fill" '
            f'style="width:{pr:.1f}%; background:{color};"></div></div>'
            f'<span class="cmp-val">{pr:.0f}%</span>'
            f'</div></td>'
            f'<td><div class="cmp-bar">'
            f'<div class="cmp-track"><div class="cmp-fill" '
            f'style="width:{cost_pct:.1f}%; background:{_ACCENT};"></div></div>'
            f'<span class="cmp-val">{_esc(cost_txt)}</span>'
            f'</div></td>'
            f'<td class="cmp-n">'
            f'<span style="color:{_MUTED};">{i["n_pass"]}/{i["n_att"]}</span>'
            f'</td>'
            f'</tr>'
        )

    out.append('</tbody></table>')
    out.append(
        f'<div style="display:flex; gap:18px; margin-top:2px; '
        f'flex-wrap:wrap; font-size:12px; color:{_MUTED};">'
        f'<span><span style="display:inline-block; width:10px; height:10px; '
        f'border-radius:2px; background:{_GREEN}; margin-right:5px;"></span>'
        f'&ge;90% pass</span>'
        f'<span><span style="display:inline-block; width:10px; height:10px; '
        f'border-radius:2px; background:{_AMBER}; margin-right:5px;"></span>'
        f'50&ndash;90%</span>'
        f'<span><span style="display:inline-block; width:10px; height:10px; '
        f'border-radius:2px; background:{_RED}; margin-right:5px;"></span>'
        f'&lt;50%</span>'
        f'<span style="margin-left:auto;">cost bars share one scale '
        f'(widest = {_esc(_fmt_cost(max_cost))})</span>'
        f'</div>'
    )
    # State the inclusion rule outright -- "avg cost / test" is ambiguous
    # about whether a failed attempt counts, and it does (a failed run still
    # burns tokens you pay for).
    out.append(
        f'<div style="font-size:12px; color:{_MUTED}; margin-top:4px;">'
        f'Cost and pass-rate cover every <em>attempted</em> run, failures '
        f'included &mdash; a failed attempt still spends tokens.'
        + (f' {total_skipped} skipped run(s) are excluded from both '
           f'(they never invoked the agent).' if total_skipped else '')
        + '</div>'
    )
    return "\n".join(out)


def _render_consistency_run_panel(
    conn: sqlite3.Connection,
    run_id: str,
    ts: str,
    n_rows: int,
    *,
    hidden: bool,
) -> str:
    rows = _per_run_rows(conn, run_id)
    style = ' style="display:none;"' if hidden else ''
    out = [f'<div data-consistency-run="{_esc(run_id)}"{style}>']
    out.append(_render_headline(rows, run_id, ts))
    out.append(_render_consistency_tree(conn, rows, run_id))
    out.append('</div>')
    return "\n".join(out)


def _consistency_group_key(r: sqlite3.Row) -> tuple:
    # Keep the two A/B arms in separate groups so a mixed run never conflates
    # skill and no-skill reps into one (misleading) determinism verdict.
    return (r["case_id"], r["client"], r["model"], bool(r["with_skill"]))


def _render_consistency_tree(
    conn: sqlite3.Connection, rows: list[sqlite3.Row], run_id: str,
) -> str:
    if not rows:
        return (
            f'<p style="color:{_MUTED};">No results recorded for this run.</p>'
        )

    by_skill: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for r in rows:
        by_skill[r["skill_name"]].append(r)

    clients = sorted({str(r["client"] or "—") for r in rows})
    models = sorted({str(r["model"] or "—") for r in rows})
    filter_id = f"cons-filter:{run_id}"
    out = [
        '<h3>Consistency by skill '
        f'<span style="color:{_MUTED}; font-weight:400; font-size:0.8em;">'
        '(filter groups, expand any case, and drag column edges or the table bottom to resize)</span></h3>',
        f'<div class="cons-filter-bar" data-filter-for="{_esc(filter_id)}">',
        '<input type="search" data-cons-filter="text" placeholder="Filter skill or case…" aria-label="Filter skill or case">',
        '<select data-cons-filter="client" aria-label="Filter CLI"><option value="">All CLIs</option>',
        *[f'<option value="{_esc(c.lower())}">{_esc(c)}</option>' for c in clients],
        '</select><select data-cons-filter="model" aria-label="Filter model"><option value="">All models</option>',
        *[f'<option value="{_esc(m.lower())}">{_esc(_model_label(m))}</option>' for m in models],
        '</select><select data-cons-filter="consistency" aria-label="Filter consistency">'
        '<option value="">All consistency</option><option value="stable">Stable</option>'
        '<option value="variable">Variable</option><option value="flaky">Flaky</option>'
        '<option value="single">1 rep</option></select>',
        '<select data-cons-filter="outcome" aria-label="Filter outcome"><option value="">All outcomes</option>'
        '<option value="pass">All pass</option><option value="mixed">Mixed</option>'
        '<option value="fail">No pass</option></select>',
        '<button type="button" data-cons-action="expand">Expand visible</button>',
        '<button type="button" data-cons-action="collapse">Collapse all</button>',
        '<button type="button" data-cons-action="reset">Reset filters</button>',
        '<div class="column-picker"><button type="button" data-cons-action="columns" '
        'aria-expanded="false">Columns ▾</button><div class="column-menu"></div></div>',
        '<span class="cons-filter-count"></span></div>',
        '<div class="tree-resize-hint">Drag the bottom-right corner to resize vertically</div>',
        f'<div class="skill-tree-wrap" data-cons-table="{_esc(filter_id)}"><table class="skill-tree">',
        '<colgroup><col style="width:24%"><col style="width:10%"><col style="width:15%">'
        '<col style="width:10%"><col style="width:10%"><col style="width:9%">'
        '<col style="width:8%"><col style="width:7%"><col style="width:7%"></colgroup>',
        '<thead><tr>',
        '<th data-col-key="case" data-col-label="Skill / case">Skill / case</th>',
        '<th data-col-key="cli" data-col-label="CLI">CLI</th>',
        '<th data-col-key="model" data-col-label="Model">Model</th>',
        '<th class="ctr" data-col-key="reps" data-col-label="Reps (by index)">Reps (by index)</th>',
        '<th class="ctr" data-col-key="consistency" data-col-label="Consistency">Consistency</th>',
        '<th class="ctr" data-col-key="pass-rate" data-col-label="Pass rate">Pass rate</th>',
        '<th class="num" data-col-key="avg-run" data-col-label="Avg / run">Avg / run</th>',
        '<th class="num" data-col-key="cost" data-col-label="Cost">Cost</th>',
        '<th class="num" data-col-key="tokens" data-col-label="Token consumption">Token consumption</th>',
        '</tr></thead><tbody>',
    ]

    for skill in sorted(by_skill):
        rs = by_skill[skill]
        skill_key = f"cons:{run_id}:{skill}"
        out.append(_render_consistency_skill_row(skill, skill_key, rs))
        groups: dict[tuple, list[sqlite3.Row]] = defaultdict(list)
        for r in rs:
            groups[_consistency_group_key(r)].append(r)
        # (case, client, model, skill-arm-first) ordering.
        for key in sorted(groups,
                          key=lambda k: (k[0], k[1], k[2], not k[3])):
            case, client, model, with_skill = key
            out.append(_render_consistency_group_row(
                conn, skill_key, case, client, model, with_skill, groups[key]))

    out.append('</tbody></table></div>')
    return "\n".join(out)


def _render_consistency_skill_row(
    skill: str, skill_key: str, recs: list[sqlite3.Row],
) -> str:
    groups: dict[tuple, list[sqlite3.Row]] = defaultdict(list)
    for r in recs:
        groups[_consistency_group_key(r)].append(r)
    group_stats = [_consistency_stats(g) for g in groups.values()]
    worst = _worst_class([s["cls"] for s in group_stats])

    n_reps = len(recs)
    reps_per_group = sorted({len(group) for group in groups.values()})
    if len(reps_per_group) == 1:
        reps_summary = f'{reps_per_group[0]} / case'
    else:
        reps_summary = f'{min(reps_per_group)}–{max(reps_per_group)} / case'
    n_pass = sum(1 for r in recs if r["status"] == "PASS")
    pr = (n_pass / n_reps) if n_reps else 0.0
    n_groups = len(groups)
    n_models = len({(r["client"], r["model"]) for r in recs})

    skill_st = _consistency_stats(recs)
    return (
        f'<tr class="skill-row" data-skill-key="{_esc(skill_key)}">'
        f'<td class="name"><span class="caret">&#9654;</span>{_esc(skill)} '
        f'<span style="color:{_MUTED}; font-weight:400;">'
        f'&middot; {n_groups} group{"s" if n_groups != 1 else ""} '
        f'&middot; {n_models} model{"s" if n_models != 1 else ""}</span></td>'
        f'<td></td><td></td><td class="ctr">{_esc(reps_summary)}</td>'
        f'<td class="ctr">{_consistency_badge(worst)}</td>'
        f'<td class="ctr">{_pr_html(pr, n_pass, n_reps)}</td>'
        f'<td class="num">{_avg_run_cell(skill_st)}</td>'
        f'<td class="num">{_cost_cell(skill_st)}</td>'
        f'<td class="num">{_tokens_cell(skill_st)}</td></tr>'
    )


def _render_consistency_group_row(
    conn: sqlite3.Connection, skill_key: str, case: str, client: str,
    model: str, with_skill: bool, recs: list[sqlite3.Row],
) -> str:
    st = _consistency_stats(recs)
    arm = (
        '' if with_skill else
        f' <span style="color:{_AMBER}; font-size:11px;">(no-skill)</span>'
    )

    arm_key = f'{skill_key}:{case}:{client}:{model}:{int(with_skill)}'
    outcome = "pass" if st["n_pass"] == st["n"] else ("fail" if st["n_pass"] == 0 else "mixed")
    row = (
        f'<tr class="arm-row expandable" data-parent="{_esc(skill_key)}" '
        f'data-arm-key="{_esc(arm_key)}" data-filter-text="{_esc((case + " " + client + " " + model).lower())}" '
        f'data-filter-client="{_esc(client.lower())}" data-filter-model="{_esc(model.lower())}" '
        f'data-filter-consistency="{_esc(st["cls"])}" data-filter-outcome="{outcome}">'
        f'<td class="arm-name"><span class="arm-caret">&#9656;</span>'
        f'<span class="case">{_esc(case)}</span>{arm}</td>'
        f'<td>{_esc(client)}</td>'
        f'<td title="{_esc(model)}">{_esc(_model_label(model))}</td>'
        f'<td class="ctr">{_rep_dots(recs)}</td>'
        f'<td class="ctr">{_consistency_badge(st["cls"])}</td>'
        f'<td class="ctr">{_pr_html(st["pr"], st["n_pass"], st["n"])}</td>'
        f'<td class="num">{_avg_run_cell(st)}</td>'
        f'<td class="num">{_cost_cell(st)}</td>'
        f'<td class="num">{_tokens_cell(st)}</td></tr>'
    )

    # Drill-down: per-rep detail (prompt / graders / session log).
    # _render_arm_detail picks a representative rep (first failing, else rep 0)
    # and notes the pass spread across reps.
    title = (
        f'{case} · {_model_label(model)} '
        f'· {st["n"]} rep{"s" if st["n"] != 1 else ""}'
        + ('' if with_skill else ' (no-skill)')
    )
    detail = _render_arm_detail(conn, title, recs, arm_key)
    grader_row = (
        f'<tr class="grader-row" data-parent-arm="{_esc(arm_key)}">'
        f'<td colspan="9">{detail}</td>'
        f'</tr>'
    )
    return row + grader_row


def _render_consistency_heatmap(
    conn: sqlite3.Connection,
    skill_name: str | None = None,
    run_id: str | None = None,
) -> str:
    """Replication-stability heatmap.

    *skill_name* scopes it to one skill (the standalone per-skill report)
    instead of every skill in the DB (the main dashboard's Consistency tab) --
    otherwise an unrelated skill's rows would leak into a report that's
    supposed to be self-contained.

    *run_id* scopes it to a single run. Pass it: without it the heatmap sums
    every run of the skill ever recorded, which silently mixes scopes with the
    per-run tree and model-comparison table on the same page -- a one-off
    single-model run keeps its own column alive in every later report, showing
    a client/model the current run never touched.
    """
    where = ["with_skill = 1",
             "status IN ('PASS', 'FAIL', 'ERROR', 'SKIPPED')"]
    params: list[str] = []
    if skill_name is not None:
        where.append("skill_name = ?")
        params.append(skill_name)
    if run_id is not None:
        where.append("run_id = ?")
        params.append(run_id)
    has_agg = _column_exists(conn, "skill_test_results", "aggregate_score")
    score_col = (
        "COALESCE(aggregate_score, t2_score) AS aggregate_score"
        if has_agg else "t2_score AS aggregate_score"
    )
    rows = conn.execute(f"""
        SELECT skill_name, client, model, status, t2_score, {score_col},
               wall_clock_s, cost_usd, replication_index,
               prompt_tokens, output_tokens, cache_read_tokens, cache_write_tokens
          FROM skill_test_results
         WHERE {' AND '.join(where)}
    """, tuple(params)).fetchall()
    if not rows:
        return ''

    skills: set[str] = set()
    cells: set[tuple] = set()
    bucket: dict[tuple, list[sqlite3.Row]] = defaultdict(list)
    for r in rows:
        skills.add(r["skill_name"])
        cells.add((r["client"], r["model"]))
        bucket[(r["skill_name"], r["client"], r["model"])].append(r)
    if not skills or not cells:
        return ''

    stats = {k: _consistency_stats(v) for k, v in bucket.items()}

    if run_id is not None:
        scope = f"this run &middot; {_esc(run_id[:8])}"
    elif skill_name is None:
        scope = "all runs"
    else:
        scope = f"all runs of {_esc(skill_name)}"
    out = [
        '<h3>Consistency heatmap '
        f'<span style="color:{_MUTED}; font-weight:400; font-size:0.8em;">'
        f'(with-skill, {scope})</span></h3>',
        f'<p style="color:{_MUTED};">Each cell aggregates every replication of a '
        'skill on a model. Colour reflects replication stability: '
        f'<span style="color:{_GREEN};">green = stable</span> (reps agree, low '
        f'score &sigma;), <span style="color:{_AMBER};">amber = variable</span> '
        f'(reps agree but score &sigma; high), <span style="color:{_RED};">'
        'red = flaky</span> (reps disagree on pass/fail). Cells show pass-rate, '
        '&sigma; and replication count.</p>',
        '<div class="table-wrap"><table style="border-collapse:collapse;">',
        '<thead><tr><th style="text-align:left; padding:8px;">Skill</th>',
    ]
    sorted_cells = sorted(cells)
    for client, model in sorted_cells:
        out.append(
            f'<th style="padding:8px; text-align:center;">{_esc(client)}<br>'
            f'<span style="color:{_MUTED}; font-weight:400">'
            f'{_esc(_model_label(model))}</span></th>'
        )
    out.append('</tr></thead><tbody>')
    for skill in sorted(skills):
        out.append(
            f'<tr><td style="padding:8px; font-weight:600">{_esc(skill)}</td>'
        )
        for client, model in sorted_cells:
            st = stats.get((skill, client, model))
            if st is None:
                out.append(
                    f'<td style="padding:8px; text-align:center; '
                    f'color:{_MUTED};">&mdash;</td>'
                )
                continue
            bg = _consistency_color(st["cls"])
            sigma = f'{st["stdev"]:.2f}' if st["stdev"] is not None else "—"
            out.append(
                f'<td style="padding:8px; text-align:center; background:{bg}; '
                f'font-variant-numeric:tabular-nums;">{st["pr"]:.0%}'
                f'<div style="font-size:11px; color:{_MUTED}; margin-top:2px;">'
                f'&sigma; {sigma} &middot; N={st["n"]}</div></td>'
            )
        out.append('</tr>')
    out.append('</tbody></table></div>')
    return "\n".join(out)


# ----------------------------------------- T2 lift heatmap (with delta)


def _heatmap_for_run(
    conn: sqlite3.Connection,
    run_id: str | None,
) -> tuple[set[str], set[tuple], dict[tuple, float]]:
    if run_id is None:
        rows = conn.execute("""
            SELECT skill_name, client, model, with_skill, t2_score
              FROM skill_test_results
             WHERE status IN ('PASS', 'FAIL')
        """).fetchall()
    else:
        rows = conn.execute("""
            SELECT skill_name, client, model, with_skill, t2_score
              FROM skill_test_results
             WHERE run_id = ?
               AND status IN ('PASS', 'FAIL')
        """, (run_id,)).fetchall()

    skills: set[str] = set()
    cells: set[tuple] = set()
    bucket_with: dict[tuple, list[float]] = defaultdict(list)
    bucket_without: dict[tuple, list[float]] = defaultdict(list)
    for skill, client, model, with_skill, t2 in rows:
        if t2 is None:
            continue
        skills.add(skill)
        cells.add((client, model))
        key = (skill, client, model)
        if with_skill:
            bucket_with[key].append(float(t2))
        else:
            bucket_without[key].append(float(t2))

    lift_by_cell: dict[tuple, float] = {}
    for key in set(bucket_with.keys()) | set(bucket_without.keys()):
        w = bucket_with.get(key)
        wo = bucket_without.get(key)
        if w and wo:
            lift_by_cell[key] = (sum(w) / len(w) - sum(wo) / len(wo)) * 100.0
        elif w:
            lift_by_cell[key] = (sum(w) / len(w)) * 100.0
    return skills, cells, lift_by_cell


def _render_heatmap_with_delta(
    conn: sqlite3.Connection,
    runs: list[tuple[str, str, int]],
) -> str:
    skills, cells, lift_all = _heatmap_for_run(conn, None)
    if not skills or not cells:
        return ''

    latest_id = runs[0][0] if runs else None
    prev_id = runs[1][0] if len(runs) > 1 else None
    _, _, lift_latest = (
        _heatmap_for_run(conn, latest_id) if latest_id else (set(), set(), {})
    )
    _, _, lift_prev = (
        _heatmap_for_run(conn, prev_id) if prev_id else (set(), set(), {})
    )

    out = [
        '<h3>T2 Pass-rate Lift (with-skill vs. without-skill)</h3>',
        f'<p style="color:{_MUTED};">Cells show the percentage-point lift of '
        'T2 pass-rate when the skill is enabled, aggregated across all runs. '
        'Green: &ge; 8&nbsp;pp, Amber: 0&ndash;8&nbsp;pp, Red: regression. '
        'Empty cells are missing A/B data. The smaller number underneath is '
        'the change between the latest run and the previous one.</p>',
        '<div class="table-wrap"><table style="border-collapse:collapse;">',
        '<thead><tr><th style="text-align:left; padding:8px;">Skill</th>',
    ]
    sorted_cells = sorted(cells)
    for client, model in sorted_cells:
        out.append(
            f'<th style="padding:8px; text-align:center;">'
            f'{_esc(client)}<br>'
            f'<span style="color:{_MUTED}; font-weight:400">'
            f'{_esc(model)}</span></th>'
        )
    out.append('</tr></thead><tbody>')
    for skill in sorted(skills):
        out.append(
            f'<tr><td style="padding:8px; font-weight:600">{_esc(skill)}</td>'
        )
        for client, model in sorted_cells:
            key = (skill, client, model)
            lift = lift_all.get(key)
            l_now = lift_latest.get(key)
            l_prev = lift_prev.get(key)
            delta_html = ''
            if l_now is not None and l_prev is not None:
                d = l_now - l_prev
                d_color = _GREEN if d > 0 else (_RED if d < 0 else _MUTED)
                d_sign = '+' if d > 0 else ('' if d < 0 else '\u00b1')
                delta_html = (
                    f'<div style="font-size:11px; color:{d_color}; '
                    f'margin-top:2px;">'
                    f'\u0394 {d_sign}{d:.1f} pp</div>'
                )
            if lift is None:
                out.append(
                    f'<td style="padding:8px; text-align:center; '
                    f'color:{_MUTED};">&mdash;</td>'
                )
            else:
                bg = _heatmap_color(lift)
                out.append(
                    f'<td style="padding:8px; text-align:center; '
                    f'background:{bg}; font-variant-numeric:tabular-nums;">'
                    f'{lift:+.1f} pp{delta_html}</td>'
                )
        out.append('</tr>')
    out.append('</tbody></table></div>')
    return "\n".join(out)
