#!/usr/bin/env python3
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

"""Initialize, execute, validate, and score v0.1 design regressions."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from artifact_finalize import STAGES, finalize_stage
from contract_validation import validate_artifact_set
from gate_runner import close_gate, display_path, open_gate, validate_gate_set
from run_status import write_run_status


ROOT = Path(__file__).resolve().parents[1]
CASES_ROOT = ROOT / "evals" / "designs"
RUNS_ROOT = ROOT / "runs"
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def case_dir(case_id: str) -> Path:
    path = CASES_ROOT / case_id
    if not (path / "case.json").is_file():
        raise ValueError(f"unknown case: {case_id}")
    return path


def load_case(case_id: str) -> tuple[Path, dict]:
    path = case_dir(case_id)
    case = read_json(path / "case.json")
    if case.get("id") != case_id:
        raise ValueError(f"{path / 'case.json'}: id does not match directory")
    return path, case


def new_request_id(case_id: str) -> str:
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{case_id}-{stamp}"


def validate_request_id(request_id: str) -> None:
    if not REQUEST_ID_PATTERN.fullmatch(request_id):
        raise ValueError(
            "request ID must contain only letters, digits, '.', '_', and '-'"
        )


def render_public_interface(case: dict) -> str:
    interface = case["public_interface"]
    lines = [
        "## Regression public interface (required)",
        "",
        "Place generated candidate files under `design/`. Preserve these public "
        "module names, source paths, parameters, and ports exactly so the "
        "independent regression harness can bind without design-specific adaptation.",
        "",
    ]
    for module in interface["modules"]:
        roles = ", ".join(module["roles"])
        lines.extend(
            [
                f"- Module `{module['name']}` in `{module['source']}` "
                f"(roles: {roles})",
            ]
        )
        for parameter in module["parameters"]:
            lines.append(
                f"  - parameter `{parameter['name']}`: {parameter['type']}, "
                f"default `{parameter['default']}`"
            )
        for port in module["ports"]:
            lines.append(
                f"  - {port['direction']} `{port['name']}` width `{port['width']}`"
            )
    lines.extend(["", "Required constraint files:"])
    if interface["constraints"]:
        lines.extend(f"- `{path}`" for path in interface["constraints"])
    else:
        lines.append("- None; use board-flow/IP-integrator generated constraints.")
    lines.extend(
        [
            "",
            f"Required integration mode: `{case['candidate']['integration_mode']}`.",
            "Internal decomposition may add modules and files, but it must not "
            "change this public regression interface.",
            "",
        ]
    )
    return "\n".join(lines)


def initialize_run(
    case_id: str,
    request_id: str | None,
    assurance_mode: str = "exception_approval",
) -> Path:
    case_path, case = load_case(case_id)
    request_id = request_id or new_request_id(case_id)
    validate_request_id(request_id)
    if assurance_mode not in {
        "transparent_automatic",
        "exception_approval",
        "approve_every_gate",
    }:
        raise ValueError(f"unsupported assurance mode: {assurance_mode}")
    run_dir = RUNS_ROOT / request_id
    if run_dir.exists() and any(run_dir.iterdir()):
        raise ValueError(f"run directory is not empty: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)

    prompt = (case_path / case["prompt_file"]).read_text().rstrip()
    prompt = f"{prompt}\n\n{render_public_interface(case)}"
    (run_dir / "user-request.md").write_text(prompt)
    hardware_test = case_path / "hardware-test.json"
    if hardware_test.is_file():
        shutil.copy2(hardware_test, run_dir / "hardware-test.json")
    write_json(
        run_dir / "run.json",
        {
            "schema_version": 1,
            "prototype_version": "0.1",
            "request_id": request_id,
            "case_id": case_id,
            "state": "INTAKE",
            "expected_route": case["expected_route"],
            "assurance": {
                "required": True,
                "mode": assurance_mode,
                "gate_contract_version": 1,
            },
            "artifacts": {},
        },
    )
    open_gate(
        run_dir,
        "intake",
        approval_granted_by=(
            "user initiating the run"
            if assurance_mode == "approve_every_gate"
            else None
        ),
        approval_reasons=(
            ["approve-every-gate mode"]
            if assurance_mode == "approve_every_gate"
            else None
        ),
    )
    write_json(
        run_dir / "handoff-000-intake.json",
        {
            "schema_version": 1,
            "request_id": request_id,
            "from_agent": "amd_soc_orchestrator",
            "to_agent": "amd_soc_intent_to_spec",
            "reason": "Translate the preserved user request into a measurable hardware specification.",
            "status": "READY",
            "iteration": 0,
            "input_artifacts": [
                {
                    "kind": "user-request",
                    "path": str((run_dir / "user-request.md").relative_to(ROOT)),
                    "revision": None,
                }
            ],
            "required_output": str((run_dir / "hardware-spec.json").relative_to(ROOT)),
            "evidence": [],
            "requires_user_approval": False,
        },
    )
    receipt, _ = close_gate(run_dir, "intake", auto_open_next=True)
    if receipt["verdict"] != "PASS":
        raise ValueError(
            "initial intake assurance gate failed: "
            + "; ".join(receipt["verdict_reasons"])
        )
    return run_dir


def codex_prompt(run_dir: Path, case: dict) -> str:
    hardware_ready = (run_dir / "hardware-test.json").is_file()
    hardware_instruction = (
        f"""
