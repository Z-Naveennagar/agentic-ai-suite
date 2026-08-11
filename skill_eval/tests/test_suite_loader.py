"""
Tests for the 3-file suite loader (skill_spec / grader_spec / runner_spec).

A suite directory expands into one CaseSpec per skill_spec.test_cases entry.
Grading comes from a shared grader_spec.yaml with {token} placeholders
substituted from each case's `expected`. Legacy per-case manifest.yaml
directories keep working alongside suites.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from skills_testing.core.case_loader import (
    CaseSchemaError,
    _resolve_versioned_expected,
    discover_cases,
    is_suite_dir,
    load_suite,
)


def _write_suite(root: Path, skill: str = "demo-skill") -> Path:
    suite = root / skill
    (suite / "inputs").mkdir(parents=True)
    (suite / "inputs" / "a.cpp").write_text("// a\n")
    (suite / "inputs" / "b.cpp").write_text("// b\n")

    (suite / "runner_spec.yaml").write_text(yaml.safe_dump({
        "skill_name": skill,
        "skill_version": "2.0.0",
        "suite_id": "demo-suite",
        "invocation": {
            "coding_agent": [{"name": "opencode", "model": "azure/gpt-5.4"}],
            "skills": [skill],
            "timeout_seconds": 123,
            "max_tokens_per_run": 4567,
        },
        "requirements": {"vivado": False, "vitis": False,
                         "min_memory_gb": 1, "min_disk_gb": 1,
                         "tags": ["smoke"]},
        "cleanup": ["working_dir"],
    }))

    (suite / "grader_spec.yaml").write_text(yaml.safe_dump({
        "graders": [
            {"id": "verdict_present", "type": "content_contains",
             "source": "stdout", "regex": r"(?i)VERDICT:\s*{verdict}\b"},
            {"id": "verdict_absent", "type": "content_contains",
             "source": "stdout", "regex": r"(?i)VERDICT:\s*{opposite}\b",
             "must_not_contain": True},
        ],
        "scoring": {"pass_threshold": 1.0},
    }))

    (suite / "skill_spec.yaml").write_text(yaml.safe_dump({
        "suite_id": "demo-suite",
        "test_cases": [
            {"id": "case_yes", "input_files": ["a.cpp"],
             "expected": {"verdict": "YES", "opposite": "NO"},
             "prompt": "Analyze {input_file} with {skill_name}.",
             "prompt_without_skill": "Analyze {input_file}."},
            {"id": "case_no", "input_files": ["b.cpp"],
             "expected": {"verdict": "NO", "opposite": "YES"},
             "prompt": "Analyze {input_file} with {skill_name}."},
        ],
    }))
    return suite


def test_is_suite_dir(tmp_path: Path):
    suite = _write_suite(tmp_path)
    assert is_suite_dir(suite)
    assert not is_suite_dir(tmp_path)


def test_load_suite_expands_to_one_case_per_entry(tmp_path: Path):
    suite = _write_suite(tmp_path)
    cases = load_suite(suite)
    assert [c.case_id for c in cases] == ["case_yes", "case_no"]
    for c in cases:
        assert c.skill_name == "demo-skill"
        assert c.skill_version == "2.0.0"
        assert c.suite_id == "demo-suite"
        assert c.pass_threshold == 1.0
        # coding_agent -> clients
        assert c.invocation["clients"] == [
            {"name": "opencode", "model": "azure/gpt-5.4"}]
        assert c.invocation["skills"] == ["demo-skill"]
        assert c.invocation["timeout_seconds"] == 123
        assert c.invocation["max_tokens_per_run"] == 4567


def test_setup_and_teardown_default_to_none(tmp_path: Path):
    suite = _write_suite(tmp_path)
    cases = load_suite(suite)
    for c in cases:
        assert c.setup_action is None
        assert c.teardown_action is None


def test_setup_action_prompt_parsed_from_runner_spec(tmp_path: Path):
    suite = _write_suite(tmp_path)
    doc = yaml.safe_load((suite / "runner_spec.yaml").read_text())
    doc["setup"] = {"kind": "prompt", "prompt": "start vivado please"}
    doc["teardown"] = {"kind": "bash", "command": "rm -rf leftover"}
    (suite / "runner_spec.yaml").write_text(yaml.safe_dump(doc))

    cases = load_suite(suite)
    for c in cases:
        assert c.setup_action == {
            "kind": "prompt", "prompt": "start vivado please",
            "script": None, "module": None, "args": [], "command": None, "timeout_seconds": 1800,
        }
        assert c.teardown_action == {
            "kind": "bash", "prompt": None, "script": None, "module": None, "args": [],
            "command": "rm -rf leftover", "timeout_seconds": 1800,
        }


def test_reset_action_parsed_from_runner_spec(tmp_path: Path):
    suite = _write_suite(tmp_path)
    doc = yaml.safe_load((suite / "runner_spec.yaml").read_text())
    doc["reset"] = {"kind": "bash", "command": "ipcfg-cleanup"}
    (suite / "runner_spec.yaml").write_text(yaml.safe_dump(doc))

    cases = load_suite(suite)
    for c in cases:
        assert c.reset_action == {
            "kind": "bash", "prompt": None, "script": None, "module": None, "args": [],
            "command": "ipcfg-cleanup", "timeout_seconds": 1800,
        }
        assert c.setup_action is None
        assert c.teardown_action is None


def test_setup_action_must_be_a_mapping(tmp_path: Path):
    suite = _write_suite(tmp_path)
    doc = yaml.safe_load((suite / "runner_spec.yaml").read_text())
    doc["setup"] = "reserve_license"
    (suite / "runner_spec.yaml").write_text(yaml.safe_dump(doc))

    with pytest.raises(CaseSchemaError, match="setup must be a mapping"):
        load_suite(suite)


def test_setup_action_requires_known_kind(tmp_path: Path):
    suite = _write_suite(tmp_path)
    doc = yaml.safe_load((suite / "runner_spec.yaml").read_text())
    doc["setup"] = {"kind": "carrier_pigeon"}
    (suite / "runner_spec.yaml").write_text(yaml.safe_dump(doc))

    with pytest.raises(CaseSchemaError, match="setup.kind must be one of"):
        load_suite(suite)


def test_setup_action_prompt_kind_requires_prompt_field(tmp_path: Path):
    suite = _write_suite(tmp_path)
    doc = yaml.safe_load((suite / "runner_spec.yaml").read_text())
    doc["setup"] = {"kind": "prompt"}
    (suite / "runner_spec.yaml").write_text(yaml.safe_dump(doc))

    with pytest.raises(CaseSchemaError, match="setup.prompt is required"):
        load_suite(suite)


def test_teardown_action_python_kind_requires_script_or_module(tmp_path: Path):
    """kind=python needs something to run: a suite-local script: or an
    importable module: (the shared-helper form, e.g.
    skills_testing.runtime.vivado_session_setup)."""
    suite = _write_suite(tmp_path)
    doc = yaml.safe_load((suite / "runner_spec.yaml").read_text())
    doc["teardown"] = {"kind": "python"}
    (suite / "runner_spec.yaml").write_text(yaml.safe_dump(doc))

    with pytest.raises(CaseSchemaError, match=r"either \.script or \.module"):
        load_suite(suite)


def test_discover_cases_coding_agents_override_applies_to_suite(tmp_path: Path):
    _write_suite(tmp_path)
    master = [{"name": "claude_code", "model": "sonnet"}]
    cfg = {"skill_testing": {"coding_agents": master}}
    cases = discover_cases(tmp_path, config=cfg)
    assert len(cases) == 2
    for c in cases:
        assert c.invocation["clients"] == master


def test_placeholder_substitution_in_graders(tmp_path: Path):
    suite = _write_suite(tmp_path)
    yes, no = load_suite(suite)
    # {verdict}/{opposite} substituted per case; no families involved.
    assert yes.grading[0]["regex"] == r"(?i)VERDICT:\s*YES\b"
    assert yes.grading[1]["regex"] == r"(?i)VERDICT:\s*NO\b"
    assert yes.grading[1]["must_not_contain"] is True
    assert no.grading[0]["regex"] == r"(?i)VERDICT:\s*NO\b"
    assert no.grading[1]["regex"] == r"(?i)VERDICT:\s*YES\b"
    # every grader is a plain core type
    assert all(g["type"] == "content_contains" for c in (yes, no) for g in c.grading)


def test_prompts_and_inputs(tmp_path: Path):
    suite = _write_suite(tmp_path)
    yes, no = load_suite(suite)
    # per-case prompt with {input_file}/{skill_name} substitution
    assert yes.invocation["prompt"] == "Analyze a.cpp with demo-skill."
    assert no.invocation["prompt"] == "Analyze b.cpp with demo-skill."
    # inputs staged via external_inputs (not a case-local inputs/ dir)
    assert yes.inputs_dir is None
    ext = yes.invocation["external_inputs"]
    assert ext == [{"src": str((suite / "inputs" / "a.cpp").resolve()),
                    "dest": "a.cpp"}]


def test_shared_prompt_in_skill_spec(tmp_path: Path):
    """A top-level `prompt` in skill_spec is shared by every case, with
    {input_file}/{skill_name} substituted per case."""
    suite = tmp_path / "shared-skill"
    (suite / "inputs").mkdir(parents=True)
    (suite / "inputs" / "a.cpp").write_text("// a\n")
    (suite / "inputs" / "b.cpp").write_text("// b\n")
    (suite / "runner_spec.yaml").write_text(yaml.safe_dump({
        "skill_name": "shared-skill",
        "invocation": {"coding_agent": [{"name": "opencode", "model": "m"}]},
        "requirements": {"tags": ["smoke"]},
    }))
    (suite / "grader_spec.yaml").write_text(yaml.safe_dump({
        "graders": [{"id": "v", "type": "content_contains",
                     "source": "stdout", "regex": "{verdict}"}],
    }))
    (suite / "skill_spec.yaml").write_text(yaml.safe_dump({
        "prompt": "Read inputs/{input_file} using {skill_name}.",
        "prompt_without_skill": "Read inputs/{input_file}.",
        "test_cases": [
            {"id": "c1", "input_files": ["a.cpp"], "expected": {"verdict": "YES"}},
            {"id": "c2", "input_files": ["b.cpp"], "expected": {"verdict": "NO"}},
        ],
    }))
    c1, c2 = load_suite(suite)
    assert c1.invocation["prompt"] == "Read inputs/a.cpp using shared-skill."
    assert c1.invocation["prompt_without_skill"] == "Read inputs/a.cpp."
    assert c2.invocation["prompt"] == "Read inputs/b.cpp using shared-skill."
    # grader placeholder still substituted from each case's expected
    assert c1.grading[0]["regex"] == "YES"
    assert c2.grading[0]["regex"] == "NO"


def test_shared_prompt_prefix_prepended_to_every_case_with_case_number(tmp_path: Path):
    """shared_prompt_prefix is a session-level protocol repeated per case
    (each case is its own separate agent invocation, so it can't just be
    said once) -- prepended to both prompt and prompt_without_skill, with
    {case_number} substituted as the case's 1-based position."""
    suite = tmp_path / "logging-skill"
    (suite / "inputs").mkdir(parents=True)
    (suite / "inputs" / "a.cpp").write_text("// a\n")
    (suite / "inputs" / "b.cpp").write_text("// b\n")
    (suite / "runner_spec.yaml").write_text(yaml.safe_dump({
        "skill_name": "logging-skill",
        "invocation": {"coding_agent": [{"name": "opencode", "model": "m"}]},
        "requirements": {"tags": ["smoke"]},
        "shared_prompt_prefix": "Append id {case_number} to Results/blind_run.jsonl.",
    }))
    (suite / "grader_spec.yaml").write_text(yaml.safe_dump({
        "graders": [{"id": "v", "type": "content_contains",
                     "source": "stdout", "regex": "{verdict}"}],
    }))
    (suite / "skill_spec.yaml").write_text(yaml.safe_dump({
        "prompt": "Read inputs/{input_file}.",
        "prompt_without_skill": "Read inputs/{input_file} (no skill).",
        "test_cases": [
            {"id": "c1", "input_files": ["a.cpp"], "expected": {"verdict": "YES"}},
            {"id": "c2", "input_files": ["b.cpp"], "expected": {"verdict": "NO"}},
        ],
    }))
    c1, c2 = load_suite(suite)
    assert c1.invocation["prompt"] == (
        "Append id 1 to Results/blind_run.jsonl.\n\nRead inputs/a.cpp.")
    assert c1.invocation["prompt_without_skill"] == (
        "Append id 1 to Results/blind_run.jsonl.\n\nRead inputs/a.cpp (no skill).")
    assert c2.invocation["prompt"] == (
        "Append id 2 to Results/blind_run.jsonl.\n\nRead inputs/b.cpp.")
    assert c2.invocation["prompt_without_skill"] == (
        "Append id 2 to Results/blind_run.jsonl.\n\nRead inputs/b.cpp (no skill).")


