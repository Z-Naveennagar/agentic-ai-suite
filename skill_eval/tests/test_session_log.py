"""
Tests for the per-session JSON monitoring logger (core/session_log.py).

Covers:
  - snapshot_workspace + collect_artifacts detect produced files and skip
    unchanged inputs (and copy small text artifacts).
  - write_test_log emits valid JSON at a timestamped path and truncates
    oversized stdout.
  - write_session_summary against a seeded SQLite DB produces correct totals
    and per-test rows whose log_file matches the forensic filename.
  - the disabled config path is a no-op.
"""

from __future__ import annotations

import json
import os
import time

import pytest

from skills_testing.core import db_writer, session_log
from skills_testing.core.session_log import SessionLogConfig


@pytest.fixture
def cfg(tmp_path):
    return SessionLogConfig(
        enabled=True,
        dir=str(tmp_path / "logs"),
        max_output_chars=50,
        artifact_size_cap_bytes=1024,
        copy_artifacts=True,
    )


def test_snapshot_and_collect_artifacts(tmp_path, cfg):
    ws = tmp_path / "ws"
    (ws / ".claude" / "skills").mkdir(parents=True)
    (ws / ".claude" / "skills" / "SKILL.md").write_text("staged skill body")
    (ws / "input.txt").write_text("pre-existing input")
    snapshot = session_log.snapshot_workspace(ws)

    # staged skill material is excluded from the snapshot
    assert "input.txt" in snapshot
    assert not any(p.startswith(".claude") for p in snapshot)

    # agent produces a new file; mtime gap guarantees change detection
    time.sleep(0.01)
    (ws / "out.tcl").write_text("set foo bar\n")

    copy_dir = tmp_path / "copies"
    arts = session_log.collect_artifacts(
        ws, snapshot, size_cap=cfg.artifact_size_cap_bytes, copy_dir=copy_dir)
    paths = {a["path"] for a in arts}

    assert "out.tcl" in paths           # newly produced -> captured
    assert "input.txt" not in paths     # unchanged input -> skipped
    out = next(a for a in arts if a["path"] == "out.tcl")
    assert out["size"] == len("set foo bar\n")
    assert len(out["sha256"]) == 64
    assert "saved_copy" in out
    assert (copy_dir / "out.tcl").read_text() == "set foo bar\n"


def test_snapshot_excludes_opencode_and_node_modules_anywhere(tmp_path):
    ws = tmp_path / "ws"
    # .opencode is staged CLI/MCP config, same category as .claude/.cursor.
    (ws / ".opencode" / "skills").mkdir(parents=True)
    (ws / ".opencode" / "skills" / "SKILL.md").write_text("staged")
    # node_modules dragged in by a staged CLI config -- not agent output,
    # and can be tens of MB even for a trivial dependency tree.
    (ws / ".opencode" / "node_modules" / "pkg").mkdir(parents=True)
    (ws / ".opencode" / "node_modules" / "pkg" / "index.js").write_text("module.exports = {}")
    # node_modules elsewhere in the tree (not just under a staged dir) must
    # also be excluded -- the check isn't scoped to .opencode specifically.
    (ws / "project" / "node_modules" / "dep").mkdir(parents=True)
    (ws / "project" / "node_modules" / "dep" / "index.js").write_text("x")
    (ws / "input.txt").write_text("pre-existing input")

    snapshot = session_log.snapshot_workspace(ws)

    assert "input.txt" in snapshot
    assert not any(p.startswith(".opencode") for p in snapshot)
    assert not any("node_modules" in p for p in snapshot)


def test_large_artifact_hash_only(tmp_path, cfg):
    ws = tmp_path / "ws"
    ws.mkdir()
    snapshot = session_log.snapshot_workspace(ws)
    big = "x" * (cfg.artifact_size_cap_bytes + 10)
    (ws / "big.log").write_text(big)
    copy_dir = tmp_path / "copies"
    arts = session_log.collect_artifacts(
        ws, snapshot, size_cap=cfg.artifact_size_cap_bytes, copy_dir=copy_dir)
    big_desc = next(a for a in arts if a["path"] == "big.log")
    assert "saved_copy" not in big_desc          # over cap -> referenced only
    assert not (copy_dir / "big.log").exists()


