"""
Per-session JSON monitoring logs for the skill-testing harness.

The harness already persists results to ``results.db`` and grades correctness
via graders + LLM judge, but the *agent's actual produced output* (stdout,
stderr, and the files it wrote into the workspace) is graded and then discarded
on cleanup. This module captures that output forensically.

For every executed test it writes one timestamped JSON record under
``logs/<run_id>/`` capturing the prompt, raw output, produced artifacts, every
grader verdict, and the LLM-judge verdict. A single ``session_summary.json`` is
written at the end of the run (from the DB) covering every row in the session,
including SKIPPED/ERROR.

Layout::

    logs/<run_id>/
      session_summary.json
      <ts>__<skill>__<case>__<arm>__rep<N>.json
      artifacts/<ts>__<skill>__<case>__<arm>__rep<N>/<file>   # small text copies

All writes are best-effort: a logging failure must never break a real run, so
the public entry points swallow and report their own exceptions.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .paths import session_log_dir

# Workspace material that is *staged* (skills, agent rules, vcs metadata)
# rather than *produced* by the agent. Excluded from artifact collection even
# if mtimes shift during the run.
_EXCLUDE_TOP = {".claude", ".cursor", ".opencode", ".git"}
_EXCLUDE_NAMES = {"AGENTS.md"}
# Dependency/package caches a CLI backend installs into the workspace (e.g.
# opencode's `.opencode/node_modules/`) -- never agent-produced output, and
# large enough to dominate logs/ if copied (one run's .opencode/node_modules
# alone was ~90MB across two artifact copies). Matched anywhere in the
# relative path, not just at the top level.
_EXCLUDE_ANYWHERE = {"node_modules"}
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass
class SessionLogConfig:
    """Parsed ``skill_testing.session_log`` config block."""

    enabled: bool = True
    dir: str = "_runtime/logs"
    max_output_chars: int = 1_000_000
    artifact_size_cap_bytes: int = 262_144
    copy_artifacts: bool = True

    @classmethod
    def from_config(cls, cfg: dict | None) -> "SessionLogConfig":
        block = ((cfg or {}).get("skill_testing", {}) or {}).get("session_log", {}) or {}
        return cls(
            enabled=bool(block.get("enabled", True)),
            dir=str(block.get("dir", "_runtime/logs")),
            max_output_chars=int(block.get("max_output_chars", 1_000_000)),
            artifact_size_cap_bytes=int(block.get("artifact_size_cap_bytes", 262_144)),
            copy_artifacts=bool(block.get("copy_artifacts", True)),
        )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dir_stamp(ts: str | None) -> str:
    """Compact, lexicographically-sortable UTC stamp (e.g. 20260624T125300Z)
    used to prefix the per-session directory so sessions sort chronologically
    under logs/."""
    if not ts:
        return "00000000T000000Z"
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    except ValueError:
        return "00000000T000000Z"


def _run_created_at(conn, run_id: str) -> str | None:
    """The run's creation timestamp from test_runs — stable for the whole run,
    so every writer composes the identical session directory name."""
    try:
        row = conn.execute(
            "SELECT timestamp FROM test_runs WHERE run_id=?", (run_id,)
        ).fetchone()
        return row[0] if row else None
    except Exception:
        return None


def session_dir(run_id: str, conn, cfg: "SessionLogConfig") -> Path:
    """Resolve the per-session log directory, named ``<UTC-stamp>__<run_id>``
    so sessions appear in chronological order under logs/ while remaining
    traceable back to the run_id in results.db. Falls back to a bare run_id
    when the run timestamp can't be read."""
    created = _run_created_at(conn, run_id)
    name = f"{_dir_stamp(created)}__{run_id}" if created else run_id
    return session_log_dir(name, cfg.dir)


def _safe(part: str) -> str:
    return _SAFE_NAME.sub("-", str(part)).strip("-") or "x"


def arm_label(with_skill: bool) -> str:
    return "with_skill" if with_skill else "no_skill"


