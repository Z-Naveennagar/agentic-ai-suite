"""Backend-driven tool-call recovery in ``graders.trace``.

Covers the per-client dialect dispatch added so the ``action_sequence`` grader
recovers MCP calls regardless of which CLI backend produced the transcript --
in particular OpenCode's ⚙ gear-glyph MCP lines, which the arrow-only parser
used to drop -- and the canonical ``mcp__<server>__<tool>`` normalization that
makes a single ``tool_sequence`` value portable across backends.
"""

from __future__ import annotations

import json

from skills_testing.graders.trace import (
    DEFAULT_MCP_SERVER_ALIASES,
    canonical_mcp_name,
    extract_tool_calls,
    tool_names,
)


# A faithful slice of `opencode run --print-logs` stderr: built-in tools use the
# → arrow glyph, MCP tools use the ⚙ gear glyph rendered as "<server>_<tool>".
OPENCODE_STDERR = (
    "\x1b[2m00:01\x1b[0m → Read opencode.json\n"
    "→ Read .claude/skills/ip-configurator/SKILL.md\n"
    '⚙ vivado-mcp-server_vivado_start {"session_id":"vivado-1"}\n'
    '⚙ vivado-mcp-server_vivado_doc_search {"query":"axi_gpio"}\n'
    '⚙ vivado-doc-search_vivado_doc_search {"query":"axi_gpio"}\n'
    '⚙ vivado-mcp-server_vivado_execute {"session_id":"vivado-1","command":"create_bd_cell"}\n'
    "$ ls outputs\n"
    '⚙ vivado-mcp-server_vivado_stop {"session_id":"vivado-1"}\n'
)


def test_opencode_gear_glyph_mcp_calls_recovered():
    names = tool_names(OPENCODE_STDERR, client="opencode")
    # Built-ins still parsed from the → arrow lines and $ shell line.
    assert "Read" in names
    assert "Bash" in names
    # MCP calls (⚙) now recovered and normalized to canonical mcp__server__tool.
    assert "mcp__vivado-mcp-server__vivado_execute" in names
    assert "mcp__vivado-mcp-server__vivado_start" in names
    assert "mcp__vivado-mcp-server__vivado_stop" in names
    assert "mcp__vivado-mcp-server__vivado_doc_search" in names
    assert "mcp__vivado-doc-search__vivado_doc_search" in names
    # No raw un-normalized server_tool token leaks through.
    assert not any("_vivado_" in n and not n.startswith("mcp__") for n in names)


def test_opencode_stderr_passed_as_stdout_positional():
    # trace.extract_tool_calls(stdout, stderr): opencode dialect checks stderr
    # first, then stdout, so a transcript captured on either stream works.
    names = tool_names("", OPENCODE_STDERR, client="opencode")
    assert "mcp__vivado-mcp-server__vivado_execute" in names


def test_claude_code_mcp_names_already_canonical():
    line = json.dumps({
        "type": "assistant",
        "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Read",
             "input": {"file_path": "SKILL.md"}},
            {"type": "tool_use", "id": "t2",
             "name": "mcp__vivado-mcp-server__vivado_execute",
             "input": {"command": "create_bd_cell"}},
        ]},
    })
    names = tool_names(line, client="claude_code")
    assert names == ["Read", "mcp__vivado-mcp-server__vivado_execute"]


# A faithful slice of GitHub Copilot CLI stdout: bullet (●) lines for tool
# calls, MCP calls carrying a "(MCP: <server>)" annotation, a ✗ line for a
# failed MCP call, and the skill(<name>) form.
COPILOT_STDOUT = (
    "● List directory .claude/skills/ip-configurator\n"
    "● Read SKILL.md\n"
    "● skill(ip-configurator)\n"
    "● vivado_doc_search (MCP: vivado-mcp-server) · AXI GPIO width output\n"
    "✗ vivado_start (MCP: vivado-mcp-server) · working_dir: \"/tmp/p\"\n"
    "● vivado_execute (MCP: vivado-mcp-server) · source /tmp/config_gpio.tcl\n"
    "● Create output directory (shell)\n"
)


def test_copilot_mcp_annotation_lifted_to_canonical():
    names = tool_names(COPILOT_STDOUT, client="copilot")
    canon = [canonical_mcp_name(n) for n in names]
    # The (MCP: <server>) annotation is reconstructed into mcp__server__tool
    # and collapses to the vivado family.
    assert "mcp__vivado__vivado_execute" in canon
    assert "mcp__vivado__vivado_doc_search" in canon
    # A ✗-prefixed FAILED MCP call is still captured (correctness is judged
    # elsewhere); dropping it would misrepresent the sequence.
    assert "mcp__vivado__vivado_start" in canon
    # Built-ins and the skill call are still recovered.
    assert "Skill" in names
    assert "Read" in names
    assert "ListDirectory" in names