This is a hardware-ready design run. Consume {run_dir / 'hardware-test.json'} as immutable test intent. The selected integration owner must insert the standard safe VIO/ILA test shell: use the RTL engineer for a PL-only design, or the platform integrator when the architecture selects the platform path. The verifier must validate the logical self-test oracle, and implementation closure must emit the final matching `.ltx` and implementation-derived `debug-map.json` beside the programming image. Do not program hardware or drive VIO in this design lane; serialized on-target qualification is a separate campaign stage."""
        if hardware_ready
        else ""
    )
    return f"""Run the frontier-model validation of AMD Adaptive SoC multi-agent prototype v0.1 for request {run_dir.name}.

This parent invocation is the amd_soc_orchestrator workflow owner: read .codex/agents/amd_soc_orchestrator.toml and follow it directly. Do not spawn another orchestrator.
Delegate every selected specialist stage to its named v0.1 custom-agent type. When spawning a named specialist, use fork_turns="none" and include its work package and input artifact paths in the spawn prompt. Do not combine an explicit agent type with a full-history fork. Record the returned task name, confirm it in the collaboration agent list, and wait at least 30 seconds for its result. A JSONL wait event may show an empty receiver list even when the child is live. If a spawn actually fails, report the exact runtime error and stop.
Keep orchestrator context lean: do not read all specialist schemas or examples yourself; pass their paths to the owning specialist and validate the returned artifact.
The preserved user request is at {run_dir / 'user-request.md'}.
Write all handoffs, stage artifacts, generated design sources, tests, reports, and final artifacts under {run_dir}.
The expected default route for this case is {json.dumps(case['expected_route'])}.
Treat contracts/examples/direct-rtl as field-shape examples only; derive every design value from this request and fresh tool evidence.
	Finalize every completed stage with python3 scripts/v0_1_runner.py finalize --run {run_dir} --stage <stage> --write. This deterministically closes the already-open assurance gate, writes machine-readable JSON plus user-facing Markdown under {run_dir / 'gates'}, and opens the next default gate after PASS. Read the receipt and do not dispatch the next agent unless its verdict is PASS. Validate each stage against its schema, and only this parent orchestrator runs python3 scripts/v0_1_runner.py validate --run {run_dir} before declaring completion.
