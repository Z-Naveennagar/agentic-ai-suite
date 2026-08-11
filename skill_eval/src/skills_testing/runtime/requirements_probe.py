"""
Host-capability probe + per-case gating.

probe_host() runs once at startup and returns a dict the scheduler / case
gating logic uses. Tests can pass *probe_overrides* to short-circuit any
key (e.g. force vivado=True in CI without Vivado installed).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from typing import Optional

from ..core.paths import default_workspace_root


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


# Cache the Vivado version string for the lifetime of the process. The
# `vivado -version` invocation is ~10s of network mount overhead on
# /proj installs, and we may consult it once per case.
_VIVADO_VERSION_CACHE: Optional[str] = None


def _vivado_version() -> Optional[str]:
    """Return e.g. '2026.2.0' or None if vivado is unavailable / fails."""
    global _VIVADO_VERSION_CACHE
    if _VIVADO_VERSION_CACHE is not None:
        return _VIVADO_VERSION_CACHE or None
    if not _have("vivado"):
        _VIVADO_VERSION_CACHE = ""
        return None
    env_override = os.environ.get("SKILL_TEST_VIVADO_VERSION", "").strip()
    if env_override:
        _VIVADO_VERSION_CACHE = env_override
        return env_override
    try:
        out = subprocess.run(
            ["vivado", "-version"], capture_output=True, text=True,
            timeout=30,
        )
        # Vivado emits this header in a few forms depending on version:
        #   "vivado v2026.1 (64-bit)"               (release builds)
        #   "Vivado v.2024.1.1 (lin64)"             (Tool Version banner)
        # Match either, case-insensitively, capturing 2-3 component versions.
        m = re.search(
            r"(?i)vivado\s+v\.?([0-9]+(?:\.[0-9]+){1,2})",
            out.stdout,
        )
        version = m.group(1) if m else ""
    except (subprocess.TimeoutExpired, OSError):
        version = ""
    _VIVADO_VERSION_CACHE = version
    return version or None


def vivado_version() -> Optional[str]:
    """Public wrapper for the installed Vivado version string."""
    return _vivado_version()


def vivado_satisfies(constraint: str) -> tuple[bool, str]:
    """Return whether the installed Vivado version satisfies *constraint*."""
    installed = _vivado_version()
    if not installed:
        return False, "not found"
    return _satisfies(installed, constraint)


# Cache the Vitis version for the process lifetime (see _VIVADO_VERSION_CACHE).
_VITIS_VERSION_CACHE: Optional[str] = None


def _vitis_version() -> Optional[str]:
    """Return e.g. '2026.1' or None if v++ is unavailable / fails."""
    global _VITIS_VERSION_CACHE
    if _VITIS_VERSION_CACHE is not None:
        return _VITIS_VERSION_CACHE or None
    # Env override wins even when v++ is not on PATH, so version gating can be
    # exercised in CI / on hosts without a real Vitis install.
    env_override = os.environ.get("SKILL_TEST_VITIS_VERSION", "").strip()
    if env_override:
        _VITIS_VERSION_CACHE = env_override
        return env_override
    if not _have("v++"):
        _VITIS_VERSION_CACHE = ""
        return None
    try:
        out = subprocess.run(
            ["v++", "--version"], capture_output=True, text=True,
            timeout=30,
        )
        # v++ prints a banner like:
        #   "v++ v2026.1 (64-bit)"
        #   "Vitis v2025.2.1 (64-bit)"
        blob = f"{out.stdout}\n{out.stderr}"
        m = re.search(
            r"(?i)(?:v\+\+|vitis)\s+v\.?([0-9]+(?:\.[0-9]+){1,2})",
            blob,
        )
        version = m.group(1) if m else ""
    except (subprocess.TimeoutExpired, OSError):
        version = ""
    _VITIS_VERSION_CACHE = version
    return version or None


def vitis_version() -> Optional[str]:
    """Public wrapper for the installed Vitis (v++) version string."""
    return _vitis_version()


def vitis_satisfies(constraint: str) -> tuple[bool, str]:
    """Return whether the installed Vitis version satisfies *constraint*."""
    installed = _vitis_version()
    if not installed:
        return False, "not found"
    return _satisfies(installed, constraint)


# A requirement value is a version *constraint* (vs. a bare presence flag or
# an exact version) when it contains a comparison operator.
_HAS_OPERATOR = re.compile(r"(>=|<=|==|>|<)")


def _requires_version_constraint(value) -> Optional[str]:
    """Return a normalised constraint string for *value*, or None.

    ``True``/``False``/``None`` and empty strings are presence flags, not
    version constraints. A plain version like ``"2026.1"`` is treated as an
    exact ``==`` constraint; a string already carrying an operator
    (``">=2026.1"``) is used as-is.
    """
    if value is None or isinstance(value, bool):
        return None
    s = str(value).strip()
    if not s:
        return None
    if _HAS_OPERATOR.search(s):
        return s
    # A bare version number -> exact match; anything else (e.g. "true") is
    # just a presence flag.
    if re.match(r"^[0-9]+(?:\.[0-9]+){0,3}$", s):
        return f"=={s}"
    return None


def _parse_version_constraint(spec: str) -> list[tuple[str, tuple[int, ...]]]:
    """
    Parse a comma-separated PEP 440 / npm-style range like
    ``">=2024.1,<2027.1"`` into a list of (op, version_tuple).
    """
    out: list[tuple[str, tuple[int, ...]]] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"\s*(>=|<=|==|>|<)\s*([0-9]+(?:\.[0-9]+){0,3})\s*$", part)
        if not m:
            raise ValueError(f"unparseable version constraint fragment: {part!r}")
        op = m.group(1)
        ver = tuple(int(x) for x in m.group(2).split("."))
        out.append((op, ver))
    return out


def _version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in v.split(".")) if v else tuple()


def _satisfies(version: str, constraint: str) -> tuple[bool, str]:
    """Return (ok, reason). reason is filled when ok=False."""
    try:
        constraints = _parse_version_constraint(constraint)
    except ValueError as exc:
        return False, str(exc)
    vt = _version_tuple(version)
    if not vt:
        return False, f"could not parse installed version: {version!r}"
    ops = {
        ">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b,
        ">":  lambda a, b: a > b,  "<":  lambda a, b: a < b,
        "==": lambda a, b: a == b,
    }
    # Pad both sides to the same length so 2026.2 compares cleanly to 2026.2.0.
    def _pad(a: tuple[int, ...], b: tuple[int, ...]) -> tuple[tuple[int, ...], tuple[int, ...]]:
        n = max(len(a), len(b))
        return (a + (0,) * (n - len(a)), b + (0,) * (n - len(b)))
    for op, target in constraints:
        va, vb = _pad(vt, target)
        if not ops[op](va, vb):
            return False, (
                f"installed {version} does not satisfy {op}{'.'.join(str(x) for x in target)}"
            )
    return True, ""


def _free_memory_gb() -> float:
    try:
        # Linux /proc/meminfo
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    kb = int(line.split()[1])
                    return round(kb / (1024 * 1024), 1)
    except OSError:
        pass
    return 0.0


def _free_disk_gb(path: str | None = None) -> float:
    target = path or str(default_workspace_root())
    try:
        usage = shutil.disk_usage(target)
        return round(usage.free / (1024 ** 3), 1)
    except FileNotFoundError:
        # The workspace root is created lazily per-case; on a fresh host it
        # may not exist yet when the probe runs. It's about to be created
        # for real case workspaces anyway, so create it now rather than
        # reporting a false 0.0 GB that fails every disk-gated case.
        try:
            os.makedirs(target, exist_ok=True)
            usage = shutil.disk_usage(target)
            return round(usage.free / (1024 ** 3), 1)
        except OSError:
            return 0.0
    except OSError:
        return 0.0


def probe_host(
    probe_overrides: Optional[dict] = None,
    workspace_root: Optional[str] = None,
) -> dict:
    ws_root = workspace_root or str(default_workspace_root())
    base = {
        "vivado": _have("vivado") or os.environ.get("SKILL_TEST_VIVADO_AVAILABLE", "") == "1",
        "vitis": _have("v++") or os.environ.get("SKILL_TEST_VITIS_AVAILABLE", "") == "1",
        # Installed Vitis version (None when v++ absent); used to gate cases
        # that declare a version constraint (e.g. vitis: ">=2026.1").
        "vitis_version": _vitis_version(),
        "xsdb": _have("xsdb"),
        "free_memory_gb": _free_memory_gb(),
        # Disk free at the actual workspace root the runner will write to.
        "free_disk_gb_tmp": _free_disk_gb(ws_root),
        "free_disk_gb_workspace": _free_disk_gb(ws_root),
        "workspace_root": ws_root,
        "available_hardware": [],  # populated by board scanners; empty by default
    }
    if probe_overrides:
        base.update(probe_overrides)
    return base


def case_can_run(requirements: dict, host_caps: dict) -> tuple[bool, Optional[str]]:
    """Return (ok, skip_reason). Reason is None iff ok is True."""
    if requirements.get("vivado") and not host_caps.get("vivado"):
        return False, "vivado_not_available"
    if requirements.get("vitis") and not host_caps.get("vitis"):
        return False, "vitis_not_available"
    if requirements.get("xsdb") and not host_caps.get("xsdb"):
        return False, "xsdb_not_available"

    # Vitis version constraint. `vitis:` may be a bare presence flag
    # (true/false, handled above) OR a version constraint like ">=2026.1",
    # "<=2025.2", or an exact "2026.1". When a constraint is present and
    # Vitis is installed, compare the probed version. Skipped entirely when
    # SKILL_TEST_DISABLE_VERSION_CHECK=1.
    vitis_constraint = _requires_version_constraint(requirements.get("vitis"))
    if (vitis_constraint and host_caps.get("vitis")
            and os.environ.get("SKILL_TEST_DISABLE_VERSION_CHECK", "0") != "1"):
        installed = host_caps.get("vitis_version") or _vitis_version()
        if installed:
            ok, why = _satisfies(installed, vitis_constraint)
            if not ok:
                return False, f"vitis_version_unsatisfied: {why}"

    # Optional per-case Vivado floor. Most skills are version-agnostic,
    # so this is opt-in (declare only when a case uses a feature added
    # in a specific release, e.g. report_qor_assessment >= 2024.1). The
    # default behaviour is "run on whatever Vivado is on PATH" so the
    # dashboard can correlate failures with the installed version.
    # Set SKILL_TEST_DISABLE_VERSION_CHECK=1 to skip the probe entirely.
    min_v = requirements.get("min_vivado_version")
    if (min_v and requirements.get("vivado")
            and os.environ.get("SKILL_TEST_DISABLE_VERSION_CHECK", "0") != "1"):
        installed = _vivado_version()
        if installed:
            ok, why = _satisfies(installed, f">={min_v}")
            if not ok:
                return False, f"vivado_below_min_version: {why}"

    hw = requirements.get("hardware")
    if hw and hw not in (host_caps.get("available_hardware") or []):
        return False, f"hardware_not_available:{hw}"

    need_mem = float(requirements.get("min_memory_gb", 0) or 0)
    if need_mem and host_caps.get("free_memory_gb", 0) < need_mem:
        return False, f"insufficient_memory: need {need_mem} GB"

    need_disk = float(requirements.get("min_disk_gb", 0) or 0)
    free_disk = host_caps.get(
        "free_disk_gb_workspace", host_caps.get("free_disk_gb_tmp", 0)
    )
    if need_disk and free_disk < need_disk:
        ws_root = host_caps.get("workspace_root", str(default_workspace_root()))
        return False, f"insufficient_disk: need {need_disk} GB on {ws_root}"

    return True, None
