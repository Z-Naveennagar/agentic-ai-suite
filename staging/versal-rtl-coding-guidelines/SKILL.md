---
name: versal-rtl-coding-guidelines
description: Author and review synthesis-friendly SystemVerilog or Verilog for AMD Versal adaptive SoCs using AMD Vivado documentation-grounded guidance. Use for Versal resets, clocks, BRAM or UltraRAM, DSP58, FSMs, CDC and XPM structures, AXI ready/valid interfaces, timing-driven pipelines, hard-block boundaries, reliability logic, RF/video/network datapaths, or requests to make RTL infer and implement well in Vivado.
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Versal RTL Coding Guidelines

Author or revise RTL, preserve the requested behavior and interface contract, and verify the
result with the available Vivado-capable tools. Treat the rule examples as patterns, not
drop-in modules. Use the design's actual names, widths, reset contract, latency, throughput,
and target part.

## Select only the relevant guidance

Load the files needed for the requested block:

- [rules/reset.md](rules/reset.md) — reset choice, precedence, minimization, and DSP consistency
- [rules/clocking.md](rules/clocking.md) — clock enables, clock buffers, and generated clocks
- [rules/memory.md](rules/memory.md) — BRAM/UltraRAM inference, registers, resets, and write modes
- [rules/dsp.md](rules/dsp.md) — DSP58 inference, pipelining, reset compatibility, and explicit features
- [rules/fsm.md](rules/fsm.md) — extraction, encoding, outputs, and illegal-state recovery
- [rules/cdc.md](rules/cdc.md) — single-bit, multi-bit, reset, FIFO, and Gray-code crossings
- [rules/general.md](rules/general.md) — latches, widths, control sets, and fanout
- [rules/xpm-macros.md](rules/xpm-macros.md) — XPM memory, FIFO, and CDC macros
- [rules/interfaces.md](rules/interfaces.md) — AXI ready/valid, elastic buffering, and AXI4-Lite channels
- [rules/timing-driven.md](rules/timing-driven.md) — logic depth, pipelining, retiming, and SRLs
- [rules/versal-hardblocks.md](rules/versal-hardblocks.md) — NoC, AI Engine, DDRMC, GT, and PCIe/CPM boundaries
- [rules/safety-reliability.md](rules/safety-reliability.md) — ECC, redundancy, safe-state logic, and fault checks
- [rules/security.md](rules/security.md) — implementation cautions for security-sensitive RTL
- [rules/rf-datapath.md](rules/rf-datapath.md) — RFdc streams, I/Q alignment, fanout, and gearboxes
- [rules/streaming-video.md](rules/streaming-video.md) — video framing, buffers, and elastic pixel pipelines
- [rules/packet-processing.md](rules/packet-processing.md) — packet metadata, parsers, tables, and header edits
- [rules/dsp-datapath.md](rules/dsp-datapath.md) — FIR, complex MAC, CORDIC, and FFT structures
- [rules/high-speed-io.md](rules/high-speed-io.md) — link readiness, elastic buffers, gearboxes, and deskew

For application-level requests, first use
[references/segment-playbook.md](references/segment-playbook.md). For constraints and
verification, use:

- [references/rtl-xdc-pairing.md](references/rtl-xdc-pairing.md)
- [references/rule-check-map.md](references/rule-check-map.md)
- [references/ug-index.md](references/ug-index.md)

## Workflow

1. **Capture the contract.** Identify the target Versal part, clocks and relationships,
   reset behavior, interface protocol, latency, throughput, RAM collision semantics, and
   reliability or security requirements. Do not invent a missing requirement that changes
   externally visible behavior.
2. **Load scoped rules.** Read only the topic files needed for the block. If a rule depends
   on an IP configuration or device resource, consult the cited AMD guide for the target
   Vivado release.
3. **Author or revise RTL.** Preserve the port list and behavior unless the user requests an
   interface change. Make examples complete and compilable; otherwise label them as
   pseudocode.
4. **Review the RTL and companion XDC.** Check the topic checklist. For CDCs, classify every
   path before selecting an exception; never apply a blanket clock exception merely because
   clocks are asynchronous.
5. **Verify with available Vivado capabilities.** Use project or non-project mode correctly,
   save raw reports, and distinguish structural evidence from functional proof.
6. **Fix documented failures and re-run the affected checks.** Do not change syntax or
   architecture blindly. Use the diagnostic, the relevant AMD documentation, and the design
   contract to justify each correction.
