#!/usr/bin/env python3
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

"""Deterministic structural validation for the v0.1 prototype."""

from __future__ import annotations

import json
import re
import shutil
import sys
import tomllib
from pathlib import Path

from contract_validation import validate_artifact_set

try:
    import jsonschema
except ImportError as exc:  # pragma: no cover - actionable environment failure
    raise SystemExit("ERROR: jsonschema is required; run: .venv/bin/pip install jsonschema") from exc


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_AGENTS = {
    "amd_soc_orchestrator",
    "amd_soc_intent_to_spec",
    "amd_soc_architect",
    "vivado_rtl_engineer",
    "amd_soc_verifier",
    "vivado_impl_closure",
    "amd_soc_hardware_validator",
    "amd_soc_platform_integrator",
    "vitis_hls_engineer",
    "vitis_aie_engineer",
    "vitis_sw_engineer",
}
EXPECTED_DEFAULT_PATH = [
    "amd_soc_orchestrator",
    "amd_soc_intent_to_spec",
    "amd_soc_architect",
    "vivado_rtl_engineer",
    "amd_soc_verifier",
    "vivado_impl_closure",
]
EXPECTED_IPI_PATH = [
    "amd_soc_orchestrator",
    "amd_soc_intent_to_spec",
    "amd_soc_architect",
    "vivado_rtl_engineer",
    "amd_soc_platform_integrator",
    "amd_soc_verifier",
    "vivado_impl_closure",
]
CONTRACTS = {
    "gate-receipt",
    "handoff",
    "hardware-spec",
    "architecture-plan",
    "source-manifest",
    "verification-result",
    "implementation-result",
    "hardware-test",
    "hardware-target",
    "hardware-validation-result",
    "vitis-execution-plan",
    "vitis-result",
}


def load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path}: {exc}") from exc


def load_toml(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"{path}: {exc}") from exc


def skill_name(skill_md: Path) -> str | None:
    match = re.search(r"(?m)^name:\s*[\"']?([^\"'\n]+?)[\"']?\s*$", skill_md.read_text())
    return match.group(1).strip() if match else None


def discover_skills(registry: dict, errors: list[str]) -> dict[str, Path]:
    catalog: dict[str, Path] = {}
    roots = sorted(
        registry.get("resolution", {}).get("roots", []),
        key=lambda item: item.get("precedence", 999),
    )
    for record in roots:
        root = (ROOT / record["path"]).resolve()
        if not root.is_dir():
            errors.append(f"skill root is missing: {root}")
            continue
        for skill_md in sorted(root.rglob("SKILL.md")):
            declared = skill_name(skill_md)
            if not declared:
                errors.append(f"skill has no frontmatter name: {skill_md}")
                continue
            catalog.setdefault(declared, skill_md)

    for name, record in registry.get("skills", {}).items():
        skill_md = (ROOT / record["path"] / "SKILL.md").resolve()
        if not skill_md.is_file():
            errors.append(f"registered skill {name} has no SKILL.md at {skill_md}")
            continue
        declared = skill_name(skill_md)
        if declared != name:
            errors.append(f"registered skill {name} declares name {declared}")
        catalog[name] = skill_md
        if record.get("source") == "prototype" and "TODO" in skill_md.read_text():
            errors.append(f"prototype skill {name} still contains TODO text")
    return catalog


