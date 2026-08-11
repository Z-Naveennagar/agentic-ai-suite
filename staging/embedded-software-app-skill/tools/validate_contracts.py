#!/usr/bin/env python3
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
"""Validate skill input and output JSON artifacts against schema contracts.

Examples:
  python skills/tools/validate_contracts.py \
    --input-json skills/references/input_example.json \
    --input-schema skills/references/input_schema.json

  python skills/tools/validate_contracts.py \
    --summary-json skills/references/examples/minimal_e2e/expected_summary.json \
    --summary-schema skills/references/summary.schema.json

  python skills/tools/validate_contracts.py --all \
    --input-json skills/references/input_example.json \
    --summary-json skills/references/examples/minimal_e2e/expected_summary.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable


def _load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise ValueError(f"File not found: {path}") from None
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from None


def _import_jsonschema():
    try:
        import jsonschema  # type: ignore

        return jsonschema
    except Exception as exc:
        raise RuntimeError(
            "Missing dependency 'jsonschema'. Install with: pip install jsonschema"
        ) from exc


def _validate_with_schema(instance_path: Path, schema_path: Path, label: str) -> list[str]:
    errors: list[str] = []
    instance = _load_json(instance_path)
    schema = _load_json(schema_path)

    jsonschema = _import_jsonschema()
    validator = jsonschema.Draft202012Validator(schema)
    sorted_errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))

    if sorted_errors:
        errors.append(f"{label}: schema validation failed ({len(sorted_errors)} error(s))")
        for err in sorted_errors:
            path = ".".join(str(x) for x in err.path) or "<root>"
            errors.append(f"  - {path}: {err.message}")
    else:
        errors.append(f"{label}: schema validation passed")

    return errors


def _check_paths_exist(paths: Iterable[str], workspace_root: Path, label: str) -> list[str]:
    results: list[str] = []
    missing: list[str] = []

    for rel in paths:
        rel_norm = rel.replace("\\", "/")
        candidate = (workspace_root / rel_norm).resolve()
        if not candidate.exists():
            missing.append(rel)

    if missing:
        results.append(f"{label}: artifact existence check failed ({len(missing)} missing)")
        for p in missing:
            results.append(f"  - Missing: {p}")
    else:
        results.append(f"{label}: artifact existence check passed")

    return results


def _validate_summary_artifacts(summary_path: Path, workspace_root: Path) -> list[str]:
    summary = _load_json(summary_path)
    artifacts = summary.get("artifacts", {})
    if not isinstance(artifacts, dict):
        return ["summary: artifact existence check skipped (artifacts is not an object)"]

    # Validate only declared artifact paths; optional null/empty values are ignored.
    candidate_keys = [
        "hardware_model",
        "normalized_requirements",
        "feasibility_report",
        "implementation_plan",
        "command_plan",
        "generate_workspace_script",
        "validation_report",
        "summary_json",
        "execution_feedback_report",
        "workspace_root",
        "build_log",
        "remediation_log",
        "runtime_sanity_artifact",
    ]

    rel_paths = [
        str(artifacts[k])
        for k in candidate_keys
        if k in artifacts and isinstance(artifacts[k], str) and artifacts[k].strip()
    ]

    if not rel_paths:
        return ["summary: artifact existence check skipped (no artifact paths found)"]

    return _check_paths_exist(rel_paths, workspace_root, "summary")


def _default_path(script_file: Path, rel: str) -> Path:
    # Script is in skills/tools, so project root is two levels up.
    project_root = script_file.resolve().parents[2]
    return (project_root / rel).resolve()


def parse_args(argv: list[str]) -> argparse.Namespace:
    script_file = Path(__file__)

    parser = argparse.ArgumentParser(
        description="Validate input payload and summary report against schema contracts.")

    parser.add_argument("--all", action="store_true", help="Validate both input and summary")

    parser.add_argument(
        "--input-json",
        type=Path,
        default=_default_path(script_file, "skills/references/input_example.json"),
        help="Path to input payload JSON",
    )
    parser.add_argument(
        "--input-schema",
        type=Path,
        default=_default_path(script_file, "skills/references/input_schema.json"),
        help="Path to input JSON schema",
    )

    parser.add_argument(
        "--summary-json",
        type=Path,
        default=_default_path(
            script_file, "skills/references/examples/minimal_e2e/expected_summary.json"
        ),
        help="Path to summary JSON",
    )
    parser.add_argument(
        "--summary-schema",
        type=Path,
        default=_default_path(script_file, "skills/references/summary.schema.json"),
        help="Path to summary JSON schema",
    )

    parser.add_argument(
        "--validate-input",
        action="store_true",
        help="Validate input payload/schema pair",
    )
    parser.add_argument(
        "--validate-summary",
        action="store_true",
        help="Validate summary payload/schema pair",
    )

    parser.add_argument(
        "--check-artifacts",
        action="store_true",
        help="Additionally check whether summary artifact paths exist under workspace root",
    )
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=Path(os.getcwd()),
        help="Workspace root for artifact existence checks",
    )

    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    validate_input = args.validate_input or args.all
    validate_summary = args.validate_summary or args.all

    # Default behavior if no explicit mode flags are provided.
    if not validate_input and not validate_summary:
        validate_input = True
        validate_summary = True

    messages: list[str] = []
    failed = False

    try:
        if validate_input:
            messages.extend(
                _validate_with_schema(args.input_json, args.input_schema, "input")
            )
            if any("failed" in m for m in messages if m.startswith("input:")):
                failed = True

        if validate_summary:
            summary_messages = _validate_with_schema(
                args.summary_json, args.summary_schema, "summary"
            )
            messages.extend(summary_messages)
            if any("failed" in m for m in summary_messages):
                failed = True

            if args.check_artifacts:
                artifact_msgs = _validate_summary_artifacts(
                    args.summary_json, args.workspace_root.resolve()
                )
                messages.extend(artifact_msgs)
                if any("failed" in m for m in artifact_msgs):
                    failed = True

    except (ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}")
        return 2

    for line in messages:
        print(line)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
