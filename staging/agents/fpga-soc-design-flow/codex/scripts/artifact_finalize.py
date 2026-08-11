#!/usr/bin/env python3
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

"""Finalize one workflow stage without changing engineering content."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Callable

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
STAGE_FILES = {
    "spec": (("hardware-spec.json", "hardware-spec.schema.json"),),
    "architecture": (("architecture-plan.json", "architecture-plan.schema.json"),),
    "source": (("source-manifest.json", "source-manifest.schema.json"),),
    "verification": (("verification-result.json", "verification-result.schema.json"),),
    "implementation": (
        ("implementation-result.json", "implementation-result.schema.json"),
    ),
    "vitis": (
        ("vitis-execution-plan.json", "vitis-execution-plan.schema.json"),
        ("vitis-result.json", "vitis-result.schema.json"),
    ),
    "hardware": (
        ("hardware-validation-result.json", "hardware-validation-result.schema.json"),
    ),
}
STAGES = tuple(STAGE_FILES) + ("all",)
VOLATILE_SUFFIXES = {".bit", ".dcp", ".ltx", ".pdi", ".xpr", ".xsa"}
VOLATILE_NAMES = {"debug-map.json"}
VOLATILE_PARTS = {"checkpoints", "hardware-evidence", "hardware_evidence"}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def _atomic_write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(_json_bytes(value))
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def resolve_artifact(path_text: str, run_dir: Path) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    workspace_path = ROOT / path
    if workspace_path.exists():
        return workspace_path
    return run_dir / path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _refresh_hash(
    record: dict,
    hash_field: str,
    path_field: str,
    run_dir: Path,
    label: str,
    write: bool,
    changes: list[str],
    errors: list[str],
) -> None:
    path_text = record.get(path_field)
    if not isinstance(path_text, str) or not path_text:
        errors.append(f"{label} has no usable {path_field}")
        return
    path = resolve_artifact(path_text, run_dir)
    if not path.is_file():
        errors.append(f"{label} does not exist: {path_text}")
        return
    actual = _sha256(path)
    if record.get(hash_field) == actual:
        return
    changes.append(f"{label}.{hash_field}: {record.get(hash_field)!r} -> {actual}")
    if write:
        record[hash_field] = actual
    else:
        errors.append(f"{label} has a stale or missing {hash_field}: {path_text}")


def _source_paths(data: dict) -> list[tuple[str, str]]:
    paths: list[tuple[str, str]] = []
    for index, record in enumerate(data.get("files", [])):
        if isinstance(record, dict) and isinstance(record.get("path"), str):
            paths.append((f"files[{index}]", record["path"]))
    for index, path in enumerate(data.get("compile_order", [])):
        if isinstance(path, str):
            paths.append((f"compile_order[{index}]", path))
    elaboration = data.get("elaboration", {})
    if isinstance(elaboration, dict):
        for field in ("artifacts", "logs"):
            for index, path in enumerate(elaboration.get(field, [])):
                if isinstance(path, str):
                    paths.append((f"elaboration.{field}[{index}]", path))
    for evidence_index, evidence in enumerate(data.get("component_evidence", [])):
        if not isinstance(evidence, dict):
            continue
        for artifact_index, path in enumerate(evidence.get("artifacts", [])):
            if isinstance(path, str):
                paths.append(
                    (
                        f"component_evidence[{evidence_index}].artifacts[{artifact_index}]",
                        path,
                    )
                )
    return paths


def _is_volatile_source_path(path_text: str) -> bool:
    path = Path(path_text)
    lowered_parts = {part.lower() for part in path.parts}
    return (
        path.suffix.lower() in VOLATILE_SUFFIXES
        or path.name.lower() in VOLATILE_NAMES
        or bool(lowered_parts & VOLATILE_PARTS)
        or any(part.lower().startswith("impl_") for part in path.parts)
    )


def refresh_source(
    data: dict,
    run_dir: Path,
    write: bool,
) -> tuple[list[str], list[str]]:
    changes: list[str] = []
    errors: list[str] = []
    for label, path_text in _source_paths(data):
        if _is_volatile_source_path(path_text):
            errors.append(
                f"source-manifest volatile post-source artifact at {label}: {path_text}"
            )
    for index, record in enumerate(data.get("files", [])):
        if isinstance(record, dict):
            _refresh_hash(
                record,
                "sha256",
                "path",
                run_dir,
                f"source file[{index}]",
                write,
                changes,
                errors,
            )
    return changes, errors


def refresh_implementation(
    data: dict,
    run_dir: Path,
    write: bool,
) -> tuple[list[str], list[str]]:
    changes: list[str] = []
    errors: list[str] = []
    for index, record in enumerate(data.get("artifacts", [])):
        if isinstance(record, dict) and record.get("exists") is True:
            _refresh_hash(
                record,
                "sha256",
                "path",
                run_dir,
                f"implementation artifact[{index}]",
                write,
                changes,
                errors,
            )
    return changes, errors


def refresh_vitis(
    plan: dict,
    result: dict,
    run_dir: Path,
    write: bool,
) -> tuple[list[str], list[str]]:
    changes: list[str] = []
    errors: list[str] = []
    for index, record in enumerate(plan.get("input_artifacts", [])):
        if isinstance(record, dict):
            _refresh_hash(
                record,
                "sha256",
                "path",
                run_dir,
                f"Vitis input[{index}]",
                write,
                changes,
                errors,
            )
    plan_path = run_dir / "vitis-execution-plan.json"
    if plan_path.is_file():
        actual = (
            hashlib.sha256(_json_bytes(plan)).hexdigest()
            if write
            else _sha256(plan_path)
        )
        if result.get("plan_sha256") != actual:
            changes.append(
                f"vitis-result.plan_sha256: {result.get('plan_sha256')!r} -> {actual}"
            )
            if write:
                result["plan_sha256"] = actual
            else:
                errors.append("vitis-result has a stale plan_sha256")
    for index, record in enumerate(result.get("artifacts", [])):
        if isinstance(record, dict) and record.get("exists") is True:
            _refresh_hash(
                record,
                "sha256",
                "path",
                run_dir,
                f"Vitis artifact[{index}]",
                write,
                changes,
                errors,
            )
    return changes, errors


def refresh_hardware(
    data: dict,
    run_dir: Path,
    write: bool,
) -> tuple[list[str], list[str]]:
    changes: list[str] = []
    errors: list[str] = []
    programming = data.get("programming", {})
    if isinstance(programming, dict):
        _refresh_hash(
            programming,
            "image_sha256",
            "image",
            run_dir,
            "hardware programming image",
            write,
            changes,
            errors,
        )
        probes_file = programming.get("probes_file")
        if probes_file is not None:
            _refresh_hash(
                programming,
                "probes_sha256",
                "probes_file",
                run_dir,
                "hardware probes file",
                write,
                changes,
                errors,
            )
        elif programming.get("probes_sha256") is not None:
            errors.append("hardware probes_sha256 is set while probes_file is null")
    for index, record in enumerate(data.get("captures", [])):
        if isinstance(record, dict):
            _refresh_hash(
                record,
                "sha256",
                "path",
                run_dir,
                f"hardware capture[{index}]",
                write,
                changes,
                errors,
            )
    for index, record in enumerate(data.get("artifacts", [])):
        if isinstance(record, dict) and record.get("exists") is True:
            _refresh_hash(
                record,
                "sha256",
                "path",
                run_dir,
                f"hardware artifact[{index}]",
                write,
                changes,
                errors,
            )
    return changes, errors


def _schema_errors(data: dict, schema_name: str, artifact_name: str) -> list[str]:
    schema = read_json(CONTRACTS / schema_name)
    validator = jsonschema.validators.validator_for(schema)(schema)
    return [
        f"{artifact_name}:{'/'.join(str(item) for item in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(
            validator.iter_errors(data),
            key=lambda item: list(item.absolute_path),
        )
    ]


def _revision_link_errors(
    run_dir: Path,
    stage: str,
    loaded: dict[str, dict],
) -> list[str]:
    errors: list[str] = []
    upstream_names = {
        "architecture": ("hardware-spec.json",),
        "source": ("hardware-spec.json", "architecture-plan.json"),
        "verification": (
            "hardware-spec.json",
            "architecture-plan.json",
            "source-manifest.json",
        ),
        "implementation": (
            "hardware-spec.json",
            "architecture-plan.json",
            "source-manifest.json",
            "verification-result.json",
        ),
        "hardware": (
            "hardware-spec.json",
            "architecture-plan.json",
            "source-manifest.json",
            "verification-result.json",
            "implementation-result.json",
            "hardware-test.json",
        ),
    }
    for artifact_name in upstream_names.get(stage, ()):
        path = run_dir / artifact_name
        if not path.is_file():
            errors.append(f"missing upstream artifact {artifact_name}")
            continue
        try:
            loaded.setdefault(artifact_name, read_json(path))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{artifact_name}: {exc}")
    if errors:
        return errors

    current_name = STAGE_FILES[stage][0][0]
    current = loaded[current_name]
    if stage == "vitis":
        plan = loaded["vitis-execution-plan.json"]
        result = loaded["vitis-result.json"]
        if result.get("request_id") != plan.get("request_id"):
            errors.append("Vitis result request_id does not match the plan")
        if result.get("plan_revision") != plan.get("revision"):
            errors.append("Vitis result plan_revision does not match the plan")
        run_metadata = run_dir / "run.json"
        if run_metadata.is_file():
            try:
                expected_request_id = read_json(run_metadata).get("request_id")
                if plan.get("request_id") != expected_request_id:
                    errors.append(
                        "Vitis plan request_id does not match run.json"
                    )
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(f"run.json: {exc}")
        return errors

    request_anchor = current.get("request_id")
    run_metadata = run_dir / "run.json"
    if run_metadata.is_file():
        try:
            expected_request_id = read_json(run_metadata).get("request_id")
            if request_anchor != expected_request_id:
                errors.append(
                    f"{current_name} request_id {request_anchor!r} does not match "
                    f"run.json {expected_request_id!r}"
                )
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"run.json: {exc}")
    for artifact_name in upstream_names.get(stage, ()):
        if artifact_name == "hardware-test.json":
            continue
        if loaded[artifact_name].get("request_id") != request_anchor:
            errors.append(f"{current_name} request_id does not match {artifact_name}")

    revision_links = {
        "architecture": (
            ("spec_revision", "hardware-spec.json"),
        ),
        "source": (
            ("spec_revision", "hardware-spec.json"),
            ("architecture_revision", "architecture-plan.json"),
        ),
        "verification": (
            ("spec_revision", "hardware-spec.json"),
            ("architecture_revision", "architecture-plan.json"),
            ("source_revision", "source-manifest.json"),
        ),
        "implementation": (
            ("spec_revision", "hardware-spec.json"),
            ("architecture_revision", "architecture-plan.json"),
            ("source_revision", "source-manifest.json"),
            ("verification_revision", "verification-result.json"),
        ),
        "hardware": (
            ("spec_revision", "hardware-spec.json"),
            ("architecture_revision", "architecture-plan.json"),
            ("source_revision", "source-manifest.json"),
            ("verification_revision", "verification-result.json"),
            ("implementation_revision", "implementation-result.json"),
            ("hardware_test_revision", "hardware-test.json"),
        ),
    }
    for field, artifact_name in revision_links.get(stage, ()):
        expected = loaded[artifact_name].get("revision")
        if current.get(field) != expected:
            errors.append(
                f"{current_name} {field} is {current.get(field)!r}; "
                f"expected {expected!r} from {artifact_name}"
            )
    return errors


def _finalize_single(
    run_dir: Path,
    stage: str,
    write: bool,
) -> tuple[list[str], list[str]]:
    changes: list[str] = []
    errors: list[str] = []
    loaded: dict[str, dict] = {}
    for artifact_name, _ in STAGE_FILES[stage]:
        path = run_dir / artifact_name
        if not path.is_file():
            errors.append(f"missing {artifact_name}")
            continue
        try:
            loaded[artifact_name] = read_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{artifact_name}: {exc}")
    if errors:
        return changes, errors

    refreshers: dict[
        str,
        Callable[[dict, Path, bool], tuple[list[str], list[str]]],
    ] = {
        "source": refresh_source,
        "implementation": refresh_implementation,
        "hardware": refresh_hardware,
    }
    if stage in refreshers:
        artifact_name = STAGE_FILES[stage][0][0]
        stage_changes, stage_errors = refreshers[stage](
            loaded[artifact_name], run_dir, write
        )
        changes.extend(stage_changes)
        errors.extend(stage_errors)
    elif stage == "vitis":
        stage_changes, stage_errors = refresh_vitis(
            loaded["vitis-execution-plan.json"],
            loaded["vitis-result.json"],
            run_dir,
            write,
        )
        changes.extend(stage_changes)
        errors.extend(stage_errors)

    errors.extend(_revision_link_errors(run_dir, stage, loaded))
    for artifact_name, schema_name in STAGE_FILES[stage]:
        errors.extend(
            _schema_errors(loaded[artifact_name], schema_name, artifact_name)
        )
    if write and not errors:
        for artifact_name, _ in STAGE_FILES[stage]:
            _atomic_write_json(run_dir / artifact_name, loaded[artifact_name])
    return changes, errors


def finalize_stage(run_dir: Path, stage: str, write: bool = False) -> dict:
    """Finalize or check a stage and return a machine-readable summary."""

    run_dir = run_dir.resolve()
    if stage not in STAGES:
        raise ValueError(f"unknown finalization stage: {stage}")
    if stage == "all":
        selected = ["spec", "architecture", "source", "verification", "implementation"]
        for optional_stage in ("vitis", "hardware"):
            if any(
                (run_dir / artifact_name).is_file()
                for artifact_name, _ in STAGE_FILES[optional_stage]
            ):
                selected.append(optional_stage)
    else:
        selected = [stage]
    changes: list[str] = []
    errors: list[str] = []
    for selected_stage in selected:
        stage_changes, stage_errors = _finalize_single(
            run_dir,
            selected_stage,
            write,
        )
        changes.extend(f"{selected_stage}: {item}" for item in stage_changes)
        errors.extend(f"{selected_stage}: {item}" for item in stage_errors)
    return {
        "stage": stage,
        "write": write,
        "changes": changes,
        "errors": errors,
        "status": "PASS" if not errors else "FAIL",
    }
