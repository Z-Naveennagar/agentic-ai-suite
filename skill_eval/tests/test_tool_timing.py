"""Unit tests for cli_backends.tool_timing.build_tool_timeline."""
from __future__ import annotations

import json

from skills_testing.cli_backends.tool_timing import build_tool_timeline


def _stamp(pairs):
    """[(offset, line), ...] -> the Stamped shape the builder consumes."""
    return list(pairs)


def test_skill_activation_is_tagged_with_kind_and_name():
    # The `→ Skill "x"` line (and Claude's tool_use name:"Skill") is tagged as
    # a distinct skill-trigger event so the dashboard can explain the chain.
    stderr = _stamp([
        (0.5, '\x1b[0m→ \x1b[0mSkill "ip-configurator"'),
        (1.0, '\x1b[0m⚙ \x1b[0mvivado-mcp-server_vivado_execute {"command":"x"}'),
    ])
    tl = build_tool_timeline([], stderr, transcript_format="opencode_logs",
                             total_wall_s=5.0)
    assert tl[0]["kind"] == "skill"
    assert tl[0]["skill"] == "ip-configurator"
    assert tl[1]["kind"] == "tool"

    # Claude stream-json: name "Skill" with a command arg.
    lines = [(0.0, json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "s", "name": "Skill",
         "input": {"command": "hls-dataflow"}}]}}))]
    tl2 = build_tool_timeline(lines, [],
                              transcript_format="anthropic_stream_json",
                              total_wall_s=1.0)
    assert tl2[0]["kind"] == "skill"
    assert tl2[0]["skill"] == "hls-dataflow"

    # Claude Skill tool with a JSON-object input carrying a "skill" key.
    lines2 = [(0.0, json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "s", "name": "Skill",
         "input": {"skill": "ip-configurator", "args": "configure X"}}]}}))]
    tl3 = build_tool_timeline(lines2, [],
                              transcript_format="anthropic_stream_json",
                              total_wall_s=1.0)
    assert tl3[0]["kind"] == "skill"
    assert tl3[0]["skill"] == "ip-configurator"


def test_opencode_timeline_order_and_gap_filled_durations():
    # opencode prints one glyph line per tool call, no explicit end marker;
    # each call's duration is the gap to the next call, last -> end-of-run.
    stderr = _stamp([
        (1.0, '\x1b[0m→ \x1b[0mSkill "ip-configurator"'),
        (3.0, '\x1b[0m⚙ \x1b[0mvivado-mcp-server_vivado_execute {"command":"foo"}'),
        (9.0, '\x1b[0m⚙ \x1b[0mvivado-mcp-server_vivado_status {"session_id":"s"}'),
    ])
    tl = build_tool_timeline([], stderr, transcript_format="opencode_logs",
                             total_wall_s=12.0)
    assert [e["name"] for e in tl] == [
        "Skill",
        "mcp__vivado-mcp-server__vivado_execute",
        "mcp__vivado-mcp-server__vivado_status",
    ]
    assert [e["seq"] for e in tl] == [1, 2, 3]
    # gap-filled: 3-1, 9-3, then 12-9 (to end-of-run).
    assert [round(e["duration_s"], 1) for e in tl] == [2.0, 6.0, 3.0]
    assert tl[0]["t_start"] == 1.0


