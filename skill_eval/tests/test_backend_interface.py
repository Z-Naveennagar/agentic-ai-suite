"""Contract tests for cli_backends.interface.SkillBackend.

These pin the promises the runner relies on rather than any one backend's
parsing: that every registered backend really implements the interface, that
``invoke`` always returns the complete result dict (including the stand-in),
and that the token-stat fallback chain resolves in the documented order.
"""

from __future__ import annotations

import pytest

from skills_testing.cli_backends import list_clients
from skills_testing.cli_backends.base import NullSkillCLI, SkillCLIBackend
from skills_testing.cli_backends.interface import (
    InvokeResult,
    SkillBackend,
    TokenUsage,
)


# The keys the runner and db_writer index off an invocation result.
_RESULT_KEYS = {
    "stdout", "stderr", "exit_code", "wall_clock_s",
    "prompt_tokens", "output_tokens", "total_tokens",
    "cache_read_tokens", "cache_write_tokens",
    "vivado_session_ids", "tool_timeline", "final_response",
}


# ---- every registered backend implements the interface -----------------


def test_all_registered_backends_implement_the_interface():
    from skills_testing.cli_backends import _ensure_registry, _REGISTRY
    _ensure_registry()
    assert _REGISTRY, "no backends registered"
    for name, cls in _REGISTRY.items():
        assert issubclass(cls, SkillBackend), name
        assert issubclass(cls, SkillCLIBackend), name
        # Identity attrs must be readable off the CLASS: the workspace is
        # staged and transcripts are graded on hosts with no CLI binary,
        # where no instance can be built.
        assert cls.name == name
        assert isinstance(cls.transcript_format, str)
        assert isinstance(cls.workspace_skills_dir, str)


def test_null_backend_implements_the_interface():
    assert issubclass(NullSkillCLI, SkillBackend)


# ---- the stand-in honours the same result contract ---------------------


def test_null_backend_returns_a_complete_result_dict(tmp_path):
    cli = NullSkillCLI("nosuch", "m", reason="binary not found")
    result = cli.invoke(prompt="p", workspace_dir=tmp_path, timeout_seconds=1)
    assert set(result) == _RESULT_KEYS
    assert result["exit_code"] == 127
    assert "binary not found" in result["stderr"]
    assert result["vivado_session_ids"] == []
    assert result["tool_timeline"] == []


def test_null_backend_reports_unavailable():
    cli = NullSkillCLI("nosuch", "m", reason="binary not found")
    assert cli.is_available is False
    assert cli.unavailable_reason == "binary not found"
    assert cli.detect_skill_invocation("", "") == (False, [])
    assert cli.hide_skills_env_overrides() is None


# ---- token statistics --------------------------------------------------


class _Backend(SkillBackend):
    """Minimal interface implementation; ``parse_token_usage`` is swapped
    per-test to exercise the fallback chain."""

    name = "probe"

    def invoke(self, *, prompt, workspace_dir, timeout_seconds, env=None):
        return InvokeResult(stdout="", stderr="", exit_code=0,
                            wall_clock_s=0.0).as_dict()


def test_token_usage_prefers_the_backend_parser():
    class Parsed(_Backend):
        def parse_token_usage(self, stdout, stderr):
            return TokenUsage(input=7, output=3, cache_read=1, cache_write=2)

    usage = Parsed().token_usage('{"input_tokens": 999, "output_tokens": 999}', "")
    assert usage.as_dict() == {"input": 7, "output": 3,
                               "cache_read": 1, "cache_write": 2}
    assert usage.total == 10          # live tokens only, cache excluded
    assert usage.estimated is False


@pytest.mark.parametrize("parsed", [None, TokenUsage()])
def test_token_usage_falls_back_to_the_generic_envelope(parsed):
    """A parser that finds nothing (None or an all-zero usage) hands off to
    the shared regex sweep rather than reporting zeros."""

    class NoSignal(_Backend):
        def parse_token_usage(self, stdout, stderr):
            return parsed

    usage = NoSignal().token_usage(
        'noise {"input_tokens": 40, "output_tokens": 12} noise', "")
    assert usage.as_tuple() == (40, 12)
    assert usage.estimated is False


def test_token_usage_falls_back_to_the_char_estimate():
    usage = _Backend().token_usage("x" * 700, "")
    assert usage.estimated is True
    assert usage.input == 175         # len / 4
    assert usage.output == 100        # len / 7