def test_shared_prompt_prefix_substitutes_case_id_and_per_case_cell_name(tmp_path: Path):
    """{case_id} is always available (the case's own id); {cell_name} (or
    any other per-case field) is opt-in -- a case that declares it in
    skill_spec.yaml becomes available as {cell_name} in shared_prompt_prefix/
    prompt/prompt_without_skill, without the loader hard-coding any
    suite-specific naming convention."""
    suite = tmp_path / "cellname-skill"
    (suite / "inputs").mkdir(parents=True)
    (suite / "runner_spec.yaml").write_text(yaml.safe_dump({
        "skill_name": "cellname-skill",
        "invocation": {"coding_agent": [{"name": "opencode", "model": "m"}]},
        "requirements": {"tags": ["smoke"]},
        "shared_prompt_prefix": (
            "Add a cell named `{cell_name}`. Save results at "
            "outputs/{case_id}/as_configured.json."
        ),
    }))
    (suite / "grader_spec.yaml").write_text(yaml.safe_dump({
        "graders": [{"id": "v", "type": "content_contains",
                     "source": "stdout", "regex": "{verdict}"}],
    }))
    (suite / "skill_spec.yaml").write_text(yaml.safe_dump({
        "test_cases": [
            {"id": "c1", "cell_name": "bench_cell_001",
             "prompt": "Configure a thing.", "expected": {"verdict": "YES"}},
        ],
    }))
    [c1] = load_suite(suite)
    assert c1.invocation["prompt"] == (
        "Add a cell named `bench_cell_001`. Save results at "
        "outputs/c1/as_configured.json.\n\nConfigure a thing."
    )


