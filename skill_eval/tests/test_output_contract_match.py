"""Tests for the output_contract_match grader."""
from __future__ import annotations

import json
from pathlib import Path

from skills_testing.graders import GRADER_REGISTRY, GraderContext
from skills_testing.graders.output_contract_match import extract_json


def _ctx(stdout="", stderr="", workspace=None, llm_caller=None):
    return GraderContext(workspace_dir=workspace or Path("."),
                         stdout=stdout, stderr=stderr, llm_caller=llm_caller)


def _grade(spec, ctx):
    return GRADER_REGISTRY["output_contract_match"].grade(spec, ctx)


# ---- JSON extraction ------------------------------------------------------

def test_extract_prefers_last_fenced_json_block():
    text = ('Here is an interim ```json\n{"a": 1}\n``` and the final '
            'answer:\n```json\n{"a": 2, "b": "x"}\n```')
    obj, err = extract_json(text)
    assert err is None
    assert obj == {"a": 2, "b": "x"}


def test_extract_raw_trailing_object():
    text = 'blah blah\nResult: {"id": 1, "ok": true}\n'
    obj, err = extract_json(text)
    assert obj == {"id": 1, "ok": True}


def test_extract_none_when_no_json():
    obj, err = extract_json("no json here at all")
    assert obj is None and err


def test_extract_survives_stray_unclosed_brace_before_real_json():
    # Regression: Copilot's bullet-transcript text mode truncates a tool-call
    # command preview mid-line, e.g. a Tcl `if {$c eq "..."` snippet whose
    # closing brace never appears. A global depth counter over the whole
    # text never sees depth return to 0 after that, and silently drops the
    # real, well-formed JSON object that follows.
    text = ('vivado_execute (MCP: vivado-mcp-server) . set c [get_bd_cells '
            '-quiet x]; if {$c eq "\n'
            '{"identified_ip": "axi_gpio", "vlnv": "xilinx.com:ip:axi_gpio:2.0"}')
    obj, err = extract_json(text)
    assert err is None
    assert obj == {"identified_ip": "axi_gpio", "vlnv": "xilinx.com:ip:axi_gpio:2.0"}


def test_extract_survives_unterminated_string_before_real_json():
    # Regression: a truncated tool-output preview can also cut off mid-string
    # ("output":"...  with no closing quote), which latches a naive
    # string-tracking scanner into "inside a string" for the rest of the
    # text -- hiding the real JSON object's braces from ever being seen as
    # structural at all.
    text = ('"output":"CONFIG.C_GPIO_WIDTH 2 CONFIG.C_ALL_OUTPUTS 1 CONFIG....\n\n'
            '{"identified_ip": "axi_gpio", "tier1_success": true}')
    obj, err = extract_json(text)
    assert err is None
    assert obj == {"identified_ip": "axi_gpio", "tier1_success": True}


# ---- grading --------------------------------------------------------------

def test_exact_match_passes_with_full_score():
    golden = {"id": 1, "identified_ip": "axi_gpio", "ok": True}
    stdout = f'Final answer:\n```json\n{json.dumps(golden)}\n```'
    r = _grade({"expected": golden}, _ctx(stdout=stdout))
    assert r.passed is True
    assert r.score == 1.0
    assert not r.details["mismatches"] and not r.details["missing"]


def test_value_mismatch_fails_and_is_reported():
    golden = {"id": 1, "vlnv": "xilinx.com:ip:axi_gpio:2.0"}
    actual = {"id": 1, "vlnv": "xilinx.com:ip:axi_gpio:1.0"}
    r = _grade({"expected": golden}, _ctx(stdout=json.dumps(actual)))
    assert r.passed is False
    assert r.details["matched"] == 1 and r.details["total"] == 2
    assert r.details["mismatches"][0]["path"] == "vlnv"
    assert r.score < 1.0


def test_missing_key_fails():
    golden = {"id": 1, "tier1_success": True}
    r = _grade({"expected": golden}, _ctx(stdout='{"id": 1}'))
    assert r.passed is False
    assert r.details["missing"] == ["tier1_success"]


def test_extra_key_allowed_by_default_but_reported():
    golden = {"id": 1}
    actual = {"id": 1, "notes": "extra field"}
    r = _grade({"expected": golden}, _ctx(stdout=json.dumps(actual)))
    assert r.passed is True                 # allow_extra defaults True
    assert r.details["extra"] == ["notes"]


def test_extra_key_fails_when_not_allowed():
    golden = {"id": 1}
    actual = {"id": 1, "notes": "x"}
    r = _grade({"expected": golden, "allow_extra": False},
               _ctx(stdout=json.dumps(actual)))
    assert r.passed is False


