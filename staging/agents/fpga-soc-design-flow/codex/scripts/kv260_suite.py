#!/usr/bin/env python3
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

"""Validate, execute, and summarize the ordered KV260 frontier-model suite."""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import sys
import time
from pathlib import Path

import jsonschema

from v0_1_runner import (
    ROOT,
    execute_codex,
    initialize_run,
    load_case,
    run_simulation,
    score_run,
    write_json,
)


SUITE_PATH = ROOT / "evals" / "kv260-suite.json"
SUITE_SCHEMA = ROOT / "contracts" / "regression-suite.schema.json"
CASE_SCHEMA = ROOT / "contracts" / "evaluation-case.schema.json"
STAGE_FILES = [
    "hardware-spec.json",
    "architecture-plan.json",
    "source-manifest.json",
    "verification-result.json",
    "implementation-result.json",
]


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def suite_cases(suite: dict, first: int = 1, last: int = 50) -> list[dict]:
    return [
        item for item in suite["cases"]
        if first <= item["rank"] <= last
    ]


def validate_suite() -> tuple[dict, list[str]]:
    suite = read_json(SUITE_PATH)
    errors: list[str] = []
    for path, instance in ((SUITE_SCHEMA, suite),):
        schema = read_json(path)
        validator = jsonschema.validators.validator_for(schema)(schema)
        errors.extend(
            f"{path.name}:{'/'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}"
            for error in validator.iter_errors(instance)
        )

    cases = suite.get("cases", [])
    ranks = [item.get("rank") for item in cases]
    ids = [item.get("case_id") for item in cases]
    if ranks != list(range(1, 51)):
        errors.append(f"suite ranks must be exactly 1..50 in order; got {ranks}")
    if len(ids) != len(set(ids)):
        errors.append("suite case IDs are not unique")

    case_schema = read_json(CASE_SCHEMA)
    for item in cases:
        case_id = item["case_id"]
        case_root = ROOT / "evals" / "designs" / case_id
        case_file = case_root / "case.json"
        if not case_file.is_file():
            errors.append(f"{case_id}: missing case.json")
            continue
        case = read_json(case_file)
        validator = jsonschema.validators.validator_for(case_schema)(case_schema)
        errors.extend(
            f"{case_id}:{'/'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}"
            for error in validator.iter_errors(case)
        )
        if case.get("id") != case_id:
            errors.append(f"{case_id}: case ID does not match directory")
        target = case.get("target", {})
        for key in ("part", "board_part", "vivado_version"):
            if target.get(key) != suite["target"].get(key):
                errors.append(f"{case_id}: target {key} differs from suite")
        candidate = case.get("candidate", {})
        if candidate.get("integration_mode") != "ip_integrator":
            errors.append(f"{case_id}: integration_mode must be ip_integrator")
        public = case.get("public_interface", {})
        public_sources = {
            module.get("source") for module in public.get("modules", [])
        }
        if public_sources != set(candidate.get("rtl_sources", [])):
            errors.append(f"{case_id}: public and candidate RTL sources differ")
        simulation_tops = {
            module.get("name")
            for module in public.get("modules", [])
            if "simulation_top" in module.get("roles", [])
        }
        expected_top = candidate.get("simulation_top", candidate.get("top"))
        if simulation_tops != {expected_top}:
            errors.append(f"{case_id}: public simulation top differs from candidate")
        if any(
            "implementation_top" in module.get("roles", [])
            for module in public.get("modules", [])
        ):
            errors.append(f"{case_id}: IP-integrator case declares a handwritten implementation top")
        for source in candidate.get("rtl_sources", []):
            if not (case_root / "reference" / source).is_file():
                errors.append(f"{case_id}: missing reference source {source}")
        make_dir = case.get("simulation", {}).get("make_directory", "")
        if not (case_root / make_dir / "Makefile").is_file():
            errors.append(f"{case_id}: missing simulation Makefile")
    return suite, sorted(errors)


def print_suite(suite: dict) -> None:
    for item in suite["cases"]:
        print(
            f"{item['rank']:02d}  {item['level']:<12} "
            f"{item['case_id']:<32} {item['focus']}"
        )


def self_test(suite: dict, first: int, last: int) -> int:
    failures = 0
    for item in suite_cases(suite, first, last):
        case_root, case = load_case(item["case_id"])
        output = ROOT / "runs" / "_selftest" / item["case_id"]
        passed, details = run_simulation(
            case_root,
            case,
            case_root / "reference",
            output,
        )
        print(f"{'PASS' if passed else 'FAIL'} rank={item['rank']:02d} {item['case_id']}")
        if not passed:
            print(json.dumps(details, indent=2))
            failures += 1
    return failures