def test_no_shared_prompt_prefix_leaves_prompts_unchanged(tmp_path: Path):
    suite = _write_suite(tmp_path)
    cases = load_suite(suite)
    for c in cases:
        assert not c.invocation["prompt"].startswith("Append")


def test_shared_prompt_prefix_must_be_a_string(tmp_path: Path):
    suite = _write_suite(tmp_path)
    doc = yaml.safe_load((suite / "runner_spec.yaml").read_text())
    doc["shared_prompt_prefix"] = {"kind": "prompt"}
    (suite / "runner_spec.yaml").write_text(yaml.safe_dump(doc))

    with pytest.raises(CaseSchemaError, match="shared_prompt_prefix must be a string"):
        load_suite(suite)


def test_final_prompt_is_prefix_then_contract_then_case_prompt(tmp_path: Path):
    """The shared preamble is two parts: shared_prompt_prefix (requirement +
    instructions) then output_contract (JSON shape), assembled ahead of the
    per-case prompt -> prefix + output_contract + case prompt."""
    suite = tmp_path / "contract-skill"
    (suite / "inputs").mkdir(parents=True)
    (suite / "inputs" / "a.cpp").write_text("// a\n")
    (suite / "runner_spec.yaml").write_text(yaml.safe_dump({
        "skill_name": "contract-skill",
        "invocation": {"coding_agent": [{"name": "opencode", "model": "m"}]},
        "requirements": {"tags": ["smoke"]},
        "shared_prompt_prefix": "REQUIREMENT case {case_number}.",
        "output_contract": "CONTRACT: emit JSON {\"id\": {case_number}}.",
    }))
    (suite / "grader_spec.yaml").write_text(yaml.safe_dump({
        "graders": [{"id": "v", "type": "content_contains",
                     "source": "stdout", "regex": "{verdict}"}],
    }))
    (suite / "skill_spec.yaml").write_text(yaml.safe_dump({
        "prompt": "Do the task on inputs/{input_file}.",
        "prompt_without_skill": "No-skill: inputs/{input_file}.",
        "test_cases": [
            {"id": "c1", "input_files": ["a.cpp"], "expected": {"verdict": "YES"}},
        ],
    }))
    [c1] = load_suite(suite)
    assert c1.invocation["prompt"] == (
        "REQUIREMENT case 1.\n\n"
        'CONTRACT: emit JSON {"id": 1}.\n\n'
        "Do the task on inputs/a.cpp.")
    # Same preamble ordering applies to the no-skill arm.
    assert c1.invocation["prompt_without_skill"].startswith(
        "REQUIREMENT case 1.\n\nCONTRACT: emit JSON {\"id\": 1}.\n\n")


