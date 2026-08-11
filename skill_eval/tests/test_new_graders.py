"""
Tests for the waza-derived graders: trigger, diff, action_sequence, program.

Contracts under test mirror waza's Go implementations:

    trigger          - trigger probability in [0,1] from the transcript;
                       positive/negative modes against a threshold.
    diff             - snapshot + contains checks; score = passed/total.
    action_sequence  - exact/in_order/any_order matching; score = F1.
    program          - external command; exit 0 -> pass, non-zero -> fail.
"""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from skills_testing.graders import (
    GRADER_REGISTRY,
    GraderContext,
    get_grader,
)


# -- registry ---------------------------------------------------------------


@pytest.mark.parametrize(
    "grader_type", ["trigger", "diff", "action_sequence", "program"]
)
def test_new_graders_registered(grader_type):
    assert grader_type in GRADER_REGISTRY
    assert callable(get_grader(grader_type).grade)


# -- helpers ----------------------------------------------------------------


def _stream(*messages: dict) -> str:
    """Render a list of stream-json envelopes to a stdout blob."""
    return "\n".join(json.dumps(m) for m in messages)


def _assistant(*blocks: dict) -> dict:
    return {"type": "assistant", "message": {"content": list(blocks)}}


def _tool_use(tid: str, name: str, **inp) -> dict:
    return {"type": "tool_use", "id": tid, "name": name, "input": inp}


@pytest.fixture
def ctx_factory(tmp_path):
    def _make(stdout="", stderr="", case_dir=None, run_meta=None):
        return GraderContext(
            workspace_dir=tmp_path,
            stdout=stdout,
            stderr=stderr,
            case_dir=case_dir,
            run_meta=run_meta or {
                "skill_name": "my-skill",
                "skill_version": "1.0",
                "case_id": "c",
            },
        )

    return _make


# -- trigger ----------------------------------------------------------------


class TestTrigger:
    def test_positive_fires_on_skill_tool_call(self, ctx_factory):
        stdout = _stream(_assistant(_tool_use("t1", "Skill", skill="my-skill")))
        ctx = ctx_factory(stdout=stdout)
        r = get_grader("trigger").grade(
            {"skill": "my-skill", "mode": "positive", "threshold": 0.5}, ctx
        )
        assert r.passed is True
        assert r.score == pytest.approx(1.0)
        assert r.details["trigger_probability"] == pytest.approx(1.0)

    def test_positive_fails_when_skill_dormant(self, ctx_factory):
        stdout = _stream(_assistant(_tool_use("t1", "Bash", command="ls")))
        ctx = ctx_factory(stdout=stdout)
        r = get_grader("trigger").grade({"skill": "my-skill"}, ctx)
        assert r.passed is False
        assert r.details["trigger_probability"] == pytest.approx(0.0)

    def test_negative_mode_passes_when_dormant(self, ctx_factory):
        stdout = _stream(_assistant(_tool_use("t1", "Bash", command="ls")))
        ctx = ctx_factory(stdout=stdout)
        r = get_grader("trigger").grade(
            {"skill": "my-skill", "mode": "negative", "threshold": 0.5}, ctx
        )
        assert r.passed is True
        # In negative mode, score is the complement of the probability.
        assert r.score == pytest.approx(1.0)

    def test_negative_mode_fails_when_activated(self, ctx_factory):
        stdout = _stream(_assistant(_tool_use("t1", "Skill", skill="my-skill")))
        ctx = ctx_factory(stdout=stdout)
        r = get_grader("trigger").grade({"mode": "negative"}, ctx)
        assert r.passed is False

    def test_skill_defaults_to_run_meta(self, ctx_factory):
        stdout = _stream(
            _assistant(
                _tool_use("t1", "Read", file_path="a/.claude/skills/my-skill/SKILL.md")
            )
        )
        ctx = ctx_factory(stdout=stdout)
        r = get_grader("trigger").grade({}, ctx)  # no 'skill' key
        assert r.details["skill"] == "my-skill"
        assert r.passed is True

    def test_invalid_mode_raises(self, ctx_factory):
        with pytest.raises(ValueError):
            get_grader("trigger").grade({"mode": "sideways"}, ctx_factory())

    def test_arm_aware_default_skill_arm(self, ctx_factory):
        # No explicit mode + with_skill=True -> positive: activation passes.
        stdout = _stream(_assistant(_tool_use("t1", "Skill", skill="my-skill")))
        ctx = ctx_factory(stdout=stdout, run_meta={
            "skill_name": "my-skill", "skill_version": "1.0",
            "case_id": "c", "with_skill": True})
        r = get_grader("trigger").grade({}, ctx)
        assert r.details["mode"] == "positive"
        assert r.passed is True

    def test_arm_aware_default_no_skill_arm(self, ctx_factory):
        # No explicit mode + with_skill=False -> negative: dormancy passes.
        stdout = _stream(_assistant(_tool_use("t1", "Bash", command="ls")))
        ctx = ctx_factory(stdout=stdout, run_meta={
            "skill_name": "my-skill", "skill_version": "1.0",
            "case_id": "c", "with_skill": False})
        r = get_grader("trigger").grade({}, ctx)
        assert r.details["mode"] == "negative"
        assert r.passed is True


