"""
Tests for the per-skill skill-signoffs snapshots written after a run.

write_skill_signoffs(db_path, run_id, skill_names, skill_signoffs_root=...,
claude_skills_dir=...) must, per skill with at least one row for that run,
write to skill_signoffs_root/<skill>_summary/:
    * <skill>_summary/report/report.html (v1) the first time,
      report_v2.html/etc. on repeat runs of the same skill -- derived by
      scanning report/, not a stored counter
    * <skill>_summary/<skill>/ -- the installed skill content, copied in
      directly (unversioned -- always latest), kept separate from report/
    * <skill>_summary/report/README.md: an environment block plus one row
      per run in a run-history table, preserving prior rows verbatim
A skill with zero rows for the given run_id is left alone entirely.
"""

from __future__ import annotations

from pathlib import Path

from skills_testing.core import db_writer
from skills_testing.reporting.skill_signoffs import (
    _existing_table_rows,
    _next_report_filename,
    write_skill_signoffs,
)


def _seed_row(conn, run_id, skill, *, client="claude_code", model="sonnet",
              status="PASS", t2=1.0, cost=0.5, vivado="2026.1"):
    return db_writer.write_skill_test_result(conn, run_id, {
        "skill_name": skill, "skill_version": "1.0",
        "case_id": "c1", "client": client, "model": model,
        "with_skill": True, "replication_index": 0, "skill_invoked": True,
        "t2_score": t2, "aggregate_score": t2, "status": status,
        "wall_clock_s": 10.0, "prompt_tokens": 1000, "output_tokens": 500,
        "total_tokens": 1500, "cost_usd": cost, "vivado_version": vivado,
    })


# -- version numbering -----------------------------------------------------


def test_next_report_filename_fresh_dir(tmp_path):
    assert _next_report_filename(tmp_path / "missing") == (1, "report.html")


def test_next_report_filename_increments_from_disk(tmp_path):
    skill_dir = tmp_path / "ip-configurator"
    skill_dir.mkdir()
    (skill_dir / "report.html").write_text("v1")
    (skill_dir / "report_v2.html").write_text("v2")
    assert _next_report_filename(skill_dir) == (3, "report_v3.html")


def test_next_report_filename_ignores_unrelated_files(tmp_path):
    skill_dir = tmp_path / "ip-configurator"
    skill_dir.mkdir()
    (skill_dir / "README.md").write_text("x")
    (skill_dir / "SKILL.md").write_text("x")
    assert _next_report_filename(skill_dir) == (1, "report.html")


# -- README history table ---------------------------------------------------


def test_existing_table_rows_missing_file(tmp_path):
    assert _existing_table_rows(tmp_path / "README.md") == []


def test_existing_table_rows_roundtrip(tmp_path):
    """Old-format (T2 mean) rows are preserved verbatim by the new parser."""
    readme = tmp_path / "README.md"
    readme.write_text(
        "# x\n\n## Run history\n\n"
        "| Version | Run | Timestamp | Client / Model | Status | Pass rate | T2 mean | Cost | Tokens |\n"
        "|---|---|---|---|---|---|---|---|---|\n"
        "| v1 | `abcd1234` | 2026-08-01 00:00 | claude_code/sonnet | PASS | 100% (1/1) | 1.000 | $0.50 | 1,500 |\n"
    )
    rows = _existing_table_rows(readme)
    assert len(rows) == 1
    assert "v1" in rows[0] and "abcd1234" in rows[0]


def test_existing_table_rows_new_format(tmp_path):
    """New-format (Score mean / Score sigma) rows round-trip cleanly."""
    from skills_testing.reporting.skill_signoffs import _TABLE_HEADER
    readme = tmp_path / "README.md"
    readme.write_text(
        "# x\n\n## Run history\n\n"
        + _TABLE_HEADER
        + "| v1 | `abc12345` | 2026-08-07 00:00 | claude_code/sonnet"
          " | PASS | 100% (1/1) | 0.920 | 0.025 | $0.50 | 1,500 |\n"
    )
    rows = _existing_table_rows(readme)
    assert len(rows) == 1
    assert "abc12345" in rows[0]
    assert "0.920" in rows[0]


def test_readme_new_header_columns(tmp_db, tmp_db_path, tmp_path):
    """write_skill_signoffs emits Score mean and Score sigma columns (not T2 mean)."""
    run_id = db_writer.create_run(tmp_db, suite="skill_test")
    _seed_row(tmp_db, run_id, "ip-configurator", t2=0.875)

    out_root = tmp_path / "skill-signoffs"
    write_skill_signoffs(
        str(tmp_db_path), run_id, ["ip-configurator"],
        skill_signoffs_root=out_root, claude_skills_dir=tmp_path / "skills",
    )

    readme = (out_root / "ip-configurator_summary" / "report" / "README.md").read_text()
    # New header columns present
    assert "Score mean" in readme
    assert "Score" in readme
    # Actual score value formatted to 3dp
    assert "0.875" in readme
    # Old T2 mean column should NOT be the primary column label
    # (it may appear in old-format preserved rows but not in the header)
    header_line = [l for l in readme.splitlines() if "Version" in l][0]
    assert "Score mean" in header_line
    assert "T2 mean" not in header_line


