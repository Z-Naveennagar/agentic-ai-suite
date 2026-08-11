"""
Tests for the grader-family layer: registry, load-time expansion, the
`violation` and `tool-execution` families, and YAML boolean coercion.

Families are pure spec-expanders: expand((params, meta)) -> list of core
grader specs. These tests assert the emitted specs without running any eval.
"""

from __future__ import annotations

import pytest

from skills_testing.graders import GRADER_REGISTRY
from skills_testing.graders.families import (
    FAMILY_REGISTRY,
    expand_graders,
    get_family,
)


# -- registry + expansion plumbing ------------------------------------------


@pytest.mark.parametrize("family", ["violation", "tool-execution"])
def test_family_registered(family):
    assert family in FAMILY_REGISTRY
    assert callable(get_family(family).expand)


def test_unknown_family_raises():
    with pytest.raises(KeyError):
        get_family("does-not-exist")


def test_raw_grader_passes_through_unchanged():
    raw = {"id": "x", "type": "content_contains", "source": "stdout", "substring": "hi"}
    out = expand_graders([raw])
    assert out == [raw]


def test_children_are_namespaced_and_tagged():
    out = expand_graders([{"family": "violation", "id": "v", "verdict": "NO"}])
    assert all(s["id"].startswith("v.") for s in out)
    assert all(s["_family"] == "violation" for s in out)


def test_expanded_specs_all_resolve_to_core_graders():
    out = expand_graders([
        {"family": "violation", "id": "v", "verdict": "NO"},
        {"family": "tool-execution", "id": "u", "sequence": ["Read"]},
    ], meta={"skill": "s", "case": "c"})
    for s in out:
        assert s["type"] in GRADER_REGISTRY


def test_zero_expansion_raises():
    # tool-execution with trigger disabled and nothing else -> empty -> error.
    with pytest.raises(ValueError):
        expand_graders([{"family": "tool-execution", "id": "u", "trigger": False}])


# -- violation family -------------------------------------------------------


class TestViolationFamily:
    def test_minimal_verdict(self):
        out = expand_graders([{"family": "violation", "id": "v", "verdict": "NO"}])
        ids = [s["id"] for s in out]
        assert ids == ["v.verdict_present", "v.verdict_not_opposite"]
        assert out[0]["regex"] == r"(?i)VERDICT:\s*NO\b"
        assert out[1]["regex"] == r"(?i)VERDICT:\s*YES\b"
        assert out[1]["must_not_contain"] is True

    def test_yaml_boolean_coercion(self):
        # YAML parses unquoted NO/YES as booleans; the family must recover them.
        false_out = expand_graders([{"family": "violation", "id": "v", "verdict": False}])
        assert false_out[0]["regex"] == r"(?i)VERDICT:\s*NO\b"
        true_out = expand_graders([{"family": "violation", "id": "v", "verdict": True}])
        assert true_out[0]["regex"] == r"(?i)VERDICT:\s*YES\b"

    def test_rules_emit_one_check_each(self):
        out = expand_graders([{
            "family": "violation", "id": "v", "verdict": "NO",
            "rules": ["6.2", "6.3"],
        }])
        rule_ids = [s["id"] for s in out if ".rule_" in s["id"]]
        assert rule_ids == ["v.rule_1", "v.rule_2"]
        assert r"6\.2" in out[2]["regex"]   # rule id is regex-escaped

    def test_oracle_emits_oracle_match(self):
        out = expand_graders([{
            "family": "violation", "id": "v", "verdict": "NO",
            "oracle": "case://oracle/x.yaml", "artifact": "outputs/c.txt",
        }])
        om = [s for s in out if s["type"] == "oracle_match"]
        assert len(om) == 1
        assert om[0]["oracle"] == "case://oracle/x.yaml"
        assert om[0]["artifact"] == "outputs/c.txt"
        kinds = {r["kind"] for r in om[0]["match_rules"]}
        assert kinds == {"every_oracle_endpoint_referenced", "regex_must_not_appear"}

    def test_custom_verdict_no_opposite(self):
        out = expand_graders([{"family": "violation", "id": "v", "verdict": "PASS"}])
        # No inferred opposite for non YES/NO -> only verdict_present.
        assert [s["id"] for s in out] == ["v.verdict_present"]

    def test_missing_verdict_raises(self):
        with pytest.raises(ValueError):
            expand_graders([{"family": "violation", "id": "v"}])


# -- tool-execution family --------------------------------------------------


class TestToolExecutionFamily:
    def test_trigger_by_default(self):
        out = expand_graders([{"family": "tool-execution", "id": "u"}],
                             meta={"skill": "my-skill"})
        assert [s["id"] for s in out] == ["u.skill_triggered"]
        assert out[0]["type"] == "trigger"
        assert out[0]["skill"] == "my-skill"   # defaulted from meta

    def test_sequence_emits_action_sequence(self):
        out = expand_graders([{
            "family": "tool-execution", "id": "u",
            "sequence": ["Read", "Bash"], "matching": "in_order_match",
        }])
        seq = [s for s in out if s["type"] == "action_sequence"]
        assert seq[0]["expected_actions"] == ["Read", "Bash"]
        assert seq[0]["matching_mode"] == "in_order_match"

    def test_tool_observed_when_requested(self):
        out = expand_graders([{
            "family": "tool-execution", "id": "u",
            "tool": "vivado_mcp", "min_tool_calls": 2,
        }])
        tc = [s for s in out if s["type"] == "tool_call_observed"]
        assert tc[0]["tool"] == "vivado_mcp"
        assert tc[0]["min_calls"] == 2

    def test_explicit_trigger_mode_passed_through(self):
        out = expand_graders([{
            "family": "tool-execution", "id": "u",
            "trigger_mode": "negative", "skill": "s",
        }])
        assert out[0]["mode"] == "negative"