def validate() -> tuple[list[str], dict[str, Path]]:
    errors: list[str] = []
    workflow = load_json(ROOT / "workflow.json")
    environment = load_json(ROOT / "environment.json")
    registry = load_json(ROOT / "registry" / "skills.json")
    architecture_doc = (ROOT / "AGENT_ARCHITECTURE_v0.1.md").read_text()
    config = load_toml(ROOT / ".codex" / "config.toml")

    if workflow.get("version") != "0.1":
        errors.append("workflow version must be 0.1")

    agents = workflow.get("agents", [])
    agent_ids = [agent.get("id") for agent in agents]
    if len(agents) != 11 or set(agent_ids) != EXPECTED_AGENTS:
        errors.append(f"workflow must define the eleven v0.1 agents; got {agent_ids}")
    if len(agent_ids) != len(set(agent_ids)):
        errors.append("workflow agent IDs are not unique")
    if workflow.get("entry_agent") != "amd_soc_orchestrator":
        errors.append("entry_agent must be amd_soc_orchestrator")
    if workflow.get("routing", {}).get("default_path") != EXPECTED_DEFAULT_PATH:
        errors.append("workflow default path does not match the six-agent direct Vivado route")

    ownership = workflow.get("artifact_ownership", {})
    if ownership.get("policy") != "single-writer-multiple-readers":
        errors.append("workflow must enforce single-writer-multiple-readers ownership")
    if ownership.get("whole_run_validation_owner") != "amd_soc_orchestrator":
        errors.append("only amd_soc_orchestrator may own whole-run validation")
    ownership_document = ROOT / ownership.get("policy_document", "")
    if not ownership_document.is_file():
        errors.append(f"artifact ownership policy is missing: {ownership_document}")
    expected_finalizer = (
        "python3 scripts/v0_1_runner.py finalize --run {run_dir} "
        "--stage {stage} --write"
    )
    if ownership.get("finalizer") != expected_finalizer:
        errors.append("workflow finalizer command is not the deterministic v0.1 entry point")
    if not (ROOT / "scripts" / "artifact_finalize.py").is_file():
        errors.append("deterministic artifact finalizer is missing")
    expected_writers = {
        "hardware-spec": "amd_soc_intent_to_spec",
        "architecture-plan": "amd_soc_architect",
        "source-manifest": "integration owner",
        "platform-design-and-insertion-reports": "amd_soc_platform_integrator",
        "vitis-execution-plan": "amd_soc_platform_integrator",
        "vitis-result-and-generated-build-outputs": "deterministic Vitis runner",
        "verification-result": "amd_soc_verifier",
        "implementation-result-and-final-programming-set": "vivado_impl_closure",
        "hardware-validation-result-and-evidence": "amd_soc_hardware_validator",
        "gate-receipts-and-user-reports": "deterministic gate runner",
        "handoffs-and-final-result": "amd_soc_orchestrator",
    }
    if ownership.get("writers") != expected_writers:
        errors.append("workflow artifact writer map does not match v0.1 ownership")

    assurance = workflow.get("assurance", {})
    if assurance.get("required_for_new_runs") is not True:
        errors.append("new runs must require transition assurance gates")
    if assurance.get("default_mode") != "exception_approval":
        errors.append("default assurance mode must pause on exceptions")
    if set(assurance.get("supported_modes", [])) != {
        "transparent_automatic",
        "exception_approval",
        "approve_every_gate",
    }:
        errors.append("workflow assurance modes do not match the gate runner")
    if assurance.get("contract") != "contracts/gate-receipt.schema.json":
        errors.append("workflow assurance contract is not gate-receipt.schema.json")
    if assurance.get("evaluator") != "deterministic-not-producer":
        errors.append("gate verdicts must be evaluated outside the producing agent")
    if not (ROOT / "scripts" / "gate_runner.py").is_file():
        errors.append("deterministic transition gate runner is missing")
    allowed_gate_stages = {
        "spec",
        "architecture",
        "source",
        "verification",
        "vitis",
        "implementation",
        "hardware",
    }
    for index, rule in enumerate(workflow.get("routing", {}).get("rules", [])):
        if not isinstance(rule.get("gate_id"), str) or not rule["gate_id"].startswith(
            "GATE-"
        ):
            errors.append(f"routing rule {index} has no stable gate_id")
        if rule.get("gate_stage") not in allowed_gate_stages:
            errors.append(f"routing rule {index} has an invalid gate_stage")

    concurrency = workflow.get("concurrency", {})
    if concurrency.get("policy") != "parallel-across-runs-bounded-within-run":
        errors.append("workflow concurrency policy is not the bounded v0.1 policy")
    defaults = concurrency.get("configurable_defaults", {})
    for field in (
        "frontend_runs",
        "simulation_runs",
        "vivado_implementation_runs",
        "hardware_runs_per_target",
    ):
        if not isinstance(defaults.get(field), int) or defaults[field] < 1:
            errors.append(f"workflow concurrency default {field} must be positive")
    if defaults.get("hardware_runs_per_target") != 1:
        errors.append("hardware execution must be exclusive per target")

    agent_config = config.get("agents", {})
    if agent_config.get("enabled") is not True:
        errors.append(".codex/config.toml must enable agents")
    if agent_config.get("max_concurrent_threads_per_session", 0) < 1:
        errors.append("max_concurrent_threads_per_session must be positive")

    for agent in agents:
        prompt = ROOT / agent["prompt"]
        if not prompt.is_file():
            errors.append(f"missing custom agent file: {prompt}")
            continue
        data = load_toml(prompt)
        for field in ("name", "description", "developer_instructions"):
            if not isinstance(data.get(field), str) or not data[field].strip():
                errors.append(f"{prompt}: missing required field {field}")
        if data.get("name") != agent["id"]:
            errors.append(f"{prompt}: name {data.get('name')} does not match {agent['id']}")
        if agent["id"] not in architecture_doc:
            errors.append(f"architecture document does not mention {agent['id']}")

    agent_by_id = {agent["id"]: agent for agent in agents}
    platform_outputs = set(
        agent_by_id.get("amd_soc_platform_integrator", {}).get("outputs", [])
    )
    if {"vitis-result", "system-package", "fixed-xsa", "ltx", "debug-map"} & platform_outputs:
        errors.append("platform integrator claims finalizer/implementation-owned outputs")
    software_outputs = set(
        agent_by_id.get("vitis_sw_engineer", {}).get("outputs", [])
    )
    if {"vitis-result", "elf"} & software_outputs:
        errors.append("software agent claims deterministic Vitis-runner outputs")
    implementation_outputs = set(
        agent_by_id.get("vivado_impl_closure", {}).get("outputs", [])
    )
    if not {"implementation-result", "programming-image", "fixed-xsa", "ltx", "debug-map"} <= implementation_outputs:
        errors.append("implementation closure does not claim the complete final build set")

    custom_agent_files = list((ROOT / ".codex" / "agents").glob("*.toml"))
    if len(custom_agent_files) != 11:
        errors.append(f".codex/agents must contain exactly eleven TOML files; found {len(custom_agent_files)}")

    if workflow.get("verification", {}).get("environment") != "environment.json":
        errors.append("workflow verification environment is not environment.json")
    vitis_flow = workflow.get("vitis", {})
    if vitis_flow.get("command_policy") != "structured-fields-only":
        errors.append("Vitis command policy must be structured-fields-only")
    if vitis_flow.get("allow_arbitrary_shell") is not False:
        errors.append("Vitis workflow must reject arbitrary shell commands")
    if not (ROOT / "scripts" / "vitis_runner.py").is_file():
        errors.append("Vitis workflow runner is missing")
    completion = workflow.get("completion", {})
    if set(completion.get("accepted_extensions", [])) != {".bit", ".pdi"}:
        errors.append("workflow completion must accept .bit and .pdi artifacts")
    if not completion.get("require_artifact_exists"):
        errors.append("workflow completion must require the programming artifact to exist")
    hardware_profile = completion.get("profiles", {}).get("hardware_qualified", {})
    if hardware_profile.get("require_hardware_validation") is not True:
        errors.append("hardware-qualified completion must require hardware validation")
    if hardware_profile.get("required_hardware_status") != "PASS":
        errors.append("hardware-qualified completion must require hardware PASS")
    ready_profile = completion.get("profiles", {}).get("hardware_ready", {})
    if ready_profile.get("require_hardware_validation") is not False:
        errors.append("hardware-ready completion must not claim on-target validation")
    if ready_profile.get("require_hardware_test") is not True:
        errors.append("hardware-ready completion must require hardware-test intent")
    if set(ready_profile.get("require_implementation_artifacts", [])) != {
        "programming-image",
        "ltx",
        "debug-map",
    }:
        errors.append("hardware-ready completion must require image, LTX, and debug map")

    tools = environment.get("tools", {})
    for tool_name in (
        "verilator",
        "cocotb",
        "jsonschema",
        "codex",
        "vivado",
        "vitis",
        "vpp",
    ):
        if tool_name not in tools:
            errors.append(f"environment is missing tool {tool_name}")
    for executable in (
        tools.get("verilator", {}).get("executable"),
        tools.get("cocotb", {}).get("python"),
        tools.get("cocotb", {}).get("config_executable"),
        tools.get("jsonschema", {}).get("python"),
        tools.get("codex", {}).get("executable"),
        tools.get("vivado", {}).get("executable"),
        tools.get("vitis", {}).get("executable"),
        tools.get("vitis", {}).get("settings64"),
        tools.get("vpp", {}).get("executable"),
    ):
        if executable:
            path = Path(executable)
            if path.is_absolute() or "/" in executable:
                if not path.is_absolute():
                    path = ROOT / path
                found = path.is_file()
            else:
                found = shutil.which(executable) is not None
            if not found:
                errors.append(f"environment executable is missing: {executable}")

    catalog = discover_skills(registry, errors)
    for agent in agents:
        for capability in agent.get("skills", []):
            if capability not in catalog:
                errors.append(f"agent {agent['id']} references undiscoverable skill {capability}")

    schemas: dict[str, dict] = {}
    for contract in CONTRACTS:
        path = ROOT / "contracts" / f"{contract}.schema.json"
        if not path.is_file():
            errors.append(f"missing contract: {path.name}")
            continue
        schema = load_json(path)
        schemas[contract] = schema
        try:
            jsonschema.validators.validator_for(schema).check_schema(schema)
        except jsonschema.SchemaError as exc:
            errors.append(f"invalid JSON Schema {path.name}: {exc.message}")

    sample_handoff = load_json(ROOT / "evals" / "sample-handoff.json")
    if "handoff" in schemas:
        try:
            jsonschema.validate(sample_handoff, schemas["handoff"])
        except jsonschema.ValidationError as exc:
            errors.append(f"sample-handoff.json: {exc.message}")

    vitis_example = load_json(
        ROOT / "contracts" / "examples" / "vitis" / "vitis-execution-plan.json"
    )
    if "vitis-execution-plan" in schemas:
        try:
            jsonschema.validate(vitis_example, schemas["vitis-execution-plan"])
        except jsonschema.ValidationError as exc:
            errors.append(f"example Vitis execution plan: {exc.message}")

    example_errors = validate_artifact_set(
        ROOT / "contracts" / "examples" / "direct-rtl",
        expected_request_id="example-direct-rtl",
        require_evidence_files=False,
    )
    errors.extend(f"direct-rtl contract example: {error}" for error in example_errors)

    evaluation_schema_path = ROOT / "contracts" / "evaluation-case.schema.json"
    evaluation_schema = load_json(evaluation_schema_path)
    try:
        jsonschema.validators.validator_for(evaluation_schema).check_schema(evaluation_schema)
    except jsonschema.SchemaError as exc:
        errors.append(f"invalid JSON Schema {evaluation_schema_path.name}: {exc.message}")

    hardware_test_schema = load_json(ROOT / "contracts" / "hardware-test.schema.json")
    hardware_target_schema = load_json(ROOT / "contracts" / "hardware-target.schema.json")
    target_files = sorted((ROOT / "hardware" / "targets").glob("*.json"))
    if not target_files:
        errors.append("no hardware target profiles are defined")
    for target_file in target_files:
        target_profile = load_json(target_file)
        try:
            jsonschema.validate(target_profile, hardware_target_schema)
        except jsonschema.ValidationError as exc:
            errors.append(f"{target_file.name}: {exc.message}")

    cases_index = load_json(ROOT / "evals" / "cases.json")
    design_cases = cases_index.get("design_cases", [])
    if len(design_cases) < 2:
        errors.append("at least two real-design cases are required")
    for case_id in design_cases:
        case_root = ROOT / "evals" / "designs" / case_id
        case_file = case_root / "case.json"
        prompt_file = case_root / "prompt.md"
        if not case_file.is_file() or not prompt_file.is_file():
            errors.append(f"design case {case_id} is missing case.json or prompt.md")
            continue
        case = load_json(case_file)
        try:
            jsonschema.validate(case, evaluation_schema)
        except jsonschema.ValidationError as exc:
            errors.append(f"design case {case_id}: {exc.message}")
        if case.get("id") != case_id:
            errors.append(f"design case directory and id differ: {case_id}")
        expected_case_route = (
            EXPECTED_DEFAULT_PATH
            if case.get("candidate", {}).get("integration_mode") == "rtl_top"
            else EXPECTED_IPI_PATH
        )
        if case.get("expected_route") != expected_case_route:
            errors.append(f"design case {case_id} does not use its required integration route")
        for source in case.get("candidate", {}).get("rtl_sources", []):
            if not (case_root / "reference" / source).is_file():
                errors.append(f"design case {case_id} reference source is missing: {source}")
        public = case.get("public_interface", {})
        modules = public.get("modules", [])
        public_sources = {module.get("source") for module in modules}
        if public_sources != set(case.get("candidate", {}).get("rtl_sources", [])):
            errors.append(f"design case {case_id} candidate and public-interface RTL sources differ")
        implementation_tops = {
            module.get("name") for module in modules
            if "implementation_top" in module.get("roles", [])
        }
        integration_mode = case.get("candidate", {}).get("integration_mode")
        if integration_mode == "rtl_top" and implementation_tops != {
            case.get("candidate", {}).get("top")
        }:
            errors.append(f"design case {case_id} must declare exactly one matching implementation top")
        if integration_mode != "rtl_top" and implementation_tops:
            errors.append(f"design case {case_id} must leave implementation-top ownership to its integration flow")
        simulation_tops = {
            module.get("name") for module in modules
            if "simulation_top" in module.get("roles", [])
        }
        expected_simulation_top = case.get("candidate", {}).get(
            "simulation_top", case.get("candidate", {}).get("top")
        )
        if simulation_tops != {expected_simulation_top}:
            errors.append(f"design case {case_id} must declare exactly one matching simulation top")
        if set(public.get("constraints", [])) != set(
            case.get("candidate", {}).get("constraint_sources", [])
        ):
            errors.append(f"design case {case_id} candidate and public-interface constraints differ")
        if case.get("simulation", {}).get("toplevel") != expected_simulation_top:
            errors.append(f"design case {case_id} simulation toplevel differs from public interface")
        if sum(case.get("score_weights", {}).values()) != 100:
            errors.append(f"design case {case_id} score weights must sum to 100")
        if not (case_root / case.get("simulation", {}).get("make_directory", "") / "Makefile").is_file():
            errors.append(f"design case {case_id} simulation Makefile is missing")
        if case_id.startswith("kv260_"):
            hardware_test_file = case_root / "hardware-test.json"
            if not hardware_test_file.is_file():
                errors.append(f"design case {case_id} is missing hardware-test.json")
            else:
                hardware_test = load_json(hardware_test_file)
                try:
                    jsonschema.validate(hardware_test, hardware_test_schema)
                except jsonschema.ValidationError as exc:
                    errors.append(f"design case {case_id} hardware test: {exc.message}")
                if hardware_test.get("case_id") != case_id:
                    errors.append(f"design case {case_id} hardware-test case_id differs")
                if hardware_test.get("target") != {
                    "part": case.get("target", {}).get("part"),
                    "board_part": case.get("target", {}).get("board_part"),
                }:
                    errors.append(f"design case {case_id} hardware-test target differs")
                instrumentation = hardware_test.get("instrumentation", {})
                if not instrumentation.get("vio_cores"):
                    errors.append(f"design case {case_id} hardware test has no VIO core")
                if not instrumentation.get("ila_cores"):
                    errors.append(f"design case {case_id} hardware test has no ILA core")
                controls = {
                    probe.get("name")
                    for core in instrumentation.get("vio_cores", [])
                    for probe in core.get("controls", [])
                }
                status = {
                    probe.get("name")
                    for core in instrumentation.get("vio_cores", [])
                    for probe in core.get("status", [])
                }
                if not {"hw_test_reset", "hw_test_start", "hw_test_enable"} <= controls:
                    errors.append(f"design case {case_id} hardware test lacks standard VIO controls")
                if not {"hw_test_busy", "hw_test_done", "hw_test_pass", "hw_test_error_code"} <= status:
                    errors.append(f"design case {case_id} hardware test lacks standard VIO status")

    # Vitis owns files below each generated ``vitis/workspace`` directory and
    # may create empty JSON cache files there.  Those are tool state, not
    # prototype contracts.  Keep the syntax sweep focused on repository-owned
    # JSON plus runner results outside the generated workspace.
    for path in ROOT.rglob("*.json"):
        relative_parts = path.relative_to(ROOT).parts
        if any(
            relative_parts[index : index + 2] == ("vitis", "workspace")
            for index in range(len(relative_parts) - 1)
        ):
            continue
        if path.is_file():
            load_json(path)

    contract_map = workflow.get("contracts", {})
    if set(contract_map) != CONTRACTS:
        errors.append("workflow contract map does not name every v0.1 contract")

    return errors, catalog


def main() -> int:
    try:
        errors, catalog = validate()
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("PASS: v0.1 prototype structure is valid")
    print("agents: 11 (6 design core, 1 hardware-profile core, 4 conditional)")
    print(f"discoverable skills: {len(catalog)}")
    print(f"prototype root: {ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