7. **Report evidence and limitations.** State the part, Vivado version, files changed, checks
   run, expected versus observed inference, unresolved warnings, and tests not run.

## Vivado verification flow

Use whichever connected tool can execute Vivado Tcl. Tool adapters can require different
session identifiers, timeout handling, or long-command polling; follow the adapter's actual
schema instead of embedding client-specific arguments in this skill.

### Lint

Run `synth_design -lint` as a standalone Vivado operation. In a non-project flow, include the
actual top and part and write the report:

```tcl
synth_design -lint -rtl -top <top> -part <part> -file <report_dir>/lint.rpt
```

Do not concatenate `synth_design` with setup or report commands when the execution adapter
requires design commands to be standalone.

### Synthesis

- In project mode, launch the synthesis run and wait for it with the capabilities provided
  by the connected tool.
- In non-project mode, read the actual sources and constraints, then run `synth_design` as a
  standalone operation.
- After synthesis completes, run report and query commands separately.

Example structural summary:

```tcl
set bram [get_cells -hier -filter {PRIMITIVE_GROUP == BLOCKRAM && PRIMITIVE_SUBGROUP == BRAM}]
set uram [get_cells -hier -filter {PRIMITIVE_GROUP == BLOCKRAM && PRIMITIVE_SUBGROUP == URAM}]
set dsp  [get_cells -hier -filter {PRIMITIVE_GROUP == ARITHMETIC && PRIMITIVE_SUBGROUP == DSP}]
set lat  [get_cells -hier -filter {PRIMITIVE_GROUP == REGISTER && PRIMITIVE_SUBGROUP == LATCH}]
list BRAM [llength $bram] URAM [llength $uram] DSP [llength $dsp] LATCH [llength $lat]
```

Counts are evidence of mapping, not proof that the implementation matches the intended
latency, protocol, redundancy, or security properties.

### Reports and functional checks

Select checks according to the design:

```tcl
report_utilization -file <report_dir>/utilization.rpt
report_control_sets -file <report_dir>/control_sets.rpt
report_clock_networks -file <report_dir>/clock_networks.rpt
report_high_fanout_nets -file <report_dir>/high_fanout.rpt
report_design_analysis -logic_level_distribution -file <report_dir>/logic_levels.rpt
report_cdc -details -file <report_dir>/cdc.rpt
report_exceptions -coverage -file <report_dir>/exceptions_coverage.rpt
report_methodology -file <report_dir>/methodology.rpt
report_timing_summary -file <report_dir>/timing_summary.rpt
```

Supplement structural reports with self-checking simulation, protocol checkers, assertions,
formal checks, or fault injection where required. `report_drc`, primitive counts, or
attributes alone do not prove AXI correctness, CDC protocol correctness, TMR independence,
safe-state recovery, or security.

## Acceptance criteria

Accept the result only when the checks relevant to the requested scope pass:

- RTL elaborates and lint findings are resolved or explicitly justified.
- Inferred resources and register settings match the intended function and latency.
- No unintended latches, fabric-generated clocks, or incompatible control/reset structures
  remain.
- CDC paths have recognized structures and non-conflicting, coverage-checked constraints.
- AXI or other ready/valid payloads remain stable while stalled and pass protocol simulation.
- Timing and methodology reports have no unexplained critical findings.
- Reliability requirements have functional or fault-injection evidence, not only preservation
  attributes.
- Security claims are limited to what was actually verified under a stated threat model.

If Vivado or simulation is unavailable, clearly label the result as an unverified RTL review.

## Documentation boundary

Keep normative claims traceable to AMD documentation for the applicable release:

- UG1387 — Versal hardware, IP, and platform development methodology
- UG949 — UltraFast design methodology
- UG901 — Vivado synthesis and HDL coding techniques
- UG903 — timing constraints and exception precedence
- UG835 — Vivado Tcl command syntax
- UG912 — Vivado properties and primitive properties
- UG906 — timing analysis and exception coverage
- UG1037 and the AMBA AXI specification — AXI channel behavior
- AM004 — Versal DSP Engine
- AM007 — Versal memory resources
- UG974/UG953 and XPM documentation — Versal primitives and parameterized macros

Do not convert an IP-specific recommendation, empirical QoR observation, or security design
preference into a universal rule. State configuration dependencies and verify them on the
actual target.
