"""
Tests for the pluggable cleanup registry.

Contract:
    CleanupManager()                   - empty registry
    .register(name, fn)
    .run(steps, ctx)                   -> list[CleanupResult]
    Built-ins: 'working_dir' (wipes Workspace.dir),
               'vivado_sessions' (calls vivado_stop on tracked session_ids)

CleanupResult fields: step, ok (bool), error (str|None).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skills_testing.runtime.cleanup_manager import (
    CleanupContext,
    CleanupManager,
    default_cleanup_manager,
)
from skills_testing.runtime.workspace import create_workspace


def test_register_and_run(tmp_path):
    mgr = CleanupManager()
    calls: list[str] = []
    mgr.register("noop", lambda ctx: calls.append("noop"))
    ws = create_workspace("c1", root=tmp_path)
    ctx = CleanupContext(workspace=ws, vivado_session_ids=[], notes={})
    results = mgr.run(["noop"], ctx)
    assert calls == ["noop"]
    assert results[0].step == "noop"
    assert results[0].ok is True


def test_unknown_step_recorded_as_error(tmp_path):
    mgr = CleanupManager()
    ws = create_workspace("c1", root=tmp_path)
    ctx = CleanupContext(workspace=ws, vivado_session_ids=[], notes={})
    results = mgr.run(["nope"], ctx)
    assert results[0].ok is False
    assert "unknown" in results[0].error.lower()


def test_step_failure_does_not_stop_pipeline(tmp_path):
    mgr = CleanupManager()
    seen: list[str] = []
    def boom(ctx):
        seen.append("boom")
        raise RuntimeError("kaboom")
    mgr.register("boom", boom)
    mgr.register("after", lambda ctx: seen.append("after"))

    ws = create_workspace("c1", root=tmp_path)
    ctx = CleanupContext(workspace=ws, vivado_session_ids=[], notes={})
    results = mgr.run(["boom", "after"], ctx)
    assert seen == ["boom", "after"]
    assert results[0].ok is False
    assert "kaboom" in results[0].error
    assert results[1].ok is True


def test_default_manager_has_working_dir_and_vivado_sessions():
    mgr = default_cleanup_manager()
    assert "working_dir" in mgr.steps
    assert "vivado_sessions" in mgr.steps
    assert "workspace_processes" in mgr.steps


def test_workspace_processes_reaps_only_workspace_scoped_children(tmp_path):
    """Spawn a long-running child whose argv references the workspace
    path, and a sibling that doesn't. The cleanup step must kill the
    first and leave the second alone."""
    import subprocess
    import sys

    ws = create_workspace("c1", root=tmp_path)
    needle = str(ws.dir.resolve())

    # Use a python "sleep" that ignores trailing tag args so the cmdline
    # carries the workspace-path needle (or a sibling tag) without
    # tripping argv validation in /bin/sleep.
    sleep_py = ["import sys, time; time.sleep(300)"]
    in_ws = subprocess.Popen(
        [sys.executable, "-c", *sleep_py, "--tag", needle],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    out_of_ws = subprocess.Popen(
        [sys.executable, "-c", *sleep_py, "--tag", "/some/other/dir"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        # Confirm both are alive before we start.
        assert in_ws.poll() is None
        assert out_of_ws.poll() is None

        mgr = default_cleanup_manager()
        ctx = CleanupContext(workspace=ws,
                             vivado_session_ids=[], notes={})
        results = mgr.run(["workspace_processes"], ctx)
        assert results[0].ok is True

        # Workspace-scoped child must be reaped within the step's
        # 3 s grace window; out-of-ws sibling must survive.
        in_ws.wait(timeout=5)
        assert in_ws.returncode is not None
        assert out_of_ws.poll() is None
    finally:
        for p in (in_ws, out_of_ws):
            try:
                p.kill()
            except ProcessLookupError:
                pass
            try:
                p.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass


def test_working_dir_step_removes_workspace(tmp_path):
    ws = create_workspace("c1", root=tmp_path)
    (ws.dir / "junk").write_text("x")
    p = ws.dir
    mgr = default_cleanup_manager()
    ctx = CleanupContext(workspace=ws, vivado_session_ids=[], notes={})
    mgr.run(["working_dir"], ctx)
    assert not p.exists()


def test_vivado_sessions_step_invokes_callback(tmp_path):
    stopped: list[str] = []

    def stop(session_id: str) -> None:
        stopped.append(session_id)

    mgr = default_cleanup_manager(vivado_stop_fn=stop)
    ws = create_workspace("c1", root=tmp_path)
    ctx = CleanupContext(
        workspace=ws,
        vivado_session_ids=["sess-A", "sess-B"],
        notes={},
    )
    results = mgr.run(["vivado_sessions"], ctx)
    assert sorted(stopped) == ["sess-A", "sess-B"]
    assert results[0].ok is True
