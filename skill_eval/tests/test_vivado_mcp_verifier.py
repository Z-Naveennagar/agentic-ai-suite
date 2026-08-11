"""
Tests for the vivado_mcp verifier (skills_testing/verifiers/vivado_mcp.py).

These tests do not require a real Vivado install -- they stand up a tiny
HTTP server that mimics the streamable-HTTP MCP protocol used by the
real vivado-mcp-server binary. We exercise the happy path, the
session_id parsing fallbacks, and the error mapping.
"""
from __future__ import annotations

import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from skills_testing.verifiers.vivado_mcp import vivado_mcp_verifier


def _make_server(handler_cls):
    srv = HTTPServer(("127.0.0.1", 0), handler_cls)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    return srv, th


class _BaseHandler(BaseHTTPRequestHandler):
    """Common JSON-RPC plumbing. Subclasses override ``handle_call``."""

    session_id = "fake-session-1"
    captured: list[dict] = []

    def log_message(self, *_args, **_kw):
        pass  # silence

    def _send_json(self, payload: dict, *, with_session_header: bool = False):
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        if with_session_header:
            self.send_header("mcp-session-id", self.session_id)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        method = body.get("method")
        if method == "initialize":
            self._send_json({
                "jsonrpc": "2.0", "id": body.get("id"),
                "result": {"protocolVersion": "2024-11-05",
                           "serverInfo": {"name": "fake", "version": "0"}},
            }, with_session_header=True)
            return
        if method == "notifications/initialized":
            self.send_response(202)
            self.end_headers()
            return
        if method == "tools/call":
            params = body.get("params") or {}
            self.captured.append({"name": params.get("name"),
                                  "arguments": params.get("arguments")})
            result = self.handle_call(params.get("name"),
                                       params.get("arguments") or {})
            self._send_json({"jsonrpc": "2.0", "id": body.get("id"),
                             "result": result})
            return
        self._send_json({"jsonrpc": "2.0", "id": body.get("id"),
                         "error": {"code": -32601, "message": "no method"}})


@pytest.fixture
def fake_mcp(monkeypatch):
    """Spawn a fake MCP server, point the verifier at it, return the
    HTTPServer + handler class so tests can install per-test logic."""
    state: dict = {"calls": [], "exec_isError": False, "exec_text": "OK"}

    class H(_BaseHandler):
        captured = state["calls"]

        def handle_call(self, name, arguments):
            if name == "vivado_start":
                return {
                    "isError": False,
                    "content": [{"type": "text",
                                 "text": json.dumps({
                                     "session_id": "vivado-fake-42",
                                     "status": "success",
                                 })}],
                }
            if name == "vivado_execute":
                if state["exec_isError"]:
                    return {"isError": True,
                            "content": [{"type": "text",
                                         "text": state["exec_text"]}]}
                return {"isError": False,
                        "content": [{"type": "text",
                                     "text": state["exec_text"]}]}
            if name == "vivado_stop":
                return {"isError": False,
                        "content": [{"type": "text", "text": "stopped"}]}
            return {"isError": True,
                    "content": [{"type": "text",
                                 "text": f"unknown tool {name}"}]}

    srv, th = _make_server(H)
    url = f"http://127.0.0.1:{srv.server_address[1]}/mcp"
    monkeypatch.setenv("SKILL_TEST_VIVADO_MCP_URL", url)
    yield state
    srv.shutdown()


def test_vivado_mcp_verifier_happy_path(fake_mcp, tmp_path: Path):
    fake_mcp["exec_text"] = "VERIFY_RERUN_DONE"
    out = vivado_mcp_verifier(
        workspace_dir=tmp_path, tcl='puts "VERIFY_RERUN_DONE"',
        env=None, timeout_seconds=10,
    )
    assert out["exit_code"] == 0, out
    assert "VERIFY_RERUN_DONE" in out["stdout"]
    # all three MCP calls were made, in order
    names = [c["name"] for c in fake_mcp["calls"]]
    assert names == ["vivado_start", "vivado_execute", "vivado_stop"]
    # workspace_dir + vivado_path actually got forwarded
    args = fake_mcp["calls"][0]["arguments"]
    assert args["working_dir"] == str(tmp_path)
    assert args["session_type"] == "general"
    assert args.get("vivado_path"), "vivado_path must be passed to vivado_start"


def test_vivado_mcp_verifier_session_id_fallback_text_form(fake_mcp, tmp_path: Path):
    """If the start text isn't valid JSON we still parse the session_id
    out of a 'session_id: foo' line (real Vivado MCP versions emit this
    in a non-JSON banner)."""

    class HText(_BaseHandler):
        captured = fake_mcp["calls"]

        def handle_call(self, name, arguments):
            if name == "vivado_start":
                return {"isError": False, "content": [{"type": "text",
                        "text": "Started\nsession_id: vivado-text-7\nDone"}]}
            if name == "vivado_execute":
                return {"isError": False, "content": [{"type": "text",
                        "text": "OK"}]}
            return {"isError": False, "content": [{"type": "text", "text": ""}]}

    # Replace the running server with the text variant.
    srv, _th = _make_server(HText)
    import os
    os.environ["SKILL_TEST_VIVADO_MCP_URL"] = (
        f"http://127.0.0.1:{srv.server_address[1]}/mcp")
    try:
        out = vivado_mcp_verifier(
            workspace_dir=tmp_path, tcl='puts ok',
            env=None, timeout_seconds=10,
        )
        assert out["exit_code"] == 0, out
        # vivado_execute was called with session_id from the text banner
        exec_call = next(c for c in fake_mcp["calls"]
                         if c["name"] == "vivado_execute")
        assert exec_call["arguments"]["session_id"] == "vivado-text-7"
    finally:
        srv.shutdown()


def test_vivado_mcp_verifier_tcl_error_maps_to_nonzero_exit(fake_mcp, tmp_path: Path):
    fake_mcp["exec_isError"] = True
    fake_mcp["exec_text"] = "VERIFY_RERUN_TCL_ERROR: bad command"
    out = vivado_mcp_verifier(
        workspace_dir=tmp_path, tcl='nonexistent_command',
        env=None, timeout_seconds=10,
    )
    assert out["exit_code"] != 0
    assert "VERIFY_RERUN_TCL_ERROR" in out["stderr"]


def test_vivado_mcp_verifier_handles_unreachable_server(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SKILL_TEST_VIVADO_MCP_URL",
                       "http://127.0.0.1:1/mcp")  # closed port
    out = vivado_mcp_verifier(
        workspace_dir=tmp_path, tcl='puts ok',
        env=None, timeout_seconds=2,
    )
    assert out["exit_code"] in (2, 6, 7)
    assert "tmp_path" not in out["stderr"]
