#!/usr/bin/env python3
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

"""Serialize hardware qualification behind a design campaign."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from contract_validation import validate_artifact_set
from gate_runner import context_path, open_gate
from hardware_validation import match_target, validate_target


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "v0_1_runner.py"
RUNS_ROOT = ROOT / "runs"
CAMPAIGN_ROOT = ROOT / "runs" / "_hardware_campaigns"
LOCK_ROOT = CAMPAIGN_ROOT / "_target_locks"
CAMPAIGN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
REQUIRED_IMPLEMENTATION_KINDS = {
    "programming-image": {"bitstream", "pdi"},
    "ltx": {"ltx"},
    "debug-map": {"debug-map"},
}


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


def timestamp() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


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
        raise RuntimeError(
            f"hardware campaign is already active: {campaign_dir}"
        ) from None
    return stream


def resolve_run_dir(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        raise ValueError("design campaign run_dir must be relative to the workspace")
    resolved = (ROOT / path).resolve()
    runs_root = RUNS_ROOT.resolve()
    if not resolved.is_relative_to(runs_root) or resolved == runs_root:
        raise ValueError("design campaign run_dir escapes the runs directory")
    return resolved


def target_lock_identity(target_profile: Path) -> str:
    target = read_json(target_profile)
    endpoint = target["endpoints"]["hw_server"]
    if endpoint is None:
        return f"profile:{target['id']}"
    endpoint_url = os.environ.get(endpoint["url_env"], endpoint["default_url"])
    return f"hw_server:{endpoint_url}"


@contextlib.contextmanager
def exclusive_target_lock(target_profile: Path, timeout_seconds: int):
    """Hold an OS-level lock for the selected hardware endpoint."""

    identity = target_lock_identity(target_profile)
    lock_name = hashlib.sha256(identity.encode()).hexdigest() + ".lock"
    LOCK_ROOT.mkdir(parents=True, exist_ok=True)
    stream = (LOCK_ROOT / lock_name).open("a+")
    deadline = time.monotonic() + timeout_seconds
    try:
        while True:
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        "target/JTAG lock is busy for the selected endpoint"
                    ) from None
                time.sleep(min(1, max(0, deadline - time.monotonic())))
        stream.seek(0)
        stream.truncate()
        stream.write(
            json.dumps(
                {
                    "lock_key": lock_name.removesuffix(".lock"),
                    "pid": os.getpid(),
                    "acquired_at": dt.datetime.now(dt.UTC).isoformat(),
                },
                sort_keys=True,
            )
            + "\n"
        )
        stream.flush()
        yield
    finally:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        finally:
            stream.close()


def artifact_path(run_dir: Path, path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        resolved = path.resolve()
    else:
        workspace_path = ROOT / path
        resolved = (
            workspace_path.resolve()
            if workspace_path.exists()
            else (run_dir / path).resolve()
        )
    if not resolved.is_relative_to(run_dir.resolve()):
        raise ValueError(f"artifact escapes the selected run: {path_text}")
    return resolved


def readiness_errors(run_dir: Path, target_profile: Path) -> list[str]:
    errors: list[str] = []
    for name in ("hardware-test.json", "implementation-result.json"):
        if not (run_dir / name).is_file():
            errors.append(f"missing {name}")
    if errors:
        return errors
    target_errors, _ = match_target(
        target_profile,
        run_dir / "hardware-test.json",
    )
    errors.extend(target_errors)
    if target_errors:
        return errors
    hardware_test = read_json(run_dir / "hardware-test.json")
    if hardware_test.get("status") != "READY":
        errors.append("hardware test status is not READY")
    errors.extend(
        validate_artifact_set(
            run_dir,
            expected_request_id=run_dir.name,
            require_evidence_files=True,
            require_handoffs=True,
            require_hardware=False,
        )
    )
    if errors:
        return errors
    try:
        implementation = read_json(run_dir / "implementation-result.json")
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"implementation-result.json: {exc}")
        return errors
    if implementation.get("status") != "PASS":
        errors.append("implementation status is not PASS")
    artifacts = implementation.get("artifacts", [])
    for label, kinds in REQUIRED_IMPLEMENTATION_KINDS.items():
        records = [
            record
            for record in artifacts
            if record.get("kind") in kinds and record.get("exists") is True
        ]
        if not records:
            errors.append(f"missing implementation-owned {label}")
            continue
        for record in records:
            try:
                path = artifact_path(run_dir, record["path"])
            except (TypeError, ValueError) as exc:
                errors.append(f"{label}: {exc}")
                continue
            if not path.is_file():
                errors.append(f"{label} does not exist: {record['path']}")
                continue
            expected = record.get("sha256")
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if expected != actual:
                errors.append(f"{label} hash mismatch: {record['path']}")
    return errors


def result_binding_errors(run_dir: Path, target_profile: Path) -> list[str]:
    result_path = run_dir / "hardware-validation-result.json"
    if not result_path.is_file():
        return ["missing hardware-validation-result.json"]
    try:
        result = read_json(result_path)
        target = read_json(target_profile)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read hardware result binding: {exc}"]
    if result.get("target_profile_id") != target["id"]:
        return [
            "hardware result target_profile_id does not match the selected "
            "target profile"
        ]
    return []


def hardware_prompt(
    run_dir: Path,
    target_profile: Path,
) -> str:
    return f"""Perform only the serialized on-target hardware-qualification stage for existing run {run_dir.name}.

