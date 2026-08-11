---
name: vivado-source-authoring
description: Create and repair RTL, XDC, Vivado Tcl, IP configuration, block-design scripts, and source manifests from an approved FPGA architecture plan. Use after design architecture reports READY, when source files must be generated or modified, or when elaboration, lint, or implementation feedback identifies a source-owned defect.
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->


# Vivado Source Authoring

Implement the approved architecture without silently revising upstream requirements or architecture.

## Procedure

1. Validate the hardware specification and architecture plan.
2. Create only files listed in the architecture source plan.
3. Preserve interface names, widths, clocks, resets, latency, and parameter contracts.
4. Use the applicable coding-guideline or protocol skill from the capability registry.
5. Use `vivado_doc_search` before unfamiliar primitives, XPMs, IP parameters, attributes, or constraints.
6. Acquire the shared Vivado MCP session lock before Tcl execution.
7. Add or refresh sources, set the top, update compile order, and elaborate through `vivado_execute`.
8. Use the registered `rtl-elaboration-analysis` capability for elaboration failures.
9. Repair source-owned issues and rerun elaboration within the configured iteration budget.
10. Record every generated or modified file, its role, language, and originating architecture element.
11. Validate `source-manifest.json` against `../../contracts/source-manifest.schema.json`.

Read [references/source-ownership.md](references/source-ownership.md) before applying feedback from another agent.

## Guardrails

- Do not add false paths, multicycle paths, or clock relaxation merely to suppress timing failures.
- Do not add observable latency or change external interfaces without an approved architecture revision.
- Do not claim functional correctness; hand the elaborated sources to `amd_soc_verifier`.
- Release the MCP session lock after each bounded command sequence.
