"""
Tests for the grader framework: ABC, registry, and the 6 plug-in graders.

Design contract under test:

    GraderContext        - dataclass with workspace_dir, stdout, stderr,
                           baseline_lookup callable, llm_caller callable, run_meta.
    GraderResult         - dataclass(passed: bool, score: float, details: dict).
    Grader (ABC)         - .grade(spec, ctx) -> GraderResult
    GRADER_REGISTRY      - {grader_type: Grader instance}
    get_grader(name)     - returns the grader instance, raises KeyError if absent.

Plug-ins exercised:
    artifact_exists, artifact_valid, content_contains, metric_threshold,
    baseline_delta, llm_judge

The validator registry (used by artifact_valid) is covered in
test_validators.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skills_testing.graders import (
    GRADER_REGISTRY,
    GraderContext,
    GraderResult,
    get_grader,
)


# -- registry ---------------------------------------------------------------


@pytest.mark.parametrize(
    "grader_type",
    [
        "artifact_exists",
        "artifact_valid",
        "content_contains",
        "metric_threshold",
        "baseline_delta",
        "llm_judge",
    ],
)
def test_grader_registered(grader_type):
    assert grader_type in GRADER_REGISTRY
    g = get_grader(grader_type)
    assert hasattr(g, "grade")
    assert callable(g.grade)


def test_unknown_grader_raises():
    with pytest.raises(KeyError):
        get_grader("does_not_exist")


def test_grader_result_shape():
    r = GraderResult(passed=True, score=0.75, details={"x": 1})
    assert r.passed is True
    assert r.score == 0.75
    assert r.details == {"x": 1}


# -- shared fixture: minimal context ----------------------------------------


@pytest.fixture
def ctx_factory(tmp_path):
    """Build a GraderContext rooted at tmp_path."""

    def _make(stdout="", stderr="", baselines=None, llm_response=None, run_meta=None):
        baselines = baselines or {}

        def _baseline_lookup(skill, version, case, metric):
            return baselines.get((skill, version, case, metric))

        def _llm(prompt: str) -> dict:
            # deterministic stub: returns whatever the test prepared
            return llm_response or {"score": 0.0, "rationale": "no judge configured"}

        return GraderContext(
            workspace_dir=tmp_path,
            stdout=stdout,
            stderr=stderr,
            baseline_lookup=_baseline_lookup,
            llm_caller=_llm,
            run_meta=run_meta or {
                "skill_name": "x",
                "skill_version": "1.0",
                "case_id": "c",
            },
        )

    return _make


# -- artifact_exists --------------------------------------------------------


class TestArtifactExists:
    def test_passes_when_file_present(self, ctx_factory, tmp_path):
        (tmp_path / "outputs").mkdir()
        (tmp_path / "outputs" / "lint.rpt").write_text("ok")
        ctx = ctx_factory()
        r = get_grader("artifact_exists").grade(
            {"path": "outputs/lint.rpt"}, ctx
        )
        assert r.passed is True
        assert r.score == 1.0
        assert "outputs/lint.rpt" in r.details["path"]

    def test_fails_when_file_missing(self, ctx_factory):
        ctx = ctx_factory()
        r = get_grader("artifact_exists").grade(
            {"path": "outputs/missing.rpt"}, ctx
        )
        assert r.passed is False
        assert r.score == 0.0

    def test_min_size_bytes(self, ctx_factory, tmp_path):
        (tmp_path / "tiny.txt").write_text("x")
        ctx = ctx_factory()
        r = get_grader("artifact_exists").grade(
            {"path": "tiny.txt", "min_size_bytes": 10}, ctx
        )
        assert r.passed is False
        assert r.details["actual_size"] == 1


# -- content_contains -------------------------------------------------------


class TestContentContains:
    def test_substring_in_stdout(self, ctx_factory):
        ctx = ctx_factory(stdout="Synthesis complete; WNS 0.21 ns")
        r = get_grader("content_contains").grade(
            {"source": "stdout", "substring": "Synthesis complete"}, ctx
        )
        assert r.passed is True

    def test_substring_missing(self, ctx_factory):
        ctx = ctx_factory(stdout="something else")
        r = get_grader("content_contains").grade(
            {"source": "stdout", "substring": "no such thing"}, ctx
        )
        assert r.passed is False

    def test_regex_in_file(self, ctx_factory, tmp_path):
        (tmp_path / "rep.txt").write_text("foo\nWNS = -0.123\nbar\n")
        ctx = ctx_factory()
        r = get_grader("content_contains").grade(
            {
                "source": "file",
                "path": "rep.txt",
                "regex": r"WNS\s*=\s*-?\d+(?:\.\d+)?",
            },
            ctx,
        )
        assert r.passed is True
        assert r.details["match"].startswith("WNS")

    def test_must_not_contain(self, ctx_factory):
        ctx = ctx_factory(stdout="ERROR: timing failed")
        r = get_grader("content_contains").grade(
            {
                "source": "stdout",
                "substring": "ERROR",
                "must_not_contain": True,
            },
            ctx,
        )
        assert r.passed is False  # ERROR present, so 'must not' fails


# -- metric_threshold -------------------------------------------------------


class TestMetricThreshold:
    def test_ge_passes(self, ctx_factory):
        ctx = ctx_factory()
        r = get_grader("metric_threshold").grade(
            {"metric": "wns_ns", "value": 0.42, "op": ">=", "threshold": 0.0},
            ctx,
        )
        assert r.passed is True
        assert r.score == 1.0

    def test_le_fails(self, ctx_factory):
        ctx = ctx_factory()
        r = get_grader("metric_threshold").grade(
            {"metric": "lut_pct", "value": 92.0, "op": "<=", "threshold": 80.0},
            ctx,
        )
        assert r.passed is False

    def test_value_from_stdout_regex(self, ctx_factory):
        ctx = ctx_factory(stdout="...\nWNS_NS=0.215\n...")
        r = get_grader("metric_threshold").grade(
            {
                "metric": "wns_ns",
                "extract": {"source": "stdout", "regex": r"WNS_NS=(-?\d+(?:\.\d+)?)"},
                "op": ">=",
                "threshold": 0.0,
            },
            ctx,
        )
        assert r.passed is True
        assert r.details["value"] == pytest.approx(0.215)


# -- baseline_delta ---------------------------------------------------------


class TestBaselineDelta:
    def test_within_tolerance(self, ctx_factory):
        ctx = ctx_factory(
            baselines={("rtl-assistant", "1.0", "lint_smoke", "violation_count"): 10},
            run_meta={
                "skill_name": "rtl-assistant",
                "skill_version": "1.0",
                "case_id": "lint_smoke",
            },
        )
        r = get_grader("baseline_delta").grade(
            {"metric": "violation_count", "value": 11, "tolerance_abs": 2},
            ctx,
        )
        assert r.passed is True

    def test_out_of_tolerance(self, ctx_factory):
        ctx = ctx_factory(
            baselines={("rtl-assistant", "1.0", "lint_smoke", "violation_count"): 10},
            run_meta={
                "skill_name": "rtl-assistant",
                "skill_version": "1.0",
                "case_id": "lint_smoke",
            },
        )
        r = get_grader("baseline_delta").grade(
            {"metric": "violation_count", "value": 25, "tolerance_abs": 2},
            ctx,
        )
        assert r.passed is False

    def test_no_baseline_fails_open_unless_strict(self, ctx_factory):
        ctx = ctx_factory(baselines={})
        # default: no baseline -> not pass, but flagged as missing rather than raising
        r = get_grader("baseline_delta").grade(
            {"metric": "violation_count", "value": 11, "tolerance_abs": 2},
            ctx,
        )
        assert r.passed is False
        assert "missing_baseline" in r.details


# -- llm_judge --------------------------------------------------------------


class TestLLMJudge:
    def test_uses_provided_judge(self, ctx_factory):
        ctx = ctx_factory(
            llm_response={"score": 0.85, "rationale": "addresses all rubric items"}
        )
        r = get_grader("llm_judge").grade(
            {
                "rubric": "1. Files compile.\n2. Reports cite UG949.",
                "answer_source": "stdout",
                "pass_threshold": 0.7,
            },
            ctx,
        )
        assert r.passed is True
        assert r.score == pytest.approx(0.85)
        assert "addresses all rubric items" in r.details["rationale"]

    def test_below_threshold_fails(self, ctx_factory):
        ctx = ctx_factory(llm_response={"score": 0.3, "rationale": "weak"})
        r = get_grader("llm_judge").grade(
            {"rubric": "x", "answer_source": "stdout", "pass_threshold": 0.7},
            ctx,
        )
        assert r.passed is False


# -- artifact_valid (registry dispatch only; deep validator tests live in -- 
#    test_validators.py) ---------------------------------------------------


class TestArtifactValidDispatch:
    def test_dispatches_to_validator_by_name(self, ctx_factory, tmp_path, monkeypatch):
        called = {}
        from skills_testing.graders import validators as vmod

        def fake_validator(path: Path, params: dict) -> dict:
            called["path"] = path
            called["params"] = params
            return {"passed": True, "score": 1.0, "details": {"foo": "bar"}}

        monkeypatch.setitem(vmod.VALIDATOR_REGISTRY, "fake_check", fake_validator)

        (tmp_path / "out.bin").write_bytes(b"\x00\x01\x02")
        ctx = ctx_factory()
        r = get_grader("artifact_valid").grade(
            {"path": "out.bin", "validator": "fake_check", "params": {"k": 1}},
            ctx,
        )
        assert r.passed is True
        assert called["path"].name == "out.bin"
        assert called["params"] == {"k": 1}

    def test_unknown_validator_raises(self, ctx_factory, tmp_path):
        (tmp_path / "out.bin").write_bytes(b"\x00")
        ctx = ctx_factory()
        with pytest.raises(KeyError):
            get_grader("artifact_valid").grade(
                {"path": "out.bin", "validator": "no_such_validator"}, ctx
            )

    def test_missing_artifact_fails_without_calling_validator(
        self, ctx_factory, monkeypatch
    ):
        from skills_testing.graders import validators as vmod

        called = {"n": 0}

        def boom(*a, **kw):
            called["n"] += 1
            return {"passed": True, "score": 1.0, "details": {}}

        monkeypatch.setitem(vmod.VALIDATOR_REGISTRY, "boom", boom)

        ctx = ctx_factory()
        r = get_grader("artifact_valid").grade(
            {"path": "missing.bin", "validator": "boom"}, ctx
        )
        assert r.passed is False
        assert called["n"] == 0
        assert "missing" in r.details.get("reason", "").lower()
