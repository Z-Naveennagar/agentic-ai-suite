"""
Tests for the test-case schema loader.

Each in-scope skill case lives at:

    skills_testing/test_cases/<skill_name>/<case_id>/
        manifest.yaml      - invocation, requirements, cleanup
        grading_spec.yaml  - list of grader specs
        inputs/            - optional, copied into the per-test workspace

The loader exposes:

    discover_cases(test_cases_root) -> list[CaseSpec]
    filter_cases(cases, allowlist, denylist, tag_filter=None) -> list[CaseSpec]
    load_case(case_dir) -> CaseSpec

A CaseSpec has:
    skill_name, skill_version, case_id,
    invocation: dict, requirements: dict, cleanup: list[str],
    grading: list[dict], case_dir: Path

Validation errors should raise CaseSchemaError with a useful message.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from skills_testing.core.case_loader import (
    CaseSchemaError,
    CaseSpec,
    discover_cases,
    filter_cases,
    load_case,
)
from skills_testing.core.paths import TEST_CASES_ROOT


# -- helpers ---------------------------------------------------------------


def _write_case(
    root: Path,
    skill: str,
    case_id: str,
    *,
    manifest: dict | None = None,
    grading: list | None = None,
    inputs: dict[str, str] | None = None,
) -> Path:
    case_dir = root / skill / case_id
    case_dir.mkdir(parents=True)

    default_manifest = {
        "skill_name": skill,
        "skill_version": "1.0.0",
        "case_id": case_id,
        "description": "test case",
        "invocation": {
            "clients": [{"name": "claude_code", "model": "opus"}],
            "parameters": {},
            "timeout_seconds": 60,
        },
        "requirements": {
            "vivado": False,
            "vitis": False,
            "min_memory_gb": 1,
            "min_disk_gb": 1,
            "tags": ["smoke"],
        },
        "cleanup": ["working_dir"],
    }
    m = {**default_manifest, **(manifest or {})}
    (case_dir / "manifest.yaml").write_text(yaml.safe_dump(m))

    g = grading if grading is not None else [
        {"id": "lint_report_exists", "type": "artifact_exists",
         "path": "outputs/lint.rpt"},
    ]
    (case_dir / "grading_spec.yaml").write_text(
        yaml.safe_dump({"graders": g})
    )

    if inputs:
        (case_dir / "inputs").mkdir()
        for name, content in inputs.items():
            (case_dir / "inputs" / name).write_text(content)
    return case_dir


# -- load_case -------------------------------------------------------------


class TestLoadCase:
    def test_loads_minimal_case(self, tmp_path):
        case_dir = _write_case(tmp_path, "rtl-assistant", "rtl-lint",
                               inputs={"top.v": "module top; endmodule\n"})
        spec = load_case(case_dir)
        assert isinstance(spec, CaseSpec)
        assert spec.skill_name == "rtl-assistant"
        assert spec.case_id == "rtl-lint"
        assert spec.skill_version == "1.0.0"
        assert spec.invocation["timeout_seconds"] == 60
        assert spec.requirements["vivado"] is False
        assert spec.cleanup == ["working_dir"]
        assert len(spec.grading) == 1
        assert spec.grading[0]["type"] == "artifact_exists"
        assert spec.case_dir == case_dir

    def test_missing_manifest_raises(self, tmp_path):
        case_dir = tmp_path / "x" / "y"
        case_dir.mkdir(parents=True)
        (case_dir / "grading_spec.yaml").write_text("graders: []")
        with pytest.raises(CaseSchemaError, match="manifest.yaml"):
            load_case(case_dir)

    def test_missing_required_fields_raises(self, tmp_path):
        case_dir = tmp_path / "rtl-assistant" / "x"
        case_dir.mkdir(parents=True)
        (case_dir / "manifest.yaml").write_text(yaml.safe_dump({"skill_name": "x"}))
        (case_dir / "grading_spec.yaml").write_text("graders: []")
        with pytest.raises(CaseSchemaError):
            load_case(case_dir)

    def test_invocation_must_have_clients(self, tmp_path):
        case_dir = _write_case(
            tmp_path, "rtl-assistant", "x",
            manifest={"invocation": {"parameters": {}, "timeout_seconds": 30}},
        )
        with pytest.raises(CaseSchemaError, match="clients"):
            load_case(case_dir)

    def test_unknown_grader_type_raises(self, tmp_path):
        case_dir = _write_case(
            tmp_path, "rtl-assistant", "x",
            grading=[{"id": "g1", "type": "no_such_grader"}],
        )
        with pytest.raises(CaseSchemaError, match="grader"):
            load_case(case_dir)


# -- discover_cases --------------------------------------------------------


class TestDiscoverCases:
    def test_finds_multiple(self, tmp_path):
        _write_case(tmp_path, "rtl-assistant", "rtl-lint")
        _write_case(tmp_path, "rtl-assistant", "report_methodology")
        _write_case(tmp_path, "vivado-revision-control", "standard_export")
        cases = discover_cases(tmp_path)
        keys = {(c.skill_name, c.case_id) for c in cases}
        assert keys == {
            ("rtl-assistant", "rtl-lint"),
            ("rtl-assistant", "report_methodology"),
            ("vivado-revision-control", "standard_export"),
        }

    def test_returns_empty_when_no_cases(self, tmp_path):
        assert discover_cases(tmp_path) == []

    def test_skips_directories_without_manifest(self, tmp_path):
        _write_case(tmp_path, "rtl-assistant", "good")
        bad = tmp_path / "rtl-assistant" / "bad"
        bad.mkdir()
        (bad / "README.md").write_text("not a case")
        cases = discover_cases(tmp_path)
        assert {c.case_id for c in cases} == {"good"}


class TestCodingAgentsOverride:
    """skill_testing.coding_agents, when set, replaces every case's
    invocation.clients regardless of what its own manifest.yaml declares."""

    MASTER = [{"name": "opencode", "model": "azure/gpt-5.4"}]

    def test_no_config_leaves_clients_untouched(self, tmp_path):
        _write_case(tmp_path, "rtl-assistant", "rtl-lint")
        cases = discover_cases(tmp_path)
        assert cases[0].invocation["clients"] == [
            {"name": "claude_code", "model": "opus"}]

    def test_empty_coding_agents_leaves_clients_untouched(self, tmp_path):
        _write_case(tmp_path, "rtl-assistant", "rtl-lint")
        cfg = {"skill_testing": {"coding_agents": []}}
        cases = discover_cases(tmp_path, config=cfg)
        assert cases[0].invocation["clients"] == [
            {"name": "claude_code", "model": "opus"}]

    def test_override_replaces_clients_for_every_case(self, tmp_path):
        _write_case(tmp_path, "rtl-assistant", "rtl-lint")
        _write_case(tmp_path, "vivado-revision-control", "standard_export")
        cfg = {"skill_testing": {"coding_agents": self.MASTER}}
        cases = discover_cases(tmp_path, config=cfg)
        assert len(cases) == 2
        for c in cases:
            assert c.invocation["clients"] == self.MASTER

    def test_malformed_master_entry_raises(self, tmp_path):
        _write_case(tmp_path, "rtl-assistant", "rtl-lint")
        cfg = {"skill_testing": {"coding_agents": [{"name": "opencode"}]}}
        with pytest.raises(CaseSchemaError, match="coding_agents"):
            discover_cases(tmp_path, config=cfg)


class TestCliClientsOverride:
    """cli_clients (skills-test run --client/--model), when given, replaces
    every case's invocation.clients -- outranking both the suite's own
    declared clients AND skill_testing.coding_agents (the persistent,
    config-file fleet override)."""

    CLI_OVERRIDE = [{"name": "cursor", "model": "auto"}]

    def test_cli_clients_replaces_clients_for_every_case(self, tmp_path):
        _write_case(tmp_path, "rtl-assistant", "rtl-lint")
        _write_case(tmp_path, "vivado-revision-control", "standard_export")
        cases = discover_cases(tmp_path, cli_clients=self.CLI_OVERRIDE)
        assert len(cases) == 2
        for c in cases:
            assert c.invocation["clients"] == self.CLI_OVERRIDE

    def test_cli_clients_outranks_coding_agents(self, tmp_path):
        _write_case(tmp_path, "rtl-assistant", "rtl-lint")
        cfg = {"skill_testing": {"coding_agents": [
            {"name": "opencode", "model": "azure/gpt-5.4"},
        ]}}
        cases = discover_cases(tmp_path, config=cfg, cli_clients=self.CLI_OVERRIDE)
        assert cases[0].invocation["clients"] == self.CLI_OVERRIDE

    def test_malformed_cli_clients_raises(self, tmp_path):
        _write_case(tmp_path, "rtl-assistant", "rtl-lint")
        with pytest.raises(CaseSchemaError, match=r"--client/--model"):
            discover_cases(tmp_path, cli_clients=[{"name": "cursor"}])

    def test_no_cli_clients_leaves_coding_agents_behavior_untouched(self, tmp_path):
        _write_case(tmp_path, "rtl-assistant", "rtl-lint")
        cfg = {"skill_testing": {"coding_agents": [
            {"name": "opencode", "model": "azure/gpt-5.4"},
        ]}}
        cases = discover_cases(tmp_path, config=cfg, cli_clients=None)
        assert cases[0].invocation["clients"] == [
            {"name": "opencode", "model": "azure/gpt-5.4"}]


# -- filter_cases ---------------------------------------------------------


class TestFilterCases:
    def _three_cases(self, tmp_path):
        _write_case(tmp_path, "rtl-assistant", "a")
        _write_case(tmp_path, "vitis-vpp-link", "b")
        _write_case(tmp_path, "pptx", "c")  # blocked by denylist
        return discover_cases(tmp_path)

    def test_denylist_always_blocks(self, tmp_path):
        cases = self._three_cases(tmp_path)
        out = filter_cases(cases, allowlist=[], denylist=["pptx"])
        assert {c.skill_name for c in out} == {"rtl-assistant", "vitis-vpp-link"}

    def test_empty_allowlist_lets_through_everything_not_denied(self, tmp_path):
        cases = self._three_cases(tmp_path)
        out = filter_cases(cases, allowlist=[], denylist=["pptx"])
        assert len(out) == 2

    def test_nonempty_allowlist_restricts(self, tmp_path):
        cases = self._three_cases(tmp_path)
        out = filter_cases(cases, allowlist=["rtl-assistant"], denylist=["pptx"])
        assert {c.skill_name for c in out} == {"rtl-assistant"}

    def test_denylist_wins_over_allowlist(self, tmp_path):
        cases = self._three_cases(tmp_path)
        out = filter_cases(
            cases, allowlist=["rtl-assistant", "pptx"], denylist=["pptx"]
        )
        assert {c.skill_name for c in out} == {"rtl-assistant"}

    def test_tag_filter(self, tmp_path):
        _write_case(tmp_path, "rtl-assistant", "smoke_case")  # tag=[smoke]
        _write_case(
            tmp_path, "rtl-assistant", "heavy_case",
            manifest={"requirements": {
                "vivado": False, "vitis": False,
                "min_memory_gb": 1, "min_disk_gb": 1,
                "tags": ["heavy", "regression"],
            }},
        )
        cases = discover_cases(tmp_path)
        out = filter_cases(cases, [], [], tag_filter=["smoke"])
        assert {c.case_id for c in out} == {"smoke_case"}
        out = filter_cases(cases, [], [], tag_filter=["regression"])
        assert {c.case_id for c in out} == {"heavy_case"}


# -- the seed case ships with the repo and must load -----------------------


@pytest.mark.skip(
    reason="rtl-assistant seed case removed from src/skills_testing/test_cases/ "
           "during the tests/ (formerly vivado_skills_repo) migration, no "
           "replacement authored yet."
)
class TestSeedCaseRtlLint:
    def test_seed_case_loads(self):
        seed = TEST_CASES_ROOT / "rtl-assistant" / "rtl-lint"
        assert seed.exists(), f"seed case missing at {seed}"
        spec = load_case(seed)
        assert spec.skill_name == "rtl-assistant"
        assert spec.case_id == "rtl-lint"
        # at minimum we expect one artifact_exists or content_contains grader
        types = [g["type"] for g in spec.grading]
        assert any(t in {"artifact_exists", "content_contains"} for t in types)