def test_stream_json_timeline_exact_durations_from_tool_result_pairing():
    lines = [
        (0.5, json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Bash",
             "input": {"command": "ls"}}]}})),
        (2.5, json.dumps({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]}})),
        (3.0, json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t2",
             "name": "mcp__vivado-mcp-server__vivado_execute",
             "input": {"command": "synth"}}]}})),
        (11.0, json.dumps({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t2", "content": "done"}]}})),
    ]
    tl = build_tool_timeline(lines, [],
                             transcript_format="anthropic_stream_json",
                             total_wall_s=12.0)
    assert [e["name"] for e in tl] == [
        "Bash", "mcp__vivado-mcp-server__vivado_execute"]
    # Exact: result_offset - use_offset (NOT the gap to the next call).
    assert [round(e["duration_s"], 1) for e in tl] == [2.0, 8.0]
    assert tl[0]["args"] == "command=ls"


def test_stream_json_captures_per_call_tokens_error_and_result_size():
    lines = [
        (0.5, json.dumps({"type": "assistant", "message": {
            "usage": {"input_tokens": 1200, "output_tokens": 48,
                      "cache_read_input_tokens": 800},
            "content": [{"type": "tool_use", "id": "t1", "name": "Bash",
                         "input": {"command": "ls"}}]}})),
        (1.0, json.dumps({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1",
             "is_error": True, "content": "boom error output"}]}})),
    ]
    tl = build_tool_timeline(lines, [],
                             transcript_format="anthropic_stream_json",
                             total_wall_s=2.0)
    e = tl[0]
    assert e["tokens_in"] == 1200
    assert e["tokens_out"] == 48
    assert e["cache_read"] == 800
    assert e["is_error"] is True
    assert e["result_chars"] == len("boom error output")


def test_stream_json_final_tokens_come_from_message_delta():
    # Claude Code with --include-partial-messages: the assistant envelope holds
    # only the INITIAL usage (output_tokens ~2); the real total lands in a
    # later message_delta. Tool-result may arrive before OR after the delta.
    lines = [
        (0.1, json.dumps({"type": "stream_event", "event": {
            "type": "message_start", "message": {"usage": {
                "input_tokens": 2, "output_tokens": 2,
                "cache_read_input_tokens": 24000,
                "cache_creation_input_tokens": 9000}}}})),
        (0.5, json.dumps({"type": "assistant", "message": {
            "usage": {"input_tokens": 2, "output_tokens": 2,
                      "cache_read_input_tokens": 24000,
                      "cache_creation_input_tokens": 9000},
            "content": [{"type": "tool_use", "id": "t1", "name": "Bash",
                         "input": {"command": "ls"}}]}})),
        (0.6, json.dumps({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]}})),
        (0.9, json.dumps({"type": "stream_event", "event": {
            "type": "message_delta", "usage": {
                "input_tokens": 2, "output_tokens": 341,
                "cache_read_input_tokens": 24000,
                "cache_creation_input_tokens": 9000}}})),
    ]
    tl = build_tool_timeline(lines, [],
                             transcript_format="anthropic_stream_json",
                             total_wall_s=2.0)
    assert len(tl) == 1
    e = tl[0]
    assert e["tokens_out"] == 341          # final, NOT the initial 2
    assert e["tokens_in"] == 2
    assert e["cache_read"] == 24000
    assert e["cache_write"] == 9000


def test_stream_json_duplicate_assistant_envelope_not_double_counted():
    env = {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "dup", "name": "Read", "input": {}}]}}
    tl = build_tool_timeline([(0.1, json.dumps(env)), (0.2, json.dumps(env))],
                             [], transcript_format="anthropic_stream_json",
                             total_wall_s=1.0)
    assert len(tl) == 1


def test_stream_json_unclosed_call_falls_back_to_gap():
    # A tool_use with no matching tool_result uses the next-call gap, and the
    # very last unclosed call runs to total_wall_s.
    lines = [
        (1.0, json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "a", "name": "Read", "input": {}}]}})),
        (4.0, json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "b", "name": "Write", "input": {}}]}})),
    ]
    tl = build_tool_timeline(lines, [],
                             transcript_format="anthropic_stream_json",
                             total_wall_s=10.0)
    assert [round(e["duration_s"], 1) for e in tl] == [3.0, 6.0]


def test_cursor_started_completed_pair_gives_exact_duration():
    lines = [
        (0.0, json.dumps({"type": "tool_call", "subtype": "started",
                          "call_id": "c1", "tool_call": {
                              "shellToolCall": {"args": {"command": "echo hi"}}}})),
        (1.5, json.dumps({"type": "tool_call", "subtype": "completed",
                          "call_id": "c1", "tool_call": {
                              "shellToolCall": {"args": {"command": "echo hi"}}}})),
    ]
    tl = build_tool_timeline(lines, [], transcript_format="cursor_json",
                             total_wall_s=5.0)
    assert len(tl) == 1
    assert tl[0]["name"] == "Bash"
    assert round(tl[0]["duration_s"], 1) == 1.5


