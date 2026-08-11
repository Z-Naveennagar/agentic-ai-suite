"""Per-tool-call timing recovered from timestamped transcript lines.

``SkillCLIBackend.invoke`` captures stdout/stderr line-by-line, stamping each
line with a monotonic offset (seconds since the agent process started). This
module turns those stamped lines into an ordered timeline of tool calls with a
per-call duration, so the dashboard can show the chronological chain of tool
calls and how long each took.

Timing precision depends on what the backend transcript actually records:

* ``anthropic_stream_json`` (Claude Code): **exact** -- each ``tool_use`` block
  is paired with its ``tool_result`` by id, so duration = t(result) - t(use).
* ``cursor_json`` (Cursor): **exact** -- the ``started``/``completed`` event
  pair shares a ``call_id``, so duration = t(completed) - t(started).
* ``opencode_logs`` (opencode): **approximate** -- opencode prints one line per
  tool call but no per-call end marker, so a call's duration is the gap until
  the next tool line (the final call runs to end-of-run). This includes the
  model latency between calls, so it is an upper bound on pure tool time.
* other backends: order only (offsets unknown -> ``duration_s`` is ``None``).

The parsing reuses ``graders.trace``'s per-backend recognizers (glyph regexes,
MCP-name canonicalization, stream-json envelope walk) so this stays consistent
with how the grading path reads the same transcripts -- it only adds the
line-offset bookkeeping ``trace`` throws away.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from ..graders import trace as _trace

# (offset_seconds_since_process_start, line_text_without_trailing_newline)
Stamped = list[tuple[float, str]]

# Fallback when a backend does not declare ``transcript_format`` (it normally
# does -- this only covers a bare client name).
_FORMAT_BY_CLIENT = {
    "claude_code": "anthropic_stream_json",
    "opencode": "opencode_logs",
    "cursor": "cursor_json",
}


def build_tool_timeline(
    stdout_stamps: Stamped,
    stderr_stamps: Stamped,
    *,
    client: str = "",
    transcript_format: str = "",
    total_wall_s: Optional[float] = None,
) -> list[dict]:
    """Return an ordered ``[{seq, name, args, t_start, duration_s}, ...]``.

    ``t_start`` is seconds from process start; ``duration_s`` may be ``None``
    when the backend transcript carries no timing signal for that call.
    """
    fmt = transcript_format or _FORMAT_BY_CLIENT.get(client, "")
    if fmt == "anthropic_stream_json":
        events = _from_stream_json(stdout_stamps)
    elif fmt == "cursor_json":
        events = _from_cursor(stdout_stamps)
    elif fmt == "opencode_logs":
        events = _from_opencode(stderr_stamps) or _from_opencode(stdout_stamps)
    else:
        # Unknown dialect: try each recognizer, take the first that finds calls.
        events = (
            _from_stream_json(stdout_stamps)
            or _from_cursor(stdout_stamps)
            or _from_opencode(stderr_stamps)
            or _from_opencode(stdout_stamps)
        )

    _fill_open_durations(events, total_wall_s)
    out: list[dict] = []
    for i, e in enumerate(events):
        e.pop("_id", None)
        e["seq"] = i + 1
        # Tag skill activations distinctly so the dashboard can show *how* the
        # tool chain got triggered -- the skill invocation that opened it.
        if _trace._is_skill_name(e.get("name")):
            e["kind"] = "skill"
            e["skill"] = _trace._clean_skill_label(e.get("args"))
        else:
            e["kind"] = "tool"
        out.append(e)
    return out


def _short_args(inp: Any) -> str:
    """A compact single-line argument summary for the timeline row."""
    if not inp:
        return ""
    if isinstance(inp, str):
        return inp.strip()
    if isinstance(inp, dict):
        for k in ("command", "file_path", "path", "query", "pattern",
                  "operation", "session_id", "title"):
            v = inp.get(k)
            if isinstance(v, (str, int, float)):
                return f"{k}={v}"
        try:
            return json.dumps(inp, default=str)
        except Exception:
            return str(inp)
    return str(inp)


def _fill_open_durations(events: list[dict], total_wall_s: Optional[float]) -> None:
    """Fill any ``duration_s is None`` with the gap to the next call (or, for
    the last call, to end-of-run when ``total_wall_s`` is known)."""
    for i, e in enumerate(events):
        if e.get("duration_s") is not None:
            continue
        if i + 1 < len(events):
            nxt = events[i + 1].get("t_start")
            if nxt is not None and e.get("t_start") is not None:
                e["duration_s"] = max(0.0, nxt - e["t_start"])
        elif total_wall_s is not None and e.get("t_start") is not None:
            e["duration_s"] = max(0.0, total_wall_s - e["t_start"])


# ------------------------------------------------------ opencode (approx)


def _from_opencode(stamps: Stamped) -> list[dict]:
    out: list[dict] = []
    for off, raw in stamps:
        line = _trace._ANSI.sub("", raw).strip()
        if not line:
            continue
        m = _trace._OPENCODE_ARROW.match(line)
        if m:
            glyph, name = m.group(1), m.group(2)
            rest = line[m.end():].strip()
            if glyph in _trace._OPENCODE_MCP_GLYPHS:
                name = _trace._opencode_mcp_name(name)
            out.append({"name": name, "args": rest,
                        "t_start": off, "duration_s": None})
            continue
        sh = _trace._OPENCODE_SHELL.match(line)
        if sh:
            out.append({"name": "Bash", "args": sh.group(1).strip(),
                        "t_start": off, "duration_s": None})
    return out


# --------------------------------------------- anthropic stream-json (exact)


def _int(x: Any) -> Optional[int]:
    return int(x) if isinstance(x, (int, float)) else None


def _content_len(content: Any) -> Optional[int]:
    """Character length of a tool_result payload (str, or list of text blocks)."""
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        total = 0
        for b in content:
            if isinstance(b, dict) and isinstance(b.get("text"), str):
                total += len(b["text"])
            elif isinstance(b, str):
                total += len(b)
        return total or None
    return None


def _usage_stats(usage: dict) -> dict:
    return {
        "tokens_in": _int(usage.get("input_tokens")),
        "tokens_out": _int(usage.get("output_tokens")),
        "cache_read": _int(usage.get("cache_read_input_tokens")),
        "cache_write": _int(usage.get("cache_creation_input_tokens")),
    }


def _from_stream_json(stamps: Stamped) -> list[dict]:
    """Recover tool calls from Claude Code stream-json.

    Token usage is the crux: with ``--include-partial-messages`` the
    ``assistant`` envelope only carries the *initial* usage (``output_tokens``
    ~2). The turn's *final* usage arrives in a later ``message_delta``
    stream event. So we seed each tool_use with the assistant envelope's usage
    (a correct fallback when no deltas are emitted) and, when a ``message_delta``
    closes the turn, overwrite the pending tool call(s) with the final numbers.
    """
    order: list[dict] = []
    by_id: dict[str, dict] = {}
    seen: set[str] = set()
    pending: list[dict] = []  # tool events of the current (not-yet-closed) turn

    def _finalize(usage: dict) -> None:
        if usage:
            fin = _usage_stats(usage)
            for ev in pending:
                for k, v in fin.items():
                    if v is not None:
                        ev[k] = v
        pending.clear()

    for off, raw in stamps:
        raw = raw.strip()
        if not raw.startswith("{"):
            continue
        try:
            obj = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        typ = obj.get("type")
        if typ == "assistant":
            init = _usage_stats((obj.get("message") or {}).get("usage") or {})
            for b in _trace._blocks_from_message(obj):
                if b.get("type") == "tool_use" and b.get("name"):
                    tid = b.get("id")
                    if tid and tid in seen:   # dedupe repeated envelopes
                        continue
                    if tid:
                        seen.add(tid)
                    ev = {"name": str(b["name"]),
                          "args": _short_args(b.get("input")),
                          "t_start": off, "duration_s": None, "_id": tid,
                          **init}
                    order.append(ev)
                    pending.append(ev)
                    if tid:
                        by_id[tid] = ev
        elif typ == "stream_event":
            ev_obj = obj.get("event") or {}
            if ev_obj.get("type") == "message_delta":
                # End of turn: overwrite this turn's tool call(s) with the
                # final (real) token counts.
                _finalize(ev_obj.get("usage") or {})
        elif typ in ("user", "tool_result"):
            for b in _trace._blocks_from_message(obj):
                if b.get("type") == "tool_result":
                    ev = by_id.get(b.get("tool_use_id"))
                    if ev is not None:
                        if ev.get("duration_s") is None:
                            ev["duration_s"] = max(0.0, off - ev["t_start"])
                        ev["is_error"] = bool(b.get("is_error"))
                        ev["result_chars"] = _content_len(b.get("content"))
    return order


# ------------------------------------------------------ cursor stream (exact)


def _cursor_name_args(tc: dict) -> tuple[str, str]:
    kind = next((k for k in tc if k.endswith("ToolCall")), None)
    if kind is None:
        return "", ""
    body = tc.get(kind) if isinstance(tc.get(kind), dict) else {}
    args = body.get("args") if isinstance(body.get("args"), dict) else {}
    if kind == "mcpToolCall":
        server = args.get("serverIdentifier") or args.get("providerIdentifier")
        tool = args.get("toolName")
        name = (_trace._canonical_mcp(str(server), str(tool))
                if server and tool else str(args.get("name") or "mcp"))
        inner = args.get("args") if isinstance(args.get("args"), dict) else {}
        return name, _short_args(inner)
    name = _trace._CURSOR_TOOL_KIND.get(
        kind, (kind[:-len("ToolCall")] or kind).capitalize())
    return name, _short_args(args)


def _from_cursor(stamps: Stamped) -> list[dict]:
    order: list[dict] = []
    by_id: dict[str, dict] = {}
    for off, raw in stamps:
        raw = raw.strip()
        if not raw.startswith("{"):
            continue
        try:
            obj = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        if obj.get("type") != "tool_call":
            continue
        cid = obj.get("call_id")
        tc = obj.get("tool_call") if isinstance(obj.get("tool_call"), dict) else {}
        name, args = _cursor_name_args(tc)
        sub = obj.get("subtype")
        ev = by_id.get(cid) if isinstance(cid, str) else None
        if ev is None:
            ev = {"name": name or "tool", "args": args,
                  "t_start": off, "duration_s": None}
            order.append(ev)
            if isinstance(cid, str):
                by_id[cid] = ev
            if sub == "completed":
                ev["duration_s"] = 0.0
        elif sub == "completed":
            if name and ev["name"] in ("", "tool"):
                ev["name"] = name
            if args and not ev["args"]:
                ev["args"] = args
            ev["duration_s"] = max(0.0, off - ev["t_start"])
    return order