def test_write_test_log_truncates_and_is_valid_json(tmp_path, cfg):
    record = session_log.build_record(
        run_id="run1234", skill_name="hls-dataflow", skill_version="1",
        case_id="case_001", client="opencode", model="gpt", with_skill=True,
        replication_index=0, skill_invoked=True, prompt="do the thing",
        invocation={"stdout": "S" * 500, "stderr": "", "total_tokens": 10},
        grader_results=[{"id": "verdict", "type": "content_contains",
                         "mandatory": False, "passed": True, "score": 1.0,
                         "details": {}}],
        status="PASS", t2_score=1.0, pass_threshold=1.0,
        hallucination_detected=False, artifacts=[],
        timestamp_iso="2026-06-24T17:30:42+00:00", max_output_chars=50,
    )
    path = session_log.write_test_log(record, session_dir=tmp_path / "sess")

    assert path is not None and path.exists()
    # filename carries no timestamp; it is deterministic per
    # (skill, case, arm, rep, client, model) — client AND model included so
    # multi-backend AND multi-model runs don't overwrite each other.
    assert path.name == (
        "hls-dataflow__case_001__with_skill__rep0__opencode__gpt.json")
    data = json.loads(path.read_text())
    # the wall-clock time lives inside the record, not the filename
    assert data["timestamp"] == "2026-06-24T17:30:42+00:00"
    assert data["correctness"]["status"] == "PASS"
    # stdout truncated to max_output_chars (+ truncation notice)
    assert data["output"]["stdout"].startswith("S" * 50)
    assert "truncated" in data["output"]["stdout"]
    assert data["log_file"] == path.name


def test_test_log_stem_distinct_per_client():
    # A multi-backend run (cli_backend: multi) runs the same (skill,case,arm,rep)
    # across backends; the stem must differ per client so files don't overwrite.
    common = dict(skill_name="ip-configurator", case_id="c_01",
                  with_skill=True, replication_index=0)
    cur = session_log.test_log_stem(client="cursor", **common)
    cop = session_log.test_log_stem(client="copilot", **common)
    legacy = session_log.test_log_stem(**common)
    assert cur != cop
    assert cur.endswith("__cursor")
    # Omitting client preserves the legacy stem (back-compat).
    assert legacy == "ip-configurator__c_01__with_skill__rep0"
    # Same backend, different models must also differ (e.g. opencode running
    # gpt-5.4 vs gpt-5.4-mini) -- model is appended after client.
    big = session_log.test_log_stem(client="opencode",
                                    model="azure/gpt-5.4", **common)
    mini = session_log.test_log_stem(client="opencode",
                                     model="azure/gpt-5.4-mini", **common)
    assert big != mini
    assert big.endswith("__opencode__azure-gpt-5.4")
    assert mini.endswith("__opencode__azure-gpt-5.4-mini")


def test_write_session_summary(tmp_path, cfg):
    conn = db_writer.init_db({"database": {"path": str(tmp_path / "r.db")}})
    run_id = db_writer.create_run(conn, suite="skill_test")
    base = {"skill_name": "hls-dataflow", "skill_version": "1",
            "case_id": "case_001", "client": "opencode", "model": "gpt"}
    db_writer.write_skill_test_result(conn, run_id,
                                      {**base, "with_skill": True, "status": "PASS", "t2_score": 1.0})
    db_writer.write_skill_test_result(conn, run_id,
                                      {**base, "with_skill": False, "status": "FAIL", "t2_score": 0.0})
    db_writer.write_skill_test_result(conn, run_id,
                                      {**base, "case_id": "case_002", "status": "SKIPPED",
                                       "skip_reason": "vivado_not_found"})

    path = session_log.write_session_summary(
        run_id, conn, cfg=cfg, suite="skill_test", started_at="2026-06-24T00:00:00+00:00")
    assert path is not None and path.name == "session_summary.json"
    # session dir is "<sortable-UTC-stamp>__<run_id>" so logs/ sorts by time
    parent = path.parent.name
    assert parent.endswith(f"__{run_id}")
    stamp = parent.split("__")[0]
    assert len(stamp) == 16 and stamp.endswith("Z")  # YYYYMMDDTHHMMSSZ
    summary = json.loads(path.read_text())
    assert summary["run_id"] == run_id
    assert summary["totals"] == {"pass": 1, "fail": 1, "skip": 1, "err": 0}
    assert summary["n_tests"] == 3
    # executed rows get a log_file link; SKIPPED does not
    by_status = {t["status"]: t for t in summary["tests"]}
    assert by_status["PASS"]["log_file"].endswith(".json")
    assert by_status["SKIPPED"]["log_file"] is None
    conn.close()


def test_disabled_config_from_yaml():
    parsed = SessionLogConfig.from_config(
        {"skill_testing": {"session_log": {"enabled": False, "dir": "elsewhere"}}})
    assert parsed.enabled is False
    assert parsed.dir == "elsewhere"
    # defaults apply when the block is absent
    default = SessionLogConfig.from_config({"skill_testing": {}})
    assert default.enabled is True and default.dir == "_runtime/logs"
