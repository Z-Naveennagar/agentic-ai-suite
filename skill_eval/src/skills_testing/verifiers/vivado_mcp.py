"""
Vivado MCP verifier for SkillRunner's verify_by_rerun hook.

Implements the streamable-HTTP MCP transport (initialize → notifications/
initialized → tools/call) and runs a single TCL block in a fresh Vivado
session rooted at the test's workspace directory. The block is executed
as one ``vivado_execute`` call so all puts/report output ends up in a
single tool result that we surface as ``stdout``.

The Vivado MCP server URL is taken from the ``SKILL_TEST_VIVADO_MCP_URL``
env var (the same one used by the cli_backends), defaulting to the local
HTTP bridge used by the harness. If the server is unreachable the verifier
returns exit_code=2 with an error in ``stderr``.
"""
from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Optional

import httpx


_DEFAULT_VIVADO_MCP_URL = "http://127.0.0.1:18090/mcp"


def _server_url() -> str:
    return os.environ.get("SKILL_TEST_VIVADO_MCP_URL", _DEFAULT_VIVADO_MCP_URL)


def _vivado_path() -> str:
    return os.environ.get("VIVADO_PATH") or shutil.which("vivado") or "vivado"


def _decode_result(resp: httpx.Response) -> dict[str, Any]:
    """Vivado MCP responds either with ``application/json`` or with
    ``text/event-stream`` (a single ``data: { ... }`` SSE frame). Handle
    both transparently.
    """
    ctype = (resp.headers.get("content-type") or "").lower()
    if "event-stream" in ctype:
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                payload = line[len("data:"):].strip()
                if payload:
                    return json.loads(payload)
        raise RuntimeError(f"empty SSE stream: {resp.text!r}")
    return resp.json()


def _extract_text(result: dict[str, Any]) -> str:
    """``tools/call`` returns ``{result: {content: [{type: text, text: ...}]}}``
    on success or ``{result: {isError: true, content: [...]}}`` on tool
    errors. Concatenate all text parts."""
    if not isinstance(result, dict):
        return ""
    inner = result.get("result") or result.get("error") or {}
    if isinstance(inner, str):
        return inner
    parts = inner.get("content") or []
    out = []
    for p in parts:
        if isinstance(p, dict) and p.get("type") == "text":
            out.append(p.get("text", ""))
    return "\n".join(out)


def parse_session_id(start_text: str) -> Optional[str]:
    """Pull the ``session_id`` out of a ``vivado_start`` tool result.

    The server answers either with a JSON object carrying ``session_id``/
    ``id`` or with a human-readable line mentioning ``session_id``, so try
    JSON first and fall back to scanning for the first token that is long
    enough to be an id and isn't the label itself.

    Shared with ``runtime/vivado_session_setup.py``, which starts a session
    it deliberately does NOT stop -- the parsing is identical, only the
    lifetime differs.
    """
    try:
        obj = json.loads(start_text) if start_text.strip().startswith("{") else None
    except json.JSONDecodeError:
        obj = None
    if isinstance(obj, dict):
        sid = obj.get("session_id") or obj.get("id")
        if sid:
            return str(sid)
    for line in start_text.splitlines():
        if "session_id" not in line.lower():
            continue
        toks = line.replace(":", " ").replace("=", " ").split()
        # Only look AFTER the label token. Scanning the whole line lets any
        # long word that happens to precede it win (e.g. "Started. session_id
        # = <id>" would return "Started."), which is how the original inline
        # version misfired.
        for i, tok in enumerate(toks):
            if tok.lower().strip('",').startswith("session_id"):
                for cand in toks[i + 1:]:
                    cand = cand.strip().strip('",')
                    if len(cand) >= 8 and not cand.lower().startswith("session"):
                        return cand
                break
    return None


