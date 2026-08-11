"""Tests for the script-based shared Vivado session setup.

Covers the three pieces that let a ``setup: {kind: python}`` action hand a
live Vivado session to a suite's cases:

  1. ``runtime/vivado_session_setup.py`` -- starts the session, applies the
     TCL, and does NOT stop it; reports the id via a stdout sentinel.
  2. ``core/runner.py:_parse_session_id_sentinels`` -- picks that id up, which
     kind=python/bash previously dropped (it returned [] unconditionally).
  3. ``core/case_loader.py`` -- ``args:`` passthrough and suite-relative
     ``script:`` resolution, without which a generic setup helper can't be
     parameterized or even found (cwd is the workspace, not the suite dir).

The MCP transport is faked; nothing here starts Vivado.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from skills_testing.core.case_loader import CaseSchemaError, load_suite
from skills_testing.core.runner import (
    _augment_prompt_reuse_session,
    _parse_session_id_sentinels,
)
from skills_testing.runtime import vivado_session_setup as vss


# ---- the stdout sentinel contract --------------------------------------


def test_runner_picks_up_the_session_id_sentinel():
    stdout = (
        "# vivado_start\nsession started\n"
        "# vivado_execute\nSETUP_PART:xc2ve3558\nSETUP_DONE\n"
        f"{vss.SESSION_ID_SENTINEL}sess-abc123\n"
    )
    assert _parse_session_id_sentinels(stdout) == ["sess-abc123"]


def test_sentinel_parsing_dedupes_and_preserves_order():
    stdout = (
        f"{vss.SESSION_ID_SENTINEL}first-one\n"
        f"{vss.SESSION_ID_SENTINEL}second-one\n"
        f"  {vss.SESSION_ID_SENTINEL}first-one  \n"
    )
    assert _parse_session_id_sentinels(stdout) == ["first-one", "second-one"]


@pytest.mark.parametrize("stdout", ["", "no sentinel here", "VIVADO_SESSION_ID:\n"])
def test_sentinel_parsing_returns_empty_without_a_usable_id(stdout):
    assert _parse_session_id_sentinels(stdout) == []


# ---- the setup program itself ------------------------------------------


class _FakeSession:
    """Records calls and returns canned MCP tool results."""

    def __init__(self, *, exec_text="SETUP_PART:xcx\nSETUP_BD:bd\nSETUP_DONE",
                 start_text='{"session_id": "sess-fake-01"}', exec_error=False):
        self.calls: list[tuple[str, dict]] = []
        self._exec_text = exec_text
        self._start_text = start_text
        self._exec_error = exec_error
        self.closed = False

    def initialize(self):
        self.calls.append(("initialize", {}))

    def call(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "vivado_start":
            return {"result": {"content": [{"type": "text",
                                            "text": self._start_text}]}}
        if name == "vivado_execute":
            return {"result": {"isError": self._exec_error,
                               "content": [{"type": "text",
                                            "text": self._exec_text}]}}
        return {"result": {"content": []}}

    def close(self):
        self.closed = True

    def tool_names(self):
        return [n for n, _ in self.calls]


def _patch_session(monkeypatch, fake):
    monkeypatch.setattr(vss, "MCPSession", lambda url, timeout: fake)
    monkeypatch.setattr(vss, "vivado_path", lambda: "/opt/vivado")
    monkeypatch.setattr(vss, "server_url", lambda: "http://fake/mcp")


def test_successful_setup_leaves_the_session_running(monkeypatch, tmp_path):
    """The whole point: the session must survive so the suite's cases can
    reuse it. vivado_stop here would defeat the feature."""
    fake = _FakeSession()
    _patch_session(monkeypatch, fake)

    sid, transcript, err = vss.start_session(
        working_dir=tmp_path, part="xc2ve3558-sfva1440-2MP-e-S",
        bd_name="benchmark_bd", project_name="p", sources=[])

    assert sid == "sess-fake-01"
    assert err == ""
    assert "vivado_stop" not in fake.tool_names()
    assert fake.closed is True          # HTTP client closed, session not stopped
    assert "SETUP_DONE" in transcript


def test_failed_setup_stops_the_session_it_started(monkeypatch, tmp_path):
    """A half-built session must not pin Vivado for the suite's lifetime."""
    fake = _FakeSession(exec_text="ERROR: no such part")
    _patch_session(monkeypatch, fake)

    sid, _transcript, err = vss.start_session(
        working_dir=tmp_path, part="bogus", bd_name="bd",
        project_name="p", sources=[])

    assert sid is None
    assert "SETUP_DONE" in err or "did not complete" in err
    assert "vivado_stop" in fake.tool_names()