def test_generic_envelope_accepts_the_prompt_tokens_spelling():
    usage = _Backend().token_usage(
        '{"prompt_tokens": 5, "completion_tokens": 6}', "")
    assert usage.as_tuple() == (5, 6)


def test_invoke_result_from_usage_derives_total_and_splits_cache():
    result = InvokeResult.from_usage(
        stdout="o", stderr="e", exit_code=0, wall_clock_s=1.5,
        usage=TokenUsage(input=10, output=4, cache_read=99, cache_write=7),
    ).as_dict()
    assert result["total_tokens"] == 14      # cache traffic billed separately
    assert result["cache_read_tokens"] == 99
    assert result["cache_write_tokens"] == 7
    assert set(result) == _RESULT_KEYS


# ---- shared defaults ---------------------------------------------------


def test_default_detect_skill_invocation_finds_names_and_markers():
    backend = _Backend()
    invoked, names = backend.detect_skill_invocation(
        "Read .opencode/skills/hls-dataflow/SKILL.md", "")
    assert invoked is True
    assert names == ["hls-dataflow"]
    assert backend.detect_skill_invocation("nothing here", "") == (False, [])


def test_default_extract_vivado_session_ids_dedupes_and_sorts():
    ids = _Backend().extract_vivado_session_ids(
        '{"session_id": "vivado-20260731-103759"} '
        'session_id=vivado-20260731-090000 '
        '{"session_id": "vivado-20260731-103759"}', "")
    assert ids == ["vivado-20260731-090000", "vivado-20260731-103759"]


def test_default_extract_vivado_session_ids_ignores_foreign_uuid_session_id():
    # Regression test: a CLI backend (e.g. Cursor) may stamp its own
    # unrelated session_id (a bare UUID identifying the CLI's own
    # conversation, not any Vivado session) on every transcript event. That
    # UUID contains digits too, so a plain "contains a digit" check would
    # mistake it for a real Vivado session id -- and since ids are sorted
    # before a sort-then-take-first pick, a UUID starting with a digit
    # (e.g. "399c...") would win over the real "vivado-..." one.
    ids = _Backend().extract_vivado_session_ids(
        '{"session_id":"399c9ad3-655a-45c4-ac84-a8483c748cd2","type":"system"} '
        '{"session_id":"vivado-20260802-034941","command":"..."}', "")
    assert ids == ["vivado-20260802-034941"]


def test_default_extract_vivado_session_ids_ignores_keyword_values():
    # vivado_history accepts session_id="all" to mean "every session", not a
    # real one -- a bare word with no digit should never be mistaken for the
    # actual live session (e.g. "vivado-20260731-103759") mentioned elsewhere
    # in the same transcript. Regression test for a run where this caused the
    # scraped "all" to win a sort-then-take-first pick over the real id.
    ids = _Backend().extract_vivado_session_ids(
        '{"session_id":"all","search_query":"clk_wizard"} '
        '{"session_id":"vivado-20260731-103759","command":"..."}', "")
    assert ids == ["vivado-20260731-103759"]


def test_default_extract_vivado_session_ids_ignores_truncated_stream_chunks():
    # Regression test: streaming CLI backends (Claude Code's stream-json
    # output) emit the model's own output text as many incremental
    # "partial_json"/text-delta chunks, so a session id the model quotes in
    # its answer can arrive split across transcript lines. A mid-stream
    # fragment like "vivado-20260" used to pass the old "starts with
    # vivado-<digit>" check and, being a prefix of the full id, would sort
    # before it and win a sort-then-take-first pick -- silently handing a
    # dead session id to the next lifecycle step. Only the full
    # vivado-<8 digits>-<6 digits> shape should be accepted.
    ids = _Backend().extract_vivado_session_ids(
        '{"type":"input_json_delta","partial_json":". Shared block design, '
        'session_id vivado-20260"} '
        '{"session_id":"vivado-20260803-131158","command":"..."}', "")
    assert ids == ["vivado-20260803-131158"]


def test_default_preflight_skip_is_a_noop(tmp_path):
    assert _Backend().preflight_skip(
        prompt="hi", workspace_dir=tmp_path, timeout_seconds=60) is None


def test_interface_requires_invoke():
    class Incomplete(SkillBackend):
        name = "incomplete"

    with pytest.raises(TypeError):
        Incomplete()
