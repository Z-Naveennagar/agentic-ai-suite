"""
Tests for the generic ``file_diff`` grader.

Contract:
    file_diff grader_args: {file_a, file_b}   -- both workspace-relative by
    default (case://, workspace:// prefixes also accepted).

    Identical files  -> passed=True,  score=1.0, changed_line_numbers=[].
    Differing files  -> passed=False, score in [0,1), changed_line_numbers
                        holds 1-indexed positions where lines differ, and
                        details['diff'] holds a unified diff.
    Missing file(s)  -> passed=False, score=0.0, details['missing'] lists
                        the missing path(s).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skills_testing.graders import GRADER_REGISTRY, GraderContext, get_grader


def _ctx(workspace_dir: Path) -> GraderContext:
    return GraderContext(workspace_dir=workspace_dir)


def test_file_diff_registered():
    assert "file_diff" in GRADER_REGISTRY
    assert callable(get_grader("file_diff").grade)


def test_requires_both_file_a_and_file_b(tmp_path):
    grader = get_grader("file_diff")
    with pytest.raises(ValueError, match="file_a.*file_b"):
        grader.grade({"file_a": "a.txt"}, _ctx(tmp_path))


def test_identical_files_pass(tmp_path):
    (tmp_path / "a.txt").write_text("line1\nline2\nline3\n")
    (tmp_path / "b.txt").write_text("line1\nline2\nline3\n")

    grader = get_grader("file_diff")
    result = grader.grade({"file_a": "a.txt", "file_b": "b.txt"}, _ctx(tmp_path))

    assert result.passed is True
    assert result.score == pytest.approx(1.0)
    assert result.details["identical"] is True
    assert result.details["changed_line_numbers"] == []
    assert result.details["diff"] == ""


def test_pass_fail_is_derived_from_line_comparison_not_raw_string_equality(tmp_path):
    """Regression: passed/identical must agree with changed_line_numbers.
    A raw `text_a == text_b` check would say "not identical" here (the
    bytes differ, CRLF vs LF), but every line is the same after
    normalization -- changed_line_numbers must be empty and the grader
    must pass."""
    (tmp_path / "a.txt").write_bytes(b"line1\r\nline2\r\nline3\r\n")
    (tmp_path / "b.txt").write_bytes(b"line1\nline2\nline3\n")

    grader = get_grader("file_diff")
    result = grader.grade({"file_a": "a.txt", "file_b": "b.txt"}, _ctx(tmp_path))

    assert result.details["changed_line_numbers"] == []
    assert result.details["identical"] is True
    assert result.passed is True
    assert result.score == pytest.approx(1.0)


def test_differing_files_report_changed_line_numbers_and_diff(tmp_path):
    (tmp_path / "a.txt").write_text("same\nDIFFERENT-A\nsame3\n")
    (tmp_path / "b.txt").write_text("same\nDIFFERENT-B\nsame3\n")

    grader = get_grader("file_diff")
    result = grader.grade({"file_a": "a.txt", "file_b": "b.txt"}, _ctx(tmp_path))

    assert result.passed is False
    assert result.details["identical"] is False
    assert result.details["changed_line_numbers"] == [2]
    assert 0.0 < result.score < 1.0
    assert "DIFFERENT-A" in result.details["diff"]
    assert "DIFFERENT-B" in result.details["diff"]


def test_extra_trailing_lines_count_as_changed(tmp_path):
    (tmp_path / "a.txt").write_text("one\ntwo\n")
    (tmp_path / "b.txt").write_text("one\ntwo\nthree\n")

    grader = get_grader("file_diff")
    result = grader.grade({"file_a": "a.txt", "file_b": "b.txt"}, _ctx(tmp_path))

    assert result.passed is False
    # Position-based (not alignment-based) comparison: once b.txt has an
    # extra line, every position from there on is "changed" -- including
    # the split()-artifact trailing empty element from each file's final
    # newline (3 lines in a.txt's split vs 4 in b.txt's).
    assert result.details["changed_line_numbers"] == [3, 4]


def test_missing_file_reports_missing_and_fails(tmp_path):
    (tmp_path / "a.txt").write_text("only a exists\n")

    grader = get_grader("file_diff")
    result = grader.grade({"file_a": "a.txt", "file_b": "nope.txt"}, _ctx(tmp_path))

    assert result.passed is False
    assert result.score == 0.0
    assert any("nope.txt" in m for m in result.details["missing"])


def test_paths_resolve_relative_to_workspace_by_default(tmp_path):
    sub = tmp_path / "outputs" / "case_1"
    sub.mkdir(parents=True)
    (tmp_path / "shared.txt").write_text("hello\n")
    (sub / "reported.txt").write_text("hello\n")

    grader = get_grader("file_diff")
    result = grader.grade(
        {"file_a": "shared.txt", "file_b": "outputs/case_1/reported.txt"},
        _ctx(tmp_path),
    )
    assert result.passed is True