# -- write_skill_signoffs end-to-end -------------------------------------------


def test_no_rows_for_run_is_a_noop(tmp_db, tmp_db_path, tmp_path):
    log = write_skill_signoffs(
        str(tmp_db_path), "no-such-run", ["ip-configurator"],
        skill_signoffs_root=tmp_path / "skill-signoffs",
        claude_skills_dir=tmp_path / "skills",
    )
    assert log == []
    assert not (tmp_path / "skill-signoffs").exists()


def test_first_run_writes_report_and_readme(tmp_db, tmp_db_path, tmp_path):
    run_id = db_writer.create_run(tmp_db, suite="skill_test")
    _seed_row(tmp_db, run_id, "ip-configurator")

    out_root = tmp_path / "skill-signoffs"
    log = write_skill_signoffs(
        str(tmp_db_path), run_id, ["ip-configurator", "hls-dataflow"],
        skill_signoffs_root=out_root, claude_skills_dir=tmp_path / "skills",
    )

    # hls-dataflow had no rows in this run -> untouched.
    assert log == ["ip-configurator: report.html (skill content not installed -- snapshot skipped)"]
    assert not (out_root / "hls-dataflow_summary").exists()

    report_dir = out_root / "ip-configurator_summary" / "report"
    assert (report_dir / "report.html").is_file()
    readme = (report_dir / "README.md").read_text()
    assert "ip-configurator" in readme
    assert "claude_code/sonnet" in readme
    assert "2026.1" in readme
    assert readme.count("| v1 |") == 1


def test_second_run_versions_report_and_appends_history(tmp_db, tmp_db_path, tmp_path):
    out_root = tmp_path / "skill-signoffs"
    claude_skills_dir = tmp_path / "skills"

    run_1 = db_writer.create_run(tmp_db, suite="skill_test")
    _seed_row(tmp_db, run_1, "ip-configurator", status="FAIL", t2=0.2, cost=0.1)
    write_skill_signoffs(
        str(tmp_db_path), run_1, ["ip-configurator"],
        skill_signoffs_root=out_root, claude_skills_dir=claude_skills_dir,
    )

    run_2 = db_writer.create_run(tmp_db, suite="skill_test")
    _seed_row(tmp_db, run_2, "ip-configurator", status="PASS", t2=0.9, cost=0.4)
    log = write_skill_signoffs(
        str(tmp_db_path), run_2, ["ip-configurator"],
        skill_signoffs_root=out_root, claude_skills_dir=claude_skills_dir,
    )

    report_dir = out_root / "ip-configurator_summary" / "report"
    assert log == [f"ip-configurator: report_v2.html (skill content not installed -- snapshot skipped)"]
    assert (report_dir / "report.html").is_file()
    assert (report_dir / "report_v2.html").is_file()

    readme = (report_dir / "README.md").read_text()
    assert readme.count("| v1 |") == 1
    assert readme.count("| v2 |") == 1
    # first row preserved verbatim, second appended after it
    assert readme.index("| v1 |") < readme.index("| v2 |")


def test_copies_installed_skill_content_when_present(tmp_db, tmp_db_path, tmp_path):
    claude_skills_dir = tmp_path / "skills"
    (claude_skills_dir / "ip-configurator").mkdir(parents=True)
    (claude_skills_dir / "ip-configurator" / "SKILL.md").write_text("hello")

    run_id = db_writer.create_run(tmp_db, suite="skill_test")
    _seed_row(tmp_db, run_id, "ip-configurator")

    out_root = tmp_path / "skill-signoffs"
    log = write_skill_signoffs(
        str(tmp_db_path), run_id, ["ip-configurator"],
        skill_signoffs_root=out_root, claude_skills_dir=claude_skills_dir,
    )

    assert log == ["ip-configurator: report.html"]
    summary_dir = out_root / "ip-configurator_summary"
    assert (summary_dir / "ip-configurator" / "SKILL.md").read_text() == "hello"
    # skill content sits alongside report/, not inside it
    assert (summary_dir / "report" / "report.html").is_file()
    assert not (summary_dir / "report" / "SKILL.md").exists()
    assert not (summary_dir / "ip-configurator" / "report").exists()
