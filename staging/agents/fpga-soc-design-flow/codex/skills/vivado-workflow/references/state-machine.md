<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# v0.1 Workflow State Machine

## Core forward states

| State | Owner | Required artifact | Success transition |
|---|---|---|---|
| `INTAKE` | `amd_soc_orchestrator` | user request | `SPECIFYING` |
| `SPECIFYING` | `amd_soc_intent_to_spec` | `hardware-spec.json` | `ARCHITECTING` |
| `ARCHITECTING` | `amd_soc_architect` | `architecture-plan.json` | `IMPLEMENTING_SOURCES` |
| `IMPLEMENTING_SOURCES` | selected implementation agents | component and aggregate `source-manifest.json` | `VERIFYING` |
| `VERIFYING` | `amd_soc_verifier` | `verification-result.json` | `CLOSING` |
| `VITIS_ACCELERATING` | platform/specialists author the plan; deterministic Vitis runner executes it | `vitis-execution-plan.json`, `vitis-result.json` | `CLOSING` |
| `CLOSING` | `vivado_impl_closure` | `implementation-result.json` | `COMPLETE` or `HARDWARE_VALIDATING` |
| `BUILDING_PS_SOFTWARE` | software agent authors its plan fields; deterministic Vitis runner builds | `vitis-execution-plan.json`, `vitis-result.json` | `COMPLETE` or `HARDWARE_VALIDATING` |
| `HARDWARE_VALIDATING` | `amd_soc_hardware_validator` | `hardware-validation-result.json` | `COMPLETE` |

`IMPLEMENTING_SOURCES` contains only the branches selected by the architecture work packages. The integration owner is `vivado_rtl_engineer` for PL-only designs and `amd_soc_platform_integrator` for PS/CIPS, block-design, AIE, or Vitis designs.

The conditional transitions are:

- No acceleration: `VERIFYING` → `CLOSING`.
- Vitis acceleration: `VERIFYING` → `VITIS_ACCELERATING` → `CLOSING`;
  `vivado_impl_closure` independently signs off the implementation evidence
  created beneath `v++`.
- Fixed-XSA PS software: `CLOSING` → `BUILDING_PS_SOFTWARE`.
- A combined acceleration plan may build the PS application in
  `VITIS_ACCELERATING`; do not repeat that build after closure.

Every success transition passes through the deterministic finalizer for that
stage. The finalizer refreshes declared hashes and validates the owner contract;
only the orchestrator performs the whole-run cross-artifact check.

Every success transition also requires a PASS assurance receipt. A gate is
opened before producer work to capture hash-pinned inputs and the pre-work file
state. Finalization closes the gate, evaluates the producer claim outside that
agent, preserves an iteration-specific JSON/Markdown receipt, and opens the
next default gate only after PASS. `BLOCKED`, `FAIL`, and `ERROR` receipts stop
dispatch and remain visible rather than being averaged into later success.

Across run directories, front-end, simulation, and Vivado work may proceed in
the configured resource pools. Within a run, RTL authoring, platform skeleton
construction, and verification planning may overlap after architecture, but
integrated verification waits for the single-writer aggregate source manifest.
Tcl is serialized per Vivado session and hardware validation is exclusive per
target/JTAG cable.

Use `WAITING_FOR_USER`, `BLOCKED`, and `ERROR` as pause or terminal states. Resume from the artifact and owner that caused the pause.

## Feedback transitions

- Verification functional failure: `VERIFYING` to the owning source agent.
- Verification architectural mismatch: `VERIFYING` to `ARCHITECTING`.
- Implementation source or constraint defect: `CLOSING` to the owning source agent.
- Implementation structural limitation: `CLOSING` to `ARCHITECTING`.
- Vitis HLS/AIE compile failure: `VITIS_ACCELERATING` to the command owner
  recorded in `vitis-result.json`.
- Vitis link/package failure: `VITIS_ACCELERATING` to
  `amd_soc_platform_integrator`.
- BSP/application/ELF failure: `BUILDING_PS_SOFTWARE` to `vitis_sw_engineer`.
- Requirement conflict: any state to `SPECIFYING`.
- Missing test shell, logical probe, or BD access: `HARDWARE_VALIDATING` to the platform integration owner.
- Missing/mismatched `.ltx`, implemented-core identity, final debug map, or build hash: `HARDWARE_VALIDATING` to `vivado_impl_closure`.
- Hardware functional mismatch: `HARDWARE_VALIDATING` to `VERIFYING`, then to the demonstrated source owner.
- Missing target capability, equipment, or authorization: `HARDWARE_VALIDATING` to `WAITING_FOR_USER`.

Increment the revised stage artifact and preserve superseded revisions.
