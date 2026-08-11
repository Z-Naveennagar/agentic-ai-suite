#!/usr/bin/env python3
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

"""Run isolated v0.1 design workflows with a bounded process pool."""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "v0_1_runner.py"
CAMPAIGN_ROOT = ROOT / "runs" / "_campaigns"
CAMPAIGN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def atomic_write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def catalog_cases() -> list[str]:
    return list(read_json(ROOT / "evals" / "cases.json")["design_cases"])


def suite_cases(path: Path) -> list[str]:
    suite = read_json(path)
    return [record["case_id"] for record in suite["cases"]]


def timestamp() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def managed_vivado_processes() -> list[dict[str, object]]:
    """Find live Vivado processes whose working directory belongs to this prototype."""
    result: list[dict[str, object]] = []
    runs_root = (ROOT / "runs").resolve()
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            command = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
            cwd = (entry / "cwd").resolve()
        except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
            continue
        if "vivado" not in command.lower() or not cwd.is_relative_to(runs_root):
            continue
        result.append({"pid": int(entry.name), "cwd": str(cwd), "command": command.strip()})
    return sorted(result, key=lambda item: int(item["pid"]))


def preflight_errors() -> list[str]:
    errors: list[str] = []
    validator = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_prototype.py")],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if validator.returncode:
        errors.append("prototype validation failed: " + validator.stdout.strip())
    free_disk = shutil.disk_usage(ROOT).free
    if free_disk < 100 * 1024**3:
        errors.append(f"less than 100 GiB free disk remains ({free_disk / 1024**3:.1f} GiB)")
    sessions = managed_vivado_processes()
    if sessions:
        details = ", ".join(f"PID {item['pid']} in {item['cwd']}" for item in sessions)
        errors.append(f"managed Vivado sessions are already active: {details}")
    return errors


def validate_campaign_id(campaign_id: str) -> None:
    if not CAMPAIGN_ID_PATTERN.fullmatch(campaign_id):
        raise ValueError(
            "campaign ID must contain only letters, digits, '.', '_', and '-'"
        )


def acquire_campaign_lock(campaign_dir: Path):
    campaign_dir.mkdir(parents=True, exist_ok=True)
    stream = (campaign_dir / "runner.lock").open("a+")
    try:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        stream.close()
        raise RuntimeError(f"campaign is already active: {campaign_dir}") from None
    return stream


def execute(
    command: list[str],
    log_path: Path,
) -> int:
    with log_path.open("a") as stream:
        stream.write(f"$ {' '.join(command)}\n")
        stream.flush()
        result = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=stream,
            stderr=subprocess.STDOUT,
        )
        stream.write(f"exit_code={result.returncode}\n")
        return result.returncode