def test_log_stem(*, skill_name: str, case_id: str, with_skill: bool,
                  replication_index: int, client: str | None = None,
                  model: str | None = None) -> str:
    """Filesystem-safe stem shared by the JSON file and its artifacts/
    subdirectory. A session (one run_id dir) may run the SAME (skill, case,
    arm, rep) across several backends (``cli_backend: multi``) AND across
    several models on the same backend, so both ``client`` and ``model`` are
    part of the stem — without them every backend/model would overwrite the
    same file and only the last writer would survive (e.g. opencode running
    gpt-5.4 and gpt-5.4-mini would collide on client alone). No timestamp is
    needed; the wall-clock time is recorded in the record's ``timestamp``
    field."""
    stem = (
        f"{_safe(skill_name)}__{_safe(case_id)}"
        f"__{arm_label(with_skill)}__rep{int(replication_index)}"
    )
    if client:
        stem += f"__{_safe(client)}"
    if model:
        stem += f"__{_safe(model)}"
    return stem


def snapshot_workspace(ws_dir: Path | str) -> dict[str, float]:
    """Map of relative-path -> mtime for files under *ws_dir*, captured right
    after the workspace is populated. Used to detect files the agent produced
    or modified during the run. Staged skill/agent material is excluded."""
    ws_dir = Path(ws_dir)
    snap: dict[str, float] = {}
    for p in _iter_candidate_files(ws_dir):
        try:
            snap[str(p.relative_to(ws_dir))] = p.stat().st_mtime
        except OSError:
            continue
    return snap


def _iter_candidate_files(ws_dir: Path):
    if not ws_dir.exists():
        return
    for p in ws_dir.rglob("*"):
        try:
            rel_parts = p.relative_to(ws_dir).parts
        except ValueError:
            continue
        if not rel_parts:
            continue
        if rel_parts[0] in _EXCLUDE_TOP:
            continue
        if any(part in _EXCLUDE_ANYWHERE for part in rel_parts):
            continue
        if not p.is_file() or p.is_symlink():
            continue
        if p.name in _EXCLUDE_NAMES:
            continue
        yield p


def collect_artifacts(
    ws_dir: Path | str,
    baseline: dict[str, float],
    *,
    size_cap: int,
    copy_dir: Path | None,
) -> list[dict]:
    """Describe files the agent produced or modified relative to *baseline*.

    For each: relative path, size, sha256, mtime (UTC ISO). Text files at or
    below *size_cap* are copied into *copy_dir* (when provided) and recorded via
    ``saved_copy``; larger or binary files are referenced by hash only.
    """
    ws_dir = Path(ws_dir)
    out: list[dict] = []
    for p in _iter_candidate_files(ws_dir):
        rel = str(p.relative_to(ws_dir))
        try:
            st = p.stat()
        except OSError:
            continue
        prior = baseline.get(rel)
        if prior is not None and prior == st.st_mtime:
            continue  # unchanged input -> not a produced artifact
        try:
            data = p.read_bytes()
        except OSError:
            continue
        desc: dict = {
            "path": rel,
            "size": st.st_size,
            "sha256": hashlib.sha256(data).hexdigest(),
            "mtime": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
        }
        text = _as_text(data)
        if copy_dir is not None and text is not None and st.st_size <= size_cap:
            try:
                dest = copy_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(text, encoding="utf-8")
                desc["saved_copy"] = str(dest.relative_to(copy_dir.parent))
            except OSError:
                pass
        out.append(desc)
    out.sort(key=lambda d: d["path"])
    return out


def _as_text(data: bytes) -> str | None:
    if b"\x00" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _truncate(s: str | None, limit: int) -> str:
    if not s:
        return ""
    if len(s) <= limit:
        return s
    return s[:limit] + f"\n...[truncated {len(s) - limit} chars]"


def build_record(
    *,
    run_id: str,
    skill_name: str,
    skill_version: str,
    case_id: str,
    client: str,
    model: str,
    with_skill: bool,
    replication_index: int,
    skill_invoked: bool,
    prompt: str,
    invocation: dict,
    grader_results: list[dict],
    status: str,
    t2_score: float,
    pass_threshold: float,
    hallucination_detected: bool | None,
    artifacts: list[dict],
    timestamp_iso: str,
    max_output_chars: int,
) -> dict:
    """Assemble the forensic per-test record (pure; no I/O)."""
    return {
        "run_id": run_id,
        "skill_name": skill_name,
        "skill_version": skill_version,
        "case_id": case_id,
        "client": client,
        "model": model,
        "arm": arm_label(with_skill),
        "with_skill": bool(with_skill),
        "replication_index": int(replication_index),
        "skill_invoked": bool(skill_invoked),
        "timestamp": timestamp_iso,
        "prompt": prompt,
        "output": {
            "stdout": _truncate(invocation.get("stdout", ""), max_output_chars),
            "stderr": _truncate(invocation.get("stderr", ""), max_output_chars),
            "wall_clock_s": invocation.get("wall_clock_s"),
            "prompt_tokens": invocation.get("prompt_tokens"),
            "output_tokens": invocation.get("output_tokens"),
            "total_tokens": invocation.get("total_tokens"),
            # Chronological tool-call chain with per-call durations (empty for
            # older runs / backends whose transcript carries no tool signal).
            "tool_timeline": invocation.get("tool_timeline") or [],
            # The agent's final answer (extracted from full stdout at capture
            # time, so it survives the stdout truncation above).
            "final_response": invocation.get("final_response") or "",
        },
        "artifacts": artifacts,
        "correctness": {
            "status": status,
            "t2_score": t2_score,
            "pass_threshold": pass_threshold,
            "hallucination_detected": hallucination_detected,
            "graders": grader_results,
        },
    }


