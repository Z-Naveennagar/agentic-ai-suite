#!/usr/bin/env python3
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

"""Report design, hardware, and optional suite status without mutating runs."""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUITE = ROOT / "evals" / "kv260-suite.json"
DESIGN_STAGE_FILES = (
    ("hardware-spec.json", "architecture"),
    ("architecture-plan.json", "source/platform"),
    ("source-manifest.json", "verification"),
    ("verification-result.json", "implementation"),
    ("implementation-result.json", "scoring"),
    ("score.json", "complete"),
)
TERMINAL_STATUSES = {"PASS", "FAIL", "ERROR", "BLOCKED", "INTERRUPTED"}


class StatusError(ValueError):
    """Raised when campaign or suite status input cannot be inspected."""


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise StatusError(f"missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise StatusError(f"invalid JSON file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise StatusError(f"expected a JSON object: {path}")
    return value


def resolve_run_dir(root: Path, record: dict[str, Any]) -> Path | None:
    path_text = record.get("run_dir")
    if not isinstance(path_text, str) or not path_text:
        return None
    path = Path(path_text)
    return path if path.is_absolute() else root / path


def artifact_status(path: Path) -> str:
    if not path.is_file():
        return "MISSING"
    try:
        value = read_json(path)
    except StatusError:
        return "INVALID"
    status = value.get("status")
    return str(status) if status is not None else "PRESENT"


def design_artifacts(run_dir: Path | None) -> dict[str, str]:
    if run_dir is None:
        return {}
    return {
        filename: artifact_status(run_dir / filename)
        for filename, _ in DESIGN_STAGE_FILES
        if (run_dir / filename).exists()
    }


def latest_gate(run_dir: Path | None) -> dict[str, Any] | None:
    if run_dir is None:
        return None
    gate_root = run_dir / "gates"
    if not gate_root.is_dir():
        return None
    candidates: list[dict[str, Any]] = []
    for path in gate_root.glob("*.json"):
        try:
            value = read_json(path)
        except StatusError:
            continue
        if not isinstance(value.get("stage"), str):
            continue
        value = dict(value)
        value["receipt"] = str(path)
        candidates.append(value)
    if not candidates:
        return None
    value = max(
        candidates,
        key=lambda item: (
            str(item.get("evaluated_at", "")),
            int(item.get("iteration", 0)),
        ),
    )
    return {
        "gate_id": value.get("gate_id"),
        "stage": value.get("stage"),
        "iteration": value.get("iteration"),
        "verdict": value.get("verdict"),
        "producer": value.get("producer"),
        "consumer": value.get("consumer"),
        "receipt": value.get("receipt"),
        "next_action": value.get("next_action"),
    }


def infer_design_stage(run_dir: Path | None) -> str:
    if run_dir is None:
        return "queued"
    if not run_dir.exists():
        return "run-missing"
    gate = latest_gate(run_dir)
    if gate is not None and gate.get("verdict") != "PASS":
        return f"gate-{gate.get('stage')}:{str(gate.get('verdict')).lower()}"
    open_gates = sorted((run_dir / "gates").glob(".open-*.json"))
    if open_gates:
        return f"gate-{open_gates[0].stem.removeprefix('.open-')}"
    stage = "intake"
    for filename, next_stage in DESIGN_STAGE_FILES:
        if (run_dir / filename).is_file():
            stage = next_stage
        else:
            break
    return stage


def derived_campaign_status(state: dict[str, Any]) -> str:
    explicit = state.get("status")
    if isinstance(explicit, str):
        return explicit
    records = state.get("cases", {})
    if not isinstance(records, dict) or not records:
        return "EMPTY"
    statuses = {str(record.get("status", "UNKNOWN")) for record in records.values()}
    if statuses == {"PASS"}:
        return "PASS"
    if statuses & {"RUNNING", "QUEUED", "WAITING_DESIGN"}:
        return "RUNNING"
    if statuses & {"FAIL", "ERROR", "BLOCKED", "INTERRUPTED"}:
        return "FAIL"
    return "UNKNOWN"


def status_counts(records: dict[str, Any]) -> dict[str, int]:
    counts = Counter(
        str(record.get("status", "UNKNOWN"))
        for record in records.values()
        if isinstance(record, dict)
    )
    return dict(sorted(counts.items()))


def summarize_design_state(path: Path, root: Path = ROOT) -> dict[str, Any]:
    state = read_json(path)
    records = state.get("cases")
    if not isinstance(records, dict):
        raise StatusError(f"design campaign has no cases object: {path}")
    active = []
    for case_id, record in sorted(records.items()):
        if not isinstance(record, dict) or record.get("status") != "RUNNING":
            continue
        run_dir = resolve_run_dir(root, record)
        active.append(
            {
                "case_id": case_id,
                "status": "RUNNING",
                "stage": infer_design_stage(run_dir),
                "run_dir": record.get("run_dir"),
                "artifacts": design_artifacts(run_dir),
                "latest_gate": latest_gate(run_dir),
            }
        )
    return {
        "state_path": str(path),
        "campaign_id": state.get("campaign_id", path.parent.name),
        "status": derived_campaign_status(state),
        "total": len(records),
        "counts": status_counts(records),
        "active": active,
    }


def design_state_lookup(
    state_path: Path | None,
    root: Path,
) -> dict[str, dict[str, Any]]:
    if state_path is None or not state_path.is_file():
        return {}
    state = read_json(state_path)
    records = state.get("cases", {})
    return records if isinstance(records, dict) else {}


def infer_hardware_stage(
    record: dict[str, Any],
    root: Path,
    design_record: dict[str, Any] | None,
) -> str:
    status = str(record.get("status", "UNKNOWN"))
    run_dir = resolve_run_dir(root, record)
    if run_dir is None and design_record is not None:
        run_dir = resolve_run_dir(root, design_record)
    if run_dir is not None and (run_dir / "hardware-validation-result.json").is_file():
        result = artifact_status(run_dir / "hardware-validation-result.json")
        return f"hardware-result:{result.lower()}"
    if status == "RUNNING":
        return "hardware-validation"
    if status == "WAITING_DESIGN":
        return f"waiting-design:{infer_design_stage(run_dir)}"
    if status == "BLOCKED":
        return "blocked"
    if status in TERMINAL_STATUSES:
        return "complete"
    return status.lower()


def summarize_hardware_state(path: Path, root: Path = ROOT) -> dict[str, Any]:
    state = read_json(path)
    records = state.get("cases")
    if not isinstance(records, dict):
        raise StatusError(f"hardware campaign has no cases object: {path}")
    design_path_text = state.get("design_campaign")
    design_path = (
        Path(design_path_text)
        if isinstance(design_path_text, str) and design_path_text
        else None
    )
    if design_path is not None and not design_path.is_absolute():
        design_path = root / design_path
    design_records = design_state_lookup(design_path, root)
    active = []
    for case_id, record in sorted(records.items()):
        if not isinstance(record, dict) or record.get("status") != "RUNNING":
            continue
        active.append(
            {
                "case_id": case_id,
                "status": "RUNNING",
                "stage": infer_hardware_stage(
                    record,
                    root,
                    design_records.get(case_id),
                ),
                "run_dir": record.get("run_dir"),
            }
        )
    waiting = []
    for case_id, record in sorted(records.items()):
        if not isinstance(record, dict) or record.get("status") != "WAITING_DESIGN":
            continue
        waiting.append(
            {
                "case_id": case_id,
                "stage": infer_hardware_stage(
                    record,
                    root,
                    design_records.get(case_id),
                ),
            }
        )
    return {
        "state_path": str(path),
        "campaign_id": state.get("campaign_id", path.parent.name),
        "status": derived_campaign_status(state),
        "total": len(records),
        "counts": status_counts(records),
        "active": active,
        "waiting": waiting,
    }


def junit_status(path: Path) -> tuple[str, dict[str, int]]:
    if not path.is_file():
        return "MISSING", {"tests": 0, "passed": 0, "failed": 0, "skipped": 0}
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return "INVALID", {"tests": 0, "passed": 0, "failed": 0, "skipped": 0}
    testcases = list(root.iter("testcase"))
    failed = sum(
        1
        for testcase in testcases
        if testcase.find("failure") is not None or testcase.find("error") is not None
    )
    skipped = sum(1 for testcase in testcases if testcase.find("skipped") is not None)
    passed = len(testcases) - failed - skipped
    counts = {
        "tests": len(testcases),
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
    }
    if not testcases:
        return "INVALID", counts
    return ("PASS" if failed == 0 and skipped == 0 else "FAIL"), counts


def materialization_errors(case_root: Path) -> list[str]:
    errors = []
    for name in ("case.json", "prompt.md", "hardware-test.json", "testbench/Makefile"):
        if not (case_root / name).is_file():
            errors.append(f"missing {name}")
    case_path = case_root / "case.json"
    if not case_path.is_file():
        return errors
    try:
        case = read_json(case_path)
    except StatusError as exc:
        return [*errors, str(exc)]
    for source in case.get("candidate", {}).get("rtl_sources", []):
        if not (case_root / "reference" / source).is_file():
            errors.append(f"missing reference/{source}")
    make_dir = case.get("simulation", {}).get("make_directory", "testbench")
    if not (case_root / make_dir / "Makefile").is_file():
        errors.append(f"missing {make_dir}/Makefile")
    return sorted(set(errors))


def summarize_suite(
    suite_path: Path = DEFAULT_SUITE,
    root: Path = ROOT,
) -> dict[str, Any]:
    suite = read_json(suite_path)
    records = suite.get("cases")
    if not isinstance(records, list):
        raise StatusError(f"suite has no cases array: {suite_path}")
    materialized = []
    incomplete = []
    self_tests = []
    for item in records:
        if not isinstance(item, dict) or not isinstance(item.get("case_id"), str):
            raise StatusError(f"suite contains an invalid case record: {suite_path}")
        case_id = item["case_id"]
        errors = materialization_errors(root / "evals" / "designs" / case_id)
        if errors:
            incomplete.append({"case_id": case_id, "errors": errors})
        else:
            materialized.append(case_id)
        result_path = root / "runs" / "_selftest" / case_id / "results.xml"
        status, counts = junit_status(result_path)
        self_tests.append(
            {
                "case_id": case_id,
                "status": status,
                "results": (
                    str(result_path.relative_to(root))
                    if result_path.is_relative_to(root)
                    else str(result_path)
                ),
                **counts,
            }
        )
    test_counts = Counter(record["status"] for record in self_tests)
    return {
        "suite_path": str(suite_path),
        "suite_id": suite.get("id", suite_path.stem),
        "total": len(records),
        "materialized": len(materialized),
        "incomplete": incomplete,
        "reference_self_tests": {
            "counts": dict(sorted(test_counts.items())),
            "tests": sum(record["tests"] for record in self_tests),
            "passed": sum(record["passed"] for record in self_tests),
            "failed": sum(record["failed"] for record in self_tests),
            "skipped": sum(record["skipped"] for record in self_tests),
            "cases": self_tests,
        },
    }


def format_counts(counts: dict[str, int]) -> str:
    return ", ".join(f"{key}={value}" for key, value in counts.items()) or "none"


def render_human(report: dict[str, Any]) -> str:
    lines = []
    for campaign in report["design_campaigns"]:
        lines.append(
            f"Design campaign {campaign['campaign_id']}: "
            f"status={campaign['status']} total={campaign['total']}"
        )
        lines.append(f"  counts: {format_counts(campaign['counts'])}")
        if campaign["active"]:
            lines.append("  active:")
            for item in campaign["active"]:
                artifacts = format_counts(item["artifacts"])
                lines.append(
                    f"    {item['case_id']}: stage={item['stage']} "
                    f"run={item['run_dir']} artifacts=[{artifacts}]"
                )
                gate = item.get("latest_gate")
                if gate:
                    lines.append(
                        f"      gate={gate['gate_id']} "
                        f"verdict={gate['verdict']} producer={gate['producer']} "
                        f"next={gate['consumer']}"
                    )
        else:
            lines.append("  active: none")
    for campaign in report["hardware_campaigns"]:
        lines.append(
            f"Hardware campaign {campaign['campaign_id']}: "
            f"status={campaign['status']} total={campaign['total']}"
        )
        lines.append(f"  counts: {format_counts(campaign['counts'])}")
        if campaign["active"]:
            lines.append("  active:")
            for item in campaign["active"]:
                lines.append(
                    f"    {item['case_id']}: stage={item['stage']} "
                    f"run={item['run_dir']}"
                )
        else:
            lines.append("  active: none")
        if campaign["waiting"]:
            stages = Counter(item["stage"] for item in campaign["waiting"])
            lines.append(
                f"  waiting stages: {format_counts(dict(sorted(stages.items())))}"
            )
    suite = report.get("suite")
    if suite:
        lines.append(
            f"Suite {suite['suite_id']}: "
            f"materialized={suite['materialized']}/{suite['total']} "
            f"incomplete={len(suite['incomplete'])}"
        )
        self_tests = suite["reference_self_tests"]
        lines.append(
            "  reference self-tests: "
            f"{format_counts(self_tests['counts'])}; "
            f"tests={self_tests['tests']} passed={self_tests['passed']} "
            f"failed={self_tests['failed']} skipped={self_tests['skipped']}"
        )
        if suite["incomplete"]:
            lines.append("  incomplete cases:")
            for item in suite["incomplete"]:
                lines.append(
                    f"    {item['case_id']}: {', '.join(item['errors'])}"
                )
    return "\n".join(lines)


def build_report(
    design_states: list[Path],
    hardware_states: list[Path],
    suite_path: Path | None,
    root: Path = ROOT,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": 1,
        "design_campaigns": [
            summarize_design_state(path, root) for path in design_states
        ],
        "hardware_campaigns": [
            summarize_hardware_state(path, root) for path in hardware_states
        ],
    }
    if suite_path is not None:
        report["suite"] = summarize_suite(suite_path, root)
    return report


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "design_states",
        nargs="*",
        type=Path,
        help="one or more design campaign state.json files",
    )
    result.add_argument(
        "--design-state",
        action="append",
        default=[],
        type=Path,
        help="design campaign state.json; repeat for multiple campaigns",
    )
    result.add_argument(
        "--hardware-state",
        action="append",
        default=[],
        type=Path,
        help="optional hardware campaign state.json; repeat for multiple campaigns",
    )
    result.add_argument(
        "--suite-status",
        action="store_true",
        help="include suite materialization and reference self-test status",
    )
    result.add_argument(
        "--suite",
        type=Path,
        default=DEFAULT_SUITE,
        help="suite definition used with --suite-status",
    )
    result.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable JSON instead of human text",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    design_states = [*args.design_states, *args.design_state]
    if not design_states:
        print("ERROR: at least one design campaign state is required", file=sys.stderr)
        return 2
    try:
        report = build_report(
            [path.resolve() for path in design_states],
            [path.resolve() for path in args.hardware_state],
            args.suite.resolve() if args.suite_status else None,
        )
    except (OSError, StatusError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_human(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