def test_scalar_normalization_true_vs_1_and_numbers():
    golden = {"enabled": True, "width": 2}
    actual = {"enabled": 1, "width": "2"}
    r = _grade({"expected": golden}, _ctx(stdout=json.dumps(actual)))
    assert r.passed is True


def test_nested_dict_paths():
    golden = {"as_configured": {"CONFIG.C_GPIO_WIDTH": "2"}}
    actual = {"as_configured": {"CONFIG.C_GPIO_WIDTH": "4"}}
    r = _grade({"expected": golden}, _ctx(stdout=json.dumps(actual)))
    assert r.passed is False
    assert r.details["mismatches"][0]["path"] == "as_configured.CONFIG.C_GPIO_WIDTH"


def test_no_json_in_output_fails_gracefully():
    r = _grade({"expected": {"id": 1}}, _ctx(stdout="I could not produce JSON."))
    assert r.passed is False
    assert r.details["extracted"] is False


def test_extracts_from_claude_stream_json_final_message():
    # Final answer arrives as an assistant text block containing a fenced JSON.
    lines = [
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "working..."}]}}),
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text",
             "text": 'Done.\n```json\n{"id": 7, "ok": true}\n```'}]}}),
    ]
    r = _grade({"expected": {"id": 7, "ok": True}},
               _ctx(stdout="\n".join(lines)))
    assert r.passed is True


def test_artifact_source(tmp_path):
    (tmp_path / "outputs").mkdir()
    (tmp_path / "outputs" / "result.json").write_text('{"id": 3, "ok": true}')
    r = _grade({"expected": {"id": 3, "ok": True},
                "source": "artifact", "artifact": "outputs/result.json"},
               _ctx(workspace=tmp_path))
    assert r.passed is True


def test_vlnv_version_suffix_is_tolerated():
    # Golden family VLNV matches the agent's versioned VLNV.
    golden = {"vlnv": "xilinx.com:ip:axi_gpio"}
    actual = {"vlnv": "xilinx.com:ip:axi_gpio:2.0"}
    r = _grade({"expected": golden}, _ctx(stdout=json.dumps(actual)))
    assert r.passed is True


def test_vlnv_wrong_version_still_matches_family_but_plain_value_does_not():
    # Different family -> mismatch (not a colon-prefix).
    r = _grade({"expected": {"vlnv": "xilinx.com:ip:axi_gpio"}},
               _ctx(stdout=json.dumps({"vlnv": "xilinx.com:ip:axi_uartlite:2.0"})))
    assert r.passed is False
    # A plain (non-VLNV) value is NOT treated as a colon-prefix.
    r2 = _grade({"expected": {"port": "100"}},
                _ctx(stdout=json.dumps({"port": "100:5"})))
    assert r2.passed is False


def test_golden_null_is_dont_care_wildcard():
    # A golden null accepts any agent value for that field...
    golden = {"id": 1, "tier2_success": None}
    r = _grade({"expected": golden}, _ctx(stdout='{"id": 1, "tier2_success": true}'))
    assert r.passed is True
    assert r.details["matched"] == 2 and r.details["total"] == 2
    assert not r.details["mismatches"]
    # ...and also accepts the field being absent entirely.
    r2 = _grade({"expected": golden}, _ctx(stdout='{"id": 1}'))
    assert r2.passed is True
    assert not r2.details["missing"]


def test_golden_non_null_still_gates_even_alongside_a_wildcard():
    # tier2_success null is a wildcard, but tier1_success true is a hard gate.
    golden = {"tier1_success": True, "tier2_success": None}
    r = _grade({"expected": golden},
               _ctx(stdout='{"tier1_success": false, "tier2_success": true}'))
    assert r.passed is False
    assert [m["path"] for m in r.details["mismatches"]] == ["tier1_success"]


# ---- semantic (LLM-judged) fields ----------------------------------------

def test_semantic_field_passes_when_judge_scores_high():
    calls = []
    def judge(prompt):
        calls.append(prompt)
        return {"score": 88, "rationale": "same substance, different wording"}
    golden = {"id": 1, "notes": "2-bit all-outputs GPIO, PG144 grounded."}
    actual = {"id": 1, "notes": "Configured a two-bit output-only GPIO per PG144."}
    r = _grade({"expected": golden, "semantic_fields": ["notes"]},
               _ctx(stdout=json.dumps(actual), llm_caller=judge))
    assert r.passed is True
    assert len(calls) == 1                       # notes went through the judge
    assert r.details["semantic"][0]["path"] == "notes"
    assert r.details["semantic"][0]["passed"] is True
    assert r.details["semantic"][0]["score"] == 88


