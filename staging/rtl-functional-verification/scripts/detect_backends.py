#!/usr/bin/env python3
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
"""Detect supported RTL functional-verification backends without modifying the host."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Iterable


def find_command(names: Iterable[str]) -> str | None:
    for name in names:
        found = shutil.which(name)
        if found:
            return str(Path(found).resolve())
    return None


def find_vivado() -> str | None:
    found = find_command(("vivado", "vivado.bat"))
    if found:
        return found
    root = os.environ.get("XILINX_VIVADO")
    if not root:
        return None
    for name in ("vivado", "vivado.bat"):
        candidate = Path(root) / "bin" / name
        if candidate.is_file():
            return str(candidate.resolve())
    return None


def command_version(command: str | None, args: list[str]) -> str | None:
    if not command:
        return None
    try:
        completed = subprocess.run(
            [command, *args], capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    output = (completed.stdout or completed.stderr).strip().splitlines()
    return output[0].strip() if output else None


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def detect() -> dict[str, object]:
    verilator = find_command(("verilator", "verilator.exe"))
    vivado = find_vivado()
    packages = {name: package_version(name) for name in ("cocotb", "numpy", "pytest")}
    tools = {
        "python": {"path": sys.executable, "version": sys.version.split()[0]},
        "verilator": {"path": verilator, "version": command_version(verilator, ["--version"])},
        "vivado": {"path": vivado, "version": command_version(vivado, ["-version"])},
    }
    backends = {
        "cocotb-verilator": bool(verilator and packages["cocotb"]),
        "xsim-systemverilog": bool(vivado),
        "xsim-python-vectors": bool(vivado),
    }
    return {"tools": tools, "python_packages": packages, "backends": backends}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument(
        "--require",
        choices=("cocotb-verilator", "xsim-systemverilog", "xsim-python-vectors"),
        help="return nonzero unless this backend is ready",
    )
    args = parser.parse_args()
    report = detect()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for backend, ready in report["backends"].items():
            print(f"{backend}: {'READY' if ready else 'UNAVAILABLE'}")
        for name, data in report["tools"].items():
            print(f"{name}: {data['path'] or 'not found'} ({data['version'] or 'version unknown'})")
        for name, version in report["python_packages"].items():
            print(f"python package {name}: {version or 'not installed'}")
    if args.require and not report["backends"][args.require]:
        print(f"Required backend is unavailable: {args.require}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
