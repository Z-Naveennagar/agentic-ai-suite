"""
Writes test results to SQLite (for Grafana) and JSON (for git tracking).
"""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from skills_testing.core.cost_model import load_config
from skills_testing.core.paths import resolve_project_path


def _get_db_path(config: dict | None = None) -> Path:
    config = config or load_config()
    # database.path lives under _runtime/ at the repo root (see paths.py),
    # not under the package -- resolve_project_path, not resolve_repo_path.
    return resolve_project_path(config["database"]["path"])


def init_db(config: dict | None = None) -> sqlite3.Connection:
    """Create tables if they don't exist and return a connection."""
    db_path = _get_db_path(config)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS test_runs (
            run_id          TEXT PRIMARY KEY,
            timestamp       TEXT NOT NULL,
            device_filter   TEXT,
            tool_filter     TEXT,
            release_filter  TEXT,
            suite           TEXT,
            cli_backend     TEXT,
            queries_run     INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS skill_test_results (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id                  TEXT NOT NULL REFERENCES test_runs(run_id),
            skill_name              TEXT NOT NULL,
            skill_version           TEXT NOT NULL,
            case_id                 TEXT NOT NULL,
            client                  TEXT NOT NULL,
            model                   TEXT NOT NULL,
            with_skill              INTEGER NOT NULL DEFAULT 1,
            replication_index       INTEGER NOT NULL DEFAULT 0,
            skill_invoked           INTEGER DEFAULT 0,
            wall_clock_s            REAL,
            prompt_tokens           INTEGER,
            output_tokens           INTEGER,
            total_tokens            INTEGER,
            cache_read_tokens       INTEGER DEFAULT 0,
            cache_write_tokens      INTEGER DEFAULT 0,
            cost_usd                REAL,
            cost_method             TEXT,
            mcp_call_count          INTEGER,
            mcp_total_latency_ms    INTEGER,
            t2_score                REAL,
            aggregate_score         REAL,
            status                  TEXT NOT NULL DEFAULT 'PASS',
            skip_reason             TEXT,
            error                   TEXT,
            timestamp               TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_str_run ON skill_test_results(run_id);
        CREATE INDEX IF NOT EXISTS idx_str_skill ON skill_test_results(skill_name, skill_version);
        CREATE INDEX IF NOT EXISTS idx_str_arm ON skill_test_results(skill_name, with_skill);
        CREATE INDEX IF NOT EXISTS idx_str_client ON skill_test_results(client, model);
        CREATE INDEX IF NOT EXISTS idx_str_timestamp ON skill_test_results(timestamp);

        CREATE TABLE IF NOT EXISTS skill_grader_results (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_test_id       INTEGER NOT NULL REFERENCES skill_test_results(id),
            grader_id           TEXT NOT NULL,
            grader_type         TEXT NOT NULL,
            passed              INTEGER NOT NULL DEFAULT 0,
            score               REAL,
            weight              REAL,
            category            TEXT,
            details             TEXT,
            timestamp           TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_sgr_test ON skill_grader_results(skill_test_id);
        CREATE INDEX IF NOT EXISTS idx_sgr_type ON skill_grader_results(grader_type);

        CREATE TABLE IF NOT EXISTS skill_baselines (
            skill_name      TEXT NOT NULL,
            skill_version   TEXT NOT NULL,
            case_id         TEXT NOT NULL,
            metric_name     TEXT NOT NULL,
            metric_value    REAL,
            captured_at     TEXT NOT NULL,
            PRIMARY KEY (skill_name, skill_version, case_id, metric_name)
        );

        CREATE TABLE IF NOT EXISTS skill_release_evaluations (
            id                          INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_name                  TEXT NOT NULL,
            skill_version               TEXT NOT NULL,
            client                      TEXT NOT NULL,
            model                       TEXT NOT NULL,
            evaluated_at                TEXT NOT NULL,
            n_cases                     INTEGER NOT NULL DEFAULT 0,
            n_reps_per_arm              INTEGER NOT NULL DEFAULT 1,
            trigger_rate                REAL,
            t2_lift_pp                  REAL,
            token_ratio                 REAL,
            value_test_passed           INTEGER DEFAULT 0,
            lifecycle_state             TEXT NOT NULL,
            state_transition_reason     TEXT,
            prior_state                 TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_sre_skill ON skill_release_evaluations(skill_name, client, model);
        CREATE INDEX IF NOT EXISTS idx_sre_evaluated ON skill_release_evaluations(evaluated_at);

        CREATE TABLE IF NOT EXISTS skill_lifecycle_evaluations (
            id                              INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id                          TEXT NOT NULL REFERENCES test_runs(run_id),
            skill_name                      TEXT NOT NULL,
            skill_version                   TEXT NOT NULL,
            client                          TEXT NOT NULL,
            model                           TEXT NOT NULL,
            evaluated_at                    TEXT NOT NULL,
            assessment_sufficient           INTEGER NOT NULL DEFAULT 0,
            consistency_passed              INTEGER NOT NULL DEFAULT 0,
            lifecycle_state                 TEXT NOT NULL,
            prior_state                     TEXT,
            transition_reason               TEXT,
            n_cases                         INTEGER NOT NULL DEFAULT 0,
            n_reps                          INTEGER NOT NULL DEFAULT 0,
            n_results                       INTEGER NOT NULL DEFAULT 0,
            coverage_rate                   REAL,
            pass_rate                       REAL,
            fail_rate                       REAL,
            error_rate                      REAL,
            skip_rate                       REAL,
            failed_case_rate                REAL,
            aggregate_score_mean            REAL,
            aggregate_score_stdev           REAL,
            flaky_case_rate                 REAL,
            variable_case_rate              REAL,
            mandatory_grader_total          INTEGER NOT NULL DEFAULT 0,
            mandatory_grader_fail_rate      REAL,
            weighted_grader_total           INTEGER NOT NULL DEFAULT 0,
            weighted_grader_fail_rate       REAL,
            diagnostic_grader_total         INTEGER NOT NULL DEFAULT 0,
            diagnostic_grader_fail_rate     REAL,
            UNIQUE(run_id, skill_name, skill_version, client, model)
        );

        CREATE INDEX IF NOT EXISTS idx_sle_latest
            ON skill_lifecycle_evaluations(
                skill_name, skill_version, client, model, evaluated_at
            );
    """)

    # Migrate existing DBs: add columns if they don't exist
    for col_def in [
        "ALTER TABLE test_runs ADD COLUMN cli_backend TEXT",
        # Anthropic prompt-cache token accounting (added 2026-04). Cursor +
        # Claude Code expose these separately from live tokens; cost_model
        # prices them at the cache rates.
        "ALTER TABLE skill_test_results ADD COLUMN cache_read_tokens INTEGER DEFAULT 0",
        "ALTER TABLE skill_test_results ADD COLUMN cache_write_tokens INTEGER DEFAULT 0",
        # Per-row sampled power for self-hosted runs.  JSON blob with
        # avg_active_w / peak_w / baseline_w / samples_n / window_s ...
        # Used by cost_model to bill the row at the *measured* hourly rate
        # (not the static config fallback) and by the dashboard to render
        # the active/idle disclosure in the Method column.
        "ALTER TABLE skill_test_results ADD COLUMN power_metrics TEXT",
        # Hallucination tracking (added 2026-05). Set to 1 when at least
        # one grader marked `mandatory: true` failed for this row. The
        # dashboard surfaces this as `hallucination_rate` per (skill,
        # model) cell and the release gate blocks any cell with a
        # nonzero rate.
        "ALTER TABLE skill_test_results ADD COLUMN hallucination_detected INTEGER",
        # Capture the running Vivado version on every row so the
        # dashboard can correlate failures with version drift. NULL
        # when vivado is not on PATH (most CI / dev boxes).
        "ALTER TABLE skill_test_results ADD COLUMN vivado_version TEXT",
        # Per-grader `mandatory` annotation; mirrors the manifest's
        # `mandatory: true|false` field on a grader spec. NULL on
        # historical rows.
        "ALTER TABLE skill_grader_results ADD COLUMN mandatory INTEGER",
        "ALTER TABLE skill_grader_results ADD COLUMN weight REAL",
        "ALTER TABLE skill_grader_results ADD COLUMN category TEXT",
        # Release-evaluation: the new hallucination_rate aggregation.
        "ALTER TABLE skill_release_evaluations ADD COLUMN hallucination_rate REAL",
    ]:
        try:
            conn.execute(col_def)
            conn.commit()
        except sqlite3.OperationalError:
            pass

    conn.commit()
    return conn


def create_run(
    conn: sqlite3.Connection,
    device_filter: str | None = None,
    tool_filter: str | None = None,
    release_filter: str | None = None,
    suite: str | None = None,
    cli_backend: str | None = None,
) -> str:
    """Create a new test run and return its run_id."""
    run_id = str(uuid.uuid4())[:8]
    timestamp = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO test_runs (run_id, timestamp, device_filter, tool_filter, release_filter, suite, cli_backend, queries_run) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
        (run_id, timestamp, device_filter or "all", tool_filter or "all", release_filter or "all", suite or "all", cli_backend),
    )
    conn.commit()
    return run_id


def update_run_count(conn: sqlite3.Connection, run_id: str, count: int):
    conn.execute("UPDATE test_runs SET queries_run = ? WHERE run_id = ?", (count, run_id))
    conn.commit()


def run_exists(conn: sqlite3.Connection, run_id: str) -> bool:
    """True if *run_id* has a row in test_runs -- used to validate --resume."""
    row = conn.execute(
        "SELECT 1 FROM test_runs WHERE run_id = ? LIMIT 1", (run_id,)
    ).fetchone()
    return row is not None


def completed_skill_test_combos(
    conn: sqlite3.Connection, run_id: str,
) -> set[tuple[str, str, str, bool, int]]:
    """Return every (case_id, client, model, with_skill, replication_index)
    tuple already recorded in skill_test_results for *run_id*.

    Used by ``--resume <run_id>`` (see customer_cli.py/integration_runner.py)
    to skip combos an earlier, interrupted invocation of the same run_id
    already completed, rather than re-running the whole suite from scratch.
    A row existing here means it was written by ``write_skill_test_result``,
    i.e. that combo genuinely finished (PASS/FAIL/SKIPPED/ERROR all count --
    only a combo that never got a row at all, e.g. the process was killed
    mid-run, is treated as incomplete and re-run).
    """
    rows = conn.execute(
        "SELECT case_id, client, model, with_skill, replication_index "
        "FROM skill_test_results WHERE run_id = ?",
        (run_id,),
    ).fetchall()
    return {(r[0], r[1], r[2], bool(r[3]), int(r[4])) for r in rows}


# ---------------------------------------------------------------------------
# Skill-testing write helpers
# ---------------------------------------------------------------------------


def write_skill_test_result(
    conn: sqlite3.Connection, run_id: str, data: dict
) -> int:
    """
    Insert one row into skill_test_results and return the new row id.

    *data* keys:
        Required: skill_name, skill_version, case_id, client, model
        A/B + reps: with_skill (bool), replication_index (int),
                    skill_invoked (bool, optional)
        Cost / perf: wall_clock_s, prompt_tokens, output_tokens, total_tokens,
                     mcp_call_count, mcp_total_latency_ms
        Scoring: t2_score, aggregate_score, status ('PASS'|'FAIL'|'ERROR'|'SKIPPED'),
                 skip_reason, error
        Cost annotation will run automatically when usage tokens + model are
        present and cost_usd is not already set.
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    if "cost_usd" not in data or data.get("cost_usd") is None:
        try:
            from skills_testing.core.cost_model import annotate_with_cost  # type: ignore

            usage = data.get("usage") or {
                "prompt_tokens": data.get("prompt_tokens"),
                "output_tokens": data.get("output_tokens"),
                "total_tokens": data.get("total_tokens"),
                "cache_read_tokens": data.get("cache_read_tokens"),
                "cache_write_tokens": data.get("cache_write_tokens"),
                "estimated": False,
            }
            cost_fields = annotate_with_cost(
                data.get("model", "default"),
                usage,
                data.get("wall_clock_s"),
                power_metrics=data.get("power_metrics"),
            )
            for k, v in cost_fields.items():
                data.setdefault(k, v)
        except Exception:
            pass

    pm = data.get("power_metrics")
    pm_json = json.dumps(pm) if isinstance(pm, dict) else (pm if isinstance(pm, str) else None)
    halluc = data.get("hallucination_detected")
    halluc_int = None if halluc is None else (1 if halluc else 0)
    cur = conn.execute(
        """INSERT INTO skill_test_results
           (run_id, skill_name, skill_version, case_id, client, model,
            with_skill, replication_index, skill_invoked,
            wall_clock_s, prompt_tokens, output_tokens, total_tokens,
            cache_read_tokens, cache_write_tokens,
            cost_usd, cost_method, mcp_call_count, mcp_total_latency_ms,
            t2_score, aggregate_score, status, skip_reason, error, timestamp,
            power_metrics, hallucination_detected, vivado_version)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                   ?, ?)""",
        (
            run_id,
            data["skill_name"],
            data["skill_version"],
            data["case_id"],
            data["client"],
            data["model"],
            1 if data.get("with_skill", True) else 0,
            int(data.get("replication_index", 0)),
            1 if data.get("skill_invoked") else 0,
            data.get("wall_clock_s"),
            data.get("prompt_tokens"),
            data.get("output_tokens"),
            data.get("total_tokens"),
            int(data.get("cache_read_tokens") or 0),
            int(data.get("cache_write_tokens") or 0),
            data.get("cost_usd"),
            data.get("cost_method"),
            data.get("mcp_call_count"),
            data.get("mcp_total_latency_ms"),
            data.get("t2_score"),
            data.get("aggregate_score"),
            data.get("status", "PASS"),
            data.get("skip_reason"),
            data.get("error"),
            timestamp,
            pm_json,
            halluc_int,
            data.get("vivado_version") or None,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def write_skill_grader_result(
    conn: sqlite3.Connection, skill_test_id: int, data: dict
) -> int:
    """Insert one grader outcome linked to a skill_test_results row."""
    timestamp = datetime.now(timezone.utc).isoformat()
    mandatory = data.get("mandatory")
    weight = data.get("weight")
    category = data.get("category")
    if category is None:
        if mandatory:
            category = "mandatory"
        elif weight is not None:
            category = "weighted" if float(weight) > 0 else "diagnostic"
    cur = conn.execute(
        """INSERT INTO skill_grader_results
           (skill_test_id, grader_id, grader_type, passed, score, weight,
            category, details, timestamp, mandatory)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            skill_test_id,
            data["grader_id"],
            data["grader_type"],
            1 if data.get("passed") else 0,
            data.get("score"),
            weight,
            category,
            data.get("details"),
            timestamp,
            None if mandatory is None else (1 if mandatory else 0),
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def upsert_skill_baseline(conn: sqlite3.Connection, data: dict) -> None:
    """
    Insert-or-replace a baseline metric for (skill_name, skill_version,
    case_id, metric_name).
    """
    captured_at = data.get("captured_at") or datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO skill_baselines
           (skill_name, skill_version, case_id, metric_name, metric_value, captured_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(skill_name, skill_version, case_id, metric_name)
           DO UPDATE SET metric_value = excluded.metric_value,
                         captured_at  = excluded.captured_at""",
        (
            data["skill_name"],
            data["skill_version"],
            data["case_id"],
            data["metric_name"],
            data.get("metric_value"),
            captured_at,
        ),
    )
    conn.commit()


def write_skill_release_evaluation(
    conn: sqlite3.Connection, data: dict
) -> int:
    """
    Insert one release evaluation row (one per (skill, version, client, model)
    per evaluation event). Returns the new row id.
    """
    evaluated_at = data.get("evaluated_at") or datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """INSERT INTO skill_release_evaluations
           (skill_name, skill_version, client, model, evaluated_at,
            n_cases, n_reps_per_arm,
            trigger_rate, t2_lift_pp, token_ratio,
            value_test_passed, lifecycle_state, state_transition_reason, prior_state,
            hallucination_rate)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data["skill_name"],
            data["skill_version"],
            data["client"],
            data["model"],
            evaluated_at,
            int(data.get("n_cases", 0)),
            int(data.get("n_reps_per_arm", 1)),
            data.get("trigger_rate"),
            data.get("t2_lift_pp"),
            data.get("token_ratio"),
            1 if data.get("value_test_passed") else 0,
            data["lifecycle_state"],
            data.get("state_transition_reason"),
            data.get("prior_state"),
            data.get("hallucination_rate"),
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def upsert_skill_lifecycle_evaluation(
    conn: sqlite3.Connection, data: dict
) -> int:
    """Insert or replace one run-scoped consistency lifecycle snapshot."""
    evaluated_at = data.get("evaluated_at") or datetime.now(timezone.utc).isoformat()
    columns = (
        "run_id", "skill_name", "skill_version", "client", "model",
        "evaluated_at", "assessment_sufficient", "consistency_passed",
        "lifecycle_state", "prior_state", "transition_reason", "n_cases",
        "n_reps", "n_results", "coverage_rate", "pass_rate", "fail_rate",
        "error_rate", "skip_rate", "failed_case_rate", "aggregate_score_mean",
        "aggregate_score_stdev", "flaky_case_rate", "variable_case_rate",
        "mandatory_grader_total", "mandatory_grader_fail_rate",
        "weighted_grader_total", "weighted_grader_fail_rate",
        "diagnostic_grader_total", "diagnostic_grader_fail_rate",
    )
    values = {
        **data,
        "evaluated_at": evaluated_at,
        "assessment_sufficient": 1 if data.get("assessment_sufficient") else 0,
        "consistency_passed": 1 if data.get("consistency_passed") else 0,
    }
    placeholders = ", ".join("?" for _ in columns)
    updates = ", ".join(
        f"{column}=excluded.{column}" for column in columns
        if column not in {"run_id", "skill_name", "skill_version", "client", "model"}
    )
    conn.execute(
        f"""INSERT INTO skill_lifecycle_evaluations ({', '.join(columns)})
            VALUES ({placeholders})
            ON CONFLICT(run_id, skill_name, skill_version, client, model)
            DO UPDATE SET {updates}""",
        tuple(values.get(column) for column in columns),
    )
    row = conn.execute(
        """SELECT id FROM skill_lifecycle_evaluations
            WHERE run_id=? AND skill_name=? AND skill_version=?
              AND client=? AND model=?""",
        (data["run_id"], data["skill_name"], data["skill_version"],
         data["client"], data["model"]),
    ).fetchone()
    conn.commit()
    return int(row[0])


def save_json_backup(run_id: str, results: dict, config: dict | None = None):
    """Save a JSON copy of the run results for git tracking."""
    config = config or load_config()
    results_dir = resolve_project_path(config["results_dir"])
    results_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    filepath = results_dir / f"{timestamp}_{run_id}.json"
    with open(filepath, "w") as f:
        json.dump(results, f, indent=2, default=str)
    return filepath