def test_output_contract_without_prefix_still_prepends(tmp_path: Path):
    suite = tmp_path / "contract-only"
    (suite / "inputs").mkdir(parents=True)
    (suite / "runner_spec.yaml").write_text(yaml.safe_dump({
        "skill_name": "contract-only",
        "invocation": {"coding_agent": [{"name": "opencode", "model": "m"}]},
        "requirements": {"tags": ["smoke"]},
        "output_contract": "CONTRACT here.",
    }))
    (suite / "grader_spec.yaml").write_text(yaml.safe_dump({
        "graders": [{"id": "v", "type": "content_contains",
                     "source": "stdout", "regex": "{verdict}"}],
    }))
    (suite / "skill_spec.yaml").write_text(yaml.safe_dump({
        "test_cases": [
            {"id": "c1", "prompt": "Task.", "expected": {"verdict": "YES"}},
        ],
    }))
    [c1] = load_suite(suite)
    assert c1.invocation["prompt"] == "CONTRACT here.\n\nTask."


def test_output_contract_must_be_a_string(tmp_path: Path):
    suite = _write_suite(tmp_path)
    doc = yaml.safe_load((suite / "runner_spec.yaml").read_text())
    doc["output_contract"] = ["not", "a", "string"]
    (suite / "runner_spec.yaml").write_text(yaml.safe_dump(doc))
    with pytest.raises(CaseSchemaError, match="output_contract must be a string"):
        load_suite(suite)