Use Vivado MCP wherever Vivado facts or actions are required. Do not claim PASS unless the required simulation and Vivado signoff pass and a .bit or .pdi exists.
Do not read or copy sources from evals/designs/{case['id']}/reference; that directory is regression-harness reference material, not design input.
{hardware_instruction}
"""


def execute_codex(args: argparse.Namespace, run_dir: Path, case: dict) -> int:
    command = [
        "codex",
        "exec",
        "--skip-git-repo-check",
        "-C",
        str(ROOT),
        "--sandbox",
        args.sandbox,
        "--json",
        "-o",
        str(run_dir / "codex-final.txt"),
    ]
    if args.model:
        command.extend(["--model", args.model])
    if args.oss:
        command.append("--oss")
    if args.local_provider:
        command.extend(["--local-provider", args.local_provider])
    command.append(codex_prompt(run_dir, case))

    events_path = run_dir / "codex-events.jsonl"
    if events_path.exists():
        events_path = run_dir / f"codex-events-resume-{dt.datetime.now(dt.UTC).strftime('%Y%m%dT%H%M%SZ')}.jsonl"
    with events_path.open("w") as stream:
        result = subprocess.run(command, cwd=ROOT, text=True, stdout=stream, stderr=subprocess.STDOUT)
    write_run_status(run_dir, outcome="INTERRUPTED" if result.returncode else None)
    return result.returncode


def validate_run(run_dir: Path, *, require_hardware: bool = False) -> list[str]:
    errors = validate_artifact_set(
        run_dir,
        expected_request_id=run_dir.name,
        require_evidence_files=True,
        require_handoffs=True,
        require_hardware=require_hardware,
    )
    run_file = run_dir / "run.json"
    implementation_file = run_dir / "implementation-result.json"
    if run_file.is_file() and implementation_file.is_file():
        run = read_json(run_file)
        case_id = run.get("case_id")
        if case_id:
            _, case = load_case(case_id)
            hardware_test_file = run_dir / "hardware-test.json"
            if hardware_test_file.is_file():
                hardware_test = read_json(hardware_test_file)
                if hardware_test.get("case_id") != case_id:
                    errors.append(
                        "hardware-test case_id does not match run.json"
                    )
            expected_board = case["target"].get("board_part")
            if expected_board:
                implementation = read_json(implementation_file)
                if implementation.get("vivado", {}).get("board") != expected_board:
                    errors.append(
                        "implementation target board does not match the regression case"
                    )
    if run_file.is_file():
        run = read_json(run_file)
        assurance = run.get("assurance", {})
        if isinstance(assurance, dict) and assurance.get("required") is True:
            errors.extend(
                f"assurance gate: {error}"
                for error in validate_gate_set(
                    run_dir,
                    require_hardware=require_hardware,
                )
            )
    return errors


def nested_value(value: object, field: str | None) -> object:
    if not field:
        return value
    current = value
    for part in field.split("."):
        if not isinstance(current, dict) or part not in current:
            raise KeyError(field)
        current = current[part]
    return current


def semantic_rule(run_dir: Path, rule: dict) -> tuple[bool, str]:
    path = run_dir / rule["artifact"]
    if not path.is_file():
        return False, f"missing {rule['artifact']}"
    data = read_json(path)
    value: object = data
    collection_name = rule.get("collection")
    if collection_name:
        collection = data.get(collection_name)
        if not isinstance(collection, list):
            return False, f"{collection_name} is not a list"
        match = rule.get("match")
        if match:
            candidates = [
                item for item in collection
                if isinstance(item, dict) and all(nested_value(item, key) == expected for key, expected in match.items())
            ]
            if not candidates:
                return False, f"no {collection_name} item matches {match}"
            value = candidates[0]
        else:
            value = collection

    field = rule.get("field")
    operator = rule["operator"]
    expected = rule["expected"]
    if isinstance(value, list) and field:
        actual = [nested_value(item, field) for item in value if isinstance(item, dict)]
    else:
        try:
            actual = nested_value(value, field)
        except KeyError:
            return False, f"field {field} is missing"

    if operator == "equals":
        passed = actual == expected
    elif operator == "contains":
        passed = expected in actual
    elif operator == "not_contains":
        passed = expected not in actual
    else:
        return False, f"unsupported operator {operator}"
    return passed, f"actual={actual!r}, expected {operator} {expected!r}"


def tool_environment() -> dict[str, str]:
    environment = os.environ.copy()
    prepend = [
        str(ROOT / ".tools" / "verilator-5.050" / "bin"),
        str(ROOT / ".venv" / "bin"),
    ]
    environment["PATH"] = os.pathsep.join(prepend + [environment.get("PATH", "")])
    return environment


def run_simulation(case_path: Path, case: dict, candidate: Path, output_dir: Path) -> tuple[bool, dict]:
    for source in case["candidate"]["rtl_sources"]:
        if not (candidate / source).is_file():
            return False, {"error": f"missing candidate source: {candidate / source}"}

    output_dir.mkdir(parents=True, exist_ok=True)
    testbench = case_path / case["simulation"]["make_directory"]
    command = [
        "make",
        "-C",
        str(testbench),
        f"CANDIDATE_DIR={candidate}",
        f"SIM_BUILD={output_dir / 'sim_build'}",
        f"COCOTB_RESULTS_FILE={output_dir / 'results.xml'}",
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=tool_environment(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    (output_dir / "simulation.log").write_text(result.stdout)
    details = {
        "command": command,
        "returncode": result.returncode,
        "log": str(output_dir / "simulation.log"),
        "results": str(output_dir / "results.xml"),
    }
    results_file = output_dir / "results.xml"
    if result.returncode == 0 and results_file.is_file():
        testsuites = ET.parse(results_file).getroot()
        failures = sum(int(node.attrib.get("failures", 0)) for node in testsuites.iter("testsuite"))
        errors = sum(int(node.attrib.get("errors", 0)) for node in testsuites.iter("testsuite"))
        details["failures"] = failures
        details["errors"] = errors
        return failures == 0 and errors == 0, details
    return False, details


def vivado_pass(run_dir: Path, case: dict) -> tuple[bool, str]:
    path = run_dir / "implementation-result.json"
    if not path.is_file():
        return False, "implementation-result.json is missing"
    result = read_json(path)
    if result.get("status") != "PASS":
        return False, f"implementation status is {result.get('status')}"
    if result.get("vivado", {}).get("part") != case["target"]["part"]:
        return False, "implemented part does not match the case target"
    expected_board = case["target"].get("board_part")
    if expected_board and result.get("vivado", {}).get("board") != expected_board:
        return False, "implemented board part does not match the case target"
    images = [
        artifact for artifact in result.get("artifacts", [])
        if artifact.get("kind") in {"bitstream", "pdi"} and artifact.get("exists")
    ]
    for artifact in images:
        image_path = Path(artifact["path"])
        if not image_path.is_absolute():
            image_path = run_dir / image_path
        if image_path.is_file():
            return True, str(image_path)
    return False, "no recorded programming image exists"


def score_run(case_path: Path, case: dict, run_dir: Path, execute_simulation: bool) -> dict:
    weights = case["score_weights"]
    contract_errors = validate_run(run_dir)
    contract_score = weights["contracts"] if not contract_errors else 0

    semantic_results = []
    semantic_earned = 0
    semantic_total = sum(rule["weight"] for rule in case["semantic_rubric"])
    for rule in case["semantic_rubric"]:
        passed, detail = semantic_rule(run_dir, rule)
        if passed:
            semantic_earned += rule["weight"]
        semantic_results.append({"id": rule["id"], "passed": passed, "detail": detail, "weight": rule["weight"]})
    semantic_score = weights["semantics"] * semantic_earned / semantic_total if semantic_total else 0

    simulation_result = {"passed": False, "detail": "not executed"}
    simulation_score = 0
    if execute_simulation:
        passed, detail = run_simulation(case_path, case, run_dir / "design", run_dir / "regression" / "simulation")
        simulation_result = {"passed": passed, "detail": detail}
        simulation_score = weights["simulation"] if passed else 0

    implemented, implementation_detail = vivado_pass(run_dir, case)
    vivado_score = weights["vivado"] if implemented else 0
    total = contract_score + semantic_score + simulation_score + vivado_score
    return {
        "schema_version": 1,
        "request_id": run_dir.name,
        "case_id": case["id"],
        "score": round(total, 2),
        "maximum_score": sum(weights.values()),
        "breakdown": {
            "contracts": {"score": contract_score, "maximum": weights["contracts"], "errors": contract_errors},
            "semantics": {"score": round(semantic_score, 2), "maximum": weights["semantics"], "rules": semantic_results},
            "simulation": {"score": simulation_score, "maximum": weights["simulation"], **simulation_result},
            "vivado": {"score": vivado_score, "maximum": weights["vivado"], "passed": implemented, "detail": implementation_detail},
        },
    }


def list_cases() -> None:
    for path in sorted(CASES_ROOT.glob("*/case.json")):
        case = read_json(path)
        print(f"{case['id']}: {case['title']}")


def self_test() -> int:
    failures = 0
    for path in sorted(CASES_ROOT.glob("*/case.json")):
        case = read_json(path)
        case_path = path.parent
        candidate = case_path / "reference"
        output = RUNS_ROOT / "_selftest" / case["id"]
        if output.exists():
            shutil.rmtree(output)
        passed, details = run_simulation(case_path, case, candidate, output)
        print(f"{'PASS' if passed else 'FAIL'}: {case['id']} simulation")
        if not passed:
            print(details)
            failures += 1
    return 1 if failures else 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    sub = result.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list available real-design cases")

    init = sub.add_parser("init", help="create a run directory and initial handoff")
    init.add_argument("--case", required=True)
    init.add_argument("--request-id")
    init.add_argument(
        "--assurance-mode",
        choices=[
            "transparent_automatic",
            "exception_approval",
            "approve_every_gate",
        ],
        default="exception_approval",
    )

    run = sub.add_parser("run", help="initialize a run and invoke Codex")
    run.add_argument("--case", required=True)
    run.add_argument("--request-id")
    run.add_argument("--model")
    run.add_argument("--sandbox", choices=["workspace-write", "danger-full-access"], default="danger-full-access")
    run.add_argument("--oss", action="store_true", help="experimental future local-model compatibility")
    run.add_argument("--local-provider", choices=["ollama", "lmstudio"], help="experimental future local-model compatibility")
    run.add_argument(
        "--assurance-mode",
        choices=[
            "transparent_automatic",
            "exception_approval",
            "approve_every_gate",
        ],
        default="exception_approval",
    )

    resume = sub.add_parser("resume", help="resume an existing non-terminal run without replacing its evidence")
    resume.add_argument("--run", required=True, type=Path)
    resume.add_argument("--model")
    resume.add_argument("--sandbox", choices=["workspace-write", "danger-full-access"], default="workspace-write")
    resume.add_argument("--oss", action="store_true")
    resume.add_argument("--local-provider", choices=["ollama", "lmstudio"])

    validate = sub.add_parser("validate", help="validate all stage artifacts in a run")
    validate.add_argument("--run", required=True, type=Path)
    validate.add_argument("--require-hardware", action="store_true", help="also require hardware-test and hardware-validation-result artifacts")

    finalize = sub.add_parser(
        "finalize",
        help="refresh owned hashes and schema-check one handoff stage",
    )
    finalize.add_argument("--run", required=True, type=Path)
    finalize.add_argument("--stage", required=True, choices=STAGES)
    finalize.add_argument(
        "--write",
        action="store_true",
        help="atomically write refreshed declared hashes; otherwise check only",
    )

    verify = sub.add_parser("verify", help="run the case cocotb regression against a candidate directory")
    verify.add_argument("--case", required=True)
    verify.add_argument("--candidate", required=True, type=Path)
    verify.add_argument("--output", required=True, type=Path)

    score = sub.add_parser("score", help="score contracts, semantics, simulation, and Vivado outcome")
    score.add_argument("--case", required=True)
    score.add_argument("--run", required=True, type=Path)
    score.add_argument("--execute-simulation", action="store_true")

    vitis = sub.add_parser(
        "vitis",
        help="execute a schema-valid headless Vitis plan for an existing run",
    )
    vitis.add_argument("--run", required=True, type=Path)
    vitis.add_argument(
        "--dry-run",
        action="store_true",
        help="render the exact vitis/v++ argv without invoking the tools",
    )
    vitis.add_argument(
        "--validate-only",
        action="store_true",
        help="validate vitis-execution-plan.json without rendering or execution",
    )

    sub.add_parser("self-test", help="run both cocotb harnesses against known-good reference RTL")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "list":
            list_cases()
            return 0
        if args.command == "self-test":
            return self_test()
        if args.command in {"init", "run"}:
            case_path, case = load_case(args.case)
            run_dir = initialize_run(
                args.case,
                args.request_id,
                args.assurance_mode,
            )
            print(run_dir)
            if args.command == "run":
                return execute_codex(args, run_dir, case)
            return 0
        if args.command == "validate":
            errors = validate_run(args.run.resolve(), require_hardware=args.require_hardware)
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 1 if errors else 0
        if args.command == "resume":
            run_dir = args.run.resolve()
            if not run_dir.is_relative_to(RUNS_ROOT.resolve()):
                raise ValueError("resume run must be under the prototype runs directory")
            metadata = read_json(run_dir / "run.json")
            case_id = metadata.get("case_id")
            if not isinstance(case_id, str):
                raise ValueError("run.json has no case_id")
            _, case = load_case(case_id)
            return execute_codex(args, run_dir, case)
        if args.command == "finalize":
            result = finalize_stage(args.run, args.stage, args.write)
            response = dict(result)
            gate_passed = True
            run_dir = args.run.resolve()
            run_file = run_dir / "run.json"
            assurance_required = False
            if run_file.is_file():
                assurance = read_json(run_file).get("assurance", {})
                assurance_required = (
                    isinstance(assurance, dict)
                    and assurance.get("required") is True
                )
            if (
                args.write
                and args.stage != "all"
                and assurance_required
            ):
                try:
                    receipt, receipt_path = close_gate(
                        run_dir,
                        args.stage,
                        result,
                        auto_open_next=True,
                    )
                    response["gate"] = {
                        "receipt": display_path(receipt_path),
                        "markdown": display_path(receipt_path.with_suffix(".md")),
                        "verdict": receipt["verdict"],
                        "reasons": receipt["verdict_reasons"],
                    }
                    gate_passed = receipt["verdict"] == "PASS"
                except ValueError as exc:
                    response["gate"] = {
                        "verdict": "ERROR",
                        "reasons": [str(exc)],
                    }
                    gate_passed = False
            print(json.dumps(response, indent=2))
            return 0 if result["status"] == "PASS" and gate_passed else 1
        if args.command == "verify":
            case_path, case = load_case(args.case)
            passed, details = run_simulation(case_path, case, args.candidate.resolve(), args.output.resolve())
            print(json.dumps(details, indent=2))
            return 0 if passed else 1
        if args.command == "score":
            case_path, case = load_case(args.case)
            result = score_run(case_path, case, args.run.resolve(), args.execute_simulation)
            write_json(args.run.resolve() / "score.json", result)
            print(json.dumps(result, indent=2))
            return 0 if result["score"] == result["maximum_score"] else 1
        if args.command == "vitis":
            run_dir = args.run.resolve()
            command = [
                sys.executable,
                str(ROOT / "scripts" / "vitis_runner.py"),
                "--plan",
                str(run_dir / "vitis-execution-plan.json"),
                "--generated-dir",
                str(run_dir / "vitis"),
                "--result",
                str(run_dir / "vitis-result.json"),
            ]
            if args.dry_run:
                command.append("--dry-run")
            if args.validate_only:
                command.append("--validate-only")
            return subprocess.run(command, cwd=ROOT).returncode
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
