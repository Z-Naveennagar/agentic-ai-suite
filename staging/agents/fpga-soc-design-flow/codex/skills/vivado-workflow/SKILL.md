---
name: vivado-workflow
description: Coordinate the v0.1 AMD FPGA and Adaptive SoC multi-agent workflow from user intent through specification, architecture, selected source domains, independent verification, Vivado implementation, and programming-image evidence.
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->


# AMD FPGA and Adaptive SoC Multi-Agent Workflow v0.1

Coordinate work; do not perform a specialist's task in the orchestrator.

## Required inputs

- Preserve the user's original request verbatim.
- Accept an optional project, checkpoint, source tree, board, part, test suite, or regression case.
- Select one mode: `interactive`, `analyze`, `repair`, or `regression`.
- Create a request ID and `runs/<request_id>/` artifact root before dispatch.

## Default workflow

1. Dispatch `amd_soc_intent_to_spec` to produce schema-valid `hardware-spec.json`.
2. Stop for user input only when its status is `NEEDS_USER_INPUT`.
3. Dispatch `amd_soc_architect` after the specification reports `READY`.
4. Default to `vivado_rtl_engineer`.
5. Dispatch conditional agents only when selected by an approved architecture work package:
   - `amd_soc_platform_integrator` for PS/CIPS, block design, NoC, AIE, or Vitis system integration;
   - `vitis_hls_engineer` for approved HLS components;
   - `vitis_aie_engineer` for approved AIE/AIE-ML components;
   - `vitis_sw_engineer` for required PS software after the hardware platform is available.
6. Converge component outputs at the integration owner:
   - `vivado_rtl_engineer` for PL-only designs;
   - `amd_soc_platform_integrator` for PS/CIPS, block-design, AIE, or Vitis designs.
7. Dispatch `amd_soc_verifier` only after the aggregate source manifest is `READY` and required component/elaboration checks pass.
8. Dispatch `vivado_impl_closure` only after verification reports `PASS`.
9. When the architecture selects Vitis:
   - require `amd_soc_platform_integrator` to assemble schema-valid
     `vitis-execution-plan.json` from the specialist-owned fields;
   - invoke `python3 scripts/v0_1_runner.py vitis --run runs/<request_id>`;
   - run acceleration compile/link/package after component verification and
     pass the linked evidence to `vivado_impl_closure`;
   - run a fixed-XSA embedded-only application after implementation PASS.
10. For a hardware-qualified run, dispatch `amd_soc_hardware_validator` only
   after implementation reports `PASS`, the programming image and matching
   `.ltx` exist, a target profile is available, and the user authorizes
   programming and probe drive.
11. Return a final artifact inventory with evidence for every success claim.

## Artifact ownership and handoff finalization

- Read and enforce `../../ARTIFACT_OWNERSHIP_v0.1.md`.
- Every mutable artifact has one writer. Readers report a finding to that
  writer and never repair its artifact.
- Before a transition, the orchestrator invokes `python3
  scripts/v0_1_runner.py finalize --run runs/<request_id> --stage <stage>
  --write`. The finalizer may refresh declared hashes and schema-check the
  owned artifact; it never changes engineering content.
- For assurance-enabled runs, the gate context must be opened before producer
  work. Finalization closes it through `scripts/gate_runner.py`, records exact
  inputs, actions, decisions, outputs, file changes, checks, side effects,
  approvals, and uncertainty, and writes JSON plus generated Markdown beneath
  `runs/<request_id>/gates/`. Treat specialist status as a producer claim and
  the deterministic gate verdict as transition authority. Never advance on a
  non-PASS receipt, and never let a specialist write its own verdict.
- Specialists validate only their owned outputs. Only
  `amd_soc_orchestrator` invokes whole-run cross-artifact validation.
- `vitis-result.json` and generated Vitis build outputs are written by the
  deterministic Vitis runner, not by a specialist.
- Gate receipts and their Markdown views are written only by the deterministic
  gate runner. JSON is authoritative; Markdown is a rendered user view.

## Feedback routes

