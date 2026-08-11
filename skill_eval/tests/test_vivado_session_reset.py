"""Tests for the script-based per-case Vivado session reset.

``reset: {kind: python}`` replaced a ``kind: prompt`` action that asked the
agent to "confirm that ipcfg::cleanup has been run". These tests pin the
properties that made the conversion worth doing:

  * the reset acts on the group's EXISTING session -- it never starts or stops
    Vivado (that would defeat the shared-session design);
  * the baseline part comes from an argument, so a case that swapped the part
    cannot leave the group elsewhere, and cells are matched by pattern rather
    than by a name only the previous agent knew;
  * cells are deleted BEFORE the part is restored, since a case may have
    swapped to a part whose IP the baseline part cannot host;
  * a reset that cannot prove it completed fails loudly (exit non-zero), which
    the runner now treats as fatal to the group.

The MCP transport is faked; nothing here starts Vivado.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skills_testing.runtime import vivado_session_reset as vsr


class _FakeSession:
    def __init__(self, *, exec_text="RESET_CELLS:\nRESET_PART:xcx\nRESET_DONE",
                 list_text=None, exec_error=False):
        self.calls: list[tuple[str, dict]] = []
        self._exec_text = exec_text
        self._list_text = list_text or json.dumps({"sessions": {}})
        self._exec_error = exec_error
        self.closed = False

    def initialize(self):
        self.calls.append(("initialize", {}))

    def call(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "vivado_execute":
            return {"result": {"isError": self._exec_error,
                               "content": [{"type": "text",
                                            "text": self._exec_text}]}}
        if name == "vivado_list_sessions":
            return {"result": {"content": [{"type": "text",
                                            "text": self._list_text}]}}
        return {"result": {"content": []}}

    def close(self):
        self.closed = True

    def tool_names(self):
        return [n for n, _ in self.calls]

    def executed_tcl(self):
        return "\n".join(a.get("command", "") for n, a in self.calls
                         if n == "vivado_execute")


def _patch(monkeypatch, fake):
    monkeypatch.setattr(vsr, "MCPSession", lambda url, timeout: fake)
    monkeypatch.setattr(vsr, "server_url", lambda: "http://fake/mcp")


def _reset(fake, **kw):
    kw.setdefault("part", "xc2ve3558-sfva1440-2MP-e-S")
    kw.setdefault("bd_name", "benchmark_bd")
    kw.setdefault("cell_patterns", ["bench_cell_*"])
    kw.setdefault("port_patterns", ["STUB_*"])
    kw.setdefault("session_id", "sess-existing")
    return vsr.reset_session(**kw)


# ---- session handling ---------------------------------------------------


def test_reset_reuses_the_group_session_and_never_starts_or_stops_vivado(
        monkeypatch):
    fake = _FakeSession()
    _patch(monkeypatch, fake)

    ok, transcript, err = _reset(fake)

    assert ok is True and err == ""
    assert "vivado_start" not in fake.tool_names()
    assert "vivado_stop" not in fake.tool_names()
    assert fake.closed is True           # HTTP client only
    assert "RESET_DONE" in transcript
    # It acted on the id it was given, not one it discovered.
    assert ("vivado_execute", ) not in fake.calls  # sanity: args are recorded
    assert any(a.get("session_id") == "sess-existing"
               for n, a in fake.calls if n == "vivado_execute")


def test_empty_session_id_falls_back_to_the_workspace_session(monkeypatch, tmp_path):
    """The runner substitutes {session_id} from group.session_ids; an older
    spec or a setup that printed no sentinel leaves it empty, and the session
    is then identified by the workspace it belongs to."""
    listing = json.dumps({"sessions": {
        "vivado-other": {"working_dir": "/somewhere/else"},
        "vivado-mine": {"working_dir": str(tmp_path)},
    }})
    fake = _FakeSession(list_text=listing)
    _patch(monkeypatch, fake)

    ok, _t, err = _reset(fake, session_id=None, working_dir=tmp_path)

    assert ok is True, err
    assert any(a.get("session_id") == "vivado-mine"
               for n, a in fake.calls if n == "vivado_execute")


def test_ambiguous_workspace_match_refuses_to_guess(monkeypatch, tmp_path):
    """Resetting the wrong group's design would corrupt a run that is
    currently mid-case, so two candidates is an error, not a coin flip."""
    listing = json.dumps({"sessions": {
        "vivado-a": {"working_dir": str(tmp_path)},
        "vivado-b": {"working_dir": str(tmp_path)},
    }})
    fake = _FakeSession(list_text=listing)
    _patch(monkeypatch, fake)

    ok, _t, err = _reset(fake, session_id=None, working_dir=tmp_path)

    assert ok is False
    assert "refusing to guess" in err
    assert "vivado_execute" not in fake.tool_names()


def test_no_matching_session_is_an_error_that_names_what_is_live(
        monkeypatch, tmp_path):
    listing = json.dumps({"sessions": {"vivado-x": {"working_dir": "/elsewhere"}}})
    fake = _FakeSession(list_text=listing)
    _patch(monkeypatch, fake)

    ok, _t, err = _reset(fake, session_id=None, working_dir=tmp_path)

    assert ok is False
    assert "vivado-x" in err and str(tmp_path) in err


# ---- the TCL payload ---------------------------------------------------


def test_cells_are_deleted_before_the_part_is_restored():
    """Cases 016/017 swap to xcvc1902 because clk_wizard is unsupported on the
    baseline part. Restoring the part first would leave an unsupportable cell
    in the design."""
    tcl = vsr.build_tcl(part="xc2ve3558-sfva1440-2MP-e-S",
                        bd_name="benchmark_bd",
                        cell_patterns=["bench_cell_*"],
                        port_patterns=["STUB_*"])

    assert tcl.index("get_bd_cells -quiet bench_cell_*") < tcl.index("set_property PART")


def test_each_reset_carries_a_fresh_nonce_so_the_server_cannot_dedupe_it(
        monkeypatch):
    """Regression, found in a live 31-case run: the MCP server dedupes
    vivado_execute by command text. Every case's reset is otherwise identical,
    so case 2's reset came back 'SKIPPED (duplicate): ... already completed
    successfully 54 seconds ago' with case 1's result replayed and nothing
    executed -- the design was never cleaned."""
    fake = _FakeSession()
    _patch(monkeypatch, fake)

    _reset(fake)
    _reset(fake)

    sent = [a["command"] for n, a in fake.calls if n == "vivado_execute"]
    assert len(sent) == 2
    assert sent[0] != sent[1], "identical text would be deduped by the server"
    # The nonce is the ONLY difference -- the work itself stays deterministic.
    strip = lambda t: "\n".join(l for l in t.splitlines()
                                if not l.startswith("# reset-nonce:"))
    assert strip(sent[0]) == strip(sent[1])


def test_a_deduped_reset_reports_that_nothing_ran(monkeypatch):
    """If the nonce ever fails to vary, the error must say the design is not at
    baseline -- the server's reply otherwise looks like success."""
    fake = _FakeSession(
        exec_text="SKIPPED (duplicate): This command already completed "
                  "successfully 54 seconds ago.\nPrevious result: RESET_CELLS:x")
    _patch(monkeypatch, fake)

    ok, _t, err = _reset(fake)

    assert ok is False
    assert "deduplicated" in err and "NOT at baseline" in err