def test_master_prompt_still_accepted_as_deprecated_alias(tmp_path: Path):
    """The former `master_prompt` key keeps working (so existing suites don't
    break) but emits a DeprecationWarning pointing at the new name."""
    suite = tmp_path / "legacy-skill"
    (suite / "inputs").mkdir(parents=True)
    (suite / "inputs" / "a.cpp").write_text("// a\n")
    (suite / "runner_spec.yaml").write_text(yaml.safe_dump({
        "skill_name": "legacy-skill",
        "invocation": {"coding_agent": [{"name": "opencode", "model": "m"}]},
        "requirements": {"tags": ["smoke"]},
        "master_prompt": "Append id {case_number} to Results/blind_run.jsonl.",
    }))
    (suite / "grader_spec.yaml").write_text(yaml.safe_dump({
        "graders": [{"id": "v", "type": "content_contains",
                     "source": "stdout", "regex": "{verdict}"}],
    }))
    (suite / "skill_spec.yaml").write_text(yaml.safe_dump({
        "prompt": "Read inputs/{input_file}.",
        "test_cases": [
            {"id": "c1", "input_files": ["a.cpp"], "expected": {"verdict": "YES"}},
        ],
    }))
    with pytest.warns(DeprecationWarning, match="master_prompt.*deprecated"):
        [c1] = load_suite(suite)
    # Behaviour is identical to shared_prompt_prefix.
    assert c1.invocation["prompt"] == (
        "Append id 1 to Results/blind_run.jsonl.\n\nRead inputs/a.cpp.")


def test_discover_mixes_suite_and_legacy(tmp_path: Path):
    _write_suite(tmp_path, skill="demo-skill")
    # a legacy per-case manifest skill alongside the suite
    legacy = tmp_path / "legacy-skill" / "case_1"
    legacy.mkdir(parents=True)
    (legacy / "manifest.yaml").write_text(yaml.safe_dump({
        "skill_name": "legacy-skill", "skill_version": "1.0.0",
        "case_id": "case_1",
        "invocation": {"clients": [{"name": "opencode", "model": "m"}],
                       "timeout_seconds": 60},
        "requirements": {"tags": ["smoke"]},
    }))
    (legacy / "grading_spec.yaml").write_text(yaml.safe_dump({
        "graders": [{"id": "x", "type": "content_contains",
                     "source": "stdout", "substring": "ok"}]}))

    cases = discover_cases(tmp_path)
    ids = {(c.skill_name, c.case_id) for c in cases}
    assert ("demo-skill", "case_yes") in ids
    assert ("demo-skill", "case_no") in ids
    assert ("legacy-skill", "case_1") in ids


def test_missing_spec_file_raises(tmp_path: Path):
    suite = _write_suite(tmp_path)
    (suite / "grader_spec.yaml").unlink()
    with pytest.raises(CaseSchemaError):
        load_suite(suite)


