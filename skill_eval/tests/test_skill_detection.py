"""Unit tests for SkillCLIBackend.detect_skill_invocation patterns.

These exercise the shared regexes directly (not a fake backend), so they
guard the real detection surface used to set ``skill_invoked``. The
opencode cases matter because opencode does NOT read a
``.claude/skills/.../SKILL.md`` path inline the way Claude Code does --
it loads a skill via a dedicated tool and logs the load / permission
grant. Before those markers were added, opencode runs were mis-recorded
as skill_invoked=0 even when a skill fired.
"""
from __future__ import annotations

from skills_testing.cli_backends.base import (
    _SKILL_INVOKE_PATTERNS,
    _SKILL_NAME_PATTERN,
)


def _detect(text: str):
    invoked = any(p.search(text) for p in _SKILL_INVOKE_PATTERNS)
    names = sorted({m.group(1) for m in _SKILL_NAME_PATTERN.finditer(text)})
    return invoked or bool(names), names


def test_claude_code_skill_path_detected():
    inv, names = _detect("Read .claude/skills/rtl-assistant/SKILL.md")
    assert inv is True
    assert names == ["rtl-assistant"]


def test_opencode_skill_path_detected():
    inv, names = _detect("Read .opencode/skills/ip-configurator/SKILL.md")
    assert inv is True
    assert names == ["ip-configurator"]


def test_opencode_loaded_skill_marker():
    inv, _ = _detect("timestamp INFO Loaded skill: hls-dataflow")
    assert inv is True


def test_opencode_skill_content_tag():
    inv, _ = _detect('<skill_content name="hls-burst-inference">')
    assert inv is True


def test_opencode_permission_skill_marker():
    inv, _ = _detect(
        "evaluated permission=skill pattern=hls-array-to-stream "
        "action.action=allow"
    )
    assert inv is True


def test_no_false_positive_on_plain_text():
    inv, names = _detect("just some ordinary log output, nothing skilled here")
    assert inv is False
    assert names == []