# -- diff -------------------------------------------------------------------


class TestDiff:
    def test_contains_present_and_absent(self, ctx_factory, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("def new_feature():\n    pass\n")
        ctx = ctx_factory()
        r = get_grader("diff").grade(
            {
                "expected_files": [
                    {
                        "path": "src/main.py",
                        "contains": ["+def new_feature(", "-TODO: remove"],
                    }
                ]
            },
            ctx,
        )
        assert r.passed is True
        assert r.score == pytest.approx(1.0)

    def test_missing_fragment_fails_and_scores_partial(self, ctx_factory, tmp_path):
        (tmp_path / "f.txt").write_text("hello world\n")
        ctx = ctx_factory()
        r = get_grader("diff").grade(
            {
                "expected_files": [
                    {"path": "f.txt", "contains": ["+hello", "+goodbye"]}
                ]
            },
            ctx,
        )
        assert r.passed is False
        # existence(1) + hello(1) pass, goodbye(1) fails -> 2/3.
        assert r.score == pytest.approx(2 / 3)

    def test_absent_fragment_present_fails(self, ctx_factory, tmp_path):
        (tmp_path / "f.txt").write_text("secret = 1\n")
        ctx = ctx_factory()
        r = get_grader("diff").grade(
            {"expected_files": [{"path": "f.txt", "contains": ["-secret"]}]}, ctx
        )
        assert r.passed is False

    def test_missing_file_fails(self, ctx_factory):
        ctx = ctx_factory()
        r = get_grader("diff").grade(
            {"expected_files": [{"path": "nope.txt", "contains": ["+x"]}]}, ctx
        )
        assert r.passed is False
        assert any("not found" in f for f in r.details["failures"])

    def test_snapshot_exact_match(self, ctx_factory, tmp_path):
        case_dir = tmp_path / "case"
        case_dir.mkdir()
        (case_dir / "main.snap").write_text("line1\nline2\n")
        (tmp_path / "main.py").write_text("line1\nline2\n")
        ctx = ctx_factory(case_dir=case_dir)
        r = get_grader("diff").grade(
            {
                "context_dir": "case://",
                "expected_files": [{"path": "main.py", "snapshot": "main.snap"}],
            },
            ctx,
        )
        assert r.passed is True

    def test_snapshot_mismatch_fails(self, ctx_factory, tmp_path):
        case_dir = tmp_path / "case"
        case_dir.mkdir()
        (case_dir / "main.snap").write_text("expected\n")
        (tmp_path / "main.py").write_text("actual\n")
        ctx = ctx_factory(case_dir=case_dir)
        r = get_grader("diff").grade(
            {
                "context_dir": "case://",
                "expected_files": [{"path": "main.py", "snapshot": "main.snap"}],
            },
            ctx,
        )
        assert r.passed is False

    def test_update_snapshots_creates_missing(self, ctx_factory, tmp_path):
        case_dir = tmp_path / "case"
        case_dir.mkdir()
        (tmp_path / "main.py").write_text("fresh\n")
        ctx = ctx_factory(case_dir=case_dir)
        r = get_grader("diff").grade(
            {
                "context_dir": "case://",
                "update_snapshots": True,
                "expected_files": [{"path": "main.py", "snapshot": "new.snap"}],
            },
            ctx,
        )
        assert r.passed is True
        assert (case_dir / "new.snap").read_text() == "fresh\n"
        assert r.details["snapshot_updates"][0]["status"] == "created"

    def test_path_escape_raises(self, ctx_factory):
        with pytest.raises(ValueError):
            get_grader("diff").grade(
                {"expected_files": [{"path": "../escape.txt", "contains": ["+x"]}]},
                ctx_factory(),
            )

    def test_no_expected_files_raises(self, ctx_factory):
        with pytest.raises(ValueError):
            get_grader("diff").grade({"expected_files": []}, ctx_factory())

    def test_file_without_checks_raises(self, ctx_factory):
        with pytest.raises(ValueError):
            get_grader("diff").grade(
                {"expected_files": [{"path": "a.txt"}]}, ctx_factory()
            )


# -- action_sequence --------------------------------------------------------


class TestActionSequence:
    def test_exact_match(self, ctx_factory):
        stdout = _stream(
            _assistant(_tool_use("1", "Read")),
            _assistant(_tool_use("2", "Skill", skill="x")),
            _assistant(_tool_use("3", "Bash")),
        )
        ctx = ctx_factory(stdout=stdout)
        r = get_grader("action_sequence").grade(
            {"matching_mode": "exact_match",
             "expected_actions": ["Read", "Skill", "Bash"]},
            ctx,
        )
        assert r.passed is True
        assert r.score == pytest.approx(1.0)

    def test_exact_match_fails_on_extra(self, ctx_factory):
        stdout = _stream(
            _assistant(_tool_use("1", "Read")),
            _assistant(_tool_use("2", "Bash")),
            _assistant(_tool_use("3", "Bash")),
        )
        ctx = ctx_factory(stdout=stdout)
        r = get_grader("action_sequence").grade(
            {"matching_mode": "exact_match", "expected_actions": ["Read", "Bash"]},
            ctx,
        )
        assert r.passed is False

    def test_in_order_allows_extras(self, ctx_factory):
        stdout = _stream(
            _assistant(_tool_use("1", "Read")),
            _assistant(_tool_use("2", "Grep")),
            _assistant(_tool_use("3", "Bash")),
        )
        ctx = ctx_factory(stdout=stdout)
        r = get_grader("action_sequence").grade(
            {"matching_mode": "in_order_match", "expected_actions": ["Read", "Bash"]},
            ctx,
        )
        assert r.passed is True

    def test_in_order_respects_order(self, ctx_factory):
        stdout = _stream(
            _assistant(_tool_use("1", "Bash")),
            _assistant(_tool_use("2", "Read")),
        )
        ctx = ctx_factory(stdout=stdout)
        r = get_grader("action_sequence").grade(
            {"matching_mode": "in_order_match", "expected_actions": ["Read", "Bash"]},
            ctx,
        )
        assert r.passed is False

    def test_any_order(self, ctx_factory):
        stdout = _stream(
            _assistant(_tool_use("1", "Bash")),
            _assistant(_tool_use("2", "Read")),
        )
        ctx = ctx_factory(stdout=stdout)
        r = get_grader("action_sequence").grade(
            {"matching_mode": "any_order_match", "expected_actions": ["Read", "Bash"]},
            ctx,
        )
        assert r.passed is True

    def test_f1_partial_score(self, ctx_factory):
        # expected 2, actual has 1 match + 1 noise -> precision .5, recall .5, F1 .5
        stdout = _stream(
            _assistant(_tool_use("1", "Read")),
            _assistant(_tool_use("2", "Noise")),
        )
        ctx = ctx_factory(stdout=stdout)
        r = get_grader("action_sequence").grade(
            {"matching_mode": "exact_match", "expected_actions": ["Read", "Bash"]},
            ctx,
        )
        assert r.passed is False
        assert r.score == pytest.approx(0.5)

    def test_presence_match_all_present(self, ctx_factory):
        stdout = _stream(
            _assistant(_tool_use("1", "Read")),
            _assistant(_tool_use("2", "Bash")),
        )
        r = get_grader("action_sequence").grade(
            {"matching_mode": "presence_match", "expected_actions": ["Read", "Bash"]},
            ctx_factory(stdout=stdout),
        )
        assert r.passed is True
        assert r.score == pytest.approx(1.0)

    def test_presence_match_one_missing(self, ctx_factory):
        stdout = _stream(_assistant(_tool_use("1", "Read")))
        r = get_grader("action_sequence").grade(
            {"matching_mode": "presence_match", "expected_actions": ["Read", "Bash"]},
            ctx_factory(stdout=stdout),
        )
        assert r.passed is False
        assert r.score == pytest.approx(0.5)

    def test_presence_any_of_group_matched_by_command_alternative(self, ctx_factory):
        # Any-of group: "MCP execute OR a `vivado -mode batch` Bash call". Only
        # the Bash alternative is present, yet the group is satisfied.
        stdout = _stream(
            _assistant(_tool_use("1", "Bash",
                                 command="vivado -mode batch -source cfg.tcl")),
        )
        r = get_grader("action_sequence").grade(
            {"matching_mode": "presence_match",
             "expected_actions": [
                 ["mcp__vivado-mcp-server__vivado_execute",
                  "Bash: vivado -mode batch"]]},
            ctx_factory(stdout=stdout),
        )
        assert r.passed is True
        assert r.score == pytest.approx(1.0)

    def test_presence_any_of_group_matched_by_name_alternative(self, ctx_factory):
        stdout = _stream(
            _assistant(_tool_use("1", "mcp__vivado-mcp-server__vivado_execute",
                                 command="set_property ...")),
        )
        r = get_grader("action_sequence").grade(
            {"matching_mode": "presence_match",
             "expected_actions": [
                 ["mcp__vivado-mcp-server__vivado_execute",
                  "Bash: vivado -mode batch"]]},
            ctx_factory(stdout=stdout),
        )
        assert r.passed is True

    def test_presence_any_of_group_fails_when_no_alternative_present(self, ctx_factory):
        stdout = _stream(
            _assistant(_tool_use("1", "mcp__vivado-mcp-server__vivado_start")),
        )
        r = get_grader("action_sequence").grade(
            {"matching_mode": "presence_match",
             "expected_actions": [
                 ["mcp__vivado-mcp-server__vivado_execute",
                  "Bash: vivado -mode batch"]]},
            ctx_factory(stdout=stdout),
        )
        assert r.passed is False

    def test_any_of_group_rejected_in_non_presence_mode(self, ctx_factory):
        with pytest.raises(ValueError):
            get_grader("action_sequence").grade(
                {"matching_mode": "in_order_match",
                 "expected_actions": [["Read", "Bash"]]},
                ctx_factory(),
            )

    def test_no_expected_actions_raises(self, ctx_factory):
        with pytest.raises(ValueError):
            get_grader("action_sequence").grade({"expected_actions": []}, ctx_factory())

    def test_bare_string_expected_actions_raises_not_char_split(self, ctx_factory):
        """A bare string (e.g. an unresolved '{tool_sequence}' placeholder, or
        an author typing `tool_sequence: Read` without brackets) must raise a
        clear error, not silently explode into single-character "expected
        actions" via list(str) and grade against that garbage."""
        with pytest.raises(ValueError, match="must be a list"):
            get_grader("action_sequence").grade(
                {"expected_actions": "{tool_sequence}"}, ctx_factory())
        with pytest.raises(ValueError, match="must be a list"):
            get_grader("action_sequence").grade(
                {"tool_sequence": "Read"}, ctx_factory())

    def test_invalid_mode_raises(self, ctx_factory):
        with pytest.raises(ValueError):
            get_grader("action_sequence").grade(
                {"expected_actions": ["Read"], "matching_mode": "fuzzy"},
                ctx_factory(),
            )


class TestActionSequenceMcpServerAgnostic:
    """Tool-call matching is agnostic to which MCP server exposed the tool.

    Regression for run 6102c54a: claude_code reached ``vivado_doc_search``
    through the dedicated ``vivado-doc-search`` server while the spec (and
    opencode) named it under ``vivado-mcp-server``. Both must satisfy the
    same ``tool_sequence`` expectation.
    """

    # The exact spec from ip-configurator-test-kit test_cases.yaml.
    EXPECTED = [
        "mcp__vivado-mcp-server__vivado_doc_search",
        "mcp__vivado-mcp-server__vivado_execute",
    ]

    def _grade(self, ctx_factory, stdout):
        ctx = ctx_factory(stdout=stdout)
        return get_grader("action_sequence").grade(
            {"matching_mode": "any_order_match", "expected_actions": self.EXPECTED},
            ctx,
        )

    def test_doc_search_on_dedicated_server_matches(self, ctx_factory):
        # claude_code's actual routing: doc_search via vivado-doc-search.
        stdout = _stream(
            _assistant(_tool_use(
                "1", "mcp__vivado-doc-search__vivado_doc_search")),
            _assistant(_tool_use(
                "2", "mcp__vivado-mcp-server__vivado_execute")),
        )
        r = self._grade(ctx_factory, stdout)
        assert r.passed is True
        assert r.details["feedback"] == "Action sequence matched"
        # Raw names preserved for debugging; canonical shows what was compared.
        assert "mcp__vivado-doc-search__vivado_doc_search" in r.details[
            "actual_actions"]
        assert "mcp__vivado__vivado_doc_search" in r.details["canonical_actions"]
        assert r.details["canonical_expected"] == [
            "mcp__vivado__vivado_doc_search",
            "mcp__vivado__vivado_execute",
        ]

    def test_doc_search_on_unified_server_matches(self, ctx_factory):
        # opencode's actual routing: doc_search via vivado-mcp-server.
        stdout = _stream(
            _assistant(_tool_use(
                "1", "mcp__vivado-mcp-server__vivado_doc_search")),
            _assistant(_tool_use(
                "2", "mcp__vivado-mcp-server__vivado_execute")),
        )
        assert self._grade(ctx_factory, stdout).passed is True

    def test_missing_tool_still_fails(self, ctx_factory):
        # Aliasing must not paper over a genuinely absent tool: copilot never
        # called vivado_execute (nor doc_search) in run 6102c54a.
        stdout = _stream(_assistant(_tool_use("1", "Read", file_path="x.json")))
        r = self._grade(ctx_factory, stdout)
        assert r.passed is False

    def test_custom_alias_from_run_meta(self, ctx_factory):
        # A caller-supplied alias map (as wired from config) is honoured.
        stdout = _stream(
            _assistant(_tool_use("1", "mcp__acme-a__doit")),
            _assistant(_tool_use("2", "mcp__acme-b__doit")),
        )
        ctx = ctx_factory(stdout=stdout, run_meta={
            "skill_name": "s", "skill_version": "1", "case_id": "c",
            "mcp_server_aliases": {"acme-a": "acme", "acme-b": "acme"},
        })
        r = get_grader("action_sequence").grade(
            {"matching_mode": "any_order_match",
             "expected_actions": ["mcp__acme__doit", "mcp__acme__doit"]},
            ctx,
        )
        assert r.passed is True

    def test_command_bearing_entry_is_server_agnostic(self, ctx_factory):
        # `<tool>: <cmd>` entries canonicalize the tool half, keep the command.
        stdout = _stream(
            _assistant(_tool_use(
                "1", "mcp__vivado-doc-search__vivado_doc_search",
                query="axi gpio")),
        )
        ctx = ctx_factory(stdout=stdout)
        r = get_grader("action_sequence").grade(
            {"matching_mode": "any_order_match",
             "expected_actions": [
                 "mcp__vivado-mcp-server__vivado_doc_search: axi gpio"]},
            ctx,
        )
        assert r.passed is True


# -- opencode transcript format ---------------------------------------------


# A trimmed, real `opencode run --print-logs` stderr sample (tool display +
# logs go to stderr; the answer goes to stdout). ANSI codes preserved on the
# arrow line so the parser's stripping is exercised.
_OPENCODE_STDERR = (
    "timestamp=2026-06-19T10:55:05Z level=INFO message=loop step=0\n"
    "timestamp=2026-06-19T10:55:19Z level=INFO message=\"touching file\" "
    "file=/ws/.claude/skills/my-skill/SKILL.md\n"
    "\x1b[0m→ \x1b[0mRead .claude/skills/my-skill/SKILL.md\x1b[90m "
    "[offset=1, limit=200]\x1b[0m\n"
    "\x1b[0m→ \x1b[0mRead inputs/sample.cpp\x1b[0m\n"
    "timestamp=2026-06-19T10:55:21Z level=INFO message=\"exiting loop\"\n"
)


class TestOpencodeFormat:
    def test_tool_names_from_opencode_stderr(self, ctx_factory):
        ctx = ctx_factory(stdout="final answer", stderr=_OPENCODE_STDERR)
        r = get_grader("action_sequence").grade(
            {"matching_mode": "any_order_match", "expected_actions": ["Read"]}, ctx
        )
        assert r.passed is True
        assert r.details["actual_actions"] == ["Read", "Read"]

    def test_trigger_detects_skill_from_opencode(self, ctx_factory):
        ctx = ctx_factory(stdout="final answer", stderr=_OPENCODE_STDERR,
                          run_meta={"skill_name": "my-skill",
                                    "skill_version": "1.0", "case_id": "c"})
        r = get_grader("trigger").grade({"skill": "my-skill"}, ctx)
        assert r.passed is True
        assert r.details["trigger_probability"] >= 0.9


# -- program ----------------------------------------------------------------


def _write_script(path: Path, body: str) -> str:
    path.write_text("#!/usr/bin/env bash\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IRWXU)
    return str(path)


class TestProgram:
    def test_exit_zero_passes(self, ctx_factory, tmp_path):
        script = _write_script(tmp_path / "ok.sh", "exit 0\n")
        ctx = ctx_factory()
        r = get_grader("program").grade({"command": script}, ctx)
        assert r.passed is True
        assert r.score == pytest.approx(1.0)

    def test_exit_nonzero_fails(self, ctx_factory, tmp_path):
        script = _write_script(tmp_path / "bad.sh", "echo boom >&2\nexit 3\n")
        ctx = ctx_factory()
        r = get_grader("program").grade({"command": script}, ctx)
        assert r.passed is False
        assert r.score == pytest.approx(0.0)
        assert r.details["exit_code"] == 3
        assert "boom" in r.details["feedback"]

    def test_stdin_receives_agent_output(self, ctx_factory, tmp_path):
        # Fail unless the agent output contains "MAGIC".
        script = _write_script(
            tmp_path / "grep.sh", 'grep -q MAGIC && exit 0 || exit 1\n'
        )
        ctx = ctx_factory(stdout="here is the MAGIC token")
        r = get_grader("program").grade({"command": script}, ctx)
        assert r.passed is True

    def test_workspace_env_exposed(self, ctx_factory, tmp_path):
        script = _write_script(
            tmp_path / "env.sh",
            'test "$WAZA_WORKSPACE_DIR" = "$SKILL_TEST_WORKSPACE_DIR" '
            '&& test -n "$WAZA_WORKSPACE_DIR" && exit 0 || exit 1\n',
        )
        ctx = ctx_factory()
        r = get_grader("program").grade({"command": script}, ctx)
        assert r.passed is True

    def test_stdout_becomes_feedback(self, ctx_factory, tmp_path):
        script = _write_script(tmp_path / "say.sh", 'echo "all good"\nexit 0\n')
        ctx = ctx_factory()
        r = get_grader("program").grade({"command": script}, ctx)
        assert r.details["feedback"] == "all good"

    def test_timeout_fails(self, ctx_factory, tmp_path):
        script = _write_script(tmp_path / "slow.sh", "sleep 5\n")
        ctx = ctx_factory()
        r = get_grader("program").grade({"command": script, "timeout": 1}, ctx)
        assert r.passed is False
        assert "timed out" in r.details["feedback"]

    def test_missing_command_raises(self, ctx_factory):
        with pytest.raises(ValueError):
            get_grader("program").grade({}, ctx_factory())

    def test_nonexistent_binary_fails_gracefully(self, ctx_factory):
        ctx = ctx_factory()
        r = get_grader("program").grade(
            {"command": "/nonexistent/binary/xyz"}, ctx
        )
        assert r.passed is False
        assert "exit_error" in r.details

    def test_relative_command_resolves_against_case_dir(self, ctx_factory, tmp_path):
        case_dir = tmp_path / "case"
        case_dir.mkdir()
        graders_dir = case_dir / "graders"
        graders_dir.mkdir()
        _write_script(graders_dir / "check.sh", "exit 0\n")
        ctx = ctx_factory(case_dir=case_dir)
        r = get_grader("program").grade({"command": "graders/check.sh"}, ctx)
        assert r.passed is True
        assert r.details["resolved_command"] == str(graders_dir / "check.sh")