def test_deletions_are_saved_before_the_part_restore_closes_the_design():
    """Regression, found live: the deletes are in-memory and
    ``close_bd_design`` discards unsaved changes, so a part restore reloaded
    the last-saved .bd and brought every deleted cell and stub port back --
    while the reset still reported success."""
    tcl = vsr.build_tcl(part="xc2ve3558-sfva1440-2MP-e-S", bd_name="benchmark_bd",
                        cell_patterns=["bench_cell_*"], port_patterns=["STUB_*"])

    assert tcl.index("save_bd_design") < tcl.index("close_bd_design")
    assert tcl.index("delete_bd_objs") < tcl.index("save_bd_design")


def test_part_restore_is_unconditional_intent_not_inherited_state():
    """The old prompt passed $orig_part -- a Tcl variable a fresh agent could
    only inherit by luck, and which ipcfg::cleanup reads as 'don't restore'
    when empty. The part is now named outright."""
    tcl = vsr.build_tcl(part="xc2ve3558-sfva1440-2MP-e-S", bd_name="bd",
                        cell_patterns=[], port_patterns=[])

    assert "orig_part" not in tcl
    assert 'ne "xc2ve3558-sfva1440-2MP-e-S"' in tcl
    assert "set_property PART xc2ve3558-sfva1440-2MP-e-S [current_project]" in tcl
    # Reopens the BD after the close/set/open cycle, or the next case has no
    # design to work in.
    assert "open_bd_design $_bd" in tcl


