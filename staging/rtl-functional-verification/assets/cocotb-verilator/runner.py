#!/usr/bin/env python3
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
"""Copy and adapt this cocotb/Verilator runner for a project."""

from __future__ import annotations

import argparse
from pathlib import Path
from cocotb_tools.runner import get_runner


def key_value(items: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise argparse.ArgumentTypeError(f"expected NAME=VALUE, got {item!r}")
        key, value = item.split("=", 1)
        result[key] = value
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", required=True)
    parser.add_argument("--test-module", required=True)
    parser.add_argument("--source", action="append", required=True)
    parser.add_argument("--include", action="append", default=[])
    parser.add_argument("--define", action="append", default=[])
    parser.add_argument("--parameter", action="append", default=[])
    parser.add_argument("--build-dir", default="sim_build")
    parser.add_argument("--waves", action="store_true")
    parser.add_argument("--coverage", action="store_true")
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()

    build_args = ["--timing", "--assert", "-Wall"]
    if args.coverage:
        build_args.append("--coverage")
    runner = get_runner("verilator")
    runner.build(
        sources=[Path(source) for source in args.source],
        includes=[Path(include) for include in args.include],
        defines=key_value(args.define),
        parameters=key_value(args.parameter),
        hdl_toplevel=args.top,
        build_dir=Path(args.build_dir),
        build_args=build_args,
        waves=args.waves,
    )
    test_args: list[str] = []
    if args.coverage:
        test_args.append("+verilator+coverage+file+coverage.dat")
    runner.test(
        hdl_toplevel=args.top,
        test_module=args.test_module,
        build_dir=Path(args.build_dir),
        test_args=test_args,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