def test_missing_session_id_is_an_error_not_a_silent_success(monkeypatch, tmp_path):
    fake = _FakeSession(start_text="Vivado up, but nothing parseable")
    _patch_session(monkeypatch, fake)

    sid, _t, err = vss.start_session(
        working_dir=tmp_path, part="p", bd_name="bd", project_name="p",
        sources=[])

    assert sid is None
    assert "session_id" in err


def test_tcl_is_idempotent_and_sources_each_lib(tmp_path):
    tcl = vss.build_tcl(part="xcvp1002", bd_name="bench_bd",
                        project_name="proj", sources=["/skills/x/lib/ipcfg.tcl"])
    # Guarded so a re-run after a partial failure doesn't wedge the group.
    assert "catch {current_project}" in tcl
    assert "create_project -in_memory -part xcvp1002 proj" in tcl
    assert "create_bd_design bench_bd" in tcl
    assert "source {/skills/x/lib/ipcfg.tcl}" in tcl
    assert "SETUP_DONE" in tcl


def test_source_skill_lib_resolves_against_the_staged_skills_dir(monkeypatch, tmp_path):
    lib = tmp_path / ".claude" / "skills" / "ip-configurator" / "lib"
    lib.mkdir(parents=True)
    (lib / "ipcfg.tcl").write_text("# helpers\n")
    captured: dict = {}

    def _fake_start(**kwargs):
        captured.update(kwargs)
        return "sess-9", "transcript", ""

    monkeypatch.setattr(vss, "start_session", _fake_start)
    rc = vss.main([
        "--part", "xcx", f"--working-dir={tmp_path}",
        "--source-skill-lib=ip-configurator/lib/ipcfg.tcl",
    ])
    assert rc == 0
    assert captured["sources"] == [str(lib / "ipcfg.tcl")]


def test_missing_skill_lib_fails_loudly(monkeypatch, tmp_path):
    """The no-skill arm has no staged skill tree; a typo'd path in the
    with-skill arm must not silently produce a session with no helpers."""
    rc = vss.main([
        "--part", "xcx", f"--working-dir={tmp_path}",
        "--source-skill-lib=nope/lib/ipcfg.tcl",
    ])
    assert rc == 2


# ---- loader support ----------------------------------------------------


def _write_suite(tmp_path: Path, setup: dict) -> Path:
    suite = tmp_path / "suite"
    (suite / "inputs").mkdir(parents=True)
    (suite / "test_cases.yaml").write_text(yaml.safe_dump({
        "suite_id": "s", "test_cases": [
            {"id": "c1", "input_files": [], "prompt": "do it",
             "expected": {"skills": ["x"]}},
        ],
    }))
    (suite / "grader_spec.yaml").write_text(yaml.safe_dump({
        "output_schema": {"skill_triggered": {"grader": "trigger",
                                              "mandatory": True,
                                              "grader_args": "{skills}"}},
    }))
    (suite / "runner_spec.yaml").write_text(yaml.safe_dump({
        "skill_name": "x", "suite_id": "s",
        "invocation": {"coding_agent": [{"name": "opencode", "model": "m"}]},
        "requirements": {},
        "setup": setup,
    }))
    return suite


def test_args_are_parsed_and_script_resolved_against_the_suite_dir(tmp_path):
    suite = _write_suite(tmp_path, {
        "kind": "python", "script": "setup_session.py",
        "args": ["--part=xcx", "--bd-name=bench_bd"],
    })
    (suite / "setup_session.py").write_text("print('hi')\n")

    cases = load_suite(suite)
    action = cases[0].setup_action
    assert action["args"] == ["--part=xcx", "--bd-name=bench_bd"]
    # Absolute, because the runner runs it with cwd=<workspace>, not the suite.
    assert action["script"] == str((suite / "setup_session.py").resolve())


def test_missing_script_is_rejected_at_load_time(tmp_path):
    suite = _write_suite(tmp_path, {"kind": "python", "script": "nope.py"})
    with pytest.raises(CaseSchemaError, match="not found"):
        load_suite(suite)


def test_args_rejected_for_bash_kind(tmp_path):
    suite = _write_suite(tmp_path, {
        "kind": "bash", "command": "echo hi", "args": ["--x"]})
    with pytest.raises(CaseSchemaError, match="only supported for kind='python'"):
        load_suite(suite)