Act as the amd_soc_orchestrator for this hardware transition and read `.codex/agents/amd_soc_orchestrator.toml`, `.codex/agents/amd_soc_hardware_validator.toml`, `ARTIFACT_OWNERSHIP_v0.1.md`, and the `vivado-workflow` skill. Delegate the on-target work to the named `amd_soc_hardware_validator` custom-agent type with `fork_turns="none"`.

Immutable inputs:
- run root: {run_dir}
- hardware test: {run_dir / 'hardware-test.json'}
- implementation result: {run_dir / 'implementation-result.json'}
- target profile: {target_profile}

The user explicitly authorized this campaign to program the connected KV260 through JTAG, reset only the hardware test shell, drive its safe VIO controls, and capture ILA evidence. Do not power-cycle the board, alter boot media, or invent missing capabilities. SSH may be unavailable; JTAG-only VIO/ILA qualification is permitted when the hardware test does not require PS/Linux.

Before programming, recheck the image, LTX, final debug map, part, hashes, target identity, and required capabilities. Use Vivado MCP Hardware Manager. Keep one exclusive target/JTAG lock, bound every wait, and restore `hw_test_reset/start/enable = 1/0/0` on cleanup.

Write only `hardware-validation-result.json` and hardware-owned evidence under the run. Do not change any specification, architecture, source, verification, implementation, schema, runner, or debug-map artifact. Finalize the hardware stage and run:
`python3 scripts/v0_1_runner.py validate --run {run_dir} --require-hardware`