| Finding owner | Route to |
|---|---|
| Ambiguous or conflicting requirement | `amd_soc_intent_to_spec` |
| Partition, module, pipeline, interface, CDC, memory, or resource architecture | `amd_soc_architect` |
| RTL, XDC, Tcl, wrappers, or PL elaboration | `vivado_rtl_engineer` |
| HLS component | `vitis_hls_engineer` |
| AIE component | `vitis_aie_engineer` |
| PS/CIPS, block design, NoC, pre-implementation platform export, or system packaging plan | `amd_soc_platform_integrator` |
| BSP, driver, application source, or embedded plan field | `vitis_sw_engineer` |
| Testbench, checker, coverage, or simulator | `amd_soc_verifier` |
| Run recovery, placement, routing, congestion, physical optimization, final fixed XSA, `.ltx`, implemented core identity, or final debug map | `vivado_impl_closure` |
| Hardware access, target discovery, programming, VIO, ILA, or cleanup | `amd_soc_hardware_validator` |
| Hardware test shell, logical debug-core insertion, BD access, or insertion report | `amd_soc_platform_integrator` |
| `v++` link, platform connectivity, or package defect | `amd_soc_platform_integrator` |
| Vitis platform/domain, BSP, application, or ELF defect | `vitis_sw_engineer` |
| Functional mismatch observed only on hardware | `amd_soc_verifier` first, then the demonstrated source owner |

Never let an agent silently change an upstream contract. Require a revised artifact and preserve the superseded revision.

## Vivado MCP policy

- Use `vivado_client_info` and `vivado_list_sessions` at entry.
- Start Vivado in Tcl mode unless the user explicitly requests GUI.
- Use `session_type=general` for normal RTL flows and `session_type=ipi` for block-design workflows.
- Serialize `vivado_execute` calls per session.
- Pair every `launch_runs` with `wait_on_run`.
- Monitor long commands with `vivado_status`; use `vivado_log_messages` for failures.
- Use `vivado_doc_search` before unfamiliar Tcl, IP configuration, device-specific advice, or error interpretation.
- Preserve session history and raw reports as evidence.
- Treat the MCP session lock as shared infrastructure, not another reasoning agent.

## Vitis command policy

- Agents describe work through `contracts/vitis-execution-plan.schema.json`;
  they never hand the orchestrator a shell command string.
- `vitis_hls_engineer` owns HLS compile entries and `vitis_aie_engineer` owns
  AIE compile entries.
- `amd_soc_platform_integrator` owns toolchain/input identity, link, package,
  and final plan assembly.
- `vitis_sw_engineer` owns the embedded platform/application section.
- The orchestrator invokes only `scripts/vitis_runner.py`. The runner constructs
  `vitis -s`, `v++ --compile`, `v++ --link`, and `v++ --package` argv.
- Preserve `vitis/commands.json`, stage logs, reports, generated Python, and
  schema-valid `vitis-result.json`.
- The deterministic Vitis runner is the sole writer of `vitis-result.json`
  and generated ELF/XO/libadf/XCLBIN/link/package artifacts.
- A selected Vitis flow cannot pass with `DRY_RUN`, missing outputs, a hash
  mismatch, or a non-zero stage exit code.

Read [references/state-machine.md](references/state-machine.md) and [references/mcp-policy.md](references/mcp-policy.md) before implementing or modifying a runner.

## Status and stop conditions

Stop when:

- all required acceptance checks pass and the final programming image exists;
- for a hardware-qualified run, on-target validation and cleanup pass;
- a required user decision is unresolved;
- the same failure class repeats twice without new evidence;
- the configured iteration or runtime budget is reached; or
- tool, license, device, or hardware access prevents meaningful progress.

Do not average away failures. A workflow passes only when every required stage artifact exists, validates, and reports success.

## Contracts

Validate handoffs against `../../contracts/handoff.schema.json`, transition
receipts against `../../contracts/gate-receipt.schema.json`, and Vitis execution
against `../../contracts/vitis-execution-plan.schema.json` plus
`../../contracts/vitis-result.schema.json`. Resolve agents and skills through
`../../workflow.json` and `../../registry/skills.json`.
