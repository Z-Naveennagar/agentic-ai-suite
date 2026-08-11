#!/usr/bin/env python3
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

"""Create durable, customer-readable status for one design run."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from contract_validation import validate_artifact_set


ROOT = Path(__file__).resolve().parents[1]
MAX_STAGE_ITERATIONS = 3


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def relative(path: Path, run_dir: Path) -> str:
    try:
        return str(path.resolve().relative_to(run_dir.resolve()))
    except ValueError:
        return str(path.resolve())


def gate_receipts(run_dir: Path) -> list[tuple[dict[str, Any], Path]]:
    receipts: list[tuple[dict[str, Any], Path]] = []
    for path in (run_dir / "gates").glob("*.json"):
        try:
            value = read_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(value.get("stage"), str) and isinstance(value.get("verdict"), str):
            receipts.append((value, path))
    return sorted(
        receipts,
        key=lambda item: (
            str(item[0].get("evaluated_at", "")),
            int(item[0].get("iteration", 0)),
        ),
    )


def open_contexts(run_dir: Path) -> list[tuple[dict[str, Any], Path]]:
    contexts: list[tuple[dict[str, Any], Path]] = []
    for path in (run_dir / "gates").glob(".open-*.json"):
        try:
            value = read_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        contexts.append((value, path))
    return sorted(contexts, key=lambda item: str(item[0].get("opened_at", "")))


def artifact_index(run_dir: Path, receipts: list[tuple[dict[str, Any], Path]]) -> list[dict[str, Any]]:
    paths: set[Path] = {run_dir / "run.json", run_dir / "user-request.md"}
    for receipt, receipt_path in receipts:
        paths.add(receipt_path)
        markdown = receipt_path.with_suffix(".md")
        if markdown.is_file():
            paths.add(markdown)
        for item in [*receipt.get("inputs", []), *receipt.get("outputs", [])]:
            path_text = item.get("path")
            if not isinstance(path_text, str):
                continue
            candidate = Path(path_text)
            if not candidate.is_absolute():
                workspace_candidate = ROOT / candidate
                candidate = workspace_candidate if workspace_candidate.exists() else run_dir / candidate
            if candidate.is_file():
                paths.add(candidate)
    result = []
    for path in sorted(paths):
        if path.is_file():
            result.append(
                {
                    "path": relative(path, run_dir),
                    "bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )
    return result


def build_status(run_dir: Path, *, outcome: str | None = None) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    run = read_json(run_dir / "run.json")
    prior_path = run_dir / "run-status.json"
    prior = read_json(prior_path) if prior_path.is_file() else {}
    receipts = gate_receipts(run_dir)
    contexts = open_contexts(run_dir)
    latest_receipt, latest_path = receipts[-1] if receipts else (None, None)
    active_context, active_path = contexts[-1] if contexts else (None, None)

    if outcome == "INTERRUPTED":
        state = "INTERRUPTED"
    elif active_context is not None:
        state = "RUNNING"
    elif latest_receipt is None:
        state = "INITIALIZING"
    elif latest_receipt.get("verdict") == "PASS" and latest_receipt.get("stage") in {"implementation", "hardware"}:
        state = "COMPLETE"
    else:
        state = str(latest_receipt.get("verdict", "UNKNOWN"))

    if active_context is not None:
        stage = active_context.get("stage")
        owner = active_context.get("producer")
        reason = active_context.get("reason")
        iteration = int(active_context.get("iteration", 1))
        next_action = f"Complete {stage} work, then close its deterministic gate."
        evidence = relative(active_path, run_dir)
        blocking = None
    elif latest_receipt is not None:
        stage = latest_receipt.get("stage")
        owner = latest_receipt.get("producer")
        reason = latest_receipt.get("reason")
        iteration = int(latest_receipt.get("iteration", 1))
        next_action = latest_receipt.get("next_action")
        evidence = relative(latest_path, run_dir)
        blocking = None if latest_receipt.get("verdict") == "PASS" else "; ".join(latest_receipt.get("verdict_reasons", []))
    else:
        stage = "intake"
        owner = "amd_soc_orchestrator"
        reason = "Initialize the preserved customer request."
        iteration = 1
        next_action = "Open and complete the intake gate."
        evidence = "run.json"
        blocking = None

    if state == "COMPLETE":
        validation_errors = validate_artifact_set(
            run_dir,
            expected_request_id=run_dir.name,
            require_evidence_files=True,
            require_handoffs=True,
            require_hardware=latest_receipt.get("stage") == "hardware",
        )
        if validation_errors:
            state = "STALE"
            blocking = "Current contracts reject the prior completion evidence: " + "; ".join(validation_errors)
            next_action = "Resume the run so the owning stages can refresh evidence under the current contracts."

    return {
        "schema_version": 1,
        "request_id": run.get("request_id", run_dir.name),
        "case_id": run.get("case_id"),
        "state": state,
        "completion_profile": (
            "hardware-qualified"
            if latest_receipt and latest_receipt.get("stage") == "hardware" and latest_receipt.get("verdict") == "PASS"
            else "hardware-ready"
            if state == "COMPLETE" and (run_dir / "hardware-test.json").is_file()
            else "design-complete"
            if state == "COMPLETE"
            else None
        ),
        "started_at": prior.get("started_at", run.get("created_at", now())),
        "updated_at": now(),
        "current_stage": stage,
        "current_owner": owner,
        "selection_reason": reason,
        "active_task_identity": f"{stage}:i{iteration:03d}" if state == "RUNNING" else None,
        "active_session_identity": None,
        "iteration": iteration,
        "retry_budget": {
            "maximum_stage_iterations": MAX_STAGE_ITERATIONS,
            "remaining": max(0, MAX_STAGE_ITERATIONS - iteration),
        },
        "last_completed_milestone": (
            {
                "stage": latest_receipt.get("stage"),
                "verdict": latest_receipt.get("verdict"),
                "receipt": relative(latest_path, run_dir),
            }
            if latest_receipt is not None
            else None
        ),
        "latest_evidence": evidence,
        "blocking_condition": blocking,
        "next_action": next_action,
        "resume_command": f"python3 scripts/v0_1_runner.py resume --run runs/{run_dir.name} --sandbox workspace-write",
        "status_command": f"python3 scripts/run_status.py --run runs/{run_dir.name}",
        "artifacts": artifact_index(run_dir, receipts),
    }


def render_report(status: dict[str, Any]) -> str:
    milestone = status.get("last_completed_milestone")
    lines = [
        f"# Run status: {status['request_id']}",
        "",
        f"**State:** {status['state']}  ",
        f"**Current stage:** {status['current_stage']}  ",
        f"**Owner:** {status['current_owner']}  ",
        f"**Updated:** {status['updated_at']}",
        "",
        "## Why this stage",
        "",
        str(status.get("selection_reason") or "Not recorded."),
        "",
        "## Progress and recovery",
        "",
        f"- Active task: `{status.get('active_task_identity') or 'none'}`",
        f"- Active Vivado session: `{status.get('active_session_identity') or 'none recorded'}`",
        f"- Iteration: {status['iteration']} of {status['retry_budget']['maximum_stage_iterations']}",
        f"- Remaining retries: {status['retry_budget']['remaining']}",
        f"- Latest evidence: `{status['latest_evidence']}`",
        f"- Status command: `{status['status_command']}`",
        f"- Resume command: `{status['resume_command']}`",
    ]
    if milestone:
        lines.append(
            f"- Last closed gate: {milestone['stage']} = {milestone['verdict']} "
            f"(`{milestone['receipt']}`)"
        )
    lines.extend(["", "## Next action", "", str(status.get("next_action") or "None."), ""])
    if status.get("blocking_condition"):
        lines.extend(["## Blocking condition", "", str(status["blocking_condition"]), ""])
    lines.extend(["## Artifact index", ""])
    for item in status.get("artifacts", []):
        lines.append(f"- `{item['path']}` — {item['bytes']} bytes, SHA-256 `{item['sha256']}`")
    return "\n".join(lines) + "\n"


def write_run_status(run_dir: Path, *, outcome: str | None = None) -> dict[str, Any]:
    status = build_status(run_dir, outcome=outcome)
    atomic_write_json(run_dir / "run-status.json", status)
    (run_dir / "run-report.md").write_text(render_report(status))
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    status = write_run_status(args.run) if args.write else build_status(args.run)
    print(json.dumps(status, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