def write_test_log(record: dict, *, session_dir: Path) -> Path | None:
    """Atomically write one forensic per-test JSON file into the resolved
    *session_dir*. Best-effort."""
    try:
        session_dir.mkdir(parents=True, exist_ok=True)
        stem = test_log_stem(
            skill_name=record["skill_name"],
            case_id=record["case_id"],
            with_skill=record.get("with_skill", True),
            replication_index=record.get("replication_index", 0),
            client=record.get("client"),
            model=record.get("model"),
        )
        record["log_file"] = f"{stem}.json"
        path = session_dir / f"{stem}.json"
        _atomic_write_json(path, record)
        return path
    except Exception as exc:  # pragma: no cover - logging must never break a run
        sys.stderr.write(f"[session_log] failed to write test log: {exc}\n")
        return None


def artifacts_copy_dir(session_dir: Path, cfg: SessionLogConfig, stem: str) -> Path | None:
    """Directory into which small text artifacts for one test are copied."""
    if not cfg.copy_artifacts:
        return None
    return session_dir / "artifacts" / stem


def write_session_summary(
    run_id: str,
    conn,
    *,
    cfg: SessionLogConfig,
    suite: str | None = None,
    started_at: str | None = None,
) -> Path | None:
    """Write ``session_summary.json`` from the DB so it covers every row in the
    session (PASS/FAIL/SKIPPED/ERROR). Best-effort."""
    try:
        rows = conn.execute(
            """SELECT skill_name, skill_version, case_id, client, model,
                      with_skill, replication_index, status, t2_score,
                      hallucination_detected, skip_reason, error, timestamp
                 FROM skill_test_results
                WHERE run_id = ?
                ORDER BY id""",
            (run_id,),
        ).fetchall()
    except Exception as exc:  # pragma: no cover
        sys.stderr.write(f"[session_log] summary query failed: {exc}\n")
        return None

    totals = {"pass": 0, "fail": 0, "skip": 0, "err": 0}
    tests: list[dict] = []
    for r in rows:
        (skill_name, skill_version, case_id, client, model, with_skill,
         rep, status, t2, halluc, skip_reason, error, ts) = r
        key = {"PASS": "pass", "FAIL": "fail",
               "SKIPPED": "skip", "ERROR": "err"}.get(status)
        if key:
            totals[key] += 1
        stem = test_log_stem(
            skill_name=skill_name, case_id=case_id,
            with_skill=bool(with_skill), replication_index=rep,
            client=client, model=model,
        )
        tests.append({
            "skill_name": skill_name,
            "skill_version": skill_version,
            "case_id": case_id,
            "client": client,
            "model": model,
            "arm": arm_label(bool(with_skill)),
            "replication_index": rep,
            "status": status,
            "t2_score": t2,
            "hallucination_detected": (
                None if halluc is None else bool(halluc)),
            "skip_reason": skip_reason,
            "error": error,
            "timestamp": ts,
            # present only for executed (PASS/FAIL) rows that wrote a forensic file
            "log_file": f"{stem}.json" if status in ("PASS", "FAIL") else None,
        })

    summary = {
        "run_id": run_id,
        "suite": suite,
        "started_at": started_at,
        "finished_at": _utc_now_iso(),
        "totals": totals,
        "n_tests": len(tests),
        "tests": tests,
    }
    try:
        log_dir = session_dir(run_id, conn, cfg)
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / "session_summary.json"
        _atomic_write_json(path, summary)
        return path
    except Exception as exc:  # pragma: no cover
        sys.stderr.write(f"[session_log] failed to write summary: {exc}\n")
        return None


def _atomic_write_json(path: Path, obj: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, path)