class _MCPSession:
    """Minimal MCP streamable-HTTP client tailored for the verifier.

    Re-implements just enough of the protocol to call
    ``vivado_start`` / ``vivado_execute`` / ``vivado_stop``. We
    deliberately don't reuse ``mcp_client.MCPClient`` because that one
    is hard-coded for vivado_doc_search.

    Exported as ``MCPSession`` (alias below) for reuse by
    ``runtime/vivado_session_setup.py``."""

    def __init__(self, url: str, timeout: int):
        self.url = url
        self.timeout = timeout
        self.session_id: Optional[str] = None
        self.client = httpx.Client(timeout=timeout)

    def _post(self, body: dict[str, Any]) -> httpx.Response:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            headers["mcp-session-id"] = self.session_id
        return self.client.post(self.url, json=body, headers=headers)

    def initialize(self) -> None:
        body = {
            "jsonrpc": "2.0", "id": str(uuid.uuid4()),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "skill-runner-verifier", "version": "1.0"},
            },
        }
        resp = self._post(body)
        resp.raise_for_status()
        self.session_id = resp.headers.get("mcp-session-id")
        if not self.session_id:
            raise RuntimeError("Vivado MCP did not return mcp-session-id header")

        notif = {"jsonrpc": "2.0", "method": "notifications/initialized",
                 "params": {}}
        resp2 = self._post(notif)
        if resp2.status_code not in (200, 202, 204):
            resp2.raise_for_status()

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        body = {
            "jsonrpc": "2.0", "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        resp = self._post(body)
        resp.raise_for_status()
        return _decode_result(resp)

    def close(self) -> None:
        try:
            self.client.close()
        except Exception:
            pass


def vivado_mcp_verifier(
    *,
    workspace_dir: Path,
    tcl: str,
    env: Optional[dict[str, str]] = None,  # currently unused (server-side env)
    timeout_seconds: int = 1800,
) -> dict[str, Any]:
    """Apply a TCL block in a fresh Vivado session at *workspace_dir*.

    Returns ``{"stdout": str, "stderr": str, "exit_code": int}``.
    ``exit_code`` is 0 when every individual MCP call returned without
    ``isError: true`` AND the final exec call's TCL succeeded.
    """
    url = _server_url()
    started_at = time.time()
    sess: Optional[_MCPSession] = None
    transcript: list[str] = []

    def _is_error(result: dict[str, Any]) -> bool:
        inner = result.get("result") or {}
        return bool(inner.get("isError"))

    try:
        sess = _MCPSession(url, timeout_seconds)
        try:
            sess.initialize()
        except Exception as exc:
            return {"stdout": "", "stderr": f"MCP init failed: {exc}",
                    "exit_code": 2}

        # 1. vivado_start. The Vivado MCP requires session_type to be one
        #    of {"ipi", "general"}; we use "general" for the verifier
        #    re-route flow. We also pass vivado_path explicitly so the
        #    verifier works against any MCP server, not just one started
        #    with --vivado-path or VIVADO_PATH already set.
        start_args = {
            "working_dir": str(workspace_dir),
            "session_type": "general",
            "vivado_path": _vivado_path(),
            "display_mode": "none",
        }
        start_res = sess.call("vivado_start", start_args)
        start_text = _extract_text(start_res)
        transcript.append(f"# vivado_start\n{start_text}")
        if _is_error(start_res):
            return {"stdout": "\n".join(transcript),
                    "stderr": f"vivado_start returned isError\n{start_text}",
                    "exit_code": 3}
        # parse session_id out of start_text (server returns e.g. "session_id: <id>")
        session_id = parse_session_id(start_text)
        if not session_id:
            sess.call("vivado_stop", {"session_id": session_id or ""})
            return {"stdout": "\n".join(transcript),
                    "stderr": "vivado_start did not return a session_id",
                    "exit_code": 4}

        # 2. vivado_execute -- run the rendered TCL in one shot. We wrap
        #    in catch/return so we can surface a structured exit_code
        #    instead of relying on tool-level isError detection alone.
        wrapped = (
            "if {[catch {\n"
            f"{tcl}\n"
            "} _err]} {\n"
            "    puts stderr \"VERIFY_RERUN_TCL_ERROR: $_err\"\n"
            "    return -code error \"verify_rerun: $_err\"\n"
            "}\n"
            "puts \"VERIFY_RERUN_DONE\""
            if "VERIFY_RERUN_DONE" not in tcl else
            "if {[catch {\n"
            f"{tcl}\n"
            "} _err]} {\n"
            "    puts stderr \"VERIFY_RERUN_TCL_ERROR: $_err\"\n"
            "    return -code error \"verify_rerun: $_err\"\n"
            "}"
        )
        exec_args = {"session_id": session_id, "command": wrapped}
        exec_res = sess.call("vivado_execute", exec_args)
        exec_text = _extract_text(exec_res)
        transcript.append(f"# vivado_execute\n{exec_text}")

        # 3. always try to stop the session before returning
        try:
            sess.call("vivado_stop", {"session_id": session_id})
        except Exception:
            pass

        # Map outcome
        if _is_error(exec_res) or "VERIFY_RERUN_TCL_ERROR" in exec_text:
            return {"stdout": "\n".join(transcript),
                    "stderr": exec_text,
                    "exit_code": 5}
        return {"stdout": "\n".join(transcript), "stderr": "", "exit_code": 0}

    except httpx.HTTPError as exc:
        return {"stdout": "\n".join(transcript),
                "stderr": f"HTTP error talking to {url}: {exc}",
                "exit_code": 6}
    except Exception as exc:
        return {"stdout": "\n".join(transcript),
                "stderr": f"verifier exception: {exc!r}",
                "exit_code": 7}
    finally:
        if sess is not None:
            sess.close()
        # not used yet, but logged for future debugging
        _elapsed = time.time() - started_at


# Public aliases for the pieces reused outside this module (see
# runtime/vivado_session_setup.py). The underscore names stay for the
# existing in-module callers.
MCPSession = _MCPSession
extract_text = _extract_text
server_url = _server_url
vivado_path = _vivado_path

__all__ = [
    "vivado_mcp_verifier", "parse_session_id",
    "MCPSession", "extract_text", "server_url", "vivado_path",
]