# ---- the session-notice wording split ---------------------------------


def test_shared_session_notice_does_not_claim_a_timeout():
    out = _augment_prompt_reuse_session("TASK", ["sess-1"], after_timeout=False)
    assert "sess-1" in out
    assert "timed out" not in out
    assert "continue from where the prior attempt left off" not in out
    assert "no work on THIS task has been done yet" in out


def test_retry_notice_still_explains_the_timeout():
    out = _augment_prompt_reuse_session("TASK", ["sess-1"], after_timeout=True)
    assert "timed out" in out
    assert "continue from where the prior attempt left off" in out


def test_default_is_the_shared_session_wording():
    """First attempts are the common case and must not be told they failed."""
    assert "timed out" not in _augment_prompt_reuse_session("T", ["s"])


def test_module_form_needs_no_shim_script(tmp_path):
    """`module:` lets a shared helper back many suites' setup without each one
    carrying a shim, and it runs under sys.executable so `skills_testing` is
    importable by construction (unlike a bash `python -m`, which depends on
    whatever `python` resolves to on PATH -- this host has no bare `python`)."""
    suite = _write_suite(tmp_path, {
        "kind": "python",
        "module": "skills_testing.runtime.vivado_session_setup",
        "args": ["--part=xcx", "--source-skill-lib=x/lib/y.tcl"],
    })
    action = load_suite(suite)[0].setup_action
    assert action["module"] == "skills_testing.runtime.vivado_session_setup"
    assert action["script"] is None
    assert action["args"] == ["--part=xcx", "--source-skill-lib=x/lib/y.tcl"]


def test_python_kind_requires_script_or_module(tmp_path):
    suite = _write_suite(tmp_path, {"kind": "python", "args": ["--x"]})
    with pytest.raises(CaseSchemaError, match="either .script or .module"):
        load_suite(suite)


def test_script_and_module_together_is_rejected(tmp_path):
    suite = _write_suite(tmp_path, {
        "kind": "python", "script": "s.py", "module": "m"})
    (suite / "s.py").write_text("")
    with pytest.raises(CaseSchemaError, match="pick one"):
        load_suite(suite)


# ---- client-specific staged skills dir ---------------------------------


def test_skills_dir_token_is_substituted_per_client(monkeypatch, tmp_path):
    """Regression: the first real end-to-end run failed because the suite
    hardcoded .claude/skills while the client was opencode, which stages into
    .opencode/skills (create_workspace's skills_dest=skills_dir_for(client)).
    The runner substitutes {skills_dir} so one spec works for every backend."""
    from skills_testing.core.runner import SkillRunner

    class _Cli:
        workspace_skills_dir = ".opencode/skills"

        def invoke(self, **_kw):  # pragma: no cover - not used here
            raise AssertionError("kind=python must not invoke the CLI")

    captured: dict = {}

    class _Proc:
        returncode = 0
        stdout = "VIVADO_SESSION_ID:sess-77\n"
        stderr = ""

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _Proc()

    monkeypatch.setattr("subprocess.run", _fake_run)
    runner = SkillRunner.__new__(SkillRunner)      # no __init__ side effects
    result = SkillRunner._run_lifecycle_action(
        runner,
        {"kind": "python", "module": "m", "script": None,
         "args": ["--skills-dir={skills_dir}", "--wd={workspace}"],
         "timeout_seconds": 60},
        cli=_Cli(), ws_dir=tmp_path,
    )

    assert "--skills-dir=.opencode/skills" in captured["cmd"]
    assert f"--wd={tmp_path}" in captured["cmd"]
    # And the session the setup started is handed back to the group.
    assert result["ok"] is True
    assert result["vivado_session_ids"] == ["sess-77"]


def test_missing_lib_error_lists_what_is_actually_staged(tmp_path, capsys):
    """The failure mode above was hard to read; the error now shows the staged
    trees so a wrong --skills-dir is obvious."""
    staged = tmp_path / ".opencode" / "skills" / "ip-configurator"
    staged.mkdir(parents=True)
    rc = vss.main([
        "--part", "xcx", f"--working-dir={tmp_path}",
        "--skills-dir=.claude/skills",
        "--source-skill-lib=ip-configurator/lib/ipcfg.tcl",
    ])
    assert rc == 2
    err = capsys.readouterr().err
    assert ".opencode/skills/ip-configurator" in err


# ---- deferred-result recovery and serialization ------------------------