# A faithful slice of `agent -p --output-format stream-json` (Cursor). Tool
# calls are standalone tool_call envelopes (started/completed share call_id),
# NOT Anthropic tool_use blocks; MCP calls carry serverIdentifier/toolName.
CURSOR_STREAM = "\n".join(json.dumps(o) for o in [
    {"type": "system", "subtype": "init"},
    {"type": "tool_call", "subtype": "started", "call_id": "c1",
     "tool_call": {"shellToolCall": {"args": {"command": "ls -la"}}}},
    {"type": "tool_call", "subtype": "completed", "call_id": "c1",
     "tool_call": {"shellToolCall": {"args": {"command": "ls -la"},
                                     "result": {"success": {}}}}},
    {"type": "tool_call", "subtype": "completed", "call_id": "c2",
     "tool_call": {"mcpToolCall": {"args": {
         "serverIdentifier": "vivado-mcp-server",
         "toolName": "vivado_execute",
         "args": {"command": "set_property CONFIG.C_GPIO_WIDTH 2 [get_bd_cells x]"}}}}},
    {"type": "result", "subtype": "success",
     "usage": {"inputTokens": 10, "outputTokens": 5}},
])


def test_cursor_stream_json_tool_calls_recovered():
    names = tool_names(CURSOR_STREAM, client="cursor")
    # Shell tool -> Bash, deduplicated across the started/completed pair.
    assert names.count("Bash") == 1
    # MCP call lifted to canonical identity.
    assert canonical_mcp_name(
        "mcp__vivado-mcp-server__vivado_execute") == "mcp__vivado__vivado_execute"
    assert "mcp__vivado-mcp-server__vivado_execute" in names


def test_cursor_legacy_single_result_doc_yields_no_tools():
    # The old --output-format json single-doc payload carries no tool events;
    # extraction must simply be empty (not error).
    doc = json.dumps({"type": "result", "subtype": "success",
                      "result": "done", "usage": {"inputTokens": 1}})
    assert tool_names(doc, client="cursor") == []


def test_unknown_client_falls_back_to_autodetect():
    # client=None must preserve the pre-change auto-detect behavior: the
    # opencode gear/arrow lines are still recovered via the fallback chain.
    names_none = tool_names(OPENCODE_STDERR)
    names_unknown = tool_names(OPENCODE_STDERR, client="does-not-exist")
    assert names_none == names_unknown
    assert "mcp__vivado-mcp-server__vivado_execute" in names_none


def test_mcp_canonical_name_has_no_colon():
    # The canonical form must not contain ':' or it would collide with the
    # "<tool>: <command>" command-pattern syntax in action_sequence.
    for c in extract_tool_calls(OPENCODE_STDERR, client="opencode"):
        assert ":" not in c.name


# -- server-family canonicalization (backend/deployment-agnostic matching) --


def test_both_vivado_servers_canonicalize_to_one_family():
    # The same logical tool reached via either server maps to one identity.
    a = canonical_mcp_name("mcp__vivado-mcp-server__vivado_doc_search")
    b = canonical_mcp_name("mcp__vivado-doc-search__vivado_doc_search")
    assert a == b == "mcp__vivado__vivado_doc_search"


def test_canonical_preserves_tool_and_distinguishes_tools():
    # Different tools on the same family stay distinct.
    assert (canonical_mcp_name("mcp__vivado-mcp-server__vivado_execute")
            != canonical_mcp_name("mcp__vivado-mcp-server__vivado_doc_search"))


def test_non_mcp_and_unknown_server_pass_through_unchanged():
    assert canonical_mcp_name("Read") == "Read"
    assert canonical_mcp_name("Bash") == "Bash"
    # A server with no alias entry is left as-is (no accidental collapse).
    assert (canonical_mcp_name("mcp__other-server__foo")
            == "mcp__other-server__foo")


def test_custom_alias_map_overrides_default():
    aliases = {"srv-x": "fam", "srv-y": "fam"}
    assert (canonical_mcp_name("mcp__srv-x__t", aliases)
            == canonical_mcp_name("mcp__srv-y__t", aliases)
            == "mcp__fam__t")
    # Default map is untouched by passing a custom one.
    assert DEFAULT_MCP_SERVER_ALIASES["vivado-doc-search"] == "vivado"
