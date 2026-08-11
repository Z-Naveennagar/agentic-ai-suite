"""Tests for cli_backends.cli_smoke_test -- the functional readiness checks
behind `skills-test doctor`'s cli_<client> rows.

Regression coverage for the reported bug: a binary that merely *exists*
(e.g. Cursor's `agent` missing its companion node/index.js) must not read
as a doctor PASS just because the path is present on disk.
"""

from __future__ import annotations

import stat
import sys
from pathlib import Path

import pytest

from skills_testing.cli_backends.cli_smoke_test import (
    prompt_smoke_test,
    version_check,
)


def _write_script(path: Path, body: str) -> str:
    path.write_text(f"#!{sys.executable}\n{body}\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


# ---- version_check -------------------------------------------------------


def test_version_check_success(tmp_path):
    script = _write_script(tmp_path / "ok.py", (
        "import sys\n"
        "print()\n"  # some CLIs' --version banners start with a blank line
        "print('mytool v1.2.3')\n"
        "sys.exit(0)\n"
    ))
    ok, detail = version_check(script)
    assert ok is True
    assert detail == "mytool v1.2.3"


def test_version_check_nonzero_exit(tmp_path):
    script = _write_script(tmp_path / "bad.py", (
        "import sys\n"
        "sys.stderr.write('boom\\n')\n"
        "sys.exit(1)\n"
    ))
    ok, detail = version_check(script)
    assert ok is False
    assert "exited 1" in detail
    assert "boom" in detail


def test_version_check_timeout(tmp_path):
    script = _write_script(tmp_path / "hang.py", (
        "import time\n"
        "time.sleep(30)\n"
    ))
    ok, detail = version_check(script, timeout=0.2)
    assert ok is False
    assert "timed out" in detail


def test_version_check_missing_binary(tmp_path):
    ok, detail = version_check(str(tmp_path / "does-not-exist"))
    assert ok is False
    assert detail  # some OSError message


# ---- prompt_smoke_test ---------------------------------------------------


class _FakeCli:
    def __init__(self, result: dict):
        self._result = result

    def invoke(self, *, prompt, workspace_dir, timeout_seconds):
        return self._result


def test_prompt_smoke_test_success():
    cli = _FakeCli({"exit_code": 0, "stdout": "ready", "stderr": ""})
    ok, detail = prompt_smoke_test(cli)
    assert ok is True
    assert "OK" in detail


def test_prompt_smoke_test_timeout():
    cli = _FakeCli({"exit_code": 124, "stdout": "", "stderr": ""})
    ok, detail = prompt_smoke_test(cli)
    assert ok is False
    assert "timed out" in detail


def test_prompt_smoke_test_nonzero_exit_is_the_auth_failure_case():
    """A CLI that runs (passes version_check) but isn't authenticated exits
    non-zero here -- the distinct failure mode this function exists for."""
    cli = _FakeCli({"exit_code": 1, "stdout": "", "stderr": "not authenticated"})
    ok, detail = prompt_smoke_test(cli)
    assert ok is False
    assert "exited 1" in detail
    assert "not authenticated" in detail


def test_prompt_smoke_test_survives_backend_exception():
    class _RaisingCli:
        def invoke(self, **_kwargs):
            raise RuntimeError("boom")

    ok, detail = prompt_smoke_test(_RaisingCli())
    assert ok is False
    assert "boom" in detail
