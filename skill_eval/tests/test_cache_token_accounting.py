"""
Tests for prompt-cache token accounting end-to-end:

  1. Cursor's camelCase usage block (inputTokens / outputTokens /
     cacheReadTokens / cacheWriteTokens) is parsed correctly.
  2. Claude Code's snake_case usage block including
     cache_read_input_tokens / cache_creation_input_tokens is parsed.
  3. cost_model.compute_cost prices cache reads at ~10% of input rate
     and cache writes at ~125% of input rate when explicit overrides
     aren't supplied in the rule.
  4. db_writer.write_skill_test_result persists the new columns.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest


# ----------------------- 1. Cursor parser -------------------------------


def test_cursor_parser_reads_camelCase_and_cache_tokens(monkeypatch):
    from skills_testing.cli_backends.cursor import CursorSkillCLI

    monkeypatch.setattr(CursorSkillCLI, "_default_binary_lookup",
                        lambda self: "/bin/true")
    cli = CursorSkillCLI(model="claude-4.6-sonnet-medium-thinking")

    stdout = json.dumps({
        "type": "result",
        "result": "pong",
        "usage": {
            "inputTokens": 12,
            "outputTokens": 7,
            "cacheReadTokens": 4321,
            "cacheWriteTokens": 1000,
        },
    })
    u = cli.token_usage(stdout, "").as_dict()
    assert u == {"input": 12, "output": 7,
                 "cache_read": 4321, "cache_write": 1000}

    # Live-token tuple form.
    pin, pout = cli.token_usage(stdout, "").as_tuple()
    assert (pin, pout) == (12, 7)

    # Deprecated pre-interface shims still answer for external callers.
    assert cli._parse_usage_extended(stdout, "") == u
    assert cli._parse_usage(stdout, "") == (12, 7)


def test_cursor_parser_falls_back_for_garbage_stdout(monkeypatch):
    from skills_testing.cli_backends.cursor import CursorSkillCLI

    monkeypatch.setattr(CursorSkillCLI, "_default_binary_lookup",
                        lambda self: "/bin/true")
    cli = CursorSkillCLI(model="anything")

    # No JSON, no "input_tokens" regex match -> char-count heuristic;
    # cache fields should be 0.
    stdout = "blah blah blah" * 100
    usage = cli.token_usage(stdout, "")
    u = usage.as_dict()
    assert u["cache_read"] == 0
    assert u["cache_write"] == 0
    assert u["input"] >= 0 and u["output"] >= 0
    # Heuristic numbers are labelled as such so callers can tell them apart
    # from a vendor-reported count.
    assert usage.estimated is True


# ----------------------- 2. Claude Code parser --------------------------


def test_claude_code_parser_reads_anthropic_cache_keys(monkeypatch):
    from skills_testing.cli_backends.claude_code import ClaudeCodeSkillCLI

    monkeypatch.setattr(ClaudeCodeSkillCLI, "_default_binary_lookup",
                        lambda self: "/bin/true")
    cli = ClaudeCodeSkillCLI(model="opus")

    # Two "message"-typed records: input + cache_read take max
    # (Anthropic's stream-json reissues the running message totals on
    # each chunk), output + cache_write are summed across deltas.
    stream = "\n".join([
        json.dumps({"type": "system", "subtype": "init"}),
        json.dumps({"type": "assistant_message",
                    "usage": {"input_tokens": 100,
                              "output_tokens": 25,
                              "cache_read_input_tokens": 5000,
                              "cache_creation_input_tokens": 800}}),
        json.dumps({"type": "assistant_message_delta",
                    "usage": {"input_tokens": 150,
                              "output_tokens": 30,
                              "cache_read_input_tokens": 5500,
                              "cache_creation_input_tokens": 900}}),
    ])
    u = cli.token_usage(stream, "").as_dict()
    assert u["output"] == 25 + 30
    assert u["input"] == 150          # max() for "message"-typed records
    assert u["cache_read"] == 5500    # max()
    assert u["cache_write"] == 900    # max()


# ----------------------- 2b. Copilot banner parser ----------------------


def test_copilot_parser_reads_text_mode_exit_banner(monkeypatch):
    """Copilot's text-mode exit banner is the only place input + cache
    tokens are exposed; --output-format json drops them."""
    from skills_testing.cli_backends.copilot import CopilotSkillCLI

    monkeypatch.setattr(CopilotSkillCLI, "_default_binary_lookup",
                        lambda self: "/bin/true")
    cli = CopilotSkillCLI(model="claude-haiku-4.5")

    stdout = (
        "pong\n"
        "\n"
        "Changes   +0 -0\n"
        "Requests  0.33 Premium (4s)\n"
        "Tokens    \u2191 38.2k \u2022 \u2193 53 \u2022 24.2k (cached)\n"
    )
    u = cli.token_usage(stdout, "").as_dict()
    # 38.2k -> 38_200 (banner uses ×10^3, not KiB).
    assert u["input"] == 38_200
    assert u["output"] == 53
    assert u["cache_read"] == 24_200
    # Copilot does not report cache writes -- always 0.
    assert u["cache_write"] == 0

    pin, pout = cli.token_usage(stdout, "").as_tuple()
    assert (pin, pout) == (38_200, 53)


def test_copilot_parser_handles_raw_integers_and_megasuffix(monkeypatch):
    from skills_testing.cli_backends.copilot import CopilotSkillCLI

    monkeypatch.setattr(CopilotSkillCLI, "_default_binary_lookup",
                        lambda self: "/bin/true")
    cli = CopilotSkillCLI(model="anything")

    stdout = "Tokens    \u2191 1234 \u2022 \u2193 7 \u2022 2.5M (cached)\n"
    u = cli.token_usage(stdout, "").as_dict()
    assert u == {"input": 1234, "output": 7,
                 "cache_read": 2_500_000, "cache_write": 0}


def test_copilot_parser_falls_back_when_banner_missing(monkeypatch):
    from skills_testing.cli_backends.copilot import CopilotSkillCLI

    monkeypatch.setattr(CopilotSkillCLI, "_default_binary_lookup",
                        lambda self: "/bin/true")
    cli = CopilotSkillCLI(model="anything")

    # No banner, no JSON -> char-count heuristic; cache fields zero.
    stdout = "just some plain output without any banner at all"
    u = cli.token_usage(stdout, "").as_dict()
    assert u["cache_read"] == 0 and u["cache_write"] == 0


# ----------------------- 3. cost_model pricing --------------------------


_TEST_PRICING = {
    "model_pricing": {
        "default_currency": "usd",
        "estimation_chars_per_token": 3.5,
        "hosted_gpu_hourly_usd": 1.50,
        "models": {
            "test-sonnet": {
                "input_per_mtok": 3.00,
                "output_per_mtok": 15.00,
                # No explicit cache rates -> defaults apply.
            },
            "test-haiku-with-overrides": {
                "input_per_mtok": 1.00,
                "output_per_mtok": 5.00,
                "cache_read_per_mtok": 0.08,
                "cache_write_per_mtok": 1.25,
            },
        },
    },
}


def test_cost_model_default_cache_rates():
    from skills_testing.core.cost_model import compute_cost

    # 1M input, 1M output, 10M cache reads, 1M cache writes
    cost, method = compute_cost(
        "test-sonnet",
        prompt_tokens=1_000_000,
        output_tokens=1_000_000,
        elapsed_s=1.0,
        cache_read_tokens=10_000_000,
        cache_write_tokens=1_000_000,
        config=_TEST_PRICING,
    )
    # input  : 1M * $3                 = $3.00
    # output : 1M * $15                = $15.00
    # cache R: 10M * ($3 * 0.10 = $0.30) = $3.00
    # cache W: 1M  * ($3 * 1.25 = $3.75) = $3.75
    # total                                = $24.75
    assert method == "api_priced_with_cache"
    assert cost == pytest.approx(24.75, rel=1e-9)


def test_cost_model_explicit_cache_overrides():
    from skills_testing.core.cost_model import compute_cost

    cost, method = compute_cost(
        "test-haiku-with-overrides",
        prompt_tokens=0,
        output_tokens=0,
        elapsed_s=1.0,
        cache_read_tokens=2_000_000,
        cache_write_tokens=1_000_000,
        config=_TEST_PRICING,
    )
    # cache R: 2M * $0.08 = $0.16
    # cache W: 1M * $1.25 = $1.25
    assert method == "api_priced_with_cache"
    assert cost == pytest.approx(0.16 + 1.25, rel=1e-9)


def test_cost_method_is_plain_api_priced_when_no_cache():
    from skills_testing.core.cost_model import compute_cost
    cost, method = compute_cost(
        "test-sonnet", prompt_tokens=1000, output_tokens=500,
        elapsed_s=1.0, config=_TEST_PRICING,
    )
    assert method == "api_priced"
    assert cost == pytest.approx(
        1000/1_000_000 * 3.0 + 500/1_000_000 * 15.0, rel=1e-9)


# ----------------------- 3b. pricing resolver robustness ----------------


def test_resolver_matches_gateway_qualified_id_case_insensitively():
    """amd-anthropic/Claude-Sonnet-4.5 must resolve the same row as
    claude-sonnet-4.5 -- differs only by provider prefix and case."""
    from skills_testing.core.cost_model import _resolve_pricing

    pricing = {"models": {
        "claude-sonnet-4.5": {"input_per_mtok": 3.0, "output_per_mtok": 15.0},
    }}
    rule = _resolve_pricing("amd-anthropic/Claude-Sonnet-4.5", pricing)
    assert rule == {"input_per_mtok": 3.0, "output_per_mtok": 15.0}


def test_resolver_applies_glob_to_bare_name():
    """A glob key like gpt-5.6-sol* must match a gateway-qualified id by
    matching the provider-stripped bare name, not the full id."""
    from skills_testing.core.cost_model import _resolve_pricing

    pricing = {"models": {
        "gpt-5.6-sol*": {"input_per_mtok": 5.0, "output_per_mtok": 30.0},
    }}
    rule = _resolve_pricing("amd-gateway/gpt-5.6-sol-high", pricing)
    assert rule == {"input_per_mtok": 5.0, "output_per_mtok": 30.0}


def test_resolver_returns_none_for_genuinely_unpriced_model():
    """A model absent from pricing.yaml under every candidate form must
    still fall through to None -- resolver leniency must not paper over a
    real gap."""
    from skills_testing.core.cost_model import _resolve_pricing

    pricing = {"models": {
        "claude-sonnet-4.5": {"input_per_mtok": 3.0, "output_per_mtok": 15.0},
    }}
    assert _resolve_pricing("amd-gateway/GPT-oss-20B", pricing) is None


def test_every_model_this_suite_runs_is_priced():
    """Guard against a repeat of the Opus 5 gap: every model id this
    benchmark actually invokes must resolve to a rate card, not fall
    through to the cloud_equivalent_amortized_unknown_model placeholder."""
    from skills_testing.core.cost_model import (
        _pricing_block, _resolve_pricing, load_config,
    )

    pricing = _pricing_block(load_config())
    models_in_use = [
        "claude-opus-5-thinking-high",
        "claude-opus-4-8-high",
        "claude-sonnet-5",
        "claude-fable-5",
        "composer-2.5", "composer-2.5-fast",
        "gpt-5.6-sol-high", "gpt-5.6-terra", "gpt-5.6-luna",
        "gemini-3.1-pro", "gemini-3.6-flash",
        "amd-anthropic/Claude-Sonnet-4.5",
    ]
    unpriced = [m for m in models_in_use if _resolve_pricing(m, pricing) is None]
    assert not unpriced, f"missing pricing.yaml rows for: {unpriced}"


def test_composer_fast_priced_above_standard():
    """composer-2.5-fast must be priced above composer-2.5 -- it was
    previously listed at the identical standard rate, a 6x undercount."""
    from skills_testing.core.cost_model import (
        _pricing_block, _resolve_pricing, load_config,
    )

    pricing = _pricing_block(load_config())
    standard = _resolve_pricing("composer-2.5", pricing)
    fast = _resolve_pricing("composer-2.5-fast", pricing)
    assert standard is not None and fast is not None
    assert fast["input_per_mtok"] > standard["input_per_mtok"]
    assert fast["output_per_mtok"] > standard["output_per_mtok"]


def test_no_invented_cache_write_fee_for_composer_and_gemini():
    """compute_cost defaults a missing cache_write_per_mtok to 125% of
    input, which is correct for Anthropic but invents a fee for providers
    that don't charge one. Composer and Gemini rows must pin it to 0.0
    explicitly rather than omit it."""
    from skills_testing.core.cost_model import (
        _pricing_block, _resolve_pricing, load_config,
    )

    pricing = _pricing_block(load_config())
    for model in ("composer-2.5", "composer-2.5-fast", "composer-2",
                  "composer-2-fast", "gemini-3-pro", "gemini-3-flash",
                  "gemini-3.1-pro", "gemini-3.6-flash"):
        rule = _resolve_pricing(model, pricing)
        assert rule is not None, model
        assert rule.get("cache_write_per_mtok") == 0.0, model


# ----------------------- 4. db_writer persistence -----------------------


def test_db_writer_persists_cache_token_columns(tmp_path: Path):
    from skills_testing.core import db_writer

    cfg = {"database": {"path": str(tmp_path / "results.db")}}
    conn = db_writer.init_db(cfg)
    rid = db_writer.create_run(conn, suite="cache_test")

    sid = db_writer.write_skill_test_result(conn, rid, {
        "skill_name": "demo", "skill_version": "1.0.0",
        "case_id": "c1", "client": "cursor",
        "model": "claude-4.6-sonnet-medium-thinking",
        "with_skill": True, "replication_index": 0,
        "skill_invoked": True, "wall_clock_s": 10.0,
        "prompt_tokens": 100, "output_tokens": 50,
        "total_tokens": 150,
        "cache_read_tokens": 12345, "cache_write_tokens": 678,
        "t2_score": 1.0, "aggregate_score": 1.0, "status": "PASS",
    })

    row = conn.execute(
        "SELECT cache_read_tokens, cache_write_tokens, cost_method "
        "FROM skill_test_results WHERE id=?", (sid,)
    ).fetchone()
    assert row[0] == 12345
    assert row[1] == 678
    # cost_method should reflect that cache traffic was priced.
    assert row[2] in ("api_priced_with_cache", "api_priced", None)
    conn.close()
