<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Provenance and Questions

## Provenance

- `USER`: stated directly by the user or supplied regression manifest.
- `VIVADO_OBSERVED`: queried from the active project, checkpoint, run, or report.
- `AMD_DOC`: supported by a result from `vivado_doc_search`.
- `DERIVED`: calculated from two or more sourced facts; include the derivation.
- `ASSUMED`: selected only when behavior is not consequential; state why it is safe.

## Ask the user when

- Board or part cannot be inferred.
- Behavior, protocol mode, clock, reset, latency, safety, or deliverable is ambiguous.
- Two valid architectures have materially different observable behavior or cost.
- A requested objective conflicts with device capability or another hard requirement.
- Implementation would require changing an external interface or adding observable latency.

Do not ask for facts available through Vivado MCP. Ask one question at a time and include its design consequence.
