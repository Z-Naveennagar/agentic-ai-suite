"""
Transcript-parsing helpers shared by the ``trigger`` and ``action_sequence``
graders.

The CLI backends (claude_code, opencode, ...) emit a ``stream-json``
transcript on stdout: one JSON object per line. Tool invocations appear as
``tool_use`` content blocks inside ``assistant`` messages. These helpers
recover, in chronological order, the sequence of tool names the agent
actually called -- the Python analogue of waza's ``SessionDigest.ToolsUsed``
-- plus the evidence needed to decide whether a particular skill was
activated.

Everything here is best-effort and tolerant: malformed lines are skipped, and
a generic recursive fallback recovers tool calls from transcript shapes that
don't use the canonical ``assistant`` envelope.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolCall:
    """A single tool invocation recovered from the transcript."""

    name: str
    input: dict[str, Any] = field(default_factory=dict)
    id: Optional[str] = None


def _iter_json_lines(stdout: str):
    """Yield each parseable JSON object from a stream-json stdout blob.

    Tolerates non-JSON noise (banners, progress text) interleaved with the
    stream by skipping any line that does not parse as a JSON object.
    """
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict):
            yield obj


def _blocks_from_message(obj: dict) -> list[dict]:
    """Return the content-block list of an assistant message envelope."""
    msg = obj.get("message")
    if isinstance(msg, dict):
        content = msg.get("content")
        if isinstance(content, list):
            return [b for b in content if isinstance(b, dict)]
    # Some backends inline content at the top level.
    content = obj.get("content")
    if isinstance(content, list):
        return [b for b in content if isinstance(b, dict)]
    return []


def _generic_tool_use_walk(obj: Any, acc: list[ToolCall], seen: set[str]) -> None:
    """Recursively collect ``tool_use`` blocks from an arbitrary structure.

    Used as a fallback when no canonical ``assistant`` envelopes are present.
    Dedupes by tool-use ``id`` to avoid double-counting streaming deltas.
    """
    if isinstance(obj, dict):
        if obj.get("type") == "tool_use" and obj.get("name"):
            tid = obj.get("id")
            key = tid or f"_noid_{len(acc)}"
            if key not in seen:
                seen.add(key)
                acc.append(ToolCall(
                    name=str(obj["name"]),
                    input=obj.get("input") if isinstance(obj.get("input"), dict) else {},
                    id=tid,
                ))
        for v in obj.values():
            _generic_tool_use_walk(v, acc, seen)
    elif isinstance(obj, list):
        for v in obj:
            _generic_tool_use_walk(v, acc, seen)


# ---------------------------------------------------------------------------
# OpenCode transcript format.
#
# OpenCode (`opencode run ... --print-logs`) does not emit Anthropic
# stream-json. Tool invocations surface on stderr in two shapes:
#   * a human-readable arrow line:  "→ Read sample.cpp [offset=1, limit=200]"
#   * a structured log line:        'message="touching file" file=<path>'
# The arrow lines are the cleanest ordered signal, so we parse those and use
# the log lines only as a fallback hint.
# ---------------------------------------------------------------------------

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
# Glyphs OpenCode uses to prefix a tool invocation line. → ↳ ⤷ mark built-in
# tools (Read, Bash, ...); ⚙ ⚡ mark MCP / plugin tool calls, rendered as
# "⚙ <server>_<tool> {<json-args>}". The glyph is captured so MCP calls can be
# normalized to the canonical name (see _canonical_mcp / _opencode_mcp_name).
_OPENCODE_ARROW = re.compile(r"^([→↳⤷⚙⚡])\s*([A-Za-z][\w\-]*)\b")
_OPENCODE_MCP_GLYPHS = "⚙⚡"
# OpenCode renders the shell/bash tool differently from other tools: instead of
# a "→ Bash" arrow line it echoes the command with a "$ " prefix, e.g.
# "$ ls && mkdir -p outputs". Treat those as Bash tool calls.
_OPENCODE_SHELL = re.compile(r"^\$\s+(.+)")


# ---------------------------------------------------------------------------
# Canonical MCP tool naming.
#
# The same logical MCP call is spelled differently per backend:
#   Claude Code : mcp__<server>__<tool>   (canonical form — no ":" so it never
#                                           collides with the "<tool>: <cmd>"
#                                           command-pattern syntax)
#   OpenCode    : <server>_<tool>         (single "_" join; server keys use
#                                           hyphens, never underscores)
# We normalize every backend to the Claude Code form so a single tool_sequence
# value in test_cases.yaml matches regardless of which client ran the case.
# ---------------------------------------------------------------------------


def _canonical_mcp(server: str, tool: str) -> str:
    return f"mcp__{server}__{tool}"


# ---------------------------------------------------------------------------
# Server-family canonicalization (backend- AND deployment-agnostic matching).
#
# The canonical name form ``mcp__<server>__<tool>`` unifies how each backend
# *spells* an MCP call, but the ``<server>`` segment is still a deployment
# detail: the same logical tool can be reachable through more than one server.
# For example ``vivado_doc_search`` is exposed both by the unified local
# ``vivado-mcp-server`` and by the dedicated remote ``vivado-doc-search``
# server, and which one a given model routes through varies by backend/model.
# That must NOT change the tool's identity for grading.
#
# We collapse deployment-equivalent servers into a *family* and match on
# ``mcp__<family>__<tool>``. The default map covers the Vivado toolchain; it is
# overridable via config (``grading.mcp_server_aliases``) and merged over these
# defaults, so a call and a ``tool_sequence`` expectation match regardless of
# which server each happened to name.
# ---------------------------------------------------------------------------

DEFAULT_MCP_SERVER_ALIASES: dict[str, str] = {
    "vivado-mcp-server": "vivado",
    "vivado-doc-search": "vivado",
}

# ``mcp__<server>__<tool>`` -- server keys use hyphens, never the ``__``
# separator, so the split is unambiguous.
_MCP_NAME = re.compile(r"^mcp__(.+?)__(.+)$")


def canonical_mcp_name(
    name: str, aliases: Optional[dict[str, str]] = None,
) -> str:
    """Reduce an MCP tool name to its backend/deployment-agnostic identity.

    ``mcp__<server>__<tool>`` becomes ``mcp__<family>__<tool>`` where *family*
    is ``aliases[server]`` (falling back to
    :data:`DEFAULT_MCP_SERVER_ALIASES`). A server with no alias entry, and any
    non-MCP name (``Read``, ``Bash``, ``Skill``, ...), is returned unchanged.
    """
    m = _MCP_NAME.match(name or "")
    if not m:
        return name
    server, tool = m.group(1), m.group(2)
    table = DEFAULT_MCP_SERVER_ALIASES if aliases is None else aliases
    family = table.get(server, server)
    return _canonical_mcp(family, tool)


def _opencode_mcp_name(token: str) -> str:
    """Normalize an OpenCode MCP token ``<server>_<tool>`` to canonical form.

    OpenCode joins the MCP server key and tool name with a single underscore.
    Server keys use hyphens (e.g. ``vivado-mcp-server``, ``vivado-doc-search``)
    and never underscores, so the first ``_`` is the server/tool boundary.
    Tokens without an underscore are returned unchanged.
    """
    if "_" in token:
        server, tool = token.split("_", 1)
        return _canonical_mcp(server, tool)
    return token


def _is_skill_name(name: Any) -> bool:
    """A skill activation surfaces as a tool named ``Skill`` on every backend
    (opencode ``→ Skill "x"``, Claude ``tool_use name:"Skill"``) -- case
    varies by backend/version, so this check ignores it."""
    return str(name or "").strip().lower() == "skill"


def _clean_skill_label(args: Any) -> str:
    """Pull the bare skill name out of a skill call's raw args, e.g.
    ``"ip-configurator"``, ``command=ip-configurator``, or a JSON object like
    ``{"skill": "ip-configurator", ...}`` -> ``ip-configurator``."""
    s = str(args or "").strip()
    if s.startswith("{"):
        try:
            obj = json.loads(s)
        except (json.JSONDecodeError, ValueError):
            obj = None
        if isinstance(obj, dict):
            for k in ("skill", "name", "command"):
                if isinstance(obj.get(k), str) and obj[k].strip():
                    return obj[k].strip()
    if "=" in s and " " not in s.split("=", 1)[0]:
        s = s.split("=", 1)[1].strip()
    return s.strip().strip('"').strip("'").strip()


def _skill_invocation_target(call: "ToolCall") -> Optional[str]:
    """Return the invoked skill's name if *call* is a skill activation, else
    ``None``.

    Structured backends (Claude Code, generic) put the name directly in a
    dict key (``skill``/``name``/``command``). OpenCode instead flattens the
    whole call into one ``args`` string (see ``_opencode_tool_calls``), so it
    never populates those keys -- the ``args`` fallback below is what recovers
    the name for OpenCode specifically.
    """
    if not _is_skill_name(call.name):
        return None
    for key in ("skill", "name", "command"):
        val = call.input.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    args = call.input.get("args")
    if args:
        label = _clean_skill_label(args)
        if label:
            return label
    return None


def _opencode_tool_calls(text: str) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for raw in text.splitlines():
        line = _ANSI.sub("", raw).strip()
        if not line:
            continue
        m = _OPENCODE_ARROW.match(line)
        if m:
            glyph, name = m.group(1), m.group(2)
            # The remainder of the line is the tool's argument blob; keep it as
            # a single "args" string so SKILL.md-path detection works.
            rest = line[m.end():].strip()
            if glyph in _OPENCODE_MCP_GLYPHS:
                # MCP / plugin call: normalize "<server>_<tool>" -> canonical.
                name = _opencode_mcp_name(name)
            calls.append(ToolCall(name=name, input={"args": rest} if rest else {}))
            continue
        sh = _OPENCODE_SHELL.match(line)
        if sh:
            calls.append(ToolCall(name="Bash", input={"args": sh.group(1).strip()}))
    return calls


def _stream_json_calls(stdout: str) -> list[ToolCall]:
    """Anthropic stream-json ``assistant`` envelopes on stdout (Claude Code)."""
    calls: list[ToolCall] = []
    seen: set[str] = set()
    for obj in _iter_json_lines(stdout):
        if obj.get("type") != "assistant":
            continue
        for block in _blocks_from_message(obj):
            if block.get("type") != "tool_use" or not block.get("name"):
                continue
            tid = block.get("id")
            key = tid or f"_noid_{len(calls)}"
            if key in seen:
                continue
            seen.add(key)
            calls.append(ToolCall(
                name=str(block["name"]),
                input=block.get("input") if isinstance(block.get("input"), dict) else {},
                id=tid,
            ))
    return calls


def _generic_json_calls(stdout: str) -> list[ToolCall]:
    """Recursive walk for other JSON ``tool_use`` shapes (e.g. Cursor's doc)."""
    calls: list[ToolCall] = []
    seen: set[str] = set()
    for obj in _iter_json_lines(stdout):
        _generic_tool_use_walk(obj, calls, seen)
    return calls


# ---------------------------------------------------------------------------
# Cursor CLI stream-json (``agent -p --output-format stream-json``).
#
# Cursor does NOT emit Anthropic ``tool_use`` content blocks. Each tool call is
# a pair of standalone envelopes (``started`` then ``completed``) that share a
# ``call_id``::
#   {"type":"tool_call","subtype":"started","call_id":"...",
#    "tool_call":{"shellToolCall":{"args":{"command":"echo hi", ...}}}}
#   {"type":"tool_call","subtype":"completed","call_id":"...",
#    "tool_call":{"mcpToolCall":{"args":{"serverIdentifier":"vivado-mcp-server",
#                                        "toolName":"vivado_list_sessions",
#                                        "args":{...}}}}}
# The kind is the single ``<kind>ToolCall`` key. MCP calls carry
# ``serverIdentifier``/``toolName`` which we lift to ``mcp__<server>__<tool>``.
# (The older ``--output-format json`` produced a single ``type:result`` doc
# with no tool events at all, hence the historical empty extraction.)
# ---------------------------------------------------------------------------

_CURSOR_TOOL_KIND = {
    "shellToolCall": "Bash",
    "readToolCall": "Read",
    "writeToolCall": "Write",
    "editToolCall": "Edit",
    "lsToolCall": "ListDirectory",
    "globToolCall": "Glob",
    "grepToolCall": "Grep",
    "searchToolCall": "Grep",
    "todoToolCall": "TodoWrite",
}


def _cursor_stream_calls(stdout: str) -> list[ToolCall]:
    """Recover ordered tool calls from Cursor's stream-json ``tool_call`` events.

    Deduplicates the ``started``/``completed`` pair by ``call_id`` (keeping the
    first, so call order is preserved) and maps each ``<kind>ToolCall`` to a
    tool name, lifting ``mcpToolCall`` to its ``mcp__<server>__<tool>`` identity.
    """
    calls: list[ToolCall] = []
    seen: set[str] = set()
    for obj in _iter_json_lines(stdout):
        if obj.get("type") != "tool_call":
            continue
        cid = obj.get("call_id")
        if isinstance(cid, str):
            if cid in seen:
                continue
            seen.add(cid)
        tc = obj.get("tool_call")
        if not isinstance(tc, dict):
            continue
        kind = next((k for k in tc if k.endswith("ToolCall")), None)
        if kind is None:
            continue
        body = tc.get(kind) if isinstance(tc.get(kind), dict) else {}
        args = body.get("args") if isinstance(body.get("args"), dict) else {}
        if kind == "mcpToolCall":
            server = args.get("serverIdentifier") or args.get("providerIdentifier")
            tool = args.get("toolName")
            if server and tool:
                name = _canonical_mcp(str(server), str(tool))
            else:
                name = str(args.get("name") or "mcp")
            inner = args.get("args") if isinstance(args.get("args"), dict) else {}
            calls.append(ToolCall(name=name, input=inner))
        else:
            name = _CURSOR_TOOL_KIND.get(
                kind, (kind[:-len("ToolCall")] or kind).capitalize()
            )
            calls.append(ToolCall(name=name, input=args))
    return calls


# Per-backend transcript parsers, keyed by ``SkillCLIBackend.transcript_format``.
# Each takes ``(stdout, stderr)`` and returns the ordered tool calls, or [] if
# it recognized nothing. ``graders.trace.extract_tool_calls`` dispatches here
# when the grading context knows which client produced the transcript.
_DIALECTS = {
    "anthropic_stream_json": lambda so, se: _stream_json_calls(so),
    "opencode_logs": lambda so, se: _opencode_tool_calls(se) or _opencode_tool_calls(so),
    "copilot_bullets": lambda so, se: _copilot_tool_calls(so),
    # Cursor stream-json first; fall back to the legacy tool_use/single-doc
    # shapes so old ``--output-format json`` transcripts still parse (as []).
    "cursor_json": lambda so, se: (
        _cursor_stream_calls(so) or _generic_json_calls(so) or _stream_json_calls(so)
    ),
}


def _auto_detect(stdout: str, stderr: str) -> list[ToolCall]:
    """Format-sniffing fallback used when the client/dialect is unknown."""
    calls = _stream_json_calls(stdout)
    if calls:
        return calls
    # Fallback 1: no assistant envelopes -> walk every line generically.
    calls = _generic_json_calls(stdout)
    if calls:
        return calls
    # Fallback 2: OpenCode arrow/gear lines (tool display goes to stderr).
    oc = _opencode_tool_calls(stderr) or _opencode_tool_calls(stdout)
    if oc:
        return oc
    # Fallback 3: GitHub Copilot CLI bullet lines (stdout only).
    #   ● Read hls-array2stream-01.cpp
    #   ● skill(hls-array-to-stream)
    return _copilot_tool_calls(stdout)


def extract_tool_calls(
    stdout: str, stderr: str = "", *, client: Optional[str] = None,
) -> list[ToolCall]:
    """Recover the ordered, deduplicated sequence of tool calls.

    When *client* is given and maps to a known backend dialect (via
    ``skills_testing.cli_backends.format_for``), the matching parser is used
    directly -- so, e.g., OpenCode's ⚙ MCP-tool lines are always recovered.
    Otherwise (unknown/omitted client) it falls back to format auto-detection,
    preserving the previous behavior for every existing caller.
    """
    if client:
        try:
            from ..cli_backends import format_for
            fmt = format_for(client)
        except Exception:
            fmt = ""
        parser = _DIALECTS.get(fmt)
        if parser is not None:
            calls = parser(stdout, stderr)
            if calls:
                return calls
    return _auto_detect(stdout, stderr)


# ---------------------------------------------------------------------------
# GitHub Copilot CLI transcript format.
#
# Copilot emits human-readable bullet lines on stdout:
#   ● Read <path>
#   ● List directory <path>
#   ● skill(<name>)
#   ● <label> (shell)      -- Bash / shell tool
#   ● vivado_execute (MCP: vivado-mcp-server) · <command>   -- MCP tool call
#   ✗ vivado_start (MCP: vivado-mcp-server) · <args>         -- failed MCP call
# The first word after the bullet glyph is the tool name, with special-casing
# for the skill-invocation form and for MCP calls (which carry a
# ``(MCP: <server>)`` annotation we lift back into the canonical
# ``mcp__<server>__<tool>`` identity). Both succeeded (``●``/``•``) and failed
# (``✗``) calls are captured -- the correctness of a call is judged elsewhere
# (``no_tool_errors``/``config_match``), so dropping ``✗`` lines would
# misrepresent the tool sequence that actually ran.
# ---------------------------------------------------------------------------

_COPILOT_BULLET = re.compile(r"^[●•✗✓]\s+(.+)$")
_COPILOT_SKILL_CALL = re.compile(r"^skill\(([^)]*)\)", re.I)
# ``(MCP: <server>)`` annotation Copilot appends after an MCP tool's name.
_COPILOT_MCP_ANNOT = re.compile(r"\(MCP:\s*([\w.\-]+)\)")


def _copilot_tool_calls(text: str) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for raw in text.splitlines():
        line = _ANSI.sub("", raw).strip()
        m = _COPILOT_BULLET.match(line)
        if not m:
            continue
        body = m.group(1).strip()
        # skill(<name>) → Skill tool
        sm = _COPILOT_SKILL_CALL.match(body)
        if sm:
            skill_arg = sm.group(1).strip()
            calls.append(ToolCall(name="Skill", input={"skill": skill_arg}))
            continue
        # "<ToolName> <rest>" — extract the first word as tool name
        parts = body.split(None, 1)
        name = parts[0]
        rest = parts[1] if len(parts) > 1 else ""
        # MCP call: reconstruct the ``mcp__<server>__<tool>`` identity from the
        # ``(MCP: <server>)`` annotation so canonical_mcp_name can collapse it
        # to its server-agnostic family (e.g. mcp__vivado__vivado_execute).
        am = _COPILOT_MCP_ANNOT.search(rest)
        if am:
            name = _canonical_mcp(am.group(1), name)
        else:
            # Normalise multi-word copilot labels to canonical tool names
            name_lower = name.lower()
            if name_lower in ("list",):
                name = "ListDirectory"
            elif name_lower in ("find",):
                name = "Bash"
        calls.append(ToolCall(name=name, input={"args": rest} if rest else {}))
    return calls


def tool_names(
    stdout: str, stderr: str = "", *, client: Optional[str] = None,
) -> list[str]:
    """The ordered list of tool names -- waza's ``SessionDigest.ToolsUsed``."""
    return [c.name for c in extract_tool_calls(stdout, stderr, client=client)]


# Argument keys, in priority order, that carry the "command" a tool ran.
# ``command`` is Bash's; the file/path keys give Read/Write a meaningful
# argument; ``args`` is the OpenCode/Copilot arrow-line argument blob.
_COMMAND_KEYS = (
    "command", "cmd", "script", "args",
    "file_path", "path", "filePath", "query", "pattern",
)


def command_of(call: ToolCall) -> str:
    """Best-effort executed-command / argument string for a tool call.

    Returns the shell command for Bash, the target path for Read/Write, or
    the raw argument blob for arrow-line backends. Empty when the transcript
    carried no arguments for the call.
    """
    inp = call.input or {}
    for key in _COMMAND_KEYS:
        v = inp.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def tool_calls_detailed(
    stdout: str, stderr: str = "", *, client: Optional[str] = None,
) -> list[tuple[str, str]]:
    """Ordered ``(tool_name, command)`` pairs recovered from the transcript.

    ``command`` is the executed command / primary argument (see
    :func:`command_of`) and may be empty when none was captured.
    """
    return [
        (c.name, command_of(c))
        for c in extract_tool_calls(stdout, stderr, client=client)
    ]


def final_response_text(stdout: str, stderr: str = "",
                        transcript_format: str = "") -> str:
    """The agent's final answer text (NOT the raw transcript).

    * Plain-text stdout (opencode) is already the final answer -> returned as-is.
    * JSON-envelope transcripts (Claude Code / Cursor stream-json): prefer a
      ``{"type":"result","result": "..."}`` envelope, else the last
      ``assistant`` message's concatenated text blocks.

    Best captured at run time from the *full* stdout: the session log truncates
    stdout, which can drop the final message that lives at the very end.
    """
    s = (stdout or "").strip()
    if not s:
        return ""
    if not s.startswith("{"):
        return s
    result_text = None
    last_assistant = None
    for obj in _iter_json_lines(stdout):
        typ = obj.get("type")
        if typ == "result" and isinstance(obj.get("result"), str) and obj["result"].strip():
            result_text = obj["result"]
        elif typ == "assistant":
            texts = [b.get("text", "") for b in _blocks_from_message(obj)
                     if b.get("type") == "text" and b.get("text")]
            if texts:
                last_assistant = "\n".join(texts)
    return (result_text or last_assistant or "").strip()


def command_matches(actual_cmd: str, want_cmd: str) -> bool:
    """Tolerant match of an expected command string against an actual one.

    Whitespace is normalised; passes on a plain substring hit or, failing
    that, when every whitespace-delimited token of *want_cmd* appears in
    *actual_cmd* (so argument reordering / extra flags do not break it).
    An empty *want_cmd* matches anything.
    """
    a = re.sub(r"\s+", " ", actual_cmd or "").strip().lower()
    w = re.sub(r"\s+", " ", want_cmd or "").strip().lower()
    if not w:
        return True
    if w in a:
        return True
    return all(tok in a for tok in w.split())


def find_tool_calls(
    stdout: str, stderr: str = "", *, tool: str = "", command: str = "",
    client: Optional[str] = None, aliases: Optional[dict[str, str]] = None,
) -> list[str]:
    """Return ``"name: command"`` strings for calls matching *tool*/*command*.

    *tool* (case-insensitive, empty = any) filters by tool name; *command*
    is matched with :func:`command_matches` against each call's executed
    command. Used by graders that assert a specific command actually ran.

    Tool-name comparison is MCP-server-agnostic: both the expected *tool* and
    each actual name are reduced with :func:`canonical_mcp_name` (using
    *aliases*), so ``mcp__vivado-doc-search__vivado_doc_search`` matches an
    expectation written as ``mcp__vivado-mcp-server__vivado_doc_search``.
    """
    want_tool = canonical_mcp_name(tool.strip(), aliases).lower()
    out: list[str] = []
    for name, cmd in tool_calls_detailed(stdout, stderr, client=client):
        if want_tool and canonical_mcp_name(name, aliases).lower() != want_tool:
            continue
        if command_matches(cmd, command):
            out.append(f"{name}: {cmd}" if cmd else name)
    return out


def tool_commands(
    stdout: str, stderr: str = "", *, client: Optional[str] = None,
) -> list[str]:
    """Ordered ``"name: command"`` strings for the agent's tool calls.

    Unlike :func:`tool_names`, this preserves the actual executed command so
    graders can match on *what* was run (e.g. ``"Bash: v++ --compile ..."``),
    not merely that a Bash tool was used. Falls back to the bare tool name
    when no command/argument was captured.
    """
    out: list[str] = []
    for name, cmd in tool_calls_detailed(stdout, stderr, client=client):
        out.append(f"{name}: {cmd}" if cmd else name)
    return out


# ---------------------------------------------------------------------------
# Skill-activation evidence (used by the trigger grader).
# ---------------------------------------------------------------------------


def _norm(name: str) -> str:
    """Normalize a skill name for tolerant comparison."""
    return re.sub(r"[\s_\-/]+", "-", str(name).strip().lower())


# Prose signals that a skill was applied, mirroring the backend's
# ``_SKILL_INVOKE_PATTERNS`` but kept local so graders stay decoupled.
_PROSE_SKILL_PATTERNS = [
    re.compile(r"\bappl(?:y|ying|ied)\s+the\s+([A-Za-z0-9_\-/]+)\s+skill", re.I),
    re.compile(r"\bus(?:e|ing)\s+the\s+([A-Za-z0-9_\-/]+)\s+skill", re.I),
    re.compile(r"\binvok(?:e|ing|ed)\s+the\s+([A-Za-z0-9_\-/]+)\s+skill", re.I),
]
_SKILL_MD_PATH = re.compile(r"skills/([A-Za-z0-9_\-/]+)/SKILL\.md", re.I)
_READ_SKILL_MD = re.compile(r"\bSKILL\.md\b", re.I)


@dataclass
class ActivationEvidence:
    probability: float
    signals: list[str] = field(default_factory=list)
    matched_skill: Optional[str] = None


def detect_skill_activation(
    stdout: str,
    stderr: str = "",
    *,
    skill_name: Optional[str] = None,
    client: Optional[str] = None,
) -> ActivationEvidence:
    """Estimate the probability that ``skill_name`` was activated by the agent.

    Combines structured tool-call evidence (a ``Skill`` tool call, a ``Read``
    of a ``SKILL.md``) with prose evidence in the transcript. The returned
    probability is the strongest single signal found, in ``[0, 1]``:

        1.0  explicit ``Skill`` tool call (matching name, when provided)
        0.9  ``Read``/tool access of ``.../<skill>/SKILL.md`` (matching name)
        0.8  ``Read`` of some ``SKILL.md`` / generic ``Skill`` tool call
        0.6  prose: "using/applying the <skill> skill"
        0.3  the skill name simply appears in the transcript
        0.0  no evidence
    """
    target = _norm(skill_name) if skill_name else None
    signals: list[str] = []
    best = 0.0
    matched: Optional[str] = None

    def bump(score: float, label: str, found_skill: Optional[str] = None) -> None:
        nonlocal best, matched
        signals.append(label)
        if score > best:
            best = score
            if found_skill:
                matched = found_skill

    # 1. Structured tool-call evidence.
    for call in extract_tool_calls(stdout, stderr, client=client):
        invoked = _skill_invocation_target(call)
        if invoked is not None:
            if target and _norm(invoked) == target:
                bump(1.0, f"skill_tool_call:{invoked}", invoked)
            elif not target:
                bump(1.0, f"skill_tool_call:{invoked}", invoked)
            else:
                bump(0.8, f"skill_tool_call_other:{invoked}", invoked)
        elif call.name in ("Read", "View", "Open"):
            path = str(
                call.input.get("file_path")
                or call.input.get("path")
                or call.input.get("filePath")
                or call.input.get("args")  # OpenCode arrow-line argument blob
                or ""
            )
            m = _SKILL_MD_PATH.search(path)
            if m:
                found = m.group(1).split("/")[-1]
                if target and _norm(found) == target:
                    bump(0.9, f"read_skill_md:{found}", found)
                elif not target:
                    bump(0.9, f"read_skill_md:{found}", found)
                else:
                    bump(0.8, f"read_skill_md_other:{found}", found)
            elif _READ_SKILL_MD.search(path):
                bump(0.8, "read_skill_md_generic")

    haystack = f"{stdout}\n{stderr}"

    # 2. Prose evidence.
    for pat in _PROSE_SKILL_PATTERNS:
        for m in pat.finditer(haystack):
            found = m.group(1)
            if target and _norm(found) == target:
                bump(0.6, f"prose_apply:{found}", found)
            elif not target:
                bump(0.6, f"prose_apply:{found}", found)
    for m in _SKILL_MD_PATH.finditer(haystack):
        found = m.group(1).split("/")[-1]
        if target and _norm(found) == target:
            bump(0.9, f"skill_md_path:{found}", found)
        elif not target:
            bump(0.9, f"skill_md_path:{found}", found)

    # 3. Weakest signal: bare name mention.
    if target:
        name_re = re.compile(
            r"\b" + re.escape(_norm(skill_name)).replace(r"\-", r"[\s_\-]") + r"\b",
            re.I,
        )
        if name_re.search(_norm(haystack)) or skill_name.lower() in haystack.lower():
            bump(0.3, f"name_mention:{skill_name}", skill_name)

    return ActivationEvidence(probability=best, signals=signals, matched_skill=matched)
