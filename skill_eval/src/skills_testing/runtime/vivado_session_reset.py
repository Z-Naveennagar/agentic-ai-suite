"""
Deterministic Vivado session reset for a suite's ``reset:`` action.

Restores the shared block design to baseline between cases: deletes the
throwaway cells the last case created and puts the project part back, in the
**already-running** session that ``vivado_session_setup`` handed the group.
The session is left alive -- it belongs to the group, not to any one case.

Why a program instead of ``reset: {kind: prompt}``:
  * Determinism, the same argument the ``setup:`` action already makes -- but
    reset runs once per *case* rather than once per group, so a prompt-based
    reset multiplies LLM variance by the suite's case count.
  * A prompt can only *ask* for cleanup. The previous ip-configurator reset
    said "confirm that ``ipcfg::cleanup`` has been run… if it did not run, run
    it now", which a stateless agent can satisfy with text alone, and nothing
    graded or verified it.
  * A fresh CLI process knows neither which cell the last case created nor
    what the part was before a swap. The prompt passed ``$orig_part``, a Tcl
    variable it could only inherit if the previous agent happened to set it at
    global scope; when unset, ``ipcfg::cleanup`` treats it as "don't restore"
    and the part silently stays swapped for every later case in the group.
    This program takes the baseline part as an argument instead of hoping to
    recover it, and matches cells by pattern instead of by name.

Contract with the runner (``core/runner.py:_run_lifecycle_action``): exits 0
after printing ``RESET_DONE``-bearing transcript on stdout; on failure writes
a diagnostic to stderr and exits non-zero, which the runner now treats as
fatal to the rest of the group (a silently dirty block design is worse than a
loud stop, because it fails *later* cases that have nothing wrong with them).

Invoked as a ``kind: python`` lifecycle action with ``args``::

    reset:
      kind: python
      module: skills_testing.runtime.vivado_session_reset
      args:
        - --part=xc2ve3558-sfva1440-2MP-e-S
        - --bd-name=benchmark_bd
        - --cell-pattern=bench_cell_*
        - --session-id={session_id}
      timeout_seconds: 300

``{session_id}`` is substituted by the runner with the group's live session
(the one ``setup:`` printed via ``VIVADO_SESSION_ID:``). When it resolves
empty -- an older spec, or a group whose setup printed no sentinel -- this
falls back to finding the session whose ``working_dir`` is the workspace it
was invoked in, which is exactly the group's workspace.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from ..verifiers.vivado_mcp import MCPSession, extract_text, server_url
from .vivado_session_setup import _is_error, _looks_deferred, await_command

#: Last line the reset TCL prints; the authoritative success signal, mirroring
#: ``SETUP_DONE`` in vivado_session_setup.
RESET_DONE_SENTINEL = "RESET_DONE"


def build_tcl(
    *,
    part: str,
    bd_name: str,
    cell_patterns: list[str],
    port_patterns: list[str],
    nonce: str = "",
) -> str:
    """Render the reset TCL: drop throwaway cells/ports, then restore *part*.

    Cells are deleted **before** the part is restored, deliberately. A case
    may have swapped the project to a part that supports an IP the baseline
    part does not (ip-configurator's clk_wizard cases swap to ``xcvc1902``
    because ``clk_wizard:1.0`` is unsupported on ``xc2ve3558``); restoring the
    part first would leave an unsupportable cell in the design.

    Everything is guarded/``-quiet`` so a reset after a case that created
    nothing -- or that already cleaned up after itself -- is a no-op rather
    than an error.
    """
    lines = [
        "# --- harness suite reset (skills_testing.runtime.vivado_session_reset) ---",
    ]
    if nonce:
        # The MCP server deduplicates vivado_execute by command text: an
        # identical command inside its window comes back "SKIPPED (duplicate):
        # This command already completed successfully N seconds ago" WITHOUT
        # running. Every case's reset is otherwise byte-identical (same part,
        # same patterns), so case 2's reset was answered with case 1's result
        # and the design was never actually cleaned. A per-invocation nonce
        # keeps the text unique; it changes nothing about what the TCL does.
        lines.append(f"# reset-nonce: {nonce}")
    lines.append("set _removed {}")
    for pat in cell_patterns:
        lines += [
            f"foreach _c [get_bd_cells -quiet {pat}] {{",
            "    lappend _removed [get_property NAME $_c]",
            "    catch {delete_bd_objs [get_bd_intf_nets -quiet -of_objects $_c]}",
            "    catch {delete_bd_objs [get_bd_nets -quiet -of_objects $_c]}",
            "    delete_bd_objs $_c",
            "}",
        ]
    # Stub ports the skill's own helpers create to make a bare cell
    # connectable; ipcfg::cleanup removes these too, and a leftover stub port
    # would collide with the next case's stubs.
    for pat in port_patterns:
        lines += [
            f"foreach _p [get_bd_intf_ports -quiet {pat}] {{",
            "    catch {delete_bd_objs [get_bd_intf_nets -quiet -of_objects $_p]}",
            "    catch {delete_bd_objs $_p}",
            "}",
            f"foreach _p [get_bd_ports -quiet {pat}] {{",
            "    catch {delete_bd_objs [get_bd_nets -quiet -of_objects $_p]}",
            "    catch {delete_bd_objs $_p}",
            "}",
        ]
    lines += [
        # MUST come before the part restore below. The deletes above are
        # in-memory; `close_bd_design` discards unsaved changes, so restoring
        # the part would reload the last-saved .bd and RESURRECT every cell and
        # stub port we just removed. Found by a live smoke test -- the reset
        # reported success while leaving bench_cell_001 and STUB_* in the
        # design. (ipcfg::cleanup in the skill's own lib has the same
        # delete-then-close-without-save shape.)
        "catch {save_bd_design}",
        # Unconditional intent, conditional work: only touch the part when it
        # actually differs, since the close/reopen cycle is not free.
        f'if {{[get_property PART [current_project]] ne "{part}"}} {{',
        f"    set _bd [get_files -quiet {bd_name}.bd]",
        "    close_bd_design [current_bd_design]",
        f"    set_property PART {part} [current_project]",
        "    open_bd_design $_bd",
        '    puts "RESET_PART_RESTORED:1"',
        "}",
        'puts "RESET_CELLS:$_removed"',
        'puts "RESET_PART:[get_property PART [current_project]]"',
        'puts "RESET_BD:[current_bd_design]"',
        f'puts "{RESET_DONE_SENTINEL}"',
    ]
    return "\n".join(lines)


def find_session_for_workspace(
    sess: Any, working_dir: Path,
) -> tuple[Optional[str], str]:
    """Locate the live session whose ``working_dir`` is *working_dir*.

    Fallback for when the runner substituted no ``--session-id``. Returns
    ``(session_id | None, detail)``; ambiguity is an error rather than a
    guess, since resetting the wrong group's design would corrupt a run that
    is currently mid-case.
    """
    text = extract_text(sess.call("vivado_list_sessions", {}))
    try:
        obj = json.loads(text[text.index("{"):])
    except (ValueError, json.JSONDecodeError):
        return None, f"could not parse vivado_list_sessions output:\n{text}"
    sessions = obj.get("sessions", obj) or {}
    target = str(working_dir)
    matches = [sid for sid, info in sessions.items()
               if str((info or {}).get("working_dir", "")) == target]
    if not matches:
        return None, (f"no live Vivado session has working_dir {target}; "
                      f"live sessions: {sorted(sessions)}")
    if len(matches) > 1:
        return None, (f"{len(matches)} live sessions share working_dir "
                      f"{target}: {matches}; refusing to guess")
    return matches[0], ""


def reset_session(
    *,
    part: str,
    bd_name: str,
    cell_patterns: list[str],
    port_patterns: list[str],
    session_id: Optional[str] = None,
    working_dir: Optional[Path] = None,
    timeout_seconds: int = 300,
    url: Optional[str] = None,
    nonce: Optional[str] = None,
) -> tuple[bool, str, str]:
    """Apply the reset TCL in an existing session, leaving it running.

    Returns ``(ok, stdout_transcript, stderr_detail)``. The session is never
    stopped -- unlike setup's failure path, a failed reset leaves the session
    up so the group's teardown (and a human) can inspect what state the shared
    design was actually left in.
    """
    transcript: list[str] = []
    sess = MCPSession(url or server_url(), timeout_seconds)
    try:
        try:
            sess.initialize()
        except Exception as exc:
            return False, "", f"MCP init failed against {url or server_url()}: {exc}"

        if not session_id:
            session_id, detail = find_session_for_workspace(
                sess, (working_dir or Path.cwd()).resolve())
            transcript.append(f"# vivado_list_sessions\n{detail or session_id}")
            if not session_id:
                return False, "\n".join(transcript), detail

        tcl = build_tcl(part=part, bd_name=bd_name,
                        cell_patterns=cell_patterns,
                        port_patterns=port_patterns,
                        nonce=nonce if nonce is not None else uuid.uuid4().hex)
        exec_res = sess.call("vivado_execute", {
            "session_id": session_id, "command": tcl})
        exec_text = extract_text(exec_res)
        transcript.append(f"# vivado_execute\n{exec_text}")

        # Same deferred-result dance as setup: a "[REJECTED] ... already
        # running" or dropped connection means the TCL may still be running,
        # so recover the outcome from vivado_status instead of re-sending it
        # (a second delete_bd_objs on an already-deleted cell would error).
        if RESET_DONE_SENTINEL not in exec_text and _looks_deferred(exec_text):
            completed, detail = await_command(
                sess, session_id,
                deadline=time.monotonic() + max(60.0, timeout_seconds / 2),
                transcript=transcript)
            exec_text = f"{exec_text}\n{detail}"
            if not completed:
                return False, "\n".join(transcript), (
                    f"reset command never completed: {detail}")

        if RESET_DONE_SENTINEL not in exec_text:
            if "SKIPPED (duplicate)" in exec_text:
                # Should be unreachable now that every reset carries a nonce,
                # but name the cause if it ever recurs: the server replayed an
                # older identical command's result and ran nothing, so the
                # design is NOT at baseline despite a success-looking reply.
                return False, "\n".join(transcript), (
                    "the MCP server deduplicated this reset and ran nothing "
                    "(the design is therefore NOT at baseline). The nonce that "
                    f"should prevent this failed to vary:\n{exec_text}")
            reason = ("vivado_execute isError"
                      if _is_error(exec_res) else "no RESET_DONE")
            return False, "\n".join(transcript), (
                f"reset TCL did not complete ({reason}):\n{exec_text}")

        return True, "\n".join(transcript), ""
    finally:
        # Closes the HTTP client only; the Vivado session stays up for the
        # next case in the group.
        sess.close()


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="vivado_session_reset",
        description="Restore a suite's shared block design to baseline in the "
                    "group's already-running Vivado MCP session.")
    ap.add_argument("--part", required=True,
                    help="Baseline device part to restore the project to. Given "
                         "explicitly rather than recovered from session state, "
                         "so a case that swapped the part cannot leave the rest "
                         "of the group on the wrong one")
    ap.add_argument("--bd-name", default="benchmark_bd",
                    help="Block-design name to reopen after a part restore "
                         "(default: %(default)s)")
    ap.add_argument("--cell-pattern", action="append", default=[],
                    metavar="GLOB",
                    help="Block-design cell name pattern to delete, e.g. "
                         "'bench_cell_*'. Repeatable. Pattern-based so the "
                         "reset needn't know which cell the last case created")
    ap.add_argument("--port-pattern", action="append", default=[],
                    metavar="GLOB",
                    help="Stub port name pattern to delete (default: STUB_*)")
    ap.add_argument("--session-id", default="",
                    help="Live session to reset. Pass {session_id} to have the "
                         "runner fill in the group's session; when empty, the "
                         "session is discovered by matching --working-dir")
    ap.add_argument("--working-dir", default=".",
                    help="Group workspace, used to discover the session when "
                         "--session-id is empty (default: cwd, which the runner "
                         "sets to the group's workspace)")
    ap.add_argument("--timeout-seconds", type=int, default=300)
    args = ap.parse_args(argv)

    ok, transcript, err = reset_session(
        part=args.part,
        bd_name=args.bd_name,
        cell_patterns=args.cell_pattern or [],
        port_patterns=args.port_pattern or ["STUB_*"],
        session_id=args.session_id.strip() or None,
        working_dir=Path(args.working_dir),
        timeout_seconds=args.timeout_seconds,
    )
    if transcript:
        print(transcript)
    if not ok:
        print(err, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
