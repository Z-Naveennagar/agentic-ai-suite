---
name: vivado-intent-to-spec
description: Translate natural-language FPGA goals and existing Vivado project evidence into a traceable, measurable hardware specification. Use for greenfield design requests, modifications to existing Vivado projects, failed-build requests, or regression manifests that need requirements, acceptance criteria, assumptions, and unresolved decisions normalized before architecture or source generation.
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->


# Vivado Intent to Specification

Produce `hardware-spec.json`; do not create or modify RTL, XDC, Tcl, projects, or runs.

## Procedure

1. Preserve the user's request and classify the entry as `greenfield`, `existing_project`, `checkpoint`, `failure`, or `regression`.
2. Extract functional behavior, interfaces, clocks, resets, performance, resources, power, verification, deliverables, and allowed changes.
3. Use Vivado MCP to discover facts already present:
   - call `vivado_client_info` and `vivado_list_sessions`;
   - reconnect or request a Tcl-mode session when project inspection is needed;
   - query the part, board, top, filesets, clocks, IP, and run state without modifying them.
4. Use `vivado_doc_search` only for AMD-specific facts such as device capability, supported IP behavior, inference templates, constraint semantics, or release differences.
5. Label each value `USER`, `VIVADO_OBSERVED`, `AMD_DOC`, `DERIVED`, or `ASSUMED`.
6. Convert qualitative goals into measurable acceptance criteria or explicit optimization objectives.
7. Detect conflicts and list questions that materially affect behavior, interfaces, latency, safety, clocks, or signoff.
8. Ask one focused question at a time in interactive mode. In regression mode, return `NEEDS_USER_INPUT` instead of inventing an answer.
9. Validate the result against `../../contracts/hardware-spec.schema.json`.

Read [references/provenance-and-questions.md](references/provenance-and-questions.md) when deciding whether an assumption requires user input.

## Completion rules

Return:

- `READY` when every hard requirement is measurable and no blocking question remains.
- `NEEDS_USER_INPUT` when a consequential product decision is missing.
- `INFEASIBLE` when documented capability and stated requirements conflict.
- `ERROR` when evidence collection or validation fails.

Never use documentation to decide a user-owned requirement. Never mark an assumption as observed.
