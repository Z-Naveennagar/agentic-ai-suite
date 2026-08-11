#!/usr/bin/env python3
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

"""Deterministic schema, reference, gate, and evidence validation for v0.1 artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
ARTIFACT_SCHEMAS = {
    "hardware-spec.json": "hardware-spec.schema.json",
    "architecture-plan.json": "architecture-plan.schema.json",
    "source-manifest.json": "source-manifest.schema.json",
    "verification-result.json": "verification-result.schema.json",
    "implementation-result.json": "implementation-result.schema.json",
}
HARDWARE_ARTIFACT_SCHEMAS = {
    "hardware-test.json": "hardware-test.schema.json",
    "hardware-validation-result.json": "hardware-validation-result.schema.json",
}
VITIS_ARTIFACT_SCHEMAS = {
    "vitis-execution-plan.json": "vitis-execution-plan.schema.json",
    "vitis-result.json": "vitis-result.schema.json",
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def _schema_errors(path: Path, schema_path: Path) -> tuple[list[str], dict | None]:
    if not path.is_file():
        return [f"missing {path.name}"], None
    try:
        instance = read_json(path)
        schema = read_json(schema_path)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{path.name}: {exc}"], None
    validator = jsonschema.validators.validator_for(schema)(schema)
    errors = [
        f"{path.name}:{'/'.join(str(item) for item in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.absolute_path))
    ]
    return errors, instance if not errors else None


def _ids(items: list[dict], field: str, label: str, errors: list[str]) -> set[str]:
    values = [item[field] for item in items]
    duplicates = sorted({value for value in values if values.count(value) > 1})
    if duplicates:
        errors.append(f"{label} contains duplicate {field} values: {duplicates}")
    return set(values)


def _references(
    values: list[str],
    allowed: set[str],
    label: str,
    errors: list[str],
) -> None:
    unknown = sorted(set(values) - allowed)
    if unknown:
        errors.append(f"{label} references unknown IDs: {unknown}")


def _resolve_artifact(path_text: str, artifact_root: Path) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    workspace_path = ROOT / path
    if workspace_path.exists():
        return workspace_path
    return artifact_root / path


def _check_file(
    path_text: str,
    artifact_root: Path,
    label: str,
    errors: list[str],
    sha256: str | None = None,
) -> None:
    path = _resolve_artifact(path_text, artifact_root)
    if not path.is_file():
        errors.append(f"{label} does not exist: {path_text}")
        return
    if sha256 is not None:
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual.lower() != sha256.lower():
            errors.append(f"{label} SHA-256 mismatch: {path_text}")


def _check_path(
    path_text: str,
    artifact_root: Path,
    label: str,
    errors: list[str],
    sha256: str | None = None,
) -> None:
    path = _resolve_artifact(path_text, artifact_root)
    if not path.exists():
        errors.append(f"{label} does not exist: {path_text}")
        return
    if sha256 is not None:
        if not path.is_file():
            errors.append(f"{label} is not a hashable file: {path_text}")
            return
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual.lower() != sha256.lower():
            errors.append(f"{label} SHA-256 mismatch: {path_text}")


def _hardware_criterion_passes(criterion: dict, measurements: dict) -> bool:
    name = criterion["measurement"]
    if name not in measurements:
        return False
    actual = measurements[name]
    expected = criterion["expected"]
    operator = criterion["operator"]
    try:
        if operator == "equals":
            return actual == expected
        if operator == "not_equals":
            return actual != expected
        if operator == "greater_or_equal":
            return actual >= expected
        if operator == "less_or_equal":
            return actual <= expected
        if operator == "exists":
            return bool(actual) if expected is True else actual is not None
    except TypeError:
        return False
    return False


def _validate_handoffs(artifact_root: Path, request_id: str, errors: list[str]) -> None:
    run_metadata = artifact_root / "run.json"
    if not run_metadata.is_file():
        errors.append("missing run.json")
        return
    run = read_json(run_metadata)
    route = run.get("expected_route", [])
    expected_edges = set(zip(route, route[1:]))
    actual_edges: set[tuple[str, str]] = set()
    for path in sorted(artifact_root.glob("handoff-*.json")):
        handoff_errors, handoff = _schema_errors(path, CONTRACTS / "handoff.schema.json")
        errors.extend(handoff_errors)
        if handoff is None:
            continue
        if handoff["request_id"] != request_id:
            errors.append(f"{path.name}: request_id does not match {request_id}")
        actual_edges.add((handoff["from_agent"], handoff["to_agent"]))
        for artifact in handoff["input_artifacts"]:
            _check_file(artifact["path"], artifact_root, f"{path.name} input", errors)
    missing = sorted(expected_edges - actual_edges)
    if missing:
        errors.append(f"missing workflow handoffs: {missing}")


def validate_artifact_set(
    artifact_root: Path,
    *,
    expected_request_id: str | None = None,
    require_evidence_files: bool = True,
    require_handoffs: bool = False,
    require_hardware: bool = False,
) -> list[str]:
    """Validate design artifacts and optional hardware-qualified evidence."""

    artifact_root = artifact_root.resolve()
    errors: list[str] = []
    artifacts: dict[str, dict] = {}
    for artifact_name, schema_name in ARTIFACT_SCHEMAS.items():
        artifact_errors, instance = _schema_errors(
            artifact_root / artifact_name,
            CONTRACTS / schema_name,
        )
        errors.extend(artifact_errors)
        if instance is not None:
            artifacts[artifact_name] = instance
    hardware_presence = {
        artifact_name: (artifact_root / artifact_name).is_file()
        for artifact_name in HARDWARE_ARTIFACT_SCHEMAS
    }
    if require_hardware and not all(hardware_presence.values()):
        missing = sorted(name for name, present in hardware_presence.items() if not present)
        errors.append(f"hardware-qualified validation is missing artifacts: {missing}")
    if (
        hardware_presence["hardware-validation-result.json"]
        and not hardware_presence["hardware-test.json"]
    ):
        errors.append(
            "hardware-validation-result.json requires hardware-test.json"
        )
    if hardware_presence["hardware-test.json"]:
        artifact_errors, instance = _schema_errors(
            artifact_root / "hardware-test.json",
            CONTRACTS / HARDWARE_ARTIFACT_SCHEMAS["hardware-test.json"],
        )
        errors.extend(artifact_errors)
        if instance is not None:
            artifacts["hardware-test.json"] = instance
    if hardware_presence["hardware-validation-result.json"]:
        for artifact_name in ("hardware-validation-result.json",):
            schema_name = HARDWARE_ARTIFACT_SCHEMAS[artifact_name]
            artifact_errors, instance = _schema_errors(
                artifact_root / artifact_name,
                CONTRACTS / schema_name,
            )
            errors.extend(artifact_errors)
            if instance is not None:
                artifacts[artifact_name] = instance
    if errors:
        return errors

    spec = artifacts["hardware-spec.json"]
    architecture = artifacts["architecture-plan.json"]
    source = artifacts["source-manifest.json"]
    verification = artifacts["verification-result.json"]
    implementation = artifacts["implementation-result.json"]

    debug_maps = [
        item for item in implementation.get("artifacts", [])
        if item.get("kind") == "debug-map" and item.get("exists")
    ]
    debug_map = None
    if debug_maps:
        debug_path = _resolve_artifact(debug_maps[0]["path"], artifact_root)
        debug_errors, debug_map = _schema_errors(
            debug_path, CONTRACTS / "debug-map.schema.json"
        )
        errors.extend(debug_errors)
    if (
        "hardware-test.json" in artifacts
        and artifacts["hardware-test.json"].get("instrumentation", {}).get("debug_map_required")
        and not debug_maps
    ):
        errors.append("hardware-ready design requires a debug-map artifact")

    vitis_presence = {
        artifact_name: (artifact_root / artifact_name).is_file()
        for artifact_name in VITIS_ARTIFACT_SCHEMAS
    }
    software_selected = any(
        package.get("agent") == "vitis_sw_engineer"
        for package in architecture.get("work_packages", [])
    )
    if software_selected and not all(vitis_presence.values()):
        missing = sorted(name for name, present in vitis_presence.items() if not present)
        errors.append(f"PS software selection is missing Vitis artifacts: {missing}")
    if any(vitis_presence.values()) and not all(vitis_presence.values()):
        missing = sorted(name for name, present in vitis_presence.items() if not present)
        errors.append(f"incomplete Vitis artifact pair; missing: {missing}")
    if all(vitis_presence.values()):
        for artifact_name, schema_name in VITIS_ARTIFACT_SCHEMAS.items():
            artifact_errors, instance = _schema_errors(
                artifact_root / artifact_name,
                CONTRACTS / schema_name,
            )
            errors.extend(artifact_errors)
            if instance is not None:
                artifacts[artifact_name] = instance
    if errors:
        return errors

    request_ids = {
        artifact["request_id"]
        for artifact_name, artifact in artifacts.items()
        if artifact_name != "hardware-test.json"
    }
    if len(request_ids) != 1:
        errors.append(f"artifact request_id mismatch: {sorted(request_ids)}")
        request_id = ""
    else:
        request_id = next(iter(request_ids))
    if expected_request_id is not None and request_id != expected_request_id:
        errors.append(f"artifact request_id {request_id!r} does not match {expected_request_id!r}")

    if "hardware-test.json" in artifacts:
        hardware_test = artifacts["hardware-test.json"]
        if hardware_test["target"]["part"] != spec["target"]["part"]:
            errors.append("hardware-test target part does not match hardware specification")
        if hardware_test["target"]["board_part"] != spec["target"]["board"]:
            errors.append("hardware-test target board_part does not match hardware specification")
        if debug_map is not None:
            expected_revisions = {
                "hardware_spec": spec["revision"],
                "architecture_plan": architecture["revision"],
                "hardware_test": hardware_test["revision"],
                "source_manifest": source["revision"],
                "verification_result": verification["revision"],
            }
            for name, revision in expected_revisions.items():
                if debug_map["source_lineage"][name]["revision"] != revision:
                    errors.append(f"debug-map {name} revision does not match the run")
            if debug_map["request_id"] != request_id:
                errors.append("debug-map request_id does not match design artifacts")
            planned_ids = {
                item["id"] for item in hardware_test["instrumentation"].get("vio_cores", [])
            } | {
                item["id"] for item in hardware_test["instrumentation"].get("ila_cores", [])
            }
            mapped_ids = {item["logical_id"] for item in debug_map["cores"]}
            missing_debug_ids = sorted(planned_ids - mapped_ids)
            if missing_debug_ids:
                errors.append(f"debug-map is missing planned cores: {missing_debug_ids}")
            for label in ("bitstream", "ltx", "routed_checkpoint", "fixed_xsa"):
                record = debug_map["build_set"][label]
                _check_file(record["path"], artifact_root, f"debug-map {label}", errors, record["sha256"])

    if "vitis-result.json" in artifacts:
        plan_path = artifact_root / "vitis-execution-plan.json"
        plan = artifacts["vitis-execution-plan.json"]
        vitis_result = artifacts["vitis-result.json"]
        if vitis_result["plan_revision"] != plan["revision"]:
            errors.append("Vitis result plan_revision does not match the execution plan")
        actual_plan_sha256 = hashlib.sha256(plan_path.read_bytes()).hexdigest()
        if vitis_result["plan_sha256"].lower() != actual_plan_sha256:
            errors.append("Vitis result plan_sha256 does not match the execution plan")
        if vitis_result["status"] != "PASS":
            errors.append(f"Vitis result status is {vitis_result['status']}; expected PASS")
        if vitis_result["toolchain_version"] != plan["toolchain"]["version"]:
            errors.append("Vitis result toolchain version does not match the execution plan")
        if require_evidence_files:
            for input_artifact in plan["input_artifacts"]:
                _check_path(
                    input_artifact["path"],
                    artifact_root,
                    f"Vitis input {input_artifact['kind']}",
                    errors,
                    input_artifact["sha256"],
                )
            for output_artifact in vitis_result["artifacts"]:
                if output_artifact["exists"]:
                    _check_path(
                        output_artifact["path"],
                        artifact_root,
                        f"Vitis output {output_artifact['kind']}",
                        errors,
                        output_artifact["sha256"],
                    )

    revision_links = (
        ("architecture spec_revision", architecture["spec_revision"], spec["revision"]),
        ("source spec_revision", source["spec_revision"], spec["revision"]),
        ("source architecture_revision", source["architecture_revision"], architecture["revision"]),
        ("verification spec_revision", verification["spec_revision"], spec["revision"]),
        ("verification architecture_revision", verification["architecture_revision"], architecture["revision"]),
        ("verification source_revision", verification["source_revision"], source["revision"]),
        ("implementation spec_revision", implementation["spec_revision"], spec["revision"]),
        ("implementation architecture_revision", implementation["architecture_revision"], architecture["revision"]),
        ("implementation source_revision", implementation["source_revision"], source["revision"]),
        ("implementation verification_revision", implementation["verification_revision"], verification["revision"]),
    )
    for label, actual, expected in revision_links:
        if actual != expected:
            errors.append(f"{label} is {actual}; expected {expected}")

    requirements = spec["requirements"]
    requirement_ids = _ids(requirements, "id", "requirements", errors)
    must_requirement_ids = {item["id"] for item in requirements if item["priority"] == "must"}
    acceptance_ids = _ids(spec["acceptance"], "id", "acceptance", errors)
    accepted_requirements: set[str] = set()
    for item in spec["acceptance"]:
        _references(item["requirement_ids"], requirement_ids, item["id"], errors)
        accepted_requirements.update(item["requirement_ids"])
    missing_acceptance = sorted(must_requirement_ids - accepted_requirements)
    if missing_acceptance:
        errors.append(f"must requirements lack acceptance criteria: {missing_acceptance}")

    modules = architecture["modules"]
    interfaces = architecture["interfaces"]
    clocks = architecture["clock_domains"]
    resets = architecture["reset_domains"]
    crossings = architecture["cdc_crossings"]
    work_packages = architecture["work_packages"]
    source_plan = architecture["source_plan"]
    obligations = architecture["verification_obligations"]
    decisions = architecture["decisions"]
    module_ids = _ids(modules, "id", "modules", errors)
    interface_ids = _ids(interfaces, "id", "interfaces", errors)
    clock_ids = _ids(clocks, "id", "clock_domains", errors)
    reset_ids = _ids(resets, "id", "reset_domains", errors)
    _ids(crossings, "id", "cdc_crossings", errors)
    work_package_ids = _ids(work_packages, "id", "work_packages", errors)
    _ids(source_plan, "id", "source_plan", errors)
    _ids(obligations, "id", "verification_obligations", errors)
    _ids(decisions, "id", "decisions", errors)
    architecture_ids = module_ids | interface_ids

    for module in modules:
        _references(module["requirement_ids"], requirement_ids, module["id"], errors)
        _references(module["clock_domains"], clock_ids, module["id"], errors)
        _references(module["reset_domains"], reset_ids, module["id"], errors)
    for interface in interfaces:
        _references(interface["requirement_ids"], requirement_ids, interface["id"], errors)
        for endpoint in ("source_module", "destination_module"):
            value = interface[endpoint]
            if value is not None:
                _references([value], module_ids, f"{interface['id']}.{endpoint}", errors)
        if interface["clock_domain"] is not None:
            _references([interface["clock_domain"]], clock_ids, interface["id"], errors)
    for reset in resets:
        _references([reset["clock_domain"]], clock_ids, reset["id"], errors)
    for crossing in crossings:
        _references([crossing["source_clock"], crossing["destination_clock"]], clock_ids, crossing["id"], errors)
    for package in work_packages:
        _references(package["architecture_elements"], architecture_ids, package["id"], errors)
        _references(package["acceptance_ids"], acceptance_ids, package["id"], errors)
        _references(package["depends_on"], work_package_ids, package["id"], errors)
    for module in modules:
        owners = [
            package["agent"]
            for package in work_packages
            if module["id"] in package["architecture_elements"]
        ]
        if owners != [module["owner"]]:
            errors.append(f"{module['id']} must have exactly one matching work-package owner; got {owners}")
    for planned_source in source_plan:
        _references(planned_source["implements"], architecture_ids, planned_source["id"], errors)
    for obligation in obligations:
        _references(obligation["requirement_ids"], requirement_ids, obligation["id"], errors)
    for decision in decisions:
        _references(decision["requirement_ids"], requirement_ids, decision["id"], errors)

    manifest_paths = {item["path"] for item in source["files"]}
    duplicate_paths = sorted(
        {path for path in manifest_paths if sum(item["path"] == path for item in source["files"]) > 1}
    )
    if duplicate_paths:
        errors.append(f"source manifest contains duplicate file paths: {duplicate_paths}")
    _references(source["compile_order"], manifest_paths, "compile_order", errors)
    # A file with kind="package" is a packaged deliverable such as an XSA, not
    # necessarily an HDL compilation unit. SystemVerilog package source is
    # represented as kind="rtl". Require authored RTL in the deterministic
    # source order, but do not require generated wrappers or packaged-IP source
    # copies: listing those copies beside their authored originals would
    # describe duplicate module compilation. Vivado project/BD evidence proves
    # the generated units actually selected by the implementation flow.
    required_compile_paths = {
        item["path"]
        for item in source["files"]
        if item["kind"] == "rtl" and not item.get("generated", False)
    }
    missing_compile_paths = sorted(required_compile_paths - set(source["compile_order"]))
    if missing_compile_paths:
        errors.append(f"RTL files missing from compile_order: {missing_compile_paths}")
    for file_record in source["files"]:
        _references([file_record["architecture_element"]], architecture_ids, file_record["path"], errors)
        if require_evidence_files:
            # Vivado can legitimately rewrite generated project, wrapper, HWH,
            # and block-design products during synthesis/implementation. Their
            # source-stage hashes are useful provenance at handoff time but are
            # not immutable final-run identities. Final generated artifacts are
            # hash-pinned by implementation-result.json instead.
            _check_file(
                file_record["path"],
                artifact_root,
                "source file",
                errors,
                None if file_record["generated"] else file_record["sha256"],
            )
    _ids(source["component_evidence"], "id", "component_evidence", errors)
    if source["status"] == "READY":
        failing_evidence = [
            item["id"] for item in source["component_evidence"] if item["status"] != "PASS"
        ]
        if failing_evidence:
            errors.append(f"READY source manifest has non-PASS evidence: {failing_evidence}")

    test_ids = _ids(verification["tests"], "id", "verification tests", errors)
    for test in verification["tests"]:
        _references(test["requirement_ids"], requirement_ids, test["id"], errors)
    coverage_ids = _ids(
        verification["requirement_coverage"],
        "requirement_id",
        "requirement coverage",
        errors,
    )
    for coverage in verification["requirement_coverage"]:
        _references([coverage["requirement_id"]], requirement_ids, "requirement coverage", errors)
        _references(coverage["test_ids"], test_ids, coverage["requirement_id"], errors)
    missing_coverage = sorted(must_requirement_ids - coverage_ids)
    if missing_coverage:
        errors.append(f"must requirements lack verification coverage records: {missing_coverage}")
    _ids(verification["checks"], "id", "verification checks", errors)
    if require_evidence_files:
        for artifact in verification["artifacts"]:
            if artifact["exists"]:
                _check_file(artifact["path"], artifact_root, "verification artifact", errors)

    run_names = _ids(implementation["runs"], "name", "Vivado runs", errors)
    for required_run in ("synth_1", "impl_1"):
        if required_run not in run_names:
            errors.append(f"implementation is missing required Vivado run {required_run}")
    check_kinds = {item["kind"] for item in implementation["checks"]}
    required_checks = {"synthesis", "implementation", "timing", "drc", "methodology", "artifact"}
    missing_checks = sorted(required_checks - check_kinds)
    if missing_checks:
        errors.append(f"implementation is missing required checks: {missing_checks}")
    _ids(implementation["checks"], "id", "implementation checks", errors)
    if implementation["vivado"]["part"] != spec["target"]["part"]:
        errors.append("implemented part does not match hardware specification")
    if require_evidence_files:
        for run in implementation["runs"]:
            _check_file(run["log"], artifact_root, f"{run['name']} log", errors)
        for check in implementation["checks"]:
            _check_file(check["report"], artifact_root, f"{check['kind']} report", errors)
        for artifact in implementation["artifacts"]:
            if artifact["exists"]:
                _check_file(
                    artifact["path"],
                    artifact_root,
                    f"{artifact['kind']} artifact",
                    errors,
                    artifact["sha256"],
                )

    if "hardware-validation-result.json" in artifacts:
        hardware_test = artifacts["hardware-test.json"]
        hardware = artifacts["hardware-validation-result.json"]
        if require_hardware and hardware["status"] != "PASS":
            errors.append(
                f"hardware validation status is {hardware['status']}; expected PASS"
            )
        if hardware["request_id"] != request_id:
            errors.append("hardware validation request_id does not match design artifacts")
        hardware_links = (
            ("hardware spec_revision", hardware["spec_revision"], spec["revision"]),
            ("hardware architecture_revision", hardware["architecture_revision"], architecture["revision"]),
            ("hardware source_revision", hardware["source_revision"], source["revision"]),
            ("hardware verification_revision", hardware["verification_revision"], verification["revision"]),
            ("hardware implementation_revision", hardware["implementation_revision"], implementation["revision"]),
            ("hardware hardware_test_revision", hardware["hardware_test_revision"], hardware_test["revision"]),
        )
        for label, actual, expected in hardware_links:
            if actual != expected:
                errors.append(f"{label} is {actual}; expected {expected}")
        if hardware["identity"]["part"] != spec["target"]["part"]:
            errors.append("hardware target identity part does not match hardware specification")
        if hardware["identity"]["board_part"] != spec["target"]["board"]:
            errors.append("hardware target identity board_part does not match hardware specification")
        if hardware["status"] == "PASS" and implementation["status"] != "PASS":
            errors.append("hardware validation cannot PASS when implementation is not PASS")
        if hardware["status"] == "PASS":
            if (
                hardware["authorization"]["granted_by"] is None
                or hardware["authorization"]["granted_at"] is None
            ):
                errors.append(
                    "hardware PASS lacks explicit authorization provenance"
                )
            result_test_ids = _ids(
                hardware["tests"],
                "id",
                "hardware tests",
                errors,
            )
            mandatory_criteria = {
                criterion["id"]: criterion
                for criterion in hardware_test["pass_criteria"]
                if criterion["mandatory"]
            }
            missing_tests = sorted(set(mandatory_criteria) - result_test_ids)
            if missing_tests:
                errors.append(
                    f"hardware PASS is missing mandatory tests: {missing_tests}"
                )
            result_tests = {
                test["id"]: test
                for test in hardware["tests"]
            }
            for criterion_id, criterion in mandatory_criteria.items():
                test = result_tests.get(criterion_id)
                if test is not None and not _hardware_criterion_passes(
                    criterion,
                    test["measurements"],
                ):
                    errors.append(
                        f"hardware test {criterion_id} measurements do not "
                        "satisfy the test plan criterion"
                    )

            implementation_images = {
                (artifact["path"], artifact["sha256"].lower())
                for artifact in implementation["artifacts"]
                if artifact["kind"] in {"bitstream", "pdi"}
                and artifact["exists"]
                and artifact["sha256"] is not None
            }
            programmed_image = (
                hardware["programming"]["image"],
                hardware["programming"]["image_sha256"].lower(),
            )
            if programmed_image not in implementation_images:
                errors.append(
                    "hardware programming image is not the hash-matched "
                    "implementation programming image"
                )
            implementation_probes = {
                (artifact["path"], artifact["sha256"].lower())
                for artifact in implementation["artifacts"]
                if artifact["kind"] == "ltx"
                and artifact["exists"]
                and artifact["sha256"] is not None
            }
            programmed_probes = (
                hardware["programming"]["probes_file"],
                hardware["programming"]["probes_sha256"].lower(),
            )
            if programmed_probes not in implementation_probes:
                errors.append(
                    "hardware probes file is not the hash-matched "
                    "implementation LTX"
                )
        if require_evidence_files:
            _check_file(
                hardware["programming"]["image"],
                artifact_root,
                "hardware programming image",
                errors,
                hardware["programming"]["image_sha256"],
            )
            _check_file(
                hardware["programming"]["probes_file"],
                artifact_root,
                "hardware probes file",
                errors,
                hardware["programming"]["probes_sha256"],
            )
            for capture in hardware["captures"]:
                _check_file(
                    capture["path"],
                    artifact_root,
                    "hardware capture",
                    errors,
                    capture["sha256"],
                )
            for artifact in hardware["artifacts"]:
                if artifact["exists"]:
                    _check_file(
                        artifact["path"],
                        artifact_root,
                        "hardware artifact",
                        errors,
                        artifact["sha256"],
                    )

    if require_handoffs and request_id:
        _validate_handoffs(artifact_root, request_id, errors)
    return errors