def test_semantic_field_fails_when_judge_scores_low():
    def judge(prompt):
        return {"score": 20, "rationale": "contradicts the width and direction"}
    golden = {"notes": "2-bit all-outputs GPIO."}
    actual = {"notes": "32-bit bidirectional GPIO."}
    r = _grade({"expected": golden, "semantic_fields": ["notes"]},
               _ctx(stdout=json.dumps(actual), llm_caller=judge))
    assert r.passed is False
    m = r.details["mismatches"][0]
    assert m["path"] == "notes" and m.get("semantic") is True
    assert "contradicts" in m["rationale"]


def test_semantic_field_intent_is_passed_into_the_prompt():
    seen = {}
    def judge(prompt):
        seen["prompt"] = prompt
        return {"score": 95, "rationale": "consistent"}
    intent = "Ignore execution narration; fail only on a factual contradiction."
    golden = {"notes": "2-bit all-outputs GPIO."}
    r = _grade({"expected": golden, "semantic_fields": {"notes": intent}},
               _ctx(stdout='{"notes": "did some steps on a 2-bit GPIO"}',
                    llm_caller=judge))
    assert r.passed is True
    assert intent in seen["prompt"]                    # field intent reached judge
    assert r.details["semantic"][0]["intent"] == intent


def test_semantic_default_intent_used_for_bare_list():
    seen = {}
    def judge(prompt):
        seen["prompt"] = prompt
        return {"score": 95, "rationale": "ok"}
    _grade({"expected": {"notes": "x"}, "semantic_fields": ["notes"]},
           _ctx(stdout='{"notes": "y"}', llm_caller=judge))
    assert "semantically consistent" in seen["prompt"]  # default intent text


def test_semantic_per_field_threshold_overrides_default():
    def judge(prompt):
        return {"score": 80, "rationale": "partial"}
    # Global default 70 would pass 80, but the per-field threshold of 90 fails.
    r = _grade({"expected": {"notes": "x"}, "semantic_threshold": 70,
                "semantic_fields": {"notes": {"intent": "check", "threshold": 90}}},
               _ctx(stdout='{"notes": "y"}', llm_caller=judge))
    assert r.passed is False


def test_semantic_threshold_is_configurable():
    def judge(prompt):
        return {"score": 75, "rationale": "mostly consistent"}
    golden = {"notes": "x"}
    # 75 clears default 70 but not a raised 90.
    assert _grade({"expected": golden, "semantic_fields": ["notes"]},
                  _ctx(stdout='{"notes": "y"}', llm_caller=judge)).passed is True
    assert _grade({"expected": golden, "semantic_fields": ["notes"],
                   "semantic_threshold": 90},
                  _ctx(stdout='{"notes": "y"}', llm_caller=judge)).passed is False


def test_semantic_field_not_gated_when_no_judge_configured():
    # No llm_caller -> the field is skipped (not gated), never a spurious fail.
    golden = {"notes": "2-bit all-outputs GPIO."}
    r = _grade({"expected": golden, "semantic_fields": ["notes"]},
               _ctx(stdout='{"notes": "totally different"}', llm_caller=None))
    assert r.passed is True
    assert r.details["semantic"][0]["skipped"] is True


def test_semantic_field_not_gated_when_judge_raises():
    def judge(prompt):
        raise RuntimeError("gateway down")
    golden = {"notes": "x"}
    r = _grade({"expected": golden, "semantic_fields": ["notes"]},
               _ctx(stdout='{"notes": "y"}', llm_caller=judge))
    assert r.passed is True
    assert r.details["semantic"][0]["skipped"] is True


def test_skill_outcome_fields_in_golden_are_compared():
    golden = {"id": 1, "tier1_success": True, "tier2_success": None,
              "self_fidelity": "full"}
    ok = {"id": 1, "tier1_success": True, "tier2_success": None,
          "self_fidelity": "Full", "notes": "whatever", "mcp_calls": 3}
    assert _grade({"expected": golden}, _ctx(stdout=json.dumps(ok))).passed is True
    # self_fidelity divergence is a real anomaly.
    bad = {"id": 1, "tier1_success": True, "tier2_success": None,
           "self_fidelity": "partial"}
    r = _grade({"expected": golden}, _ctx(stdout=json.dumps(bad)))
    assert r.passed is False
    assert r.details["mismatches"][0]["path"] == "self_fidelity"
