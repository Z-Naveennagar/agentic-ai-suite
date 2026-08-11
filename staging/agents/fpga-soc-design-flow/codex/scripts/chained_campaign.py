#!/usr/bin/env python3
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

"""Wait for one campaign, then launch the R21-R50 design and hardware queues."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN_RUNNER = ROOT / "scripts" / "campaign_runner.py"
HARDWARE_RUNNER = ROOT / "scripts" / "hardware_campaign_runner.py"
SUITE = ROOT / "evals" / "kv260-suite.json"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def wait_for_terminal(path: Path, poll_seconds: int) -> dict:
    while True:
        if path.is_file():
            state = read_json(path)
            if state.get("status") in {"PASS", "FAIL"}:
                return state
        time.sleep(max(5, poll_seconds))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--wait-state", required=True, type=Path)
    result.add_argument("--design-campaign-id", required=True)
    result.add_argument("--hardware-campaign-id", required=True)
    result.add_argument("--target-profile", required=True, type=Path)
    result.add_argument("--workers", type=int, default=2)
    result.add_argument("--poll-seconds", type=int, default=30)
    result.add_argument(
        "--authorize-hardware-actions",
        action="store_true",
        required=True,
        help="explicitly authorize programming, test-shell reset, and safe VIO drive",
    )
    result.add_argument("--model")
    return result


def main() -> int:
    args = parser().parse_args()
    prerequisite = args.wait_state.resolve()
    target_profile = args.target_profile.resolve()
    print(f"WAIT prerequisite={prerequisite}", flush=True)
    prior = wait_for_terminal(prerequisite, args.poll_seconds)
    print(f"PREREQUISITE status={prior['status']}", flush=True)

    suite = read_json(SUITE)
    cases = [
        record["case_id"]
        for record in suite["cases"]
        if 21 <= record["rank"] <= 50
    ]
    design_command = [
        sys.executable,
        str(CAMPAIGN_RUNNER),
        "--campaign-id",
        args.design_campaign_id,
        "--workers",
        str(args.workers),
        "--cases",
        *cases,
    ]
    if args.model:
        design_command.extend(["--model", args.model])
    design = subprocess.Popen(design_command, cwd=ROOT)

    design_state = (
        ROOT
        / "runs"
        / "_campaigns"
        / args.design_campaign_id
        / "state.json"
    )
    while design.poll() is None and not design_state.is_file():
        time.sleep(1)
    if not design_state.is_file():
        print("ERROR: expansion design campaign did not create state", flush=True)
        return design.wait()

    hardware_command = [
        sys.executable,
        str(HARDWARE_RUNNER),
        "--design-campaign-state",
        str(design_state),
        "--target-profile",
        str(target_profile),
        "--campaign-id",
        args.hardware_campaign_id,
        "--poll-seconds",
        str(args.poll_seconds),
        "--authorize-hardware-actions",
    ]
    if args.model:
        hardware_command.extend(["--model", args.model])
    hardware = subprocess.Popen(hardware_command, cwd=ROOT)
    design_exit = design.wait()
    hardware_exit = hardware.wait()
    print(
        f"COMPLETE design_exit={design_exit} hardware_exit={hardware_exit}",
        flush=True,
    )
    return 0 if design_exit == 0 and hardware_exit == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
