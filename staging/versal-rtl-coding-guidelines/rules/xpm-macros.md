<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# XPM Guidelines

Sources: the current XPM documentation and Vivado language templates. Copy the complete
instance from the target Vivado release because required ports, parameters, reset behavior,
and feature encodings can change.

## XPM-1 — Prefer supported macros for standard structures

Use XPM CDC, FIFO, and memory macros when their documented contract matches the design. They
provide reviewed structures and scoped constraints, but they are safe only when parameters,
clock relationships, reset sequencing, and use of source/destination registers follow the
macro documentation.

Do not present an abbreviated instance with missing required ports as a compilable golden
module. Generate a complete instance from Vivado Language Templates and connect every required
status, sleep, injection, reset, and enable port deliberately.

## XPM-2 — Preserve scoped CDC constraints

XPM CDC/FIFO macros include scoped timing constraints. Do not override them with blanket
`set_clock_groups` or overlapping false paths. Run `report_exceptions -coverage`,
`report_methodology`, and `report_cdc` after the XPM XDC is loaded.

## XPM-3 — Select memory by behavior and implementation results

Choose distributed RAM, BRAM, UltraRAM, registers, or SRLs using required ports, clocking,
read mode, byte enables, ECC, capacity, latency, power, and timing. Do not use fixed bit/depth
thresholds as universal boundaries. `MEMORY_PRIMITIVE` or `ram_style` expresses intent but
does not override an unsupported configuration; verify the inferred primitive and properties.

## XPM-4 — Follow the build flow for the installed release

Project and non-project flows can differ in how XPM sources/libraries are enabled. Use the
current Vivado documentation and language template for the build mode. Confirm elaboration
with a standalone lint/synthesis operation rather than assuming a project property is required
or sufficient in every flow.

## Verification

```tcl
set bram [get_cells -hier -filter {PRIMITIVE_GROUP == BLOCKRAM && PRIMITIVE_SUBGROUP == BRAM}]
set uram [get_cells -hier -filter {PRIMITIVE_GROUP == BLOCKRAM && PRIMITIVE_SUBGROUP == URAM}]
set sync [get_cells -hier -filter {ASYNC_REG == TRUE}]
list BRAM [llength $bram] URAM [llength $uram] ASYNC_REG [llength $sync]
report_exceptions -coverage -file <report_dir>/exceptions_coverage.rpt
report_cdc -details -file <report_dir>/cdc.rpt
report_methodology -file <report_dir>/methodology.rpt
```

Also run the XPM-specific simulation model and test reset, overflow/underflow, error flags,
latency, and any ECC injection features used.

## Checklist

- [ ] The complete instance comes from the installed-release language template.
- [ ] Parameters and ports match the required clock/reset/protocol contract.
- [ ] XPM scoped constraints are present and not overridden.
- [ ] Memory/resource selection is verified after synthesis.
- [ ] Functional corner cases are tested with the XPM simulation model.
