"""
Tests for skills_testing.runtime.skill_hider - returns env overrides that suppress
agent-skill discovery for the without-skill A/B arm, per CLI backend.
"""

from __future__ import annotations

import os

from skills_testing.runtime.skill_hider import hide_skills_env, redirect_skills_env


def test_returns_dict_for_known_clis():
    for client in ("claude_code", "cursor", "copilot", "opencode", "goose", "qwen"):
        env = hide_skills_env(client)
        assert isinstance(env, dict)
        assert env, f"{client} should have at least one override"


def test_unknown_cli_returns_empty():
    assert hide_skills_env("unknown-cli-xyz") == {}


def test_overrides_redirect_skills_dir_to_empty_path():
    env = hide_skills_env("claude_code")
    # values should look like env-style strings, not None
    for k, v in env.items():
        assert isinstance(k, str)
        assert isinstance(v, str)


def test_apply_to_env_merges():
    env = hide_skills_env("claude_code")
    base = {"PATH": "/usr/bin"}
    merged = {**base, **env}
    assert merged["PATH"] == "/usr/bin"
    for k, v in env.items():
        assert merged[k] == v


def test_opencode_uses_real_disable_vars_not_fake_skills_dir():
    """Regression for the 2026-04 no-skill-arm bug.

    Earlier versions set ``OPENCODE_SKILLS_DIR`` / ``AGENT_SKILLS_DIR``
    for opencode, neither of which exist in the opencode binary (verified
    via ``strings $(which opencode) | grep OPENCODE_``).  Those were
    silent no-ops, so the no-skill arm could still pick up
    ``~/.claude/skills/``.  The real knobs are the two ``DISABLE_*``
    flags below; assert we use them instead.
    """
    env = hide_skills_env("opencode")
    assert env.get("OPENCODE_DISABLE_CLAUDE_CODE_SKILLS") == "1"
    assert env.get("OPENCODE_DISABLE_EXTERNAL_SKILLS") == "1"
    assert "OPENCODE_SKILLS_DIR" not in env
    assert "AGENT_SKILLS_DIR" not in env


def test_opencode_hide_does_not_disable_capabilities():
    """MCP, bash, project config, and the Claude Code prompt layer must
    all remain available in the no-skill arm.  Only skill discovery
    should be affected."""
    env = hide_skills_env("opencode")
    for forbidden in (
        "OPENCODE_DISABLE_DEFAULT_PLUGINS",
        "OPENCODE_DISABLE_CLAUDE_CODE",
        "OPENCODE_DISABLE_CLAUDE_CODE_PROMPT",
        "OPENCODE_DISABLE_PROJECT_CONFIG",
    ):
        assert forbidden not in env, (
            f"{forbidden} would disable capabilities beyond skills"
        )


def test_opencode_redirect_is_empty_because_cli_has_no_path_knob():
    """opencode exposes disable flags, not a SKILLS_DIR path.  The
    runner stages the workspace ``.claude/skills/`` tree and lets
    opencode's CWD walk find it; no env redirect is needed."""
    assert redirect_skills_env("opencode", "/example/some/skills") == {}


def test_redirect_for_path_based_clients_still_works():
    env = redirect_skills_env("claude_code", "/example/s")
    assert env, "path-based clients should still get an env redirect"
    assert all(v == "/example/s" for v in env.values())
