"""
Deterministic Vivado session setup for a suite's ``setup:`` action.

Starts ONE Vivado MCP session, runs a TCL payload in it (set the part,
create/open the shared block design, source a skill's helper library), then
**leaves the session alive** for every case in the suite to reuse. That last
part is the whole point, and the reason this can't just call
``verifiers/vivado_mcp.py:vivado_mcp_verifier`` -- that one stops the session
it creates, because a verifier wants an isolated throwaway.

Why a program instead of ``setup: {kind: prompt}``:
  * Determinism. A prompt-based setup makes an LLM turn the gate on all of a
    suite's cases -- if it improvises, every case inherits the damage, and the
    failures look like skill failures.
  * No tokens, no timeout risk, no variance -- which matters now that
    run-to-run consistency is the signoff bar (see CLAUDE.md "Development
    priorities").
  * Arm-symmetry. The same script can back ``setup:`` and
    ``setup_without_skill:``; the no-skill arm just passes no ``--source``,
    since its skill tree isn't staged.

Contract with the runner (``core/runner.py:_run_lifecycle_action``): on
success this prints

    VIVADO_SESSION_ID:<id>

on stdout and exits 0. The runner parses that line into
``group.session_ids``, which seeds ``carried_session_ids`` for every case in
the group, so each case's prompt is told to reuse this session instead of
starting its own Vivado. On failure it writes a diagnostic to stderr and
exits non-zero, which the runner records as ``suite setup failed``.

Invoked as a ``kind: python`` lifecycle action with ``args``::

    setup:
      kind: python
      script: setup_session.py        # resolved against the suite dir
      args:
        - --part=xc2ve3558-sfva1440-2MP-e-S
        - --bd-name=benchmark_bd
        - --source-skill-lib=ip-configurator/lib/ipcfg.tcl
      timeout_seconds: 900

or directly::

    python -m skills_testing.runtime.vivado_session_setup --part <part> ...
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Iterator, Optional

from ..verifiers.vivado_mcp import (
    MCPSession,
    extract_text,
    parse_session_id,
    server_url,
    vivado_path,
)

#: Sentinel the runner greps for on stdout. Keep in sync with
#: ``core/runner.py:_SESSION_ID_SENTINEL``.
SESSION_ID_SENTINEL = "VIVADO_SESSION_ID:"


#: Substrings that mean "your command may have been accepted, but this
#: response does not carry its result" -- observed from the Vivado MCP server
#: when two sessions are started at once: a "[REJECTED] ... is already
#: running" for one and a connection-drop notice for the other, the latter
#: explicitly instructing clients to check ``vivado_status`` instead of
#: re-issuing ``vivado_execute``.
_DEFERRED_RESULT_HINTS = (
    "[REJECTED]",
    "is already running",
    "connection drop",
    "thread-handling",
    "do not call vivado_execute",
)


def _is_error(result: dict[str, Any]) -> bool:
    inner = result.get("result") or {}
    return bool(inner.get("isError"))


def _looks_deferred(text: str) -> bool:
    low = (text or "").lower()
    return any(h.lower() in low for h in _DEFERRED_RESULT_HINTS)


@contextlib.contextmanager
def server_lock(url: str, *, timeout_seconds: float = 600.0,
                enabled: bool = True,
                launch_gap_seconds: float = 0.0) -> Iterator[bool]:
    """Reserve a globally staggered launch slot on one Vivado MCP server.

    Parallel suite groups share this advisory ``flock`` (keyed by server URL).
    Once held, the lock waits until ``launch_gap_seconds`` have elapsed since
    the previous reservation, records the new reservation time, and yields.
    The caller must leave the context *before* starting Vivado: reservations
    are serialized, but the expensive ``vivado_start`` and setup TCL calls are
    then free to overlap. This matches the validated capacity-test pattern.

    Yields True when held, False when lock acquisition timed out. Callers still
    proceed on timeout rather than failing a suite on coordination alone.
    """
    if not enabled:
        yield True
        return
    digest = hashlib.sha256(url.encode()).hexdigest()[:16]
    lock_path = Path(tempfile.gettempdir()) / f"skills-test-vivado-mcp-{digest}.lock"
    deadline = time.monotonic() + timeout_seconds
    fh = open(lock_path, "w")
    try:
        held = False
        while time.monotonic() < deadline:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                held = True
                break
            except BlockingIOError:
                time.sleep(1.0)
        if held:
            stamp_path = lock_path.with_suffix(".last-launch")
            if launch_gap_seconds > 0:
                try:
                    previous = float(stamp_path.read_text().strip())
                except (OSError, ValueError):
                    previous = 0.0
                wait = launch_gap_seconds - (time.time() - previous)
                if wait > 0:
                    time.sleep(wait)
                stamp_path.write_text(f"{time.time():.6f}\n")
            fh.write(f"{os.getpid()}\n")
            fh.flush()
        yield held
    finally:
        with contextlib.suppress(Exception):
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        fh.close()


def await_command(
    sess: Any, session_id: str, *, deadline: float,
    transcript: list[str], sleep=time.sleep,
) -> tuple[bool, str]:
    """Recover the result of an execute whose response didn't carry one.

    The server's own instruction for this case is to sleep, then call
    ``vivado_status`` **once** -- it tracks poll frequency and returns
    throttled cached responses to callers that spin -- so back off
    geometrically rather than polling tightly.

    Returns ``(completed, detail)`` where *detail* is the recovered output
    (``last_completed_output``, else ``status_summary``) or the reason we gave up.
    """
    delay = 3.0
    while time.monotonic() < deadline:
        sleep(delay)
        status_text = extract_text(sess.call(
            "vivado_status", {"session_id": session_id, "action": "session"}))
        transcript.append(f"# vivado_status\n{status_text}")
        try:
            obj = json.loads(status_text)
        except (json.JSONDecodeError, TypeError):
            obj = {}
        if obj.get("process_running") is False:
            return False, "Vivado process is no longer running"
        if obj.get("is_command_running") is False:
            return True, str(obj.get("last_completed_output")
                             or obj.get("status_summary") or "")
        delay = min(delay * 1.6, 30.0)
    return False, "timed out waiting for the setup command to complete"


def build_tcl(
    *,
    part: str,
    bd_name: str,
    project_name: str,
    sources: list[str],
    nonce: str = "",
) -> str:
    """Render the setup TCL: in-memory project on *part*, a block design, and
    each *sources* file sourced once.

    Deliberately idempotent -- ``create_project -in_memory`` on an already-open
    project and ``create_bd_design`` for an existing name both error, so both
    are guarded. That makes a re-run after a partial failure safe instead of
    leaving the group wedged.
    """
    lines = [
        "# --- harness suite setup (skills_testing.runtime.vivado_session_setup) ---",
    ]
    if nonce:
        # The MCP server dedupes vivado_execute by command text and replays the
        # earlier result without running anything (see vivado_session_reset for
        # the case that caught this). Setup usually varies via the absolute
        # --source paths, but a suite that sources nothing -- e.g. the no-skill
        # A/B arm -- produces byte-identical TCL every time.
        lines.append(f"# setup-nonce: {nonce}")
    lines += [
        f"if {{[catch {{current_project}}]}} {{",
        f"    create_project -in_memory -part {part} {project_name}",
        "} else {",
        f"    set_property PART {part} [current_project]",
        "}",
        # Probe with get_files -quiet only. `current_bd_design` writes
        # "ERROR: [BD 5-104] A block design must be open" to stderr even
        # inside a catch, and that string then shows up in the session's
        # stderr_output -- which the skill's own output-scan backstop reads as
        # a failure signal. create_bd_design opens what it creates, so the
        # file check alone is enough.
        f"if {{[llength [get_files -quiet {bd_name}.bd]] == 0}} {{",
        f"    create_bd_design {bd_name}",
        "} else {",
        f"    open_bd_design [get_files -quiet {bd_name}.bd]",
        "}",
    ]
    for src in sources:
        # Sourced ONCE per session here; the persistent session means every
        # case in the suite inherits the procs without re-sourcing.
        lines += [
            f"if {{[catch {{source {{{src}}}}} _src_err]}} {{",
            f'    puts stderr "SETUP_SOURCE_FAILED:{src}:$_src_err"',
            f'    return -code error "source failed: {src}"',
            "}",
        ]
    lines += [
        f'puts "SETUP_PART:[get_property PART [current_project]]"',
        'puts "SETUP_BD:[current_bd_design]"',
        'puts "SETUP_DONE"',
    ]
    return "\n".join(lines)


def start_session(
    *,
    working_dir: Path,
    part: str,
    bd_name: str,
    project_name: str,
    sources: list[str],
    session_type: str = "ipi",
    timeout_seconds: int = 900,
    url: Optional[str] = None,
) -> tuple[Optional[str], str, str]:
    """Start a Vivado session, apply the setup TCL, and leave it running.

    Returns ``(session_id | None, stdout_transcript, stderr_detail)``. The
    session is intentionally NOT stopped on success. On failure it IS stopped,
    so a botched setup doesn't leak a Vivado process for the suite's lifetime.
    """
    transcript: list[str] = []
    sess = MCPSession(url or server_url(), timeout_seconds)
    session_id: Optional[str] = None
    try:
        try:
            sess.initialize()
        except Exception as exc:
            return None, "", f"MCP init failed against {url or server_url()}: {exc}"

        start_res = sess.call("vivado_start", {
            "working_dir": str(working_dir),
            "session_type": session_type,
            "vivado_path": vivado_path(),
            "display_mode": "none",
        })
        start_text = extract_text(start_res)
        transcript.append(f"# vivado_start\n{start_text}")
        if _is_error(start_res):
            return None, "\n".join(transcript), f"vivado_start isError:\n{start_text}"

        session_id = parse_session_id(start_text)
        if not session_id:
            return None, "\n".join(transcript), (
                "vivado_start returned no session_id; cannot hand a session to "
                f"the suite's cases. Raw result:\n{start_text}")

        tcl = build_tcl(part=part, bd_name=bd_name,
                        project_name=project_name, sources=sources,
                        nonce=uuid.uuid4().hex)
        exec_res = sess.call("vivado_execute", {
            "session_id": session_id, "command": tcl})
        exec_text = extract_text(exec_res)
        transcript.append(f"# vivado_execute\n{exec_text}")

        # The response may not carry the result: under concurrent starts the
        # server answers "[REJECTED] ... already running" or drops the
        # connection mid-command and tells the client to consult
        # vivado_status. Re-issuing the TCL would double-apply it, so ask the
        # server what happened instead.
        if "SETUP_DONE" not in exec_text and _looks_deferred(exec_text):
            completed, detail = await_command(
                sess, session_id,
                deadline=time.monotonic() + max(60.0, timeout_seconds / 2),
                transcript=transcript)
            exec_text = f"{exec_text}\n{detail}"
            if not completed:
                try:
                    sess.call("vivado_stop", {"session_id": session_id})
                except Exception:
                    pass
                return None, "\n".join(transcript), (
                    f"setup command never completed: {detail}")

        # SETUP_DONE is the authoritative signal -- it is the last line the TCL
        # prints. An isError response that was nonetheless recovered above (the
        # REJECTED case) is not a failure if the TCL demonstrably ran.
        failed = "SETUP_DONE" not in exec_text
        if failed:
            # Stop the half-built session rather than leaving Vivado pinned
            # for the whole suite on a setup we already know is broken.
            try:
                sess.call("vivado_stop", {"session_id": session_id})
            except Exception:
                pass
            return None, "\n".join(transcript), (
                f"setup TCL did not complete (no SETUP_DONE):\n{exec_text}")

        return session_id, "\n".join(transcript), ""
    finally:
        # Closes the HTTP client only. The Vivado session lives on server-side
        # under session_id -- that is what the cases reuse.
        sess.close()


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="vivado_session_setup",
        description="Start a shared Vivado MCP session for a suite and leave "
                    "it open, printing VIVADO_SESSION_ID:<id> for the runner.")
    ap.add_argument("--part", required=True,
                    help="Device part the shared block design is built on")
    ap.add_argument("--bd-name", default="benchmark_bd",
                    help="Block-design name to create/open (default: %(default)s)")
    ap.add_argument("--project-name", default="harness_setup",
                    help="In-memory project name (default: %(default)s)")
    ap.add_argument("--source", action="append", default=[], metavar="TCL",
                    help="Absolute path to a TCL file to source once in the "
                         "session. Repeatable. Omit entirely for the no-skill "
                         "arm, which has no staged skill tree to source from")
    ap.add_argument("--source-skill-lib", action="append", default=[],
                    metavar="REL",
                    help="Like --source but resolved against the workspace's "
                         "staged skills dir, e.g. "
                         "'ip-configurator/lib/ipcfg.tcl'. Keeps the suite "
                         "spec free of absolute paths")
    ap.add_argument("--skills-dir", default=".claude/skills",
                    help="Workspace-relative staged skills root used to "
                         "resolve --source-skill-lib (default: %(default)s)")
    ap.add_argument("--working-dir", default=".",
                    help="Vivado session working dir (default: cwd, which the "
                         "runner sets to the group's workspace)")
    ap.add_argument("--session-type", default="ipi", choices=("ipi", "general"),
                    help="Vivado MCP session type (default: %(default)s)")
    ap.add_argument("--timeout-seconds", type=int, default=900)
    ap.add_argument("--no-serialize", action="store_true",
                    help="Skip the advisory lock that serializes session "
                         "creation against one MCP server. The lock exists "
                         "because two groups starting setup simultaneously hit "
                         "the server's webserver thread-handling issue "
                         "([REJECTED] / dropped connection)")
    ap.add_argument("--lock-timeout-seconds", type=float, default=600.0,
                    help="How long to wait for that lock before proceeding "
                         "anyway (default: %(default)s)")
    ap.add_argument("--launch-gap-seconds", type=float, default=0.0,
                    help="Minimum global gap between Vivado starts sharing "
                         "this MCP URL (default: disabled)")
    args = ap.parse_args(argv)

    working_dir = Path(args.working_dir).resolve()
    sources = [str(Path(s).resolve()) for s in args.source]
    for rel in args.source_skill_lib:
        resolved = (working_dir / args.skills_dir / rel).resolve()
        if not resolved.is_file():
            # Most likely cause: --skills-dir names the wrong client's staged
            # tree (opencode uses .opencode/skills, Claude Code/Copilot
            # .claude/skills), so show what IS staged rather than just the
            # miss. Pass --skills-dir={skills_dir} in runner_spec.yaml args to
            # have the runner fill in the right one per client.
            staged = sorted(
                str(p.relative_to(working_dir))
                for p in working_dir.glob("*/skills/*")
            ) or ["<nothing staged>"]
            print(f"--source-skill-lib not found: {resolved}\n"
                  f"  --skills-dir={args.skills_dir} under {working_dir}\n"
                  f"  staged skill trees: {', '.join(staged)}",
                  file=sys.stderr)
            return 2
        sources.append(str(resolved))

    with server_lock(server_url(),
                     timeout_seconds=args.lock_timeout_seconds,
                     enabled=not args.no_serialize,
                     launch_gap_seconds=args.launch_gap_seconds) as held:
        if not held:
            print(f"proceeding without the MCP launch lock after "
                  f"{args.lock_timeout_seconds}s wait", file=sys.stderr)
    session_id, transcript, err = start_session(
        working_dir=working_dir,
        part=args.part,
        bd_name=args.bd_name,
        project_name=args.project_name,
        sources=sources,
        session_type=args.session_type,
        timeout_seconds=args.timeout_seconds,
    )
    if transcript:
        print(transcript)
    if not session_id:
        print(err, file=sys.stderr)
        return 1
    # The runner greps this line; keep it last and on its own line.
    print(f"{SESSION_ID_SENTINEL}{session_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
