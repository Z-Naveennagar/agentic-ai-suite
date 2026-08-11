#!/usr/bin/env python3
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
"""Validate the normalized RTL functional-verification PASS contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


REQUIRED_CHECKS = (
    "compile_ok",
    "elaboration_ok",
    "simulator_exit_code",
    "terminal_pass",
    "assertion_failures",
    "checker_failures",
    "timeouts",
)
REQUIRED_TESTS = ("required", "run", "passed", "failed", "skipped")


def is_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def validate(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["top-level JSON value must be an object"]
    if data.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if not isinstance(data.get("backend"), str) or not data["backend"].strip():
        errors.append("backend must be a non-empty string")
    if data.get("status") not in {"PASS", "FAIL", "ERROR"}:
        errors.append("status must be PASS, FAIL, or ERROR")
    if not isinstance(data.get("tool_versions"), dict):
        errors.append("tool_versions must be an object")
    if not isinstance(data.get("coverage_required"), bool):
        errors.append("coverage_required must be boolean")
    if not isinstance(data.get("coverage_reviewed"), bool):
        errors.append("coverage_reviewed must be boolean")
    for key in ("seeds", "exclusions", "unverified_boundaries"):
        if not isinstance(data.get(key), list):
            errors.append(f"{key} must be an array")
    if not isinstance(data.get("artifacts"), dict):
        errors.append("artifacts must be an object")

    tests = data.get("tests")
    test_values_valid = isinstance(tests, dict)
    if not test_values_valid:
        errors.append("tests must be an object")
    else:
        for key in REQUIRED_TESTS:
            if not is_nonnegative_int(tests.get(key)):
                errors.append(f"tests.{key} must be a nonnegative integer")
                test_values_valid = False
        if test_values_valid and tests["run"] != tests["passed"] + tests["failed"] + tests["skipped"]:
            errors.append("tests.run must equal passed + failed + skipped")

    checks = data.get("checks")
    if not isinstance(checks, dict):
        errors.append("checks must be an object")
    else:
        for key in REQUIRED_CHECKS:
            if key not in checks:
                errors.append(f"checks.{key} is required")
        for key in ("compile_ok", "elaboration_ok", "terminal_pass"):
            if key in checks and not isinstance(checks[key], bool):
                errors.append(f"checks.{key} must be boolean")
        for key in ("simulator_exit_code", "assertion_failures", "checker_failures", "timeouts"):
            if key in checks and not is_nonnegative_int(checks[key]):
                errors.append(f"checks.{key} must be a nonnegative integer")

    if data.get("status") == "PASS" and isinstance(tests, dict) and isinstance(checks, dict):
        if test_values_valid:
            if not (tests["required"] == tests["run"] == tests["passed"]):
                errors.append("PASS requires tests.required == tests.run == tests.passed")
            if tests["failed"] != 0 or tests["skipped"] != 0:
                errors.append("PASS requires tests.failed == 0 and tests.skipped == 0")
        if checks.get("compile_ok") is not True:
            errors.append("PASS requires checks.compile_ok == true")
        if checks.get("elaboration_ok") is not True:
            errors.append("PASS requires checks.elaboration_ok == true")
        if checks.get("simulator_exit_code") != 0:
            errors.append("PASS requires checks.simulator_exit_code == 0")
        if checks.get("terminal_pass") is not True:
            errors.append("PASS requires checks.terminal_pass == true")
        for key in ("assertion_failures", "checker_failures", "timeouts"):
            if checks.get(key) != 0:
                errors.append(f"PASS requires checks.{key} == 0")
        if data.get("coverage_required") is True and data.get("coverage_reviewed") is not True:
            errors.append("PASS with required coverage requires coverage_reviewed == true")
        if not data.get("tool_versions"):
            errors.append("PASS requires at least one tool version")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path, help="result JSON to validate")
    parser.add_argument("--schema-only", action="store_true", help="allow a valid FAIL or ERROR result")
    args = parser.parse_args()
    try:
        data = json.loads(args.result.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Invalid result file: {exc}", file=sys.stderr)
        return 2
    errors = validate(data)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if not args.schema_only and data["status"] != "PASS":
        print(f"Result is valid but not PASS: {data['status']}", file=sys.stderr)
        return 1
    print(f"RESULT_GATE_{data['status']} backend={data['backend']} tests={data['tests']['passed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
