"""
Pluggable cleanup registry.

A *cleanup step* is a callable taking a CleanupContext. The default manager
ships three built-ins:

    working_dir          wipes the per-test workspace directory
    vivado_sessions      stops every tracked Vivado MCP session_id
    workspace_processes  reaps any child process (vivado tcl, proxy-mode
                         vivado-mcp-server, opencode serve, ...) whose
                         cmdline references the workspace path. This is
                         the safety net for tools we never got an MCP
                         session id for (e.g. proxy-mode workers spawned
                         by the IDE-side MCP server inside our workspace).

Failures in one step do not stop the pipeline; each step's outcome is
returned in a CleanupResult so the runner can record it.
"""

from __future__ import annotations

import os
import signal
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from .workspace import Workspace


@dataclass
class CleanupContext:
    workspace: Workspace
    vivado_session_ids: list[str] = field(default_factory=list)
    notes: dict[str, Any] = field(default_factory=dict)


@dataclass
class CleanupResult:
    step: str
    ok: bool
    error: Optional[str] = None


class CleanupManager:
    def __init__(self) -> None:
        self.steps: dict[str, Callable[[CleanupContext], None]] = {}

    def register(self, name: str, fn: Callable[[CleanupContext], None]) -> None:
        self.steps[name] = fn

    def run(self, steps: list[str], ctx: CleanupContext) -> list[CleanupResult]:
        results: list[CleanupResult] = []
        for name in steps:
            fn = self.steps.get(name)
            if fn is None:
                results.append(CleanupResult(step=name, ok=False,
                                             error=f"unknown cleanup step: {name!r}"))
                continue
            try:
                fn(ctx)
                results.append(CleanupResult(step=name, ok=True))
            except Exception as exc:  # don't let one step block the rest
                results.append(CleanupResult(step=name, ok=False, error=str(exc)))
        return results


# -- default manager + built-ins -----------------------------------------


def _working_dir(ctx: CleanupContext) -> None:
    ctx.workspace.cleanup()


def default_cleanup_manager(
    *, vivado_stop_fn: Callable[[str], None] | None = None
) -> CleanupManager:
    """
    Return a CleanupManager with built-ins registered.

    vivado_stop_fn is the function used to stop a Vivado session (e.g. a
    closure around the MCP client's vivado_stop tool). The default is a
    no-op so unit tests can run without an MCP server.
    """
    mgr = CleanupManager()
    mgr.register("working_dir", _working_dir)

    def _vivado_sessions(ctx: CleanupContext) -> None:
        errors: list[str] = []
        for sid in list(ctx.vivado_session_ids):
            if vivado_stop_fn is None:
                continue
            try:
                vivado_stop_fn(sid)
            except Exception as exc:
                errors.append(f"{sid}: {exc}")
        if errors:
            raise RuntimeError("; ".join(errors))

    mgr.register("vivado_sessions", _vivado_sessions)
    mgr.register("workspace_processes", _workspace_processes)
    return mgr


# -- workspace-scoped process reaper -------------------------------------


def _workspace_processes(ctx: CleanupContext) -> None:
    """SIGTERM (then SIGKILL) every process whose cmdline references
    the test workspace path. Workspace-scoped so it CANNOT touch the
    user's IDE-side Vivado / opencode / etc.
    """
    ws_path = str(Path(ctx.workspace.dir).resolve())
    if not ws_path or len(ws_path) < 8:
        return  # paranoia: never run with a too-short / empty path
    victims = _scan_proc_for_path(ws_path)
    if not victims:
        return
    for pid in victims:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
    # Give them a brief moment to exit cleanly before escalating.
    deadline = time.time() + 3.0
    survivors: list[int] = []
    while time.time() < deadline:
        survivors = [pid for pid in victims if _pid_alive(pid)]
        if not survivors:
            break
        time.sleep(0.2)
    for pid in survivors:
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def _scan_proc_for_path(needle: str) -> list[int]:
    """Return PIDs whose /proc/<pid>/cmdline or /proc/<pid>/cwd match
    the workspace path. Skips ourselves and our parent."""
    me = os.getpid()
    parent = os.getppid()
    out: list[int] = []
    try:
        entries = os.listdir("/proc")
    except OSError:
        return out
    for name in entries:
        if not name.isdigit():
            continue
        pid = int(name)
        if pid in (me, parent):
            continue
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as f:
                cmdline = f.read().replace(b"\x00", b" ").decode(
                    errors="replace")
        except (OSError, PermissionError):
            cmdline = ""
        cwd = ""
        try:
            cwd = os.readlink(f"/proc/{pid}/cwd")
        except (OSError, PermissionError):
            pass
        if needle in cmdline or needle in cwd:
            out.append(pid)
    return out


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
