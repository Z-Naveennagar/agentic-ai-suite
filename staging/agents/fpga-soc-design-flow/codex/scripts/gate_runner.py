#!/usr/bin/env python3
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

"""Create, evaluate, render, and validate transparent agent transition gates."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import jsonschema

from artifact_finalize import finalize_stage
from contract_validation import validate_artifact_set
from run_status import write_run_status


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
GATE_SCHEMA = CONTRACTS / "gate-receipt.schema.json"
GATE_ROOT_NAME = "gates"
CHANGE_LIMIT = 200
SNAPSHOT_HASH_LIMIT = 8 * 1024 * 1024

STAGE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "intake": {
        "gate_id": "GATE-G0-INTAKE",
        "producer": "amd_soc_orchestrator",
        "consumer": "amd_soc_intent_to_spec",
        "objective": "Preserve the user's request and authorize a bounded specification task.",
        "reason": "Specification must start from an immutable, attributable user request.",
        "inputs": (("user-request", "user-request.md"),),
        "outputs": (("handoff", "handoff-000-intake.json"),),
        "success_status": "READY",
    },
    "spec": {
        "gate_id": "GATE-G1-SPECIFICATION",
        "producer": "amd_soc_intent_to_spec",
        "consumer": "amd_soc_architect",
        "objective": "Translate user intent into traceable requirements and acceptance criteria.",
        "reason": "Architecture may proceed only from a complete, measurable specification.",
        "inputs": (("user-request", "user-request.md"), ("handoff", "handoff-000-intake.json")),
        "outputs": (("hardware-spec", "hardware-spec.json"),),
        "success_status": "READY",
    },
    "architecture": {
        "gate_id": "GATE-G2-ARCHITECTURE",
        "producer": "amd_soc_architect",
        "consumer": "integration owner",
        "objective": "Produce an implementable, owned architecture satisfying the approved specification.",
        "reason": "Source work needs stable interfaces, clocks, resets, budgets, and ownership.",
        "inputs": (("hardware-spec", "hardware-spec.json"),),
        "outputs": (("architecture-plan", "architecture-plan.json"),),
        "success_status": "READY",
    },
    "source": {
        "gate_id": "GATE-G3-SOURCE-INTEGRATION",
        "producer": "integration owner",
        "consumer": "amd_soc_verifier",
        "objective": "Create the approved source set and demonstrate complete elaboration.",
        "reason": "Independent verification requires revision-consistent, elaborated sources.",
        "inputs": (("hardware-spec", "hardware-spec.json"), ("architecture-plan", "architecture-plan.json")),
        "outputs": (("source-manifest", "source-manifest.json"),),
        "success_status": "READY",
    },
    "verification": {
        "gate_id": "GATE-G4-VERIFICATION",
        "producer": "amd_soc_verifier",
        "consumer": "vivado_impl_closure",
        "objective": "Independently verify required behavior and disclose all unverified boundaries.",
        "reason": "Physical implementation may start only after functional obligations pass.",
        "inputs": (("hardware-spec", "hardware-spec.json"), ("architecture-plan", "architecture-plan.json"), ("source-manifest", "source-manifest.json")),
        "outputs": (("verification-result", "verification-result.json"),),
        "success_status": "PASS",
    },
    "vitis": {
        "gate_id": "GATE-G4V-VITIS",
        "producer": "deterministic Vitis runner",
        "consumer": "vivado_impl_closure",
        "objective": "Execute the approved structured Vitis plan and bind outputs to its inputs.",
        "reason": "Closure may consume Vitis outputs only when every selected command and artifact passes.",
        "inputs": (("hardware-spec", "hardware-spec.json"), ("architecture-plan", "architecture-plan.json"), ("source-manifest", "source-manifest.json"), ("verification-result", "verification-result.json"), ("vitis-plan", "vitis-execution-plan.json")),
        "outputs": (("vitis-result", "vitis-result.json"),),
        "success_status": "PASS",
    },
    "implementation": {
        "gate_id": "GATE-G5-IMPLEMENTATION",
        "producer": "vivado_impl_closure",
        "consumer": "amd_soc_orchestrator",
        "objective": "Complete Vivado signoff and produce a traceable programming image.",
        "reason": "Design completion requires functional PASS, physical signoff, and an existing image.",
        "inputs": (("hardware-spec", "hardware-spec.json"), ("architecture-plan", "architecture-plan.json"), ("source-manifest", "source-manifest.json"), ("verification-result", "verification-result.json")),
        "outputs": (("implementation-result", "implementation-result.json"),),
        "success_status": "PASS",
    },
    "hardware": {
        "gate_id": "GATE-G7-HARDWARE-QUALIFICATION",
        "producer": "amd_soc_hardware_validator",
        "consumer": "amd_soc_orchestrator",
        "objective": "Qualify the immutable build on an authorized target and restore safe state.",
        "reason": "Hardware-qualified status requires programming, measurements, captures, and cleanup evidence.",
        "inputs": (("hardware-spec", "hardware-spec.json"), ("architecture-plan", "architecture-plan.json"), ("source-manifest", "source-manifest.json"), ("verification-result", "verification-result.json"), ("implementation-result", "implementation-result.json"), ("hardware-test", "hardware-test.json")),
        "outputs": (("hardware-validation-result", "hardware-validation-result.json"),),
        "success_status": "PASS",
    },
}


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def atomic_write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(_json_bytes(value))
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def now() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def display_path(path: Path) -> str:
    resolved = path.resolve()
    if resolved.is_relative_to(ROOT.resolve()):
        return str(resolved.relative_to(ROOT.resolve()))
    return str(resolved)


def resolve_path(path_text: str, run_dir: Path) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    workspace_path = ROOT / path
    if workspace_path.exists():
        return workspace_path
    return run_dir / path


def run_metadata(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "run.json"
    if not path.is_file():
        raise ValueError(f"missing run.json: {run_dir}")
    return read_json(path)


def assurance_mode(run: dict[str, Any]) -> str:
    assurance = run.get("assurance", {})
    mode = assurance.get("mode", "exception_approval") if isinstance(assurance, dict) else "exception_approval"
    if mode not in {"transparent_automatic", "exception_approval", "approve_every_gate"}:
        raise ValueError(f"unsupported assurance mode: {mode}")
    return mode


def gate_dir(run_dir: Path) -> Path:
    return run_dir / GATE_ROOT_NAME


def context_path(run_dir: Path, stage: str) -> Path:
    return gate_dir(run_dir) / f".open-{stage}.json"


def snapshot_run(run_dir: Path) -> dict[str, dict[str, Any]]:
    snapshot: dict[str, dict[str, Any]] = {}
    gates = gate_dir(run_dir).resolve()
    for path in run_dir.rglob("*"):
        if not path.is_file() or path.resolve().is_relative_to(gates):
            continue
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        record: dict[str, Any] = {"size": stat.st_size}
        if stat.st_size <= SNAPSHOT_HASH_LIMIT:
            try:
                record["sha256"] = sha256(path)
            except FileNotFoundError:
                continue
        else:
            record["mtime_ns"] = stat.st_mtime_ns
        snapshot[str(path.relative_to(run_dir))] = record
    return snapshot


def stage_scope_violations(
    stage: str,
    baseline: dict[str, dict[str, Any]],
    current: dict[str, dict[str, Any]],
) -> list[str]:
    """Return cross-owner writes for stages with a narrow, enforceable scope."""
    if stage != "verification":
        return []
    allowed_prefixes = (
        "verification/",
        "workspaces/verification/",
        "superseded/verification-",
        ".vivado-ai/",
        "handoff-",
    )
    allowed_files = {
        "verification-result.json",
        "codex-events.jsonl",
        "run-status.json",
        "run-report.md",
    }
    changed = (
        set(current) - set(baseline)
        | set(baseline) - set(current)
        | {path for path in set(current) & set(baseline) if current[path] != baseline[path]}
    )
    return sorted(
        path
        for path in changed
        if path not in allowed_files and not path.startswith(allowed_prefixes)
    )


def next_iteration(run_dir: Path, stage: str) -> int:
    values: list[int] = []
    for path in gate_dir(run_dir).glob(f"*-{stage}-i*.json"):
        try:
            values.append(int(path.stem.rsplit("i", 1)[1]))
        except (IndexError, ValueError):
            continue
    return max(values, default=0) + 1


def integration_owner(run: dict[str, Any]) -> str:
    route = run.get("expected_route", [])
    return (
        "amd_soc_platform_integrator"
        if "amd_soc_platform_integrator" in route
        else "vivado_rtl_engineer"
    )


def default_participants(run: dict[str, Any], stage: str) -> tuple[str, str]:
    definition = STAGE_DEFINITIONS[stage]
    producer = definition["producer"]
    consumer = definition["consumer"]
    if producer == "integration owner":
        producer = integration_owner(run)
    if consumer == "integration owner":
        consumer = integration_owner(run)
    return producer, consumer


def artifact_record(
    run_dir: Path,
    kind: str,
    path_text: str,
    *,
    integrity: str = "PINNED",
    revision: int | None = None,
) -> dict[str, Any]:
    path = resolve_path(path_text, run_dir)
    exists = path.is_file()
    if revision is None and exists and path.suffix == ".json":
        try:
            candidate = read_json(path).get("revision")
            revision = candidate if isinstance(candidate, int) else None
        except (OSError, ValueError, json.JSONDecodeError):
            revision = None
    return {
        "kind": kind,
        "path": display_path(path),
        "revision": revision,
        "exists": exists,
        "integrity": integrity,
        "sha256": sha256(path) if exists and integrity == "PINNED" else None,
    }


def open_gate(
    run_dir: Path,
    stage: str,
    *,
    producer: str | None = None,
    consumer: str | None = None,
    objective: str | None = None,
    approval_granted_by: str | None = None,
    approval_reasons: list[str] | None = None,
    waivers: list[str] | None = None,
) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    if stage not in STAGE_DEFINITIONS:
        raise ValueError(f"unknown gate stage: {stage}")
    open_path = context_path(run_dir, stage)
    if open_path.exists():
        raise ValueError(f"gate is already open: {stage}")
    run = run_metadata(run_dir)
    default_producer, default_consumer = default_participants(run, stage)
    definition = STAGE_DEFINITIONS[stage]
    inputs = [
        artifact_record(run_dir, kind, path)
        for kind, path in definition["inputs"]
    ]
    prior_receipts = latest_receipts(run_dir)
    if prior_receipts:
        prior_receipt, prior_path = max(
            prior_receipts.values(),
            key=lambda item: (
                str(item[0].get("evaluated_at", "")),
                int(item[0].get("iteration", 0)),
            ),
        )
        inputs.append(
            artifact_record(
                run_dir,
                f"prior-gate-{prior_receipt['stage']}",
                str(prior_path),
            )
        )
    context = {
        "schema_version": 1,
        "request_id": run["request_id"],
        "stage": stage,
        "iteration": next_iteration(run_dir, stage),
        "mode": assurance_mode(run),
        "opened_at": now(),
        "producer": producer or default_producer,
        "consumer": consumer or default_consumer,
        "objective": objective or definition["objective"],
        "reason": definition["reason"],
        "approval_granted_by": approval_granted_by,
        "approval_granted_at": now() if approval_granted_by else None,
        "approval_reasons": sorted(set(approval_reasons or [])),
        "waivers": _unique(waivers or []),
        "inputs": inputs,
        "baseline": snapshot_run(run_dir),
    }
    atomic_write_json(open_path, context)
    write_run_status(run_dir)
    return context


def approve_gate(
    run_dir: Path,
    stage: str,
    *,
    granted_by: str,
    reasons: list[str] | None = None,
) -> dict[str, Any]:
    open_path = context_path(run_dir.resolve(), stage)
    if not open_path.is_file():
        raise ValueError(f"gate is not open: {stage}")
    context = read_json(open_path)
    context["approval_granted_by"] = granted_by
    context["approval_granted_at"] = now()
    context["approval_reasons"] = _unique(
        [*context.get("approval_reasons", []), *(reasons or [])]
    )
    atomic_write_json(open_path, context)
    return context


def _change_summary(
    baseline: dict[str, dict[str, Any]], current: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    created_all = sorted(set(current) - set(baseline))
    deleted_all = sorted(set(baseline) - set(current))
    modified_all = sorted(
        path for path in set(current) & set(baseline) if current[path] != baseline[path]
    )
    total = len(created_all) + len(modified_all) + len(deleted_all)
    budget = CHANGE_LIMIT

    def take(values: list[str]) -> list[str]:
        nonlocal budget
        selected = values[:budget]
        budget -= len(selected)
        return selected

    return {
        "created": take(created_all),
        "modified": take(modified_all),
        "deleted": take(deleted_all),
        "total_created": len(created_all),
        "total_modified": len(modified_all),
        "total_deleted": len(deleted_all),
        "truncated": total > CHANGE_LIMIT,
    }


def check(
    check_id: str,
    category: str,
    description: str,
    passed: bool,
    evidence: list[str],
    *,
    blocked: bool = False,
) -> dict[str, Any]:
    return {
        "id": check_id,
        "category": category,
        "description": description,
        "mandatory": True,
        "status": "PASS" if passed else ("BLOCKED" if blocked else "FAIL"),
        "evidence": evidence or [description],
    }


def _unique(values: list[str]) -> list[str]:
    return sorted(set(value for value in values if isinstance(value, str) and value))


def _status_artifact(run_dir: Path, stage: str) -> tuple[dict[str, Any] | None, str]:
    output_name = STAGE_DEFINITIONS[stage]["outputs"][0][1]
    path = run_dir / output_name
    if not path.is_file():
        return None, "MISSING"
    try:
        data = read_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return None, "ERROR"
    return data, str(data.get("status", "UNKNOWN"))


def _semantic_checks(stage: str, data: dict[str, Any] | None, run_dir: Path) -> list[dict[str, Any]]:
    if data is None:
        return [check(f"{stage}-output", "integrity", "The stage output exists and is readable.", False, ["stage output missing or invalid"])]
    result: list[dict[str, Any]] = []
    if stage == "intake":
        result.append(check("intake-request-id", "revision", "The intake handoff belongs to this run.", data.get("request_id") == run_metadata(run_dir).get("request_id"), ["handoff-000-intake.json", "run.json"]))
    elif stage == "spec":
        requirements = data.get("requirements", [])
        acceptance = data.get("acceptance", [])
        requirement_ids = [item.get("id") for item in requirements if isinstance(item, dict)]
        must_ids = {item.get("id") for item in requirements if isinstance(item, dict) and item.get("priority") == "must"}
        accepted = {rid for item in acceptance if isinstance(item, dict) for rid in item.get("requirement_ids", [])}
        result.extend([
            check("spec-unique-requirements", "requirements", "Requirement IDs are unique.", len(requirement_ids) == len(set(requirement_ids)), ["hardware-spec.json:requirements"]),
            check("spec-must-acceptance", "requirements", "Every must requirement has an acceptance criterion.", must_ids <= accepted, [f"must={sorted(must_ids)}", f"accepted={sorted(accepted)}"]),
            check("spec-no-open-questions", "requirements", "A READY specification has no unresolved questions.", not data.get("unresolved_questions"), ["hardware-spec.json:unresolved_questions"]),
        ])
    elif stage == "architecture":
        spec = read_json(run_dir / "hardware-spec.json")
        req_ids = {item["id"] for item in spec.get("requirements", [])}
        modules = data.get("modules", [])
        module_ids = {item.get("id") for item in modules}
        clocks = {item.get("id") for item in data.get("clock_domains", [])}
        resets = {item.get("id") for item in data.get("reset_domains", [])}
        packages = data.get("work_packages", [])
        reference_ok = True
        owner_ok = True
        for module in modules:
            reference_ok &= set(module.get("requirement_ids", [])) <= req_ids
            reference_ok &= set(module.get("clock_domains", [])) <= clocks
            reference_ok &= set(module.get("reset_domains", [])) <= resets
            owners = [p.get("agent") for p in packages if module.get("id") in p.get("architecture_elements", [])]
            owner_ok &= owners == [module.get("owner")]
        for interface in data.get("interfaces", []):
            endpoints = {interface.get("source_module"), interface.get("destination_module")} - {None}
            reference_ok &= endpoints <= module_ids
            clock_id = interface.get("clock_domain")
            reference_ok &= clock_id is None or clock_id in clocks
        decision_refs = all(set(item.get("requirement_ids", [])) <= req_ids for item in data.get("decisions", []))
        result.extend([
            check("architecture-references", "architecture", "Modules and interfaces reference defined requirements, clocks, resets, and endpoints.", reference_ok and decision_refs, ["architecture-plan.json", "hardware-spec.json"]),
            check("architecture-ownership", "authority", "Every module has exactly one matching work-package owner.", owner_ok, ["architecture-plan.json:modules", "architecture-plan.json:work_packages"]),
        ])
    elif stage == "source":
        result.extend([
            check("source-elaboration", "elaboration", "The complete source set elaborates successfully.", data.get("elaboration", {}).get("status") == "PASS", _unique(data.get("elaboration", {}).get("artifacts", []) + data.get("elaboration", {}).get("logs", []))),
            check("source-components", "elaboration", "Every declared component check passes.", all(item.get("status") == "PASS" for item in data.get("component_evidence", [])), [item.get("id", "component") for item in data.get("component_evidence", [])] or ["no component checks declared"]),
            check("source-unresolved", "requirements", "No unresolved source issue remains.", not data.get("unresolved"), ["source-manifest.json:unresolved"]),
        ])
    elif stage == "verification":
        spec = read_json(run_dir / "hardware-spec.json")
        must = {item["id"] for item in spec.get("requirements", []) if item.get("priority") == "must"}
        covered = {item.get("requirement_id") for item in data.get("requirement_coverage", []) if item.get("status") == "COVERED"}
        result.extend([
            check("verification-tests", "verification", "Every executed verification test passes.", bool(data.get("tests")) and all(item.get("status") == "PASS" for item in data.get("tests", [])), [item.get("id", "test") for item in data.get("tests", [])]),
            check("verification-coverage", "verification", "Every must requirement is independently covered.", must <= covered and data.get("coverage_reviewed") is True, [f"must={sorted(must)}", f"covered={sorted(covered)}"]),
            check("verification-boundaries", "verification", "No unaccepted verification boundary remains.", not data.get("unverified_boundaries"), ["verification-result.json:unverified_boundaries"]),
        ])
    elif stage == "vitis":
        result.extend([
            check("vitis-commands", "implementation", "Every selected Vitis command passes.", bool(data.get("commands")) and all(item.get("status") == "PASS" and item.get("exit_code") == 0 for item in data.get("commands", [])), [item.get("id", "command") for item in data.get("commands", [])]),
            check("vitis-artifacts", "integrity", "Every declared Vitis output exists with a hash when applicable.", all(not item.get("exists") or resolve_path(item.get("path", ""), run_dir).exists() for item in data.get("artifacts", [])), [item.get("path", "artifact") for item in data.get("artifacts", [])]),
        ])
    elif stage == "implementation":
        required_kinds = {"synthesis", "implementation", "timing", "drc", "methodology", "artifact"}
        passed_kinds = {item.get("kind") for item in data.get("checks", []) if item.get("status") == "PASS"}
        images = [item for item in data.get("artifacts", []) if item.get("kind") in {"bitstream", "pdi"} and item.get("exists")]
        image_ok = bool(images) and all(resolve_path(item["path"], run_dir).is_file() and item.get("sha256") == sha256(resolve_path(item["path"], run_dir)) for item in images)
        cross_errors = validate_artifact_set(run_dir, expected_request_id=run_dir.name, require_evidence_files=True, require_handoffs=False, require_hardware=False)
        diagnostics = data.get("diagnostics", {})
        occurrences = diagnostics.get("occurrences", {})
        classified = diagnostics.get("classified_occurrences", {})
        diagnostic_counts_match = all(
            occurrences.get(level) == classified.get(level)
            for level in ("error", "critical_warning", "warning")
        )
        lifecycle = data.get("vivado", {})
        result.extend([
            check("implementation-runs", "implementation", "Synthesis and implementation runs completed successfully.", bool(data.get("runs")) and all(item.get("status") == "PASS" and item.get("completed") is True for item in data.get("runs", [])), [item.get("log", item.get("name", "run")) for item in data.get("runs", [])]),
            check("implementation-signoff", "implementation", "All mandatory signoff categories pass.", required_kinds <= passed_kinds, [f"required={sorted(required_kinds)}", f"passed={sorted(passed_kinds)}"]),
            check("implementation-image", "integrity", "A hash-matched programming image exists.", image_ok, [item.get("path", "image") for item in images] or ["no programming image"]),
            check("implementation-diagnostics", "implementation", "Every authoritative error, critical warning, and warning occurrence is classified and no message ID is left unexplained.", diagnostic_counts_match and not diagnostics.get("unclassified_message_ids"), [f"occurrences={occurrences}", f"classified={classified}", f"unclassified={diagnostics.get('unclassified_message_ids', [])}"]),
            check("implementation-session-lifecycle", "implementation", "The dedicated Vivado session was closed or explicitly handed back.", lifecycle.get("session_closed") is True and lifecycle.get("session_close_result") in {"PASS", "HANDED_BACK"}, [f"session_id={lifecycle.get('session_id')}", f"owner={lifecycle.get('session_owner')}", f"close={lifecycle.get('session_close_result')}"]),
            check("implementation-cross-artifact", "revision", "The complete design artifact set is revision- and evidence-consistent.", not cross_errors, cross_errors or ["whole-run cross-artifact validation passed"]),
        ])
    elif stage == "hardware":
        cross_errors = validate_artifact_set(run_dir, expected_request_id=run_dir.name, require_evidence_files=True, require_handoffs=False, require_hardware=True)
        result.extend([
            check("hardware-programming", "hardware", "The matching image and probes were programmed successfully.", data.get("programming", {}).get("status") == "PASS", [data.get("programming", {}).get("image", "programming image")]),
            check("hardware-tests", "hardware", "Every mandatory hardware observation passes.", bool(data.get("tests")) and all(item.get("status") == "PASS" for item in data.get("tests", [])), [item.get("id", "hardware test") for item in data.get("tests", [])]),
            check("hardware-cleanup", "hardware", "The target was restored to its declared safe state.", data.get("cleanup", {}).get("status") == "PASS", data.get("cleanup", {}).get("actions", []) or ["cleanup not recorded"]),
            check("hardware-cross-artifact", "revision", "Hardware evidence is bound to the signed-off build and test plan.", not cross_errors, cross_errors or ["hardware-qualified cross-artifact validation passed"]),
        ])
    return result


def _actions(stage: str, data: dict[str, Any] | None) -> list[dict[str, Any]]:
    if data is None:
        return [{"id": f"ACTION-{stage.upper()}-ATTEMPT", "summary": "Attempted to produce the required stage artifact.", "evidence": ["stage output missing or invalid"]}]
    path = STAGE_DEFINITIONS[stage]["outputs"][0][1]
    if stage == "intake":
        summaries = [("PRESERVE", "Preserved the user request and issued the specification work package.", ["user-request.md", path])]
    elif stage == "spec":
        summaries = [("SPECIFY", f"Defined {len(data.get('requirements', []))} requirements and {len(data.get('acceptance', []))} acceptance criteria.", [path])]
    elif stage == "architecture":
        summaries = [("ARCHITECT", f"Defined {len(data.get('modules', []))} modules, {len(data.get('interfaces', []))} interfaces, and {len(data.get('work_packages', []))} owned work packages.", [path])]
    elif stage == "source":
        summaries = [("AUTHOR", f"Authored or integrated {len(data.get('files', []))} declared source files.", [path]), ("ELABORATE", f"Elaborated top {data.get('top', '<unknown>')} with {data.get('elaboration', {}).get('tool') or 'the declared tool'}.", _unique(data.get("elaboration", {}).get("logs", []) + data.get("elaboration", {}).get("artifacts", [])) or [path])]
    elif stage == "verification":
        summaries = [("VERIFY", f"Ran {len(data.get('tests', []))} independent tests using {', '.join(data.get('backends', [])) or 'declared backends'}.", [item.get("command", item.get("id", "test")) for item in data.get("tests", [])])]
    elif stage == "vitis":
        summaries = [("EXECUTE", f"Executed {len(data.get('commands', []))} structured Vitis commands.", [item.get("log", item.get("id", "command")) for item in data.get("commands", [])])]
    elif stage == "implementation":
        summaries = [("IMPLEMENT", "Ran synthesis, placement, routing, and requested physical signoff checks.", [item.get("log", item.get("name", "run")) for item in data.get("runs", [])]), ("EXPORT", "Generated the declared implementation artifact set.", [item.get("path", "artifact") for item in data.get("artifacts", [])])]
    else:
        summaries = [("QUALIFY", f"Programmed through {data.get('programming', {}).get('backend', 'the declared backend')} and evaluated {len(data.get('tests', []))} hardware criteria.", [data.get("programming", {}).get("image", path)]), ("CLEANUP", "Restored the target to the declared safe state.", data.get("cleanup", {}).get("actions", []) or [path])]
    return [{"id": f"ACTION-{stage.upper()}-{suffix}", "summary": summary, "evidence": _unique(evidence) or [path]} for suffix, summary, evidence in summaries]


def _decisions(stage: str, data: dict[str, Any] | None) -> list[dict[str, Any]]:
    if stage != "architecture" or data is None:
        return []
    return [
        {
            "id": item["id"],
            "requirement_ids": item.get("requirement_ids", []),
            "selected": item["selected"],
            "alternatives": item.get("alternatives", []),
            "rationale": item["rationale"],
            "confidence": item.get("confidence", "MEDIUM"),
            "source": item.get("evidence_source", "DERIVED"),
        }
        for item in data.get("decisions", [])
    ]


def _claims(stage: str, data: dict[str, Any] | None) -> list[dict[str, Any]]:
    if data is None:
        return [{"id": f"CLAIM-{stage.upper()}-OUTPUT", "statement": "The required stage output was produced.", "requirement_ids": [], "evidence": [STAGE_DEFINITIONS[stage]["outputs"][0][1]], "status": "FAIL"}]
    status = "PASS" if data.get("status") == STAGE_DEFINITIONS[stage]["success_status"] else "FAIL"
    claims = [{"id": f"CLAIM-{stage.upper()}-STATUS", "statement": f"The {stage} stage satisfies its declared transition condition.", "requirement_ids": [], "evidence": [STAGE_DEFINITIONS[stage]["outputs"][0][1]], "status": status}]
    if stage == "architecture":
        for item in data.get("decisions", []):
            claims.append({"id": f"CLAIM-{item['id']}", "statement": item["selected"], "requirement_ids": item.get("requirement_ids", []), "evidence": [item["rationale"]], "status": status})
    elif stage == "verification":
        for item in data.get("requirement_coverage", []):
            claims.append({"id": f"CLAIM-COVERAGE-{item['requirement_id']}", "statement": f"Requirement {item['requirement_id']} is independently covered.", "requirement_ids": [item["requirement_id"]], "evidence": item.get("test_ids", []), "status": "PASS" if item.get("status") == "COVERED" else "FAIL"})
    elif stage == "implementation":
        for item in data.get("checks", []):
            claims.append({"id": f"CLAIM-{item['id']}", "statement": f"Implementation check {item['kind']} passed.", "requirement_ids": [], "evidence": [item.get("report", "implementation-result.json")], "status": "PASS" if item.get("status") == "PASS" else "FAIL"})
    elif stage == "hardware":
        for item in data.get("tests", []):
            claims.append({"id": f"CLAIM-HARDWARE-{item['id']}", "statement": f"Hardware criterion {item['id']} passed.", "requirement_ids": [], "evidence": item.get("evidence", []), "status": "PASS" if item.get("status") == "PASS" else "FAIL"})
    return claims


def _declared_outputs(stage: str, data: dict[str, Any] | None, run_dir: Path) -> list[dict[str, Any]]:
    outputs = [artifact_record(run_dir, kind, path) for kind, path in STAGE_DEFINITIONS[stage]["outputs"]]
    if data is None:
        return outputs
    extras: list[tuple[str, str, bool]] = []
    if stage == "source":
        extras.extend((item.get("kind", "source"), item.get("path", ""), not item.get("generated", False)) for item in data.get("files", []))
        elaboration = data.get("elaboration", {})
        extras.extend(
            ("elaboration-evidence", path, True)
            for path in [
                *elaboration.get("artifacts", []),
                *elaboration.get("logs", []),
            ]
        )
        extras.extend(
            ("component-evidence", path, True)
            for item in data.get("component_evidence", [])
            for path in item.get("artifacts", [])
        )
    elif stage == "verification":
        extras.extend((item.get("kind", "verification-evidence"), item.get("path", ""), True) for item in data.get("artifacts", []) if item.get("exists"))
    elif stage in {"implementation", "vitis", "hardware"}:
        extras.extend((item.get("kind", "artifact"), item.get("path", ""), bool(item.get("sha256"))) for item in data.get("artifacts", []) if item.get("exists"))
        if stage == "implementation":
            extras.extend(
                ("vivado-run-log", item.get("log", ""), True)
                for item in data.get("runs", [])
            )
            extras.extend(
                (f"{item.get('kind', 'signoff')}-report", item.get("report", ""), True)
                for item in data.get("checks", [])
            )
        if stage == "vitis":
            extras.extend(
                ("vitis-command-log", item.get("log", ""), True)
                for item in data.get("commands", [])
            )
        if stage == "hardware":
            programming = data.get("programming", {})
            extras.extend([("programming-image", programming.get("image", ""), True), ("probes", programming.get("probes_file", ""), True)])
            extras.extend((f"capture-{item.get('format', 'evidence')}", item.get("path", ""), True) for item in data.get("captures", []))
    seen = {item["path"] for item in outputs}
    for kind, path_text, pinned in extras:
        if not path_text:
            continue
        record = artifact_record(run_dir, kind, path_text, integrity="PINNED" if pinned else "OBSERVED")
        if record["path"] not in seen:
            outputs.append(record)
            seen.add(record["path"])
    return outputs


def _disclosures(stage: str, data: dict[str, Any] | None, run_dir: Path) -> list[dict[str, Any]]:
    disclosures: list[dict[str, Any]] = []
    hardware_test_path = run_dir / "hardware-test.json"
    if hardware_test_path.is_file() and stage in {"source", "implementation", "hardware"}:
        test = read_json(hardware_test_path)
        stimulus = test.get("stimulus", {})
        for key in ("adapter", "control_plane", "data_plane", "description"):
            if key in stimulus:
                disclosures.append({"key": f"stimulus.{key}", "value": stimulus[key], "source": "hardware-test.json"})
        disclosures.append({"key": "external_equipment.count", "value": len(test.get("external_equipment", [])), "source": "hardware-test.json"})
    if stage == "source" and data is not None:
        constraints = [item.get("path") for item in data.get("files", []) if item.get("kind") == "constraint"]
        disclosures.append({"key": "constraints.user_or_rtl_owned", "value": ", ".join(constraints) if constraints else "none declared", "source": "source-manifest.json"})
    if stage == "implementation" and data is not None:
        disclosures.extend([
            {"key": "hardware.programmed", "value": False, "source": "implementation boundary policy"},
            {"key": "vivado.session_id", "value": data.get("vivado", {}).get("session_id"), "source": "implementation-result.json"},
            {"key": "vivado.part", "value": data.get("vivado", {}).get("part"), "source": "implementation-result.json"},
            {"key": "vivado.board", "value": data.get("vivado", {}).get("board"), "source": "implementation-result.json"},
        ])
    if stage == "hardware" and data is not None:
        disclosures.extend([
            {"key": "hardware.programmed", "value": data.get("programming", {}).get("status") == "PASS", "source": "hardware-validation-result.json"},
            {"key": "hardware.programming_backend", "value": data.get("programming", {}).get("backend"), "source": "hardware-validation-result.json"},
            {"key": "hardware.target", "value": data.get("identity", {}).get("target_name"), "source": "hardware-validation-result.json"},
        ])
    return disclosures


def _assumptions(stage: str, data: dict[str, Any] | None) -> list[str]:
    if data is None:
        return []
    if stage == "spec":
        return _unique(data.get("assumptions", []))
    if stage == "architecture":
        return _unique([risk.get("statement") for risk in data.get("risks", []) if risk.get("severity") in {"medium", "high"}])
    return []


def _unverified(stage: str, data: dict[str, Any] | None) -> list[str]:
    if data is None:
        return ["The required stage output is missing or invalid."]
    if stage == "verification":
        return _unique(data.get("unverified_boundaries", []))
    if stage == "implementation":
        return ["The build has not been programmed or exercised on hardware."]
    return []


def _side_effects(stage: str, data: dict[str, Any] | None) -> dict[str, Any]:
    project_mutated = stage in {"source", "vitis", "implementation"}
    programmed = stage == "hardware" and data is not None and data.get("programming", {}).get("status") == "PASS"
    vio = stage == "hardware" and programmed and any(core.get("kind") == "vio" for core in data.get("debug_cores", []))
    external = stage == "hardware" and data is not None and any(item.get("adapter") == "external_equipment" and item.get("status") == "PASS" for item in data.get("connections", []))
    details = []
    if project_mutated:
        details.append("Vivado/Vitis project or build state may have been created or updated within the run.")
    if programmed:
        details.append("The authorized target was programmed with the recorded image.")
    if vio:
        details.append("VIO outputs were driven according to the hardware test sequence.")
    if not details:
        details.append("No hardware or external-equipment mutation is claimed by this stage.")
    return {"vivado_project_mutated": project_mutated, "hardware_programmed": programmed, "vio_driven": vio, "external_equipment_controlled": external, "details": details}


def _approval(stage: str, data: dict[str, Any] | None, context: dict[str, Any], mode: str) -> dict[str, Any]:
    reasons = list(context.get("approval_reasons", []))
    if context.get("waivers"):
        reasons.append("one or more explicit waivers were requested")
    if mode == "approve_every_gate":
        reasons.append("approve-every-gate mode")
    if stage == "architecture" and data is not None:
        if any(item.get("changes_observable_behavior") for item in data.get("decisions", [])):
            reasons.append("architecture decision changes observable behavior")
    if stage == "hardware":
        reasons.append("hardware programming or probe drive")
    reasons = _unique(reasons)
    granted_by = context.get("approval_granted_by")
    granted_at = context.get("approval_granted_at")
    if stage == "hardware" and data is not None:
        authorization = data.get("authorization", {})
        if authorization.get("programming") and authorization.get("probe_drive") and authorization.get("granted_by"):
            granted_by = authorization.get("granted_by")
            granted_at = authorization.get("granted_at")
    required = bool(reasons)
    status = "GRANTED" if required and granted_by else ("PENDING" if required else "NOT_REQUIRED")
    return {"required": required, "reasons": reasons, "status": status, "granted_by": granted_by, "granted_at": granted_at}


def _schema_check(path: Path, schema_path: Path) -> list[str]:
    if not path.is_file():
        return [f"missing {path.name}"]
    try:
        data = read_json(path)
        schema = read_json(schema_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [str(exc)]
    validator = jsonschema.validators.validator_for(schema)(schema)
    return [
        f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(data), key=lambda item: list(item.absolute_path))
    ]


def _intake_finalizer(run_dir: Path) -> dict[str, Any]:
    errors = _schema_check(run_dir / "handoff-000-intake.json", CONTRACTS / "handoff.schema.json")
    return {"stage": "intake", "write": False, "changes": [], "errors": errors, "status": "PASS" if not errors else "FAIL"}


def receipt_filename(stage: str, iteration: int, markdown: bool = False) -> str:
    prefix = STAGE_DEFINITIONS[stage]["gate_id"].removeprefix("GATE-").lower()
    suffix = "md" if markdown else "json"
    return f"{prefix}-{stage}-i{iteration:03d}.{suffix}"


def close_gate(
    run_dir: Path,
    stage: str,
    finalizer_result: dict[str, Any] | None = None,
    *,
    auto_open_next: bool = False,
) -> tuple[dict[str, Any], Path]:
    run_dir = run_dir.resolve()
    if stage not in STAGE_DEFINITIONS:
        raise ValueError(f"unknown gate stage: {stage}")
    open_path = context_path(run_dir, stage)
    if not open_path.is_file():
        raise ValueError(f"gate was not opened before work began: {stage}")
    context = read_json(open_path)
    run = run_metadata(run_dir)
    if context.get("request_id") != run.get("request_id"):
        raise ValueError("open gate context belongs to a different request")
    if finalizer_result is None:
        finalizer_result = _intake_finalizer(run_dir) if stage == "intake" else finalize_stage(run_dir, stage, write=True)
    data, producer_status = _status_artifact(run_dir, stage)
    definition = STAGE_DEFINITIONS[stage]
    checks = [
        check("gate-authority", "authority", "The configured producer owns this stage transition.", context.get("producer") == default_participants(run, stage)[0], [f"producer={context.get('producer')}", f"expected={default_participants(run, stage)[0]}"]),
        check("gate-input-integrity", "integrity", "All inputs existed and were hash-pinned before work began.", all(item.get("exists") and item.get("sha256") for item in context.get("inputs", [])), [item.get("path", "input") for item in context.get("inputs", [])] or ["stage has no declared inputs"]),
        check("gate-stage-contract", "schema", "The owned artifact schema and upstream revision links pass.", finalizer_result.get("status") == "PASS", finalizer_result.get("errors") or ["deterministic stage finalizer passed"]),
        check("gate-producer-status", "other", f"The producer reports the required {definition['success_status']} status.", producer_status == definition["success_status"], [f"actual={producer_status}", f"required={definition['success_status']}"]),
    ]
    checks.extend(_semantic_checks(stage, data, run_dir))
    outputs = _declared_outputs(stage, data, run_dir)
    checks.append(check("gate-output-integrity", "integrity", "Every declared output exists; pinned outputs are hash-bound to disk.", bool(outputs) and outputs[0]["sha256"] is not None and all(item["exists"] and (item["integrity"] != "PINNED" or item["sha256"] is not None) for item in outputs), [item["path"] for item in outputs]))
    approval = _approval(stage, data, context, context["mode"])
    checks.append(check("gate-approval", "approval", "Every required user approval is recorded.", approval["status"] in {"NOT_REQUIRED", "GRANTED"}, approval["reasons"] or ["no approval required"], blocked=approval["status"] == "PENDING"))
    current = snapshot_run(run_dir)
    changes = _change_summary(context.get("baseline", {}), current)
    scope_violations = stage_scope_violations(
        stage, context.get("baseline", {}), current
    )
    checks.append(
        check(
            "gate-write-scope",
            "authority",
            "The stage changed only files owned by that specialist or its disposable workspace.",
            not scope_violations,
            scope_violations or ["no cross-owner file changes detected"],
        )
    )
    failures = [item for item in checks if item["status"] != "PASS" and item["mandatory"]]
    if any(item["status"] == "BLOCKED" for item in failures):
        verdict = "BLOCKED"
    elif failures:
        verdict = "FAIL"
    else:
        verdict = "PASS"
    reasons = [f"{item['id']}: {item['description']}" for item in failures] or ["All mandatory deterministic checks passed."]
    next_action = (
        f"Proceed to {context['consumer']}."
        if verdict == "PASS"
        else ("Obtain the recorded approval before continuing." if verdict == "BLOCKED" else "Return findings to the owning agent and do not advance.")
    )
    receipt = {
        "schema_version": 1,
        "request_id": context["request_id"],
        "gate_id": definition["gate_id"],
        "iteration": context["iteration"],
        "stage": stage,
        "mode": context["mode"],
        "opened_at": context["opened_at"],
        "evaluated_at": now(),
        "producer": context["producer"],
        "consumer": context["consumer"],
        "objective": context["objective"],
        "reason": context["reason"],
        "inputs": context["inputs"],
        "actions": _actions(stage, data),
        "decisions": _decisions(stage, data),
        "claims": _claims(stage, data),
        "outputs": outputs,
        "checks": checks,
        "changes": changes,
        "disclosures": _disclosures(stage, data, run_dir),
        "assumptions": _assumptions(stage, data),
        "waivers": context.get("waivers", []),
        "unverified_boundaries": _unverified(stage, data),
        "side_effects": _side_effects(stage, data),
        "approval": approval,
        "producer_status": producer_status,
        "evaluator": {"kind": "deterministic", "implementation": "scripts/gate_runner.py", "command": f"python3 scripts/gate_runner.py close --run {display_path(run_dir)} --stage {stage}"},
        "verdict": verdict,
        "verdict_reasons": reasons,
        "next_action": next_action,
    }
    validator = jsonschema.validators.validator_for(read_json(GATE_SCHEMA))(read_json(GATE_SCHEMA))
    schema_errors = list(validator.iter_errors(receipt))
    if schema_errors:
        details = "; ".join(f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}" for error in schema_errors)
        raise ValueError(f"generated gate receipt is invalid: {details}")
    receipt_path = gate_dir(run_dir) / receipt_filename(stage, context["iteration"])
    atomic_write_json(receipt_path, receipt)
    markdown_path = gate_dir(run_dir) / receipt_filename(stage, context["iteration"], markdown=True)
    markdown_path.write_text(render_receipt(receipt))
    open_path.unlink()
    if auto_open_next and verdict == "PASS":
        next_stage = next_stage_for(run_dir, stage)
        if next_stage and not context_path(run_dir, next_stage).exists():
            open_gate(run_dir, next_stage)
        else:
            write_run_status(run_dir)
    else:
        write_run_status(run_dir)
    return receipt, receipt_path


def next_stage_for(run_dir: Path, stage: str) -> str | None:
    if stage == "intake":
        return "spec"
    if stage == "spec":
        return "architecture"
    if stage == "architecture":
        return "source"
    if stage == "source":
        return "verification"
    if stage == "verification":
        return "vitis" if (run_dir / "vitis-execution-plan.json").is_file() else "implementation"
    if stage == "vitis":
        return "implementation"
    return None


def latest_receipts(run_dir: Path) -> dict[str, tuple[dict[str, Any], Path]]:
    latest: dict[str, tuple[dict[str, Any], Path]] = {}
    for path in sorted(gate_dir(run_dir).glob("*.json")):
        if path.name.startswith(".open-"):
            continue
        try:
            receipt = read_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        stage = receipt.get("stage")
        iteration = receipt.get("iteration", 0)
        if stage not in STAGE_DEFINITIONS:
            continue
        current = latest.get(stage)
        if current is None or iteration > current[0].get("iteration", 0):
            latest[stage] = (receipt, path)
    return latest


def required_gate_stages(run_dir: Path, require_hardware: bool = False) -> list[str]:
    stages = ["intake", "spec", "architecture", "source", "verification"]
    if (run_dir / "vitis-execution-plan.json").is_file() or (run_dir / "vitis-result.json").is_file():
        stages.append("vitis")
    stages.append("implementation")
    if require_hardware or (run_dir / "hardware-validation-result.json").is_file():
        stages.append("hardware")
    return stages


def validate_gate_set(run_dir: Path, *, require_hardware: bool = False) -> list[str]:
    run_dir = run_dir.resolve()
    errors: list[str] = []
    run = run_metadata(run_dir)
    receipts = latest_receipts(run_dir)
    schema = read_json(GATE_SCHEMA)
    validator = jsonschema.validators.validator_for(schema)(schema)
    for stage in required_gate_stages(run_dir, require_hardware):
        if stage not in receipts:
            errors.append(f"missing transition gate receipt for {stage}")
            continue
        receipt, path = receipts[stage]
        for error in sorted(validator.iter_errors(receipt), key=lambda item: list(item.absolute_path)):
            errors.append(f"{path.name}:{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}")
        if receipt.get("request_id") != run.get("request_id"):
            errors.append(f"{path.name}: request_id does not match run.json")
        if receipt.get("verdict") != "PASS":
            errors.append(f"{path.name}: latest verdict is {receipt.get('verdict')}")
        for artifact in [*receipt.get("inputs", []), *receipt.get("outputs", [])]:
            if artifact.get("integrity") != "PINNED" or not artifact.get("exists"):
                continue
            resolved = resolve_path(artifact["path"], run_dir)
            if not resolved.is_file():
                errors.append(f"{path.name}: pinned artifact is missing: {artifact['path']}")
            elif sha256(resolved) != artifact.get("sha256"):
                errors.append(f"{path.name}: pinned artifact hash mismatch: {artifact['path']}")
    return errors


def render_receipt(receipt: dict[str, Any]) -> str:
    lines = [
        f"# {receipt['gate_id']}: {receipt['stage']}",
        "",
        f"**Verdict:** {receipt['verdict']}  ",
        f"**Producer:** {receipt['producer']}  ",
        f"**Next:** {receipt['consumer']}  ",
        f"**Iteration:** {receipt['iteration']}",
        "",
        "## Why this work was done",
        "",
        receipt["objective"],
        "",
        receipt["reason"],
        "",
        "## Inputs",
        "",
    ]
    for item in receipt["inputs"]:
        digest = item["sha256"][:12] if item["sha256"] else "not pinned"
        lines.append(f"- `{item['kind']}`: `{item['path']}` (revision {item['revision']}, SHA-256 `{digest}`)")
    lines.extend(["", "## Actions", ""])
    for item in receipt["actions"]:
        lines.append(f"- **{item['id']}** — {item['summary']}")
    if receipt["decisions"]:
        lines.extend(["", "## Engineering decisions", ""])
        for item in receipt["decisions"]:
            requirements = ", ".join(item["requirement_ids"]) or "none"
            lines.append(f"- **{item['id']}** — {item['selected']}: {item['rationale']} (requirements: {requirements}; confidence: {item['confidence']})")
    lines.extend(["", "## Outputs", ""])
    for item in receipt["outputs"]:
        digest = item["sha256"][:12] if item["sha256"] else item["integrity"].lower()
        lines.append(f"- `{item['kind']}`: `{item['path']}` — {'exists' if item['exists'] else 'missing'}, `{digest}`")
    lines.extend(["", "## Deterministic checks", ""])
    for item in receipt["checks"]:
        lines.append(f"- **{item['status']}** `{item['id']}` — {item['description']}")
    changes = receipt["changes"]
    lines.extend(["", "## Change summary", "", f"Created {changes['total_created']}, modified {changes['total_modified']}, deleted {changes['total_deleted']} files during this gate."])
    for label in ("created", "modified", "deleted"):
        if changes[label]:
            lines.append(f"- {label}: " + ", ".join(f"`{path}`" for path in changes[label]))
    if changes["truncated"]:
        lines.append(f"- The displayed file list is capped at {CHANGE_LIMIT}; totals above are authoritative.")
    if receipt["disclosures"]:
        lines.extend(["", "## Operational disclosures", ""])
        for item in receipt["disclosures"]:
            lines.append(f"- `{item['key']}`: {item['value']} _(source: {item['source']})_")
    lines.extend(["", "## Assumptions, waivers, and unverified boundaries", ""])
    for label, values in (("Assumption", receipt["assumptions"]), ("Waiver", receipt["waivers"]), ("Unverified", receipt["unverified_boundaries"])):
        for value in values:
            lines.append(f"- **{label}:** {value}")
    if not receipt["assumptions"] and not receipt["waivers"] and not receipt["unverified_boundaries"]:
        lines.append("- None declared.")
    approval = receipt["approval"]
    lines.extend(["", "## Approval and next action", "", f"Approval: **{approval['status']}**" + (f" — {', '.join(approval['reasons'])}" if approval["reasons"] else ""), "", receipt["next_action"], ""])
    return "\n".join(lines)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    sub = result.add_subparsers(dest="command", required=True)
    opened = sub.add_parser("open", help="capture gate inputs and pre-work file state")
    opened.add_argument("--run", required=True, type=Path)
    opened.add_argument("--stage", required=True, choices=STAGE_DEFINITIONS)
    opened.add_argument("--producer")
    opened.add_argument("--consumer")
    opened.add_argument("--objective")
    opened.add_argument("--approval-granted-by")
    opened.add_argument("--approval-reason", action="append", default=[])
    opened.add_argument("--waiver", action="append", default=[])
    approve = sub.add_parser("approve", help="record user approval on an open gate")
    approve.add_argument("--run", required=True, type=Path)
    approve.add_argument("--stage", required=True, choices=STAGE_DEFINITIONS)
    approve.add_argument("--granted-by", required=True)
    approve.add_argument("--reason", action="append", default=[])
    closed = sub.add_parser("close", help="finalize a stage and write its gate receipt")
    closed.add_argument("--run", required=True, type=Path)
    closed.add_argument("--stage", required=True, choices=STAGE_DEFINITIONS)
    closed.add_argument("--auto-open-next", action="store_true")
    validate = sub.add_parser("validate", help="validate the latest required receipt chain")
    validate.add_argument("--run", required=True, type=Path)
    validate.add_argument("--require-hardware", action="store_true")
    render = sub.add_parser("render", help="render one receipt as Markdown")
    render.add_argument("receipt", type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "open":
            context = open_gate(args.run, args.stage, producer=args.producer, consumer=args.consumer, objective=args.objective, approval_granted_by=args.approval_granted_by, approval_reasons=args.approval_reason, waivers=args.waiver)
            print(json.dumps({key: value for key, value in context.items() if key != "baseline"}, indent=2, sort_keys=True))
            return 0
        if args.command == "approve":
            context = approve_gate(
                args.run,
                args.stage,
                granted_by=args.granted_by,
                reasons=args.reason,
            )
            print(
                json.dumps(
                    {
                        "request_id": context["request_id"],
                        "stage": context["stage"],
                        "approval_granted_by": context["approval_granted_by"],
                        "approval_granted_at": context["approval_granted_at"],
                        "approval_reasons": context["approval_reasons"],
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "close":
            receipt, path = close_gate(args.run, args.stage, auto_open_next=args.auto_open_next)
            print(json.dumps({"receipt": display_path(path), "markdown": display_path(path.with_suffix('.md')), "verdict": receipt["verdict"], "reasons": receipt["verdict_reasons"]}, indent=2, sort_keys=True))
            return 0 if receipt["verdict"] == "PASS" else 1
        if args.command == "validate":
            errors = validate_gate_set(args.run, require_hardware=args.require_hardware)
            for error in errors:
                print(f"ERROR: {error}")
            return 1 if errors else 0
        if args.command == "render":
            print(render_receipt(read_json(args.receipt)), end="")
            return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