def test_missing_input_file_raises(tmp_path: Path):
    suite = _write_suite(tmp_path)
    (suite / "inputs" / "a.cpp").unlink()
    with pytest.raises(CaseSchemaError):
        load_suite(suite)


def _write_output_schema_suite(root: Path, *, case_expected: dict) -> Path:
    """A suite using the real `output_schema:` (rich) grader_spec shape, with
    one always-required whole-value placeholder (`skill_triggered`'s
    `{skills}`) and one conditional one (`tool_sequence`'s `{tool_sequence}`)
    -- the shape that actually exercises the whole-value substitution path
    (unlike `_write_suite`'s legacy `graders:` list with only inline
    placeholders)."""
    suite = root / "output-schema-skill"
    (suite / "inputs").mkdir(parents=True)
    (suite / "inputs" / "a.cpp").write_text("// a\n")

    (suite / "runner_spec.yaml").write_text(yaml.safe_dump({
        "skill_name": "output-schema-skill",
        "skill_version": "1.0.0",
        "suite_id": "output-schema-suite",
        "invocation": {
            "coding_agent": [{"name": "opencode", "model": "azure/gpt-5.4"}],
            "skills": ["output-schema-skill"],
            "timeout_seconds": 123,
        },
        "requirements": {"vivado": False, "vitis": False,
                         "min_memory_gb": 1, "min_disk_gb": 1, "tags": []},
        "cleanup": ["working_dir"],
    }))
    (suite / "grader_spec.yaml").write_text(yaml.safe_dump({
        "output_schema": {
            "skill_triggered": {
                "grader": "trigger",
                "mandatory": True,
                "grader_args": "{skills}",
            },
            "tool_sequence": {
                "grader": "action_sequence",
                "mandatory": False,
                "weight": 1.0,
                "grader_args": {
                    "matching_mode": "any_order_match",
                    "tool_sequence": "{tool_sequence}",
                },
            },
        },
        "scoring": {"aggregation": "weighted_sum", "pass_threshold": 70.0},
    }))
    (suite / "skill_spec.yaml").write_text(yaml.safe_dump({
        "suite_id": "output-schema-suite",
        "test_cases": [
            {"id": "case_1", "input_files": ["a.cpp"], "expected": case_expected},
        ],
    }))
    return suite


def test_missing_always_required_placeholder_raises(tmp_path: Path):
    """A case whose `expected:` block omits a key an always-required
    whole-value placeholder (e.g. `skill_triggered`'s `{skills}`) needs must
    fail loudly at load time -- not silently leave the literal `"{skills}"`
    string in place for the grader to mis-interpret."""
    suite = _write_output_schema_suite(
        tmp_path, case_expected={"tool_sequence": ["Read"]})
    with pytest.raises(CaseSchemaError, match="missing expected.skills"):
        load_suite(suite)


def test_missing_conditional_placeholder_drops_grader(tmp_path: Path):
    """A case whose `expected:` block omits a key a *conditional*
    whole-value placeholder needs (e.g. `tool_sequence` -- only meaningful
    for some case shapes within a suite) must NOT fail load; that grader is
    simply dropped from this case's grading list instead."""
    suite = _write_output_schema_suite(
        tmp_path, case_expected={"skills": ["output-schema-skill"]})
    [case] = load_suite(suite)
    assert [g["id"] for g in case.grading] == ["skill_triggered"]


def test_present_whole_value_placeholder_substitutes_list(tmp_path: Path):
    suite = _write_output_schema_suite(
        tmp_path,
        case_expected={"skills": ["output-schema-skill"], "tool_sequence": ["Read"]})
    [case] = load_suite(suite)
    tool_seq_grader = next(g for g in case.grading if g["id"] == "tool_sequence")
    assert tool_seq_grader["tool_sequence"] == ["Read"]


# -- version-keyed golden answers (_by_vivado_version) ----------------------


def test_no_versioned_key_returns_input_unchanged():
    """A plain `expected:` block with no `_by_vivado_version` suffix is
    returned as-is -- no version probe is ever triggered for ordinary
    single-golden cases."""
    expected = {"verdict": "YES", "opposite": "NO"}
    assert _resolve_versioned_expected(expected) is expected


