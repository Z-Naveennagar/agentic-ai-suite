<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# AMD Adaptive SoC Artifact Ownership v0.1

Status: required workflow policy

## Rule

Every mutable artifact has exactly one writer. Any number of downstream agents
may read or independently check it, but a consumer must return a finding to the
writer instead of repairing the artifact.

The orchestrator owns transitions and invokes the deterministic artifact
finalizer. The finalizer may refresh declared hashes and validate revision
links; it does not change engineering content.

The producing specialist owns its engineering artifact and status claim, but
does not own the transition verdict. `scripts/gate_runner.py` is the sole
writer of gate receipts and their generated Markdown views. A gate receipt is
derived from hash-pinned inputs and outputs, the producer artifact, pre-work
file state, deterministic checks, and recorded approval provenance.

## Ownership

| Artifact or artifact class | Sole writer | Readers and checks |
|---|---|---|
| Preserved user request, `run.json`, handoffs, final result | `amd_soc_orchestrator` | All selected agents |
| `hardware-spec.json` | `amd_soc_intent_to_spec` | Architect and all downstream agents |
| `architecture-plan.json` | `amd_soc_architect` | All implementation, verification, and closure agents |
| RTL-owned source and manifest fragment | `vivado_rtl_engineer` | Integration owner, verifier, implementation |
| HLS source/component fragment | `vitis_hls_engineer` | Integration owner, verifier, implementation |
| AIE source/component fragment | `vitis_aie_engineer` | Platform integrator, verifier, implementation |
| PS software source/application fragment | `vitis_sw_engineer` | Platform integrator, verifier, hardware validator |
| Aggregate `source-manifest.json` | Integration owner selected by architecture | Verifier, implementation, orchestrator |
| PS/CIPS configuration, BD, address map, HWH, platform reports, insertion reports | `amd_soc_platform_integrator` | Verifier and implementation |
| `vitis-execution-plan.json` and system link/package fields | `amd_soc_platform_integrator` | Deterministic Vitis runner and orchestrator |
| `vitis-result.json` and generated Vitis outputs such as ELF, XO, XCLBIN, linked XSA, and package | Deterministic Vitis runner executing the approved plan | Owning specialists inspect command evidence; orchestrator checks the result |
| `verification-result.json` and verifier tests | `amd_soc_verifier` | Implementation and orchestrator |
| `implementation-result.json`, final `.bit`/`.pdi`, final fixed `.xsa`, `.ltx`, checkpoints, physical reports, final `debug-map.json` | `vivado_impl_closure` | Hardware validator and orchestrator |
| `hardware-test.json` | Immutable regression/test-profile input | Verifier checks the oracle; platform realizes it; hardware validator executes it |
| `hardware-validation-result.json` and hardware evidence | `amd_soc_hardware_validator` | Orchestrator |
| `gates/*.json` transition receipts and generated `gates/*.md` reports | Deterministic gate runner | User, orchestrator, and every downstream agent |
| Shared schemas, validators, runners, workflow configuration | Prototype maintainer through an explicit framework-change task | Agents report defects; they do not patch framework code during a design run |

## Source-manifest boundary

`source-manifest.json` describes inputs needed to reproduce elaboration and
implementation plus stable source-stage evidence. It must not contain mutable
post-source artifacts:

- Vivado project databases (`.xpr`);
- programming images (`.bit` or `.pdi`);
- debug probes (`.ltx`);
- XSA exports (pre-implementation exports travel in the platform handoff;
  final fixed XSA files travel in implementation results);
- final `debug-map.json`;
- implementation checkpoints or reports; or
- hardware captures and logs.

Block-design Tcl, authored RTL/XDC, required module-reference wrappers, and a BD
used as an implementation input may remain in the source manifest. Generated
HWH, pre-implementation XSA, and other platform exports are referenced by the
platform handoff rather than treated as immutable source files.

## Debug ownership

The three debug checks are intentionally different:

1. `amd_soc_platform_integrator` inserts the test shell and VIO/ILA, then emits
   insertion reports with logical probes, BD cells/nets, widths, clocks, safe
   values, and replay Tcl.
2. `amd_soc_verifier` simulates the logical self-test behavior and pass oracle.
3. `vivado_impl_closure` inventories the implemented cores, writes the matching
   LTX, records UUIDs and physical probe names, and creates final
   `debug-map.json`.

`amd_soc_hardware_validator` consumes this immutable build set. It never
repairs instrumentation or changes the debug map.

## Validation ownership

- Specialists validate their own schema, outputs, and local engineering checks.
- The deterministic finalizer refreshes owned hash fields at each transition.
- The deterministic gate runner evaluates the producer claim and writes the
  transition verdict; a producing agent never edits its own receipt.
- Only `amd_soc_orchestrator` runs whole-run cross-artifact validation.
- Independent downstream checking is encouraged; downstream mutation is not.

## Parallel execution

Parallelism is primarily across isolated run directories. Within one run,
after architecture is READY, RTL authoring, platform skeleton construction,
and verification planning may proceed concurrently when their work packages
do not write the same artifact. Convergence occurs before integrated
verification.

Vivado implementation uses a bounded global slot pool. Hardware execution uses
an exclusive lock per target profile/JTAG cable. Tcl execution remains
serialized per Vivado session.