Report PASS only if programming, matching probes, mandatory VIO/self-test observations, required ILA capture, evidence hashes, and cleanup all pass.
"""


def execute_hardware(
    run_dir: Path,
    target_profile: Path,
    campaign_dir: Path,
    case_id: str,
    model: str | None,
) -> tuple[int, int]:
    log_path = campaign_dir / "logs" / f"{case_id}.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "codex",
        "exec",
        "--skip-git-repo-check",
        "-C",
        str(ROOT),
        "--sandbox",
        "danger-full-access",
        "--json",
        "-o",
        str(run_dir / "hardware-codex-final.txt"),
    ]
    if model:
        command.extend(["--model", model])
    command.append(hardware_prompt(run_dir, target_profile))
    with log_path.open("w") as stream:
        result = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=stream,
            stderr=subprocess.STDOUT,
        )
    validation = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "validate",
            "--run",
            str(run_dir),
            "--require-hardware",
        ],
        cwd=ROOT,
    )
    validation_exit = validation.returncode
    binding_errors = result_binding_errors(run_dir, target_profile)
    if binding_errors:
        with log_path.open("a") as stream:
            for error in binding_errors:
                stream.write(f"ERROR: {error}\n")
        validation_exit = 1
    return result.returncode, validation_exit


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--design-campaign-state", required=True, type=Path)
    result.add_argument("--target-profile", required=True, type=Path)
    result.add_argument("--campaign-id", default=f"hardware-{timestamp()}")
    result.add_argument(
        "--resume",
        action="store_true",
        help="resume waiting or interrupted cases in the named campaign",
    )
    result.add_argument("--poll-seconds", type=int, default=30)
    result.add_argument(
        "--lock-timeout-seconds",
        type=int,
        default=300,
        help="bounded wait for the selected target/JTAG endpoint lock",
    )
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
    try:
        validate_campaign_id(args.campaign_id)
    except ValueError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    if args.lock_timeout_seconds < 0:
        raise SystemExit("ERROR: --lock-timeout-seconds must be nonnegative")
    design_state_path = args.design_campaign_state.resolve()
    target_profile = args.target_profile.resolve()
    if not design_state_path.is_file():
        raise SystemExit(f"ERROR: missing design campaign: {design_state_path}")
    if not target_profile.is_file():
        raise SystemExit(f"ERROR: missing target profile: {target_profile}")
    target_errors = validate_target(target_profile)
    if target_errors:
        raise SystemExit(
            "ERROR: invalid target profile:\n" + "\n".join(target_errors)
        )
    campaign_dir = CAMPAIGN_ROOT / args.campaign_id
    state_path = campaign_dir / "state.json"
    try:
        campaign_lock = acquire_campaign_lock(campaign_dir)
    except RuntimeError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    design = read_json(design_state_path)
    known_cases = set(read_json(ROOT / "evals" / "cases.json")["design_cases"])
    if not isinstance(design.get("cases"), dict):
        raise SystemExit("ERROR: design campaign has no cases object")
    invalid_cases = sorted(
        case_id
        for case_id in design["cases"]
        if case_id.startswith("kv260_") and case_id not in known_cases
    )
    if invalid_cases:
        raise SystemExit(
            f"ERROR: design campaign contains unknown KV260 cases: {invalid_cases}"
        )
    case_ids = [
        case_id
        for case_id in design["cases"]
        if case_id in known_cases and case_id.startswith("kv260_")
    ]
    if not case_ids:
        raise SystemExit("ERROR: design campaign contains no KV260 cases")
    authorization = {
        "programming": True,
        "probe_drive": True,
        "source": "--authorize-hardware-actions",
        "granted_at": dt.datetime.now(dt.UTC).isoformat(),
    }
    if args.resume:
        if not state_path.is_file():
            raise SystemExit(f"ERROR: campaign does not exist: {campaign_dir}")
        state = read_json(state_path)
        if state.get("campaign_id") != args.campaign_id:
            raise SystemExit("ERROR: campaign state ID does not match --campaign-id")
        if Path(state.get("design_campaign", "")).resolve() != design_state_path:
            raise SystemExit(
                "ERROR: resume design campaign differs from stored campaign"
            )
        if Path(state.get("target_profile", "")).resolve() != target_profile:
            raise SystemExit(
                "ERROR: resume target profile differs from stored campaign"
            )
        if set(state.get("cases", {})) != set(case_ids):
            raise SystemExit(
                "ERROR: resume design cases differ from stored campaign"
            )
        state["authorization"] = authorization
        for record in state["cases"].values():
            if record.get("status") == "ERROR":
                record["status"] = "WAITING_DESIGN"
            elif record.get("status") == "RUNNING":
                run_path = record.get("run_dir")
                run_dir = resolve_run_dir(run_path) if run_path else None
                if (
                    run_dir is not None
                    and (run_dir / "hardware-validation-result.json").is_file()
                ):
                    validation = subprocess.run(
                        [
                            sys.executable,
                            str(RUNNER),
                            "validate",
                            "--run",
                            str(run_dir),
                            "--require-hardware",
                        ],
                        cwd=ROOT,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    record["validate_exit"] = validation.returncode
                    binding_errors = result_binding_errors(
                        run_dir,
                        target_profile,
                    )
                    if binding_errors:
                        record["errors"] = binding_errors
                    record["status"] = (
                        "PASS"
                        if validation.returncode == 0 and not binding_errors
                        else "FAIL"
                    )
                    record["completed_at"] = dt.datetime.now(dt.UTC).isoformat()
                else:
                    record["status"] = "WAITING_DESIGN"
    else:
        if state_path.exists():
            raise SystemExit(f"ERROR: campaign already exists: {campaign_dir}")
        state = {
            "schema_version": 1,
            "campaign_id": args.campaign_id,
            "design_campaign": str(design_state_path),
            "target_profile": str(target_profile),
            "authorization": authorization,
            "created_at": dt.datetime.now(dt.UTC).isoformat(),
            "cases": {
                case_id: {"case_id": case_id, "status": "WAITING_DESIGN"}
                for case_id in case_ids
            },
        }
    atomic_write_json(state_path, state)

    while True:
        design = read_json(design_state_path)
        pending = False
        for case_id, record in state["cases"].items():
            if record["status"] != "WAITING_DESIGN":
                continue
            design_record = design["cases"][case_id]
            design_status = design_record["status"]
            if design_status in {"QUEUED", "RUNNING"}:
                pending = True
                continue
            if design_status != "PASS":
                record.update(
                    {
                        "status": "BLOCKED",
                        "errors": [f"design campaign status is {design_status}"],
                        "completed_at": dt.datetime.now(dt.UTC).isoformat(),
                    }
                )
                atomic_write_json(state_path, state)
                continue
            try:
                run_dir = resolve_run_dir(design_record["run_dir"])
            except (TypeError, ValueError) as exc:
                record.update(
                    {
                        "status": "BLOCKED",
                        "errors": [str(exc)],
                        "completed_at": dt.datetime.now(dt.UTC).isoformat(),
                    }
                )
                atomic_write_json(state_path, state)
                continue
            errors = readiness_errors(run_dir, target_profile)
            if errors:
                record.update(
                    {
                        "status": "BLOCKED",
                        "run_dir": str(run_dir.relative_to(ROOT)),
                        "errors": errors,
                        "completed_at": dt.datetime.now(dt.UTC).isoformat(),
                    }
                )
                atomic_write_json(state_path, state)
                continue

            run_assurance = read_json(run_dir / "run.json").get(
                "assurance", {}
            )
            if (
                isinstance(run_assurance, dict)
                and run_assurance.get("required") is True
                and not context_path(run_dir, "hardware").is_file()
            ):
                open_gate(
                    run_dir,
                    "hardware",
                    approval_granted_by="user via --authorize-hardware-actions",
                    approval_reasons=[
                        "hardware programming or probe drive",
                        f"authorized hardware campaign {args.campaign_id}",
                    ],
                )

            record.update(
                {
                    "status": "RUNNING",
                    "run_dir": str(run_dir.relative_to(ROOT)),
                    "started_at": dt.datetime.now(dt.UTC).isoformat(),
                }
            )
            atomic_write_json(state_path, state)
            lock_error = False
            try:
                with exclusive_target_lock(
                    target_profile,
                    args.lock_timeout_seconds,
                ):
                    run_exit, validate_exit = execute_hardware(
                        run_dir,
                        target_profile,
                        campaign_dir,
                        case_id,
                        args.model,
                    )
            except TimeoutError as exc:
                run_exit, validate_exit = 2, 2
                lock_error = True
                record["errors"] = [str(exc)]
            record.update(
                {
                    "run_exit": run_exit,
                    "validate_exit": validate_exit,
                    "status": (
                        "ERROR"
                        if lock_error
                        else (
                            "PASS"
                            if run_exit == 0 and validate_exit == 0
                            else "FAIL"
                        )
                    ),
                    "completed_at": dt.datetime.now(dt.UTC).isoformat(),
                }
            )
            atomic_write_json(state_path, state)
            print(
                f"{record['status']}: {case_id} "
                f"(run={run_exit}, validate={validate_exit})",
                flush=True,
            )
        waiting = any(
            record["status"] == "WAITING_DESIGN"
            for record in state["cases"].values()
        )
        if not waiting:
            break
        if not pending and design.get("status") in {"PASS", "FAIL"}:
            continue
        time.sleep(max(5, args.poll_seconds))

    failed = [
        record
        for record in state["cases"].values()
        if record["status"] != "PASS"
    ]
    state["status"] = "PASS" if not failed else "FAIL"
    state["completed_at"] = dt.datetime.now(dt.UTC).isoformat()
    atomic_write_json(state_path, state)
    campaign_lock.close()
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