def test_empty_transcript_yields_empty_timeline():
    assert build_tool_timeline([], [], transcript_format="opencode_logs") == []


def test_unknown_format_autodetects_stream_json():
    lines = [
        (1.0, json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "x", "name": "Bash", "input": {}}]}})),
    ]
    tl = build_tool_timeline(lines, [], client="mystery", total_wall_s=2.0)
    assert [e["name"] for e in tl] == ["Bash"]


# ---- streaming capture in SkillCLIBackend.invoke (real subprocess) --------

import sys  # noqa: E402
import textwrap  # noqa: E402
from pathlib import Path  # noqa: E402

from skills_testing.cli_backends.base import SkillCLIBackend  # noqa: E402


class _FakeStreamBackend(SkillCLIBackend):
    """Runs a python child emitting anthropic stream-json with real time gaps
    between tool_use and its tool_result, so invoke() timing is exercised."""
    name = "fake"
    transcript_format = "anthropic_stream_json"
    _CHILD = textwrap.dedent('''
        import json, time, sys
        def emit(o): print(json.dumps(o), flush=True)
        emit({"type":"assistant","message":{"content":[{"type":"tool_use","id":"t1","name":"Bash","input":{"command":"ls"}}]}})
        time.sleep(0.20)
        emit({"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t1","content":"ok"}]}})
        emit({"type":"assistant","message":{"content":[{"type":"tool_use","id":"t2","name":"Read","input":{"file_path":"x"}}]}})
        time.sleep(0.10)
        emit({"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"t2","content":"ok"}]}})
        sys.stderr.write("a log line\\n")
    ''')

    def build_command(self, prompt, workspace_dir):
        return [sys.executable, "-c", self._CHILD]

    def _default_binary_lookup(self):
        return sys.executable


def test_invoke_streams_output_and_builds_timeline(tmp_path):
    res = _FakeStreamBackend(model="m").invoke(
        prompt="p", workspace_dir=tmp_path, timeout_seconds=30)
    assert res["exit_code"] == 0
    assert res["stdout"].strip()            # full stdout preserved
    assert "a log line" in res["stderr"]    # stderr preserved
    tl = res["tool_timeline"]
    assert [e["name"] for e in tl] == ["Bash", "Read"]
    # Durations reflect the real inter-event gaps (>= the injected sleeps).
    assert tl[0]["duration_s"] >= 0.18
    assert tl[1]["duration_s"] >= 0.08


class _SleepBackend(SkillCLIBackend):
    name = "sleeper"

    def build_command(self, prompt, workspace_dir):
        return [sys.executable, "-c",
                "import time,sys; sys.stdout.write('started\\n'); "
                "sys.stdout.flush(); time.sleep(30)"]

    def _default_binary_lookup(self):
        return sys.executable


def test_invoke_timeout_still_kills_and_marks(tmp_path):
    res = _SleepBackend(model="m").invoke(
        prompt="p", workspace_dir=tmp_path, timeout_seconds=1)
    assert res["exit_code"] == 124
    assert "timed out after 1s" in res["stderr"]
    assert "started" in res["stdout"]   # partial output still captured


# ---- final response extraction (graders.trace.final_response_text) --------

from skills_testing.graders.trace import final_response_text  # noqa: E402


def test_final_response_plain_stdout_is_returned_verbatim():
    # opencode: stdout is already the final answer.
    assert final_response_text("The GPIO is configured.\n") == "The GPIO is configured."


def test_final_response_from_stream_json_last_assistant_text():
    so = "\n".join([
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "thinking out loud"},
            {"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}]}}),
        json.dumps({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]}}),
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "Done: applied CONFIG.X=1."}]}}),
    ])
    assert final_response_text(so, transcript_format="anthropic_stream_json") \
        == "Done: applied CONFIG.X=1."


def test_final_response_prefers_result_envelope():
    so = "\n".join([
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "interim"}]}}),
        json.dumps({"type": "result", "result": "FINAL ANSWER"}),
    ])
    assert final_response_text(so) == "FINAL ANSWER"
