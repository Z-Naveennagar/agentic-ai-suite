---
name: vivado-implementation-closure
description: Run and monitor Vivado synthesis and implementation, collect DRC, CDC, timing, utilization, congestion, and power evidence, classify failures, apply bounded implementation-level optimizations, and generate checkpoints, bitstreams, or PDIs. Use only after required functional verification passes, or for analysis-only work on an existing synthesized, implemented, or routed design.
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->


# Vivado Implementation and Closure

Own run execution and physical closure; route upstream defects to their owning agent.

## Procedure

1. Validate the specification, architecture, source manifest, and required verification result.
2. Discover or establish the Vivado MCP session and acquire its shared lock.
3. Inspect project, part, board part when specified, top, constraints, run state, and prior results.
4. Run synthesis using `launch_runs` followed by `wait_on_run`.
5. Review inferred resources, utilization, methodology, DRC, CDC, and timing constraints.
6. Run implementation using `launch_runs` followed by `wait_on_run`.
7. Monitor long operations with `vivado_status`; diagnose failures with `vivado_log_messages`.
8. Collect timing, utilization, congestion, power, DRC, CDC, checkpoint, and run-history evidence.
9. Classify each failure as requirement, architecture, source, verification, implementation, or infrastructure owned.
10. Apply only behavior-preserving implementation directives or physical optimizations within the configured budget.
11. Use registered specialist skills for timing methodology, opt/phys-opt analysis, congestion, post-route analysis, and timing closure.
12. Use `vivado_doc_search` before unfamiliar directives, messages, or device-specific remedies.
13. Use `vivado_doc_search` to confirm the target family flow, then generate the required `.bit` or `.pdi` programming image only when signoff checks pass.
14. Echo the verified board part into `vivado.board` when the hardware specification selects a board.
15. Validate `implementation-result.json` against `../../contracts/implementation-result.schema.json`.

Read [references/closure-routing.md](references/closure-routing.md) before selecting a remedy.

## Guardrails

Never silently relax clocks, add unjustified timing exceptions, change interfaces, add observable latency, remove CDC protection, or waive critical violations.

Success requires a recorded programming-image artifact that exists on disk. Otherwise stop only on the iteration budget, repeated failure without new evidence, or an upstream contract conflict. Release the MCP session lock before returning.
