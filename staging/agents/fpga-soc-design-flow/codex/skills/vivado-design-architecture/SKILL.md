---
name: vivado-design-architecture
description: Convert an approved hardware specification into an implementable FPGA architecture plan covering hierarchy, interfaces, clock and reset domains, CDC, pipelines, latency, memories, DSP resources, IP choices, work packages, source files, and verification obligations. Use after amd_soc_intent_to_spec reports READY and before RTL, XDC, Tcl, HLS, AIE, software, or block-design source generation.
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->


# Vivado Design Architecture

Produce `architecture-plan.json`; do not author implementation source files.

## Procedure

1. Reject a specification that is missing, invalid, or not `READY`.
2. Inspect existing hierarchy and device facts through read-only Vivado MCP queries when a project or checkpoint exists.
3. Define modules, responsibilities, interfaces, protocols, widths, parameters, and ownership boundaries.
4. Define all clock and reset domains and a CDC strategy for every crossing.
5. Define pipeline stages, throughput, latency, buffering, backpressure, memory architecture, and arithmetic resources.
6. Choose inferred RTL, XPM, AMD IP, HLS, block design, or hard block for each function.
7. Use `vivado_doc_search` to validate device-family or release-specific choices.
8. For Vivado IP Integrator, do not assume that a required SystemVerilog top can be
   instantiated as a Module Reference. Vivado 2025.2 regression evidence shows that
   SystemVerilog top definitions can be rejected with `filemgmt 56-195`. Preserve the
   required RTL and select either packaged custom IP or a platform-owned structural
   Verilog shim; validate the selected representation with fresh Vivado evidence.
9. Record alternatives, rationale, risks, and any specification impact.
10. Return to `amd_soc_intent_to_spec` if a choice requires changing observable behavior or a hard requirement.
11. Define one typed work package for each selected implementation agent.
12. Define the source-file plan and verification obligations.
13. Validate the result against `../../contracts/architecture-plan.schema.json`.

Read [references/architecture-decisions.md](references/architecture-decisions.md) for decision ownership and minimum plan content.

## Completion rules

Return `READY` only when every required function has an owner, every interface connects, every clock crossing has a strategy, and every source artifact has a planned purpose.

Return `NEEDS_SPEC_REVISION`, `INFEASIBLE`, or `ERROR` otherwise. Do not hide architectural uncertainty in source-generation instructions.
