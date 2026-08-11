"""Copilot CLI authentication diagnostics for the doctor check."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


def diagnose_copilot_auth(copilot_bin: str | None = None) -> tuple[bool, str]:
    """Check whether the Copilot CLI appears to be authenticated.

    Returns (ok, detail).  ok is True when a valid auth token or session
    can be found on disk.  Does not contact the network.
    """
    binary = copilot_bin or shutil.which("copilot")
    if not binary:
        return False, "copilot binary not found"

    # Check for stored OAuth token (~/.copilot/config.json)
    cfg = Path.home() / ".copilot" / "config.json"
    if cfg.is_file():
        try:
            data = json.loads(cfg.read_text())
            token = data.get("token") or data.get("accessToken") or ""
            if token:
                return True, f"token present in {cfg}"
        except (json.JSONDecodeError, OSError) as exc:
            return False, f"unreadable {cfg}: {exc}"

    # Check for GitHub PAT in env (the headless auth path)
    for var in ("GH_TOKEN", "GITHUB_TOKEN", "COPILOT_GITHUB_TOKEN"):
        val = os.environ.get(var)
        if val:
            return True, f"token set via {var}"

    return False, "no auth token found (check ~/.copilot/config.json or set GH_TOKEN)"


def smoke_test_copilot_auth(copilot_bin: str | None = None) -> tuple[bool, str]:
    """Lightweight network probe: can copilot reach the auth endpoint?

    Runs ``copilot auth status`` (or ``copilot status``) and checks for
    success.  Returns (ok, detail).
    """
    binary = copilot_bin or shutil.which("copilot")
    if not binary:
        return False, "copilot binary not found"

    for subcmd in ("auth status", "status"):
        try:
            cp = subprocess.run(
                [binary, *subcmd.split()],
                capture_output=True, text=True, timeout=15,
            )
            out = (cp.stdout or "") + (cp.stderr or "")
            if cp.returncode == 0:
                return True, f"copilot {subcmd} OK"
            # Some versions exit 0 but print auth errors to stderr
            if "authenticated" in out.lower() or "logged in" in out.lower():
                return True, out.strip()[:200]
        except subprocess.TimeoutExpired:
            continue
        except OSError:
            continue

    return False, f"copilot {subcmd} failed (binary at {binary})"