class _DeferredSession(_FakeSession):
    """First execute answers with the server's "[REJECTED] ... already
    running" notice (no result), then vivado_status reports completion."""

    def __init__(self, *, status_payloads):
        super().__init__()
        self._status_payloads = list(status_payloads)

    def call(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "vivado_start":
            return {"result": {"content": [{"type": "text",
                                            "text": '{"session_id": "sess-def-1"}'}]}}
        if name == "vivado_execute":
            return {"result": {"isError": True, "content": [{
                "type": "text",
                "text": "[REJECTED] Command '# --- harness suite setup' is "
                        "already running (started 0s ago). Use vivado_status "
                        "to monitor progress."}]}}
        if name == "vivado_status":
            payload = self._status_payloads.pop(0)
            return {"result": {"content": [{"type": "text", "text": payload}]}}
        return {"result": {"content": []}}


def test_rejected_execute_is_recovered_via_vivado_status(monkeypatch, tmp_path):
    """Regression from the first real run: two groups started setup in the same
    second and the server rejected one command / dropped the other's
    connection. Re-issuing the TCL would double-apply it, so the result is
    recovered from vivado_status instead."""
    fake = _DeferredSession(status_payloads=[
        '{"is_command_running": true, "process_running": true}',
        '{"is_command_running": false, "process_running": true,'
        ' "last_completed_output": "SETUP_PART:xcx\\nSETUP_BD:bd\\nSETUP_DONE"}',
    ])
    _patch_session(monkeypatch, fake)
    monkeypatch.setattr(vss.time, "sleep", lambda _s: None)

    sid, transcript, err = vss.start_session(
        working_dir=tmp_path, part="xcx", bd_name="bd",
        project_name="p", sources=[])

    assert sid == "sess-def-1", err
    assert err == ""
    # Exactly one execute -- the TCL must not be re-sent.
    assert fake.tool_names().count("vivado_execute") == 1
    assert fake.tool_names().count("vivado_status") == 2
    assert "vivado_stop" not in fake.tool_names()
    assert "SETUP_DONE" in transcript


def test_dead_vivado_during_recovery_fails_fast(monkeypatch, tmp_path):
    fake = _DeferredSession(status_payloads=[
        '{"is_command_running": true, "process_running": false}'])
    _patch_session(monkeypatch, fake)
    monkeypatch.setattr(vss.time, "sleep", lambda _s: None)

    sid, _t, err = vss.start_session(
        working_dir=tmp_path, part="x", bd_name="b", project_name="p",
        sources=[])

    assert sid is None
    assert "no longer running" in err
    assert "vivado_stop" in fake.tool_names()


def test_await_command_backs_off_instead_of_tight_polling(monkeypatch):
    """vivado_status documents 'DO NOT POLL IN A LOOP' and throttles callers
    that spin, so the delay must grow."""
    delays: list[float] = []
    payloads = ['{"is_command_running": true, "process_running": true}'] * 3 + [
        '{"is_command_running": false, "last_completed_output": "ok"}']
    fake = _DeferredSession(status_payloads=payloads)

    completed, detail = vss.await_command(
        fake, "sid", deadline=vss.time.monotonic() + 3600,
        transcript=[], sleep=delays.append)

    assert completed is True and detail == "ok"
    assert delays == sorted(delays) and delays[0] < delays[-1]
    assert max(delays) <= 30.0


def test_server_lock_serializes_and_is_optional(tmp_path):
    url = "http://127.0.0.1:18090/mcp"
    with vss.server_lock(url, timeout_seconds=5) as held:
        assert held is True
        # A second waiter with a short timeout gives up rather than failing the
        # suite outright -- it proceeds unserialized.
        with vss.server_lock(url, timeout_seconds=1) as second:
            assert second is False
    with vss.server_lock(url, timeout_seconds=1, enabled=False) as skipped:
        assert skipped is True


def test_server_lock_enforces_launch_gap_after_releasing_lock(monkeypatch, tmp_path):
    url = "http://127.0.0.1:18091/mcp"
    clock = iter((100.0, 100.0, 102.0, 105.0))
    sleeps: list[float] = []
    monkeypatch.setattr(vss.time, "time", lambda: next(clock))
    monkeypatch.setattr(vss.time, "sleep", sleeps.append)

    with vss.server_lock(url, launch_gap_seconds=5) as first:
        assert first is True
    with vss.server_lock(url, launch_gap_seconds=5) as second:
        assert second is True

    assert sleeps == [3.0]
