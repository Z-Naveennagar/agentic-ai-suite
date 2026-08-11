"""Functional readiness checks for `skills-test doctor`'s cli_<client> rows.

Presence on disk (``shutil.which`` / ``SkillBackend.is_available``) only
proves a binary *exists* -- it says nothing about whether it can actually
run. Confirmed live: `/usr/local/bin/agent` (Cursor CLI) read as a clean
doctor PASS on a host where its companion `node` binary and `index.js`
application bundle were both missing, so every real invocation failed with
`exit_code=127` ("command not found"). ``version_check`` catches that.

A CLI that runs but isn't authenticated (no API key, no configured
provider) is a second, distinct failure mode a version check can't see --
most CLIs print `--version` without needing credentials. ``prompt_smoke_test``
catches that by sending one trivial prompt through the backend's real
``invoke()`` path, the same code a genuine skill-test run uses.

``copilot_auth.py`` already established this "actually run the thing, don't
just check it exists" pattern for one backend; this module generalizes it
to every backend `run_doctor` iterates over.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from .interface import SkillBackend

_SMOKE_TEST_PROMPT = "Reply with the single word: ready"


def _first_nonblank_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def version_check(binary: str, *, timeout: float = 15.0) -> tuple[bool, str]:
    """Run ``<binary> --version`` and report whether it actually executes.

    Returns ``(ok, detail)``: on success, *detail* is the first non-blank
    output line (some CLIs' version banners start with a blank line or
    two, e.g. Vitis's `v++ --version` -- see runner-diagnostics.yml's own
    `awk 'NF{print; exit}'` fix for the same issue). On failure, *detail*
    is a short reason: a non-zero exit, a timeout, or an OSError (the
    binary can't even be exec'd -- e.g. a shebang/loader pointing at a
    missing interpreter).
    """
    try:
        cp = subprocess.run(
            [binary, "--version"], capture_output=True, text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"{binary} --version timed out after {timeout}s"
    except OSError as exc:
        return False, str(exc)

    if cp.returncode != 0:
        detail = (cp.stdout + cp.stderr).strip()[:200]
        return False, f"{binary} --version exited {cp.returncode}: {detail}"
    return True, _first_nonblank_line(cp.stdout or cp.stderr) or "(no version output)"


def prompt_smoke_test(cli: SkillBackend, *, timeout: float = 60.0) -> tuple[bool, str]:
    """Send one trivial real prompt through *cli*'s actual ``invoke()``.

    Exercises the same build_command/streamed-capture/timeout machinery a
    genuine skill-test case uses, in a disposable temp workspace -- so a
    PASS here means a real case invocation is credible, not just that the
    binary exists and prints a version. Returns ``(ok, detail)``.
    """
    workspace_dir = Path(tempfile.mkdtemp(prefix="doctor_smoke_test_"))
    try:
        result = cli.invoke(
            prompt=_SMOKE_TEST_PROMPT,
            workspace_dir=workspace_dir,
            timeout_seconds=int(timeout),
        )
        exit_code = result.get("exit_code")
        if exit_code == 124:
            return False, "prompt smoke test timed out"
        if exit_code != 0:
            detail = (result.get("stderr") or result.get("stdout") or "").strip()[:200]
            return False, f"prompt smoke test exited {exit_code}: {detail}"
        return True, "prompt smoke test OK"
    except Exception as exc:
        return False, f"prompt smoke test raised: {exc}"
    finally:
        shutil.rmtree(workspace_dir, ignore_errors=True)


__all__ = ["version_check", "prompt_smoke_test"]