def test_versioned_key_resolves_by_exact_prefix_match(monkeypatch):
    monkeypatch.setattr(
        "skills_testing.runtime.requirements_probe._VIVADO_VERSION_CACHE",
        "2026.1.0",
    )
    expected = {
        "expected_output_by_vivado_version": {
            "2026.1": {"identified_ip": "ps_wizard"},
            "default": {"identified_ip": "ps11"},
        },
    }
    out = _resolve_versioned_expected(expected)
    assert out == {"expected_output": {"identified_ip": "ps_wizard"}}
    assert "expected_output_by_vivado_version" not in out


def test_versioned_key_falls_back_to_default_when_no_version_matches(monkeypatch):
    monkeypatch.setattr(
        "skills_testing.runtime.requirements_probe._VIVADO_VERSION_CACHE",
        "2024.2.0",
    )
    expected = {
        "expected_output_by_vivado_version": {
            "2026.1": {"identified_ip": "ps_wizard"},
            "default": {"identified_ip": "ps11"},
        },
    }
    out = _resolve_versioned_expected(expected)
    assert out == {"expected_output": {"identified_ip": "ps11"}}


def test_versioned_key_longest_prefix_wins(monkeypatch):
    """A more specific version constraint (2026.1.5) is tried before a
    looser one (2026.1) when both would match the installed version."""
    monkeypatch.setattr(
        "skills_testing.runtime.requirements_probe._VIVADO_VERSION_CACHE",
        "2026.1.5",
    )
    expected = {
        "expected_output_by_vivado_version": {
            "2026.1": {"identified_ip": "loose_match"},
            "2026.1.5": {"identified_ip": "specific_match"},
        },
    }
    out = _resolve_versioned_expected(expected)
    assert out["expected_output"] == {"identified_ip": "specific_match"}


def test_versioned_key_no_match_and_no_default_leaves_plain_field_untouched(monkeypatch):
    monkeypatch.setattr(
        "skills_testing.runtime.requirements_probe._VIVADO_VERSION_CACHE",
        "2024.2.0",
    )
    expected = {
        "expected_output": {"identified_ip": "already_there"},
        "expected_output_by_vivado_version": {
            "2026.1": {"identified_ip": "ps_wizard"},
        },
    }
    out = _resolve_versioned_expected(expected)
    assert out == {"expected_output": {"identified_ip": "already_there"}}


def test_versioned_key_does_not_mutate_input(monkeypatch):
    monkeypatch.setattr(
        "skills_testing.runtime.requirements_probe._VIVADO_VERSION_CACHE",
        "2026.1.0",
    )
    expected = {
        "expected_output_by_vivado_version": {
            "2026.1": {"identified_ip": "ps_wizard"},
            "default": {"identified_ip": "ps11"},
        },
    }
    _resolve_versioned_expected(expected)
    assert "expected_output_by_vivado_version" in expected
    assert "expected_output" not in expected


def test_load_suite_resolves_versioned_expected_end_to_end(tmp_path: Path, monkeypatch):
    """A suite's `expected:` block using `_by_vivado_version` resolves to the
    variant matching the installed tool version, and that resolved value
    flows through to grader placeholder substitution exactly like a plain
    `expected:` field would."""
    monkeypatch.setattr(
        "skills_testing.runtime.requirements_probe._VIVADO_VERSION_CACHE",
        "2026.1.0",
    )
    suite = tmp_path / "versioned-skill"
    (suite / "inputs").mkdir(parents=True)
    (suite / "inputs" / "a.cpp").write_text("// a\n")
    (suite / "runner_spec.yaml").write_text(yaml.safe_dump({
        "skill_name": "versioned-skill",
        "invocation": {"coding_agent": [{"name": "opencode", "model": "m"}]},
        "requirements": {"tags": ["smoke"]},
    }))
    (suite / "grader_spec.yaml").write_text(yaml.safe_dump({
        "graders": [{"id": "v", "type": "content_contains",
                     "source": "stdout", "regex": "{verdict}"}],
    }))
    (suite / "skill_spec.yaml").write_text(yaml.safe_dump({
        "test_cases": [
            {"id": "c1", "input_files": ["a.cpp"], "prompt": "Task.",
             "expected": {
                 "verdict_by_vivado_version": {
                     "2026.1": "ps_wizard",
                     "default": "ps11",
                 },
             }},
        ],
    }))
    [c1] = load_suite(suite)
    assert c1.grading[0]["regex"] == "ps_wizard"