def stage_snapshot(run_dir: Path) -> str:
    states: list[str] = []
    for name in STAGE_FILES:
        path = run_dir / name
        if not path.is_file():
            continue
        try:
            status = read_json(path).get("status", "?")
        except (OSError, json.JSONDecodeError):
            status = "INVALID"
        states.append(f"{name.removesuffix('.json')}={status}")
    return ", ".join(states) if states else "intake"


def run_one(
    item: dict,
    suite_run: dict,
    suite_run_path: Path,
    args: argparse.Namespace,
) -> bool:
    case_id = item["case_id"]
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    request_id = f"kv260-r{item['rank']:02d}-{case_id.removeprefix('kv260_')}-{stamp}"
    case_root, case = load_case(case_id)
    run_dir = initialize_run(case_id, request_id)
    record = {
        "rank": item["rank"],
        "case_id": case_id,
        "level": item["level"],
        "request_id": request_id,
        "run_dir": str(run_dir.relative_to(ROOT)),
        "started_at": now(),
        "finished_at": None,
        "elapsed_seconds": None,
        "codex_returncode": None,
        "score": None,
        "status": "RUNNING",
    }
    suite_run["results"].append(record)
    write_json(suite_run_path, suite_run)
    print(f"START rank={item['rank']:02d} case={case_id} request={request_id}", flush=True)

    codex_args = argparse.Namespace(
        sandbox=args.sandbox,
        model=args.model,
        oss=False,
        local_provider=None,
    )
    start = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(execute_codex, codex_args, run_dir, case)
        while True:
            try:
                returncode = future.result(timeout=30)
                break
            except concurrent.futures.TimeoutError:
                elapsed = int(time.monotonic() - start)
                print(
                    f"PROGRESS rank={item['rank']:02d} elapsed={elapsed}s "
                    f"{stage_snapshot(run_dir)}",
                    flush=True,
                )

    elapsed = round(time.monotonic() - start, 3)
    score = score_run(case_root, case, run_dir, execute_simulation=True)
    write_json(run_dir / "score.json", score)
    record.update(
        {
            "finished_at": now(),
            "elapsed_seconds": elapsed,
            "codex_returncode": returncode,
            "score": score["score"],
            "status": "PASS" if score["score"] == score["maximum_score"] else "FAIL",
        }
    )
    write_json(suite_run_path, suite_run)
    print(
        f"END rank={item['rank']:02d} case={case_id} "
        f"status={record['status']} score={score['score']}/100 elapsed={elapsed}s",
        flush=True,
    )
    return record["status"] == "PASS"


def execute_suite(suite: dict, args: argparse.Namespace) -> Path:
    if args.resume_suite:
        suite_run_path = args.resume_suite.resolve()
        suite_run = read_json(suite_run_path)
        selected = [
            item for item in suite["cases"]
            if item["rank"] in suite_run["selection"]
        ]
        finished_ranks = {
            item["rank"]
            for item in suite_run["results"]
            if item["status"] in {"PASS", "FAIL"}
        }
        for record in suite_run["results"]:
            if record["status"] == "RUNNING":
                record["status"] = "INTERRUPTED"
                record["finished_at"] = now()
        selected = [item for item in selected if item["rank"] not in finished_ranks]
        suite_run["finished_at"] = None
        write_json(suite_run_path, suite_run)
    else:
        stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
        suite_id = f"{suite['id']}-{stamp}"
        suite_root = ROOT / "runs" / "_suites" / suite_id
        suite_root.mkdir(parents=True, exist_ok=False)
        suite_run_path = suite_root / "suite-run.json"
        selected = suite_cases(suite, args.first_rank, args.last_rank)
        if args.max_cases is not None:
            selected = selected[: args.max_cases]
        suite_run = {
            "schema_version": 1,
            "suite_id": suite_id,
            "suite_definition": str(SUITE_PATH.relative_to(ROOT)),
            "model_policy": suite["model_policy"],
            "model": args.model or "inherited",
            "started_at": now(),
            "finished_at": None,
            "selection": [item["rank"] for item in selected],
            "results": [],
        }
        write_json(suite_run_path, suite_run)
    for item in selected:
        passed = run_one(item, suite_run, suite_run_path, args)
        if not passed and args.stop_on_failure:
            break
        if args.pause_after_rank == item["rank"]:
            print(f"PAUSE requested after rank={item['rank']:02d}", flush=True)
            break
    suite_run["finished_at"] = now()
    write_json(suite_run_path, suite_run)
    write_report(suite_run_path)
    return suite_run_path