def test_reset_is_a_no_op_when_the_case_left_nothing_behind():
    """Every lookup is -quiet/guarded so a reset following a case that created
    nothing (or cleaned up after itself) succeeds instead of erroring."""
    tcl = vsr.build_tcl(part="p", bd_name="bd",
                        cell_patterns=["bench_cell_*"], port_patterns=["STUB_*"])

    for probe in ("get_bd_cells", "get_bd_intf_ports", "get_bd_ports",
                  "get_bd_intf_nets", "get_bd_nets"):
        for line in tcl.splitlines():
            if probe in line:
                assert "-quiet" in line, line


def test_every_cell_and_port_pattern_is_covered():
    tcl = vsr.build_tcl(part="p", bd_name="bd",
                        cell_patterns=["bench_cell_*", "tmp_*"],
                        port_patterns=["STUB_*", "DBG_*"])

    for pat in ("bench_cell_*", "tmp_*", "STUB_*", "DBG_*"):
        assert pat in tcl


# ---- failure signalling ------------------------------------------------


def test_missing_sentinel_fails_loudly(monkeypatch):
    """No RESET_DONE means we cannot prove the design is at baseline. The
    runner turns this into a group-fatal error rather than letting later cases
    run against unknown state."""
    fake = _FakeSession(exec_text="ERROR: [BD 5-104] something went wrong")
    _patch(monkeypatch, fake)

    ok, _t, err = _reset(fake)

    assert ok is False
    assert "did not complete" in err


def test_failed_reset_leaves_the_session_up_for_inspection(monkeypatch):
    """Unlike setup's failure path, reset must NOT stop the session -- the
    group's teardown owns it, and its state is the evidence."""
    fake = _FakeSession(exec_text="nothing useful", exec_error=True)
    _patch(monkeypatch, fake)

    ok, _t, _err = _reset(fake)

    assert ok is False
    assert "vivado_stop" not in fake.tool_names()


def test_rejected_execute_is_recovered_rather_than_re_sent(monkeypatch):
    """A '[REJECTED] ... already running' reply means the TCL may still be
    running. Re-sending it would double-apply the deletes (a second
    delete_bd_objs on a gone cell errors), so the outcome is recovered from
    vivado_status instead."""
    fake = _FakeSession(exec_text="[REJECTED] Command '# --- harness suite "
                                   "reset' is already running")
    _patch(monkeypatch, fake)
    monkeypatch.setattr(
        vsr, "await_command",
        lambda sess, sid, *, deadline, transcript, sleep=None: (
            True, "RESET_DONE"))

    ok, _t, err = _reset(fake)

    assert ok is True, err
    assert fake.executed_tcl().count("harness suite reset") == 1


def test_unrecoverable_deferred_result_fails(monkeypatch):
    fake = _FakeSession(exec_text="[REJECTED] already running")
    _patch(monkeypatch, fake)
    monkeypatch.setattr(
        vsr, "await_command",
        lambda sess, sid, *, deadline, transcript, sleep=None: (
            False, "timed out waiting"))

    ok, _t, err = _reset(fake)

    assert ok is False
    assert "never completed" in err


# ---- CLI wiring --------------------------------------------------------


def test_cli_defaults_port_pattern_and_reports_exit_codes(monkeypatch, tmp_path):
    fake = _FakeSession()
    _patch(monkeypatch, fake)

    rc = vsr.main([
        "--part=xc2ve3558-sfva1440-2MP-e-S",
        "--bd-name=benchmark_bd",
        "--cell-pattern=bench_cell_*",
        "--session-id=sess-existing",
        f"--working-dir={tmp_path}",
    ])

    assert rc == 0
    assert "STUB_*" in fake.executed_tcl()   # default port pattern applied


def test_cli_treats_an_unsubstituted_empty_session_id_as_discover(
        monkeypatch, tmp_path):
    """`--session-id={session_id}` resolves to an empty string when the group
    has no recorded session; that must mean 'discover', not 'reset a session
    literally named empty'."""
    listing = json.dumps({"sessions": {"vivado-mine": {"working_dir": str(tmp_path)}}})
    fake = _FakeSession(list_text=listing)
    _patch(monkeypatch, fake)

    rc = vsr.main([
        "--part=p", "--cell-pattern=bench_cell_*",
        "--session-id=", f"--working-dir={tmp_path}",
    ])

    assert rc == 0
    assert "vivado_list_sessions" in fake.tool_names()


def test_cli_returns_nonzero_when_the_reset_fails(monkeypatch, tmp_path, capsys):
    fake = _FakeSession(exec_text="broken")
    _patch(monkeypatch, fake)

    rc = vsr.main(["--part=p", "--cell-pattern=bench_cell_*",
                   "--session-id=s", f"--working-dir={tmp_path}"])

    assert rc == 1
    assert "did not complete" in capsys.readouterr().err