def run_case(
    case_id: str,
    campaign_id: str,
    campaign_dir: Path,
    model: str | None,
    sandbox: str,
    state: dict,
    state_lock: threading.Lock,
    adopt_existing: bool = False,
) -> dict:
    request_id = f"{campaign_id}--{case_id}"
    run_dir = ROOT / "runs" / request_id
    log_path = campaign_dir / "logs" / f"{case_id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    record = state["cases"][case_id]
    with state_lock:
        record.update(
            {
                "request_id": request_id,
                "run_dir": str(run_dir.relative_to(ROOT)),
                "status": "RUNNING",
                "started_at": dt.datetime.now(dt.UTC).isoformat(),
            }
        )
        atomic_write_json(campaign_dir / "state.json", state)

    if run_dir.exists() and any(run_dir.iterdir()):
        run_exit = 2
        with log_path.open("a") as stream:
            action = "adopting existing run" if adopt_existing else "run directory already exists"
            stream.write(f"{action}: {run_dir}\n")
        if adopt_existing:
            probe = subprocess.run(
                [sys.executable, str(RUNNER), "validate", "--run", str(run_dir)],
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if probe.returncode == 0:
                run_exit = 0
            else:
                command = [
                    sys.executable,
                    str(RUNNER),
                    "resume",
                    "--run",
                    str(run_dir),
                    "--sandbox",
                    sandbox,
                ]
                if model:
                    command.extend(["--model", model])
                run_exit = execute(command, log_path)
    else:
        active_sessions = managed_vivado_processes()
        if active_sessions:
            with log_path.open("a") as stream:
                stream.write(f"resource preflight blocked launch: {active_sessions}\n")
            run_exit = 3
        else:
            command = [
                sys.executable,
                str(RUNNER),
                "run",
                "--case",
                case_id,
                "--request-id",
                request_id,
                "--sandbox",
                sandbox,
            ]
            if model:
                command.extend(["--model", model])
            run_exit = execute(command, log_path)

    validate_exit = execute(
        [
            sys.executable,
            str(RUNNER),
            "validate",
            "--run",
            str(run_dir),
        ],
        log_path,
    )
    score_exit = execute(
        [
            sys.executable,
            str(RUNNER),
            "score",
            "--case",
            case_id,
            "--run",
            str(run_dir),
            "--execute-simulation",
        ],
        log_path,
    )
    with state_lock:
        leaked_sessions = managed_vivado_processes()
        record.update(
            {
                "run_exit": run_exit,
                "validate_exit": validate_exit,
                "score_exit": score_exit,
                "status": (
                    "PASS"
                    if run_exit == 0 and validate_exit == 0 and score_exit == 0 and not leaked_sessions
                    else "FAIL"
                ),
                "completed_at": dt.datetime.now(dt.UTC).isoformat(),
            }
        )
        if leaked_sessions:
            record["resource_leaks"] = leaked_sessions
        score_path = run_dir / "score.json"
        if score_path.is_file():
            score = read_json(score_path)
            record["score"] = score.get("score")
            record["maximum_score"] = score.get("maximum_score")
        atomic_write_json(campaign_dir / "state.json", state)
    return record


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    selection = result.add_mutually_exclusive_group()
    selection.add_argument(
        "--suite",
        type=Path,
        help="suite JSON whose cases[] records contain case_id",
    )
    selection.add_argument(
        "--cases",
        nargs="+",
        help="explicit case IDs; default is every case in evals/cases.json",
    )
    result.add_argument("--campaign-id", default=f"frontier-clean-{timestamp()}")
    result.add_argument(
        "--resume",
        action="store_true",
        help="resume the named campaign and adopt evidence-complete existing runs",
    )
    result.add_argument("--workers", type=int, default=1)
    result.add_argument("--model")
    result.add_argument(
        "--sandbox",
        choices=["workspace-write", "danger-full-access"],
        default="workspace-write",
    )
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        validate_campaign_id(args.campaign_id)
    except ValueError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    if args.workers != 1:
        raise SystemExit("ERROR: customer-readiness campaigns currently require --workers 1 until cross-run Vivado session semaphores are enforced")

    errors = preflight_errors()
    if errors:
        raise SystemExit("ERROR: campaign preflight failed:\n- " + "\n- ".join(errors))

    campaign_dir = CAMPAIGN_ROOT / args.campaign_id
    state_path = campaign_dir / "state.json"
    try:
        campaign_lock = acquire_campaign_lock(campaign_dir)
    except RuntimeError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    if args.resume:
        if not state_path.is_file():
            raise SystemExit(f"ERROR: campaign does not exist: {campaign_dir}")
        state = read_json(state_path)
        if state.get("campaign_id") != args.campaign_id:
            raise SystemExit("ERROR: campaign state ID does not match --campaign-id")
        if not isinstance(state.get("cases"), dict) or not state["cases"]:
            raise SystemExit("ERROR: campaign state has no cases")
        cases = list(state["cases"])
        requested_cases = (
            suite_cases(args.suite.resolve())
            if args.suite
            else args.cases
        )
        if requested_cases is not None and requested_cases != cases:
            raise SystemExit(
                "ERROR: resume selection differs from the stored campaign cases"
            )
    else:
        cases = (
            suite_cases(args.suite.resolve())
            if args.suite
            else args.cases or catalog_cases()
        )
        if state_path.exists():
            raise SystemExit(f"ERROR: campaign already exists: {campaign_dir}")
        state = {
            "schema_version": 1,
            "campaign_id": args.campaign_id,
            "created_at": dt.datetime.now(dt.UTC).isoformat(),
            "workers": args.workers,
            "model": args.model or "inherited-frontier",
            "sandbox": args.sandbox,
            "runner_pid": os.getpid(),
            "heartbeat_at": dt.datetime.now(dt.UTC).isoformat(),
            "cases": {
                case_id: {"case_id": case_id, "status": "QUEUED"}
                for case_id in cases
            },
        }
        atomic_write_json(state_path, state)

    known = set(catalog_cases())
    unknown = sorted(set(cases) - known)
    if unknown:
        raise SystemExit(f"ERROR: unknown cases: {unknown}")
    if len(cases) != len(set(cases)):
        raise SystemExit("ERROR: duplicate cases in campaign selection")

    failures = 0
    state_lock = threading.Lock()
    pending_cases = [
        case_id
        for case_id in cases
        if state["cases"][case_id].get("status") != "PASS"
    ]
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                run_case,
                case_id,
                args.campaign_id,
                campaign_dir,
                args.model,
                args.sandbox,
                state,
                state_lock,
                args.resume,
            ): case_id
            for case_id in pending_cases
        }
        while futures:
            done = [future for future in futures if future.done()]
            if not done:
                with state_lock:
                    state["heartbeat_at"] = dt.datetime.now(dt.UTC).isoformat()
                    atomic_write_json(state_path, state)
                time.sleep(5)
                continue
            for future in done:
                case_id = futures.pop(future)
                try:
                    record = future.result()
                    print(
                        f"{record['status']}: {case_id} "
                        f"(run={record['run_exit']}, "
                        f"validate={record['validate_exit']}, "
                        f"score={record['score_exit']})",
                        flush=True,
                    )
                    if record["status"] != "PASS":
                        failures += 1
                except BaseException as exc:
                    with state_lock:
                        state["cases"][case_id].update(
                            {
                                "status": "ERROR",
                                "error": repr(exc),
                                "completed_at": dt.datetime.now(dt.UTC).isoformat(),
                            }
                        )
                        atomic_write_json(state_path, state)
                    print(f"ERROR: {case_id}: {exc}", flush=True)
                    failures += 1
    state["completed_at"] = dt.datetime.now(dt.UTC).isoformat()
    state["status"] = "PASS" if failures == 0 else "FAIL"
    atomic_write_json(state_path, state)
    campaign_lock.close()
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
