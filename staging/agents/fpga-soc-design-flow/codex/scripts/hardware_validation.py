#!/usr/bin/env python3
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

"""Validate hardware plans, target profiles, and debug-image readiness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "evals" / "designs"
CONTRACTS = ROOT / "contracts"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def schema_errors(instance_path: Path, schema_name: str) -> list[str]:
    if not instance_path.is_file():
        return [f"missing {instance_path}"]
    try:
        instance = read_json(instance_path)
        schema = read_json(CONTRACTS / schema_name)
    except (OSError, json.JSONDecodeError) as exc:
        return [str(exc)]
    validator = jsonschema.validators.validator_for(schema)(schema)
    return [
        f"{instance_path}:{'/'.join(str(item) for item in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.absolute_path))
    ]


def validate_plans() -> list[str]:
    errors: list[str] = []
    plans = sorted(CASES.glob("kv260_*/hardware-test.json"))
    case_ids = {path.parent.name for path in CASES.glob("kv260_*/case.json")}
    plan_ids = {path.parent.name for path in plans}
    if case_ids != plan_ids:
        errors.append(f"KV260 case/plan mismatch: missing={sorted(case_ids - plan_ids)} extra={sorted(plan_ids - case_ids)}")
    for plan_path in plans:
        plan_errors = schema_errors(plan_path, "hardware-test.schema.json")
        errors.extend(plan_errors)
        if plan_errors:
            continue
        plan = read_json(plan_path)
        case = read_json(plan_path.parent / "case.json")
        if plan["case_id"] != case["id"]:
            errors.append(f"{plan_path}: case_id does not match case.json")
        if plan["target"] != {
            "part": case["target"]["part"],
            "board_part": case["target"].get("board_part"),
        }:
            errors.append(f"{plan_path}: target does not match case.json")
    return errors


def validate_target(path: Path) -> list[str]:
    return schema_errors(path, "hardware-target.schema.json")


def match_target(target_path: Path, plan_path: Path) -> tuple[list[str], dict]:
    errors = validate_target(target_path)
    errors.extend(schema_errors(plan_path, "hardware-test.schema.json"))
    if errors:
        return errors, {}
    target = read_json(target_path)
    plan = read_json(plan_path)
    if target["board"]["part"] != plan["target"]["part"]:
        errors.append("target part does not match hardware test plan")
    plan_board_part = plan["target"].get("board_part")
    if plan_board_part is not None and target["board"].get("board_part") != plan_board_part:
        errors.append("target board_part does not match hardware test plan")

    capability_groups = target["capabilities"]
    available = {
        capability
        for group in ("transports", "programming", "debug", "stimulus", "peripherals")
        for capability in capability_groups[group]
    }
    missing = sorted(set(plan["required_capabilities"]) - available)
    if missing:
        errors.append(f"target lacks required test capabilities: {missing}")

    instance_matches: list[dict] = []
    for requirement in plan["external_equipment"]:
        candidates = []
        required_capabilities = set(requirement["required_capabilities"])
        for instance in target["peripheral_instances"]:
            if instance["kind"] != requirement["target_kind"]:
                continue
            if required_capabilities <= set(instance["capabilities"]):
                candidates.append(instance["id"])
        instance_matches.append(
            {
                "kind": requirement["kind"],
                "required": requirement["required"],
                "matched_instances": candidates,
            }
        )
        if requirement["required"] and not candidates:
            errors.append(
                f"no target peripheral matches required {requirement['kind']} "
                f"capabilities {sorted(required_capabilities)}"
            )

    report = {
        "target": target["id"],
        "plan": plan["case_id"],
        "part_match": target["board"]["part"] == plan["target"]["part"],
        "required_capabilities_missing": missing,
        "peripheral_matches": instance_matches,
        "compatible": not errors,
    }
    return errors, report


def check_run(run_dir: Path, case_id: str) -> tuple[list[str], dict]:
    errors = validate_plans()
    implementation_path = run_dir / "implementation-result.json"
    if not implementation_path.is_file():
        errors.append(f"missing {implementation_path}")
        return errors, {}
    implementation = read_json(implementation_path)
    if implementation.get("status") != "PASS":
        errors.append("implementation-result status is not PASS")
    artifacts = implementation.get("artifacts", [])
    programming = [
        item for item in artifacts
        if item.get("kind") in {"bitstream", "pdi"} and item.get("exists")
    ]
    probes = [
        item for item in artifacts
        if item.get("kind") == "ltx" and item.get("exists")
    ]
    debug_maps = [
        item for item in artifacts
        if item.get("kind") == "debug-map" and item.get("exists")
    ]
    if not programming:
        errors.append("implementation result has no existing programming image")
    if not probes:
        errors.append("implementation result has no matching .ltx artifact")
    if not debug_maps:
        errors.append("implementation result has no debug-map artifact")
    plan_path = CASES / case_id / "hardware-test.json"
    errors.extend(schema_errors(plan_path, "hardware-test.schema.json"))
    report = {
        "case_id": case_id,
        "run": str(run_dir),
        "contract_ready": plan_path.is_file(),
        "implementation_pass": implementation.get("status") == "PASS",
        "programming_image_recorded": bool(programming),
        "ltx_recorded": bool(probes),
        "debug_map_recorded": bool(debug_maps),
        "hardware_debug_image_ready": not errors,
    }
    return errors, report


def emit(errors: list[str]) -> int:
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    return 1 if errors else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate-plans")
    target = sub.add_parser("validate-target")
    target.add_argument("--target", required=True, type=Path)
    match = sub.add_parser("match-target")
    match.add_argument("--target", required=True, type=Path)
    match.add_argument("--plan", required=True, type=Path)
    run = sub.add_parser("check-run")
    run.add_argument("--run", required=True, type=Path)
    run.add_argument("--case", required=True)
    args = parser.parse_args()

    if args.command == "validate-plans":
        errors = validate_plans()
        if not errors:
            print("PASS: all 20 KV260 hardware test plans are schema-valid")
        return emit(errors)
    if args.command == "validate-target":
        errors = validate_target(args.target.resolve())
        if not errors:
            print(f"PASS: hardware target profile is valid: {args.target}")
        return emit(errors)
    if args.command == "match-target":
        errors, report = match_target(args.target.resolve(), args.plan.resolve())
        print(json.dumps(report, indent=2, sort_keys=True))
        return emit(errors)
    errors, report = check_run(args.run.resolve(), args.case)
    print(json.dumps(report, indent=2, sort_keys=True))
    return emit(errors)


if __name__ == "__main__":
    raise SystemExit(main())
