"""
Tests for the Phase 1 (report_schema) and Phase 2 (oracle_match) graders,
plus the schema_checks primitives.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from skills_testing.graders import (
    GRADER_REGISTRY,
    GraderContext,
    get_grader,
    schema_checks as sc,
)


# -- schema_checks primitives ---------------------------------------------


def test_regex_required_match_and_miss():
    fn = sc.get_check("regex_required")
    assert fn("foo bar baz", {"pattern": r"\bbar\b"}, {})["passed"] is True
    assert fn("foo baz", {"pattern": r"\bbar\b"}, {})["passed"] is False


def test_any_of_regex_picks_first_hit():
    fn = sc.get_check("any_of_regex")
    out = fn("set_max_delay -from a -to b\n",
             {"patterns": [r"set_false_path", r"set_max_delay\s+-from"]}, {})
    assert out["passed"] is True


def test_all_of_regex_reports_missing():
    fn = sc.get_check("all_of_regex")
    out = fn("only foo here", {"patterns": ["foo", "bar"]}, {})
    assert out["passed"] is False
    assert out["details"]["missing"] == ["bar"]


def test_required_substrings_case_sensitive_default():
    fn = sc.get_check("required_substrings")
    assert fn("Hello World", {"substrings": ["hello"]}, {})["passed"] is False
    assert fn("Hello World",
              {"substrings": ["hello"], "case_sensitive": False}, {})["passed"] is True


def test_forbidden_substrings_flags_placeholders():
    fn = sc.get_check("forbidden_substrings")
    out = fn("set_max_delay -to TODO_endpoint",
             {"substrings": ["TODO", "FIXME"], "case_sensitive": False}, {})
    assert out["passed"] is False
    assert "TODO" in out["details"]["found"]


def test_required_headings_substring_match():
    fn = sc.get_check("required_headings")
    text = "## 1. Design Timing Summary\n## 2. Clock Summary\n"
    out = fn(text, {"headings": ["Design Timing Summary",
                                  "Clock Summary",
                                  "Intra Clock Table"]}, {})
    assert out["passed"] is False
    assert "Intra Clock Table" in out["details"]["missing"]


def test_required_columns_finds_pipe_table_header():
    fn = sc.get_check("required_columns")
    text = "| WNS(ns) | TNS(ns) | WHS(ns) | THS(ns) |\n"
    assert fn(text, {"columns": ["WNS(ns)", "WHS(ns)"]}, {})["passed"] is True


def test_required_columns_finds_whitespace_aligned_header():
    """Vivado's ``report_timing_summary`` emits whitespace-aligned tables
    with no '|' separator. The validator must accept them."""
    fn = sc.get_check("required_columns")
    text = (
        "Design Timing Summary\n"
        "---------------------\n"
        "\n"
        "    WNS(ns)      TNS(ns)      WHS(ns)      THS(ns)  \n"
        "    -------      -------      -------      -------  \n"
        "      0.472        0.000        0.030        0.000  \n"
    )
    out = fn(text,
             {"columns": ["WNS(ns)", "TNS(ns)", "WHS(ns)", "THS(ns)"]}, {})
    assert out["passed"] is True
    assert out["details"]["format"] == "whitespace"


def test_required_columns_finds_wrapped_header_across_two_lines():
    """Real Vivado output wraps the unit suffix '(ns)' onto a second line
    when columns are narrow. The validator must merge consecutive header
    rows and still find every requested column."""
    fn = sc.get_check("required_columns")
    text = (
        "Design Timing Summary\n"
        "---------------------\n"
        "\n"
        "    WNS      TNS Failing  TNS Total      WHS      THS Failing  THS Total\n"
        "    (ns)     Endpoints    Endpoints      (ns)     Endpoints    Endpoints\n"
        "    -----    -----------  ---------      -----    -----------  ---------\n"
        "    0.472              0     12345       0.030              0     12345\n"
    )
    out = fn(text,
             {"columns": ["WNS(ns)", "WHS(ns)"]}, {})
    assert out["passed"] is True
    assert out["details"]["format"] == "whitespace_wrapped"


def test_required_columns_still_fails_when_columns_truly_missing():
    fn = sc.get_check("required_columns")
    text = (
        "Design Summary\n"
        "    Slack(ns)    LogicLevels    SkewBound\n"
        "    ---------    -----------    ---------\n"
        "      0.123              4         0.050\n"
    )
    out = fn(text, {"columns": ["WNS(ns)", "TNS(ns)"]}, {})
    assert out["passed"] is False
    assert out["details"]["reason"] == "no header row matched"


def test_tcl_well_formed_balanced_and_unbalanced():
    fn = sc.get_check("tcl_well_formed")
    assert fn("set_clock_groups -group {clk_a} -group {clk_b}", {}, {})["passed"] is True
    assert fn("set_max_delay -from {a -to {b}", {}, {})["passed"] is False


def test_template_render_dotted_lookup():
    out = sc.render(
        "design={{ parameters.top_module }}",
        {"parameters": {"top_module": "u_top"}},
    )
    assert out == "design=u_top"


# -- ReportSchema grader --------------------------------------------------


def _ctx(tmp_path: Path, *, stdout: str = "", parameters=None,
         case_dir: Path | None = None) -> GraderContext:
    return GraderContext(
        workspace_dir=tmp_path,
        stdout=stdout,
        case_dir=case_dir or tmp_path,
        parameters=parameters or {},
    )


def test_report_schema_passes_when_all_checks_pass(tmp_path: Path):
    (tmp_path / "out.xdc").write_text("set_max_delay -from clk_a -to clk_b 5.0\n")
    (tmp_path / "out.xdc.schema.yaml").write_text(textwrap.dedent("""
        checks:
          - { id: idiom, type: any_of_regex,
              patterns: ['set_max_delay\\s+-from'] }
          - { id: nofixme, type: forbidden_substrings,
              substrings: ['FIXME'] }
          - { id: tcl, type: tcl_well_formed }
    """))
    g = get_grader("report_schema")
    r = g.grade({"path": "out.xdc", "schema": "out.xdc.schema.yaml"},
                _ctx(tmp_path))
    assert r.passed is True
    assert r.details["passed_checks"] == 3
    assert r.details["total_checks"] == 3


def test_report_schema_fails_with_partial_score(tmp_path: Path):
    (tmp_path / "out.xdc").write_text("# FIXME: replace this\nset_max_delay -from a -to b 5\n")
    (tmp_path / "out.xdc.schema.yaml").write_text(textwrap.dedent("""
        checks:
          - { id: idiom, type: any_of_regex, patterns: ['set_max_delay'] }
          - { id: nofixme, type: forbidden_substrings, substrings: ['FIXME'] }
    """))
    g = get_grader("report_schema")
    r = g.grade({"path": "out.xdc", "schema": "out.xdc.schema.yaml",
                 "score_partial": True}, _ctx(tmp_path))
    assert r.passed is False
    assert r.score == pytest.approx(0.5)


def test_report_schema_resolves_case_scheme(tmp_path: Path):
    case_dir = tmp_path / "case"
    (case_dir / "schemas").mkdir(parents=True)
    (case_dir / "schemas" / "s.yaml").write_text(
        "checks:\n  - { id: ok, type: regex_required, pattern: 'hello' }\n"
    )
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "out.txt").write_text("hello world")
    g = get_grader("report_schema")
    r = g.grade(
        {"path": "out.txt", "schema": "case://schemas/s.yaml"},
        GraderContext(workspace_dir=ws, case_dir=case_dir),
    )
    assert r.passed is True


def test_report_schema_template_substitutes_parameters(tmp_path: Path):
    (tmp_path / "out.txt").write_text("design=u_top\n")
    (tmp_path / "s.yaml").write_text(textwrap.dedent("""
        checks:
          - { id: name, type: regex_required,
              pattern: 'design=\\b{{ parameters.top_module }}\\b' }
    """))
    g = get_grader("report_schema")
    r = g.grade(
        {"path": "out.txt", "schema": "s.yaml"},
        _ctx(tmp_path, parameters={"top_module": "u_top"}),
    )
    assert r.passed is True


def test_report_schema_missing_artifact_is_fail(tmp_path: Path):
    (tmp_path / "s.yaml").write_text(
        "checks: [{id: x, type: regex_required, pattern: 'x'}]"
    )
    g = get_grader("report_schema")
    r = g.grade({"path": "missing.txt", "schema": "s.yaml"}, _ctx(tmp_path))
    assert r.passed is False
    assert r.details["reason"] == "missing_artifact"


# -- OracleMatch grader ---------------------------------------------------


def test_oracle_match_stdout_field_in_passes(tmp_path: Path):
    (tmp_path / "oracle.yaml").write_text("met: ['true', 'false']\n")
    g = get_grader("oracle_match")
    r = g.grade(
        {"oracle": "oracle.yaml",
         "fields_from_stdout": {"met": "met=(true|false)"},
         "match_rules": [{"kind": "stdout_field_in", "field": "met"}]},
        _ctx(tmp_path, stdout="iterations=2 met=true\n"),
    )
    assert r.passed is True


def test_oracle_match_stdout_metric_within_tolerance(tmp_path: Path):
    (tmp_path / "oracle.yaml").write_text("baseline_wns: -0.412\n")
    g = get_grader("oracle_match")
    r = g.grade(
        {"oracle": "oracle.yaml",
         "fields_from_stdout": {
             "baseline_wns": r"baseline_wns=(-?\d+(?:\.\d+)?)"},
         "match_rules": [{"kind": "stdout_metric_within",
                          "field": "baseline_wns", "tolerance": 0.05}]},
        _ctx(tmp_path, stdout="baseline_wns=-0.40\n"),
    )
    assert r.passed is True
    r2 = g.grade(
        {"oracle": "oracle.yaml",
         "fields_from_stdout": {
             "baseline_wns": r"baseline_wns=(-?\d+(?:\.\d+)?)"},
         "match_rules": [{"kind": "stdout_metric_within",
                          "field": "baseline_wns", "tolerance": 0.001}]},
        _ctx(tmp_path, stdout="baseline_wns=-0.50\n"),
    )
    assert r2.passed is False


def test_oracle_match_every_endpoint_referenced(tmp_path: Path):
    (tmp_path / "oracle.yaml").write_text(
        "required_categories: ['CDC', 'SLR', 'HighFanout', 'LongLogic']\n"
    )
    (tmp_path / "classification.txt").write_text(
        "CDC | -0.5 | a -> b\nHighFanout | -0.4 | c -> d\n"
        "SLR | -0.3 | e -> f\nLongLogic | -0.2 | g -> h\n"
    )
    g = get_grader("oracle_match")
    r = g.grade(
        {"oracle": "oracle.yaml", "artifact": "classification.txt",
         "match_rules": [{"kind": "every_oracle_endpoint_referenced",
                          "from_oracle": "required_categories"}]},
        _ctx(tmp_path),
    )
    assert r.passed is True


def test_oracle_match_every_endpoint_referenced_tolerant_spelling(tmp_path: Path):
    """Oracle says compact ('HighFanout'); artifact uses human-friendly
    ('High Fanout', 'Long Logic', 'SLR Crossing'). Default match mode is
    tolerant, so this must pass — that's the core of the loosened rule.
    """
    (tmp_path / "oracle.yaml").write_text(
        "required_categories: ['CDC', 'SLR', 'HighFanout', 'LongLogic']\n"
    )
    (tmp_path / "classification.txt").write_text(
        "CDC | -0.5 | a -> b\nHigh Fanout | -0.4 | c -> d\n"
        "SLR Crossing | -0.3 | e -> f\nLong Logic | -0.2 | g -> h\n"
    )
    g = get_grader("oracle_match")
    r = g.grade(
        {"oracle": "oracle.yaml", "artifact": "classification.txt",
         "match_rules": [{"kind": "every_oracle_endpoint_referenced",
                          "from_oracle": "required_categories"}]},
        _ctx(tmp_path),
    )
    assert r.passed is True
    # Sanity: details report tolerant mode and how each literal matched.
    details = r.details["rules"][0]["details"]
    assert details["match_mode"] == "tolerant"
    assert details["matched_as"]["HighFanout"].lower() == "high fanout"
    assert details["matched_as"]["LongLogic"].lower() == "long logic"


def test_oracle_match_every_endpoint_referenced_tolerant_variants(tmp_path: Path):
    """Hyphen, underscore and case variants are all accepted in tolerant mode."""
    (tmp_path / "oracle.yaml").write_text(
        "required_categories: ['HighFanout', 'LongLogic']\n"
    )
    (tmp_path / "classification.txt").write_text(
        "high-fanout | -0.4 | a -> b\nLONG_LOGIC | -0.2 | c -> d\n"
    )
    g = get_grader("oracle_match")
    r = g.grade(
        {"oracle": "oracle.yaml", "artifact": "classification.txt",
         "match_rules": [{"kind": "every_oracle_endpoint_referenced",
                          "from_oracle": "required_categories"}]},
        _ctx(tmp_path),
    )
    assert r.passed is True


def test_oracle_match_every_endpoint_referenced_literal_opt_in(tmp_path: Path):
    """Setting `match: literal` on the rule restores the strict
    case-sensitive substring behavior — no spaces / dashes accepted.
    """
    (tmp_path / "oracle.yaml").write_text(
        "required_categories: ['HighFanout', 'LongLogic']\n"
    )
    (tmp_path / "classification.txt").write_text(
        "High Fanout | -0.4 | a -> b\nLong Logic | -0.2 | c -> d\n"
    )
    g = get_grader("oracle_match")
    r = g.grade(
        {"oracle": "oracle.yaml", "artifact": "classification.txt",
         "match_rules": [{"kind": "every_oracle_endpoint_referenced",
                          "from_oracle": "required_categories",
                          "match": "literal"}]},
        _ctx(tmp_path),
    )
    assert r.passed is False
    missing = r.details["rules"][0]["details"]["missing"]
    assert set(missing) == {"HighFanout", "LongLogic"}


def test_oracle_match_every_endpoint_referenced_truly_missing_still_fails(tmp_path: Path):
    """Tolerant mode must NOT degrade into 'always passes' — a category
    that genuinely isn't in the artifact still has to be reported missing.
    """
    (tmp_path / "oracle.yaml").write_text(
        "required_categories: ['CDC', 'SLR', 'HighFanout', 'LongLogic']\n"
    )
    (tmp_path / "classification.txt").write_text(
        "Long Logic | -0.6 | a -> b\nSLR Crossing | -0.5 | c -> d\n"
    )
    g = get_grader("oracle_match")
    r = g.grade(
        {"oracle": "oracle.yaml", "artifact": "classification.txt",
         "match_rules": [{"kind": "every_oracle_endpoint_referenced",
                          "from_oracle": "required_categories"}]},
        _ctx(tmp_path),
    )
    assert r.passed is False
    missing = r.details["rules"][0]["details"]["missing"]
    assert set(missing) == {"CDC", "HighFanout"}


def test_oracle_match_regex_must_not_appear_flags_false_positives(tmp_path: Path):
    (tmp_path / "oracle.yaml").write_text(
        "forbidden_categories: ['UNKNOWN', 'OTHER']\n"
    )
    (tmp_path / "classification.txt").write_text(
        "CDC | -0.1 | a -> b\nUNKNOWN | -0.2 | c -> d\n"
    )
    g = get_grader("oracle_match")
    r = g.grade(
        {"oracle": "oracle.yaml", "artifact": "classification.txt",
         "match_rules": [{"kind": "regex_must_not_appear",
                          "patterns_from_oracle": "forbidden_categories"}]},
        _ctx(tmp_path),
    )
    assert r.passed is False
    rule_details = r.details["rules"][0]["details"]
    assert "UNKNOWN" in rule_details["found"]


# -- registry sanity ------------------------------------------------------


def test_new_graders_are_registered():
    assert "report_schema" in GRADER_REGISTRY
    assert "oracle_match" in GRADER_REGISTRY