def write_report(suite_run_path: Path) -> Path:
    data = read_json(suite_run_path)
    results = data["results"]
    completed = [item for item in results if item["status"] in {"PASS", "FAIL"}]
    passed = [item for item in completed if item["status"] == "PASS"]
    summary = {
        "schema_version": 1,
        "suite_id": data["suite_id"],
        "selected": len(data["selection"]),
        "completed": len(completed),
        "passed": len(passed),
        "failed": len(completed) - len(passed),
        "pass_rate": round(len(passed) / len(completed), 4) if completed else None,
        "mean_score": (
            round(sum(item["score"] for item in completed) / len(completed), 2)
            if completed
            else None
        ),
        "mean_elapsed_seconds": (
            round(sum(item["elapsed_seconds"] for item in completed) / len(completed), 2)
            if completed
            else None
        ),
        "results": results,
    }
    output = suite_run_path.parent / "evaluation-summary.json"
    write_json(output, summary)
    rows = [
        "# KV260 frontier-model workflow evaluation",
        "",
        f"- Suite: `{data['suite_id']}`",
        f"- Completed: {summary['completed']}/{summary['selected']}",
        f"- Passed: {summary['passed']}",
        f"- Mean score: {summary['mean_score']}",
        "",
        "| Rank | Case | Level | Status | Score | Seconds |",
        "|---:|---|---|---|---:|---:|",
    ]
    rows.extend(
        f"| {item['rank']} | `{item['case_id']}` | {item['level']} | "
        f"{item['status']} | {item['score']} | {item['elapsed_seconds']} |"
        for item in results
    )
    (suite_run_path.parent / "evaluation-summary.md").write_text("\n".join(rows) + "\n")
    return output


def adopt_completed_run(
    suite: dict,
    suite_run_path: Path,
    rank: int,
    run_dir: Path,
    elapsed_seconds: float,
) -> Path:
    """Score a preserved run after its outer runner was interrupted.

    This is intentionally evidence-driven: adoption succeeds only when the
    normal contract, semantic, simulation, and Vivado scorers all pass.
    """
    item = next((case for case in suite["cases"] if case["rank"] == rank), None)
    if item is None:
        raise ValueError(f"rank {rank} is not present in the KV260 suite")
    case_root, case = load_case(item["case_id"])
    score = score_run(case_root, case, run_dir, execute_simulation=True)
    write_json(run_dir / "score.json", score)

    data = read_json(suite_run_path)
    record = next((entry for entry in data["results"] if entry["rank"] == rank), None)
    if record is None:
        raise ValueError(f"suite run has no result record for rank {rank}")
    record.update(
        {
            "run_dir": str(run_dir.relative_to(ROOT)),
            "finished_at": now(),
            "elapsed_seconds": elapsed_seconds,
            "codex_returncode": 130,
            "score": score["score"],
            "status": "PASS" if score["score"] == score["maximum_score"] else "FAIL",
        }
    )
    data["finished_at"] = now()
    write_json(suite_run_path, data)
    write_report(suite_run_path)
    return run_dir / "score.json"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    sub = result.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    sub.add_parser("validate")
    test = sub.add_parser("self-test")
    test.add_argument("--first-rank", type=int, default=1)
    test.add_argument("--last-rank", type=int, default=50)
    run = sub.add_parser("run")
    run.add_argument("--first-rank", type=int, default=1)
    run.add_argument("--last-rank", type=int, default=50)
    run.add_argument("--max-cases", type=int)
    run.add_argument("--model")
    run.add_argument(
        "--resume-suite",
        type=Path,
        help="resume an interrupted suite-run.json and skip completed ranks",
    )
    run.add_argument(
        "--sandbox",
        choices=["workspace-write", "danger-full-access"],
        default="danger-full-access",
    )
    run.add_argument("--stop-on-failure", action="store_true")
    run.add_argument(
        "--pause-after-rank",
        type=int,
        help="finish this rank, write a report, and leave later selected ranks resumable",
    )
    report = sub.add_parser("report")
    report.add_argument("--suite-run", type=Path, required=True)
    adopt = sub.add_parser("adopt")
    adopt.add_argument("--suite-run", type=Path, required=True)
    adopt.add_argument("--rank", type=int, required=True)
    adopt.add_argument("--run", type=Path, required=True)
    adopt.add_argument("--elapsed-seconds", type=float, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    suite, errors = validate_suite()
    if args.command == "list":
        print_suite(suite)
        return 0
    if args.command == "validate":
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        if not errors:
            print("PASS: KV260 suite and all 50 cases are structurally valid")
        return 1 if errors else 0
    if args.command == "report":
        print(write_report(args.suite_run.resolve()))
        return 0
    if args.command == "adopt":
        print(
            adopt_completed_run(
                suite,
                args.suite_run.resolve(),
                args.rank,
                args.run.resolve(),
                args.elapsed_seconds,
            )
        )
        return 0
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if args.command == "self-test":
        return 1 if self_test(suite, args.first_rank, args.last_rank) else 0
    if args.command == "run":
        print(execute_suite(suite, args))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
