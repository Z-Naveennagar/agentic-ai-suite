---
name: soc-orchestration/vitis-platform
description: Convert an open Vivado block design into an embedded Vitis hardware platform (XSA) by setting PFM_NAME and platform.type, discovering and explaining memory, control, clock, interrupt, and stream platform candidates, applying the user's selections with the Vitis PFM Tcl APIs, generating the block-design target, and exporting the XSA. Use when a user wants to turn, convert, export, or prepare a Vivado design or block design as a Vitis platform.
metadata:
  category: amd-soc-design
  tier: domain
  tags:
    - vitis-platform
    - extensible-xsa
    - pfm
    - versal
    - zynq
    - platform-creation
  complexity: advanced
  estimated_duration: 15-45 minutes
  prerequisites_skills:
    - soc-orchestration
    - ipi-block-design
  related_skills:
    - soc-orchestration/vitis-acceleration
    - soc-orchestration/ps-software
    - soc-orchestration/partitioning
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Convert a Vivado Design to a Vitis Platform

Invoked by `soc-orchestration` (Phase 4b, v++ flow) as `soc-orchestration/vitis-platform`.

Run this workflow through the user's Vivado Tcl interface. Do not invent command results. If no Tcl execution tool is available, give the commands in small stages and ask the user to paste each stage's output before interpreting it.

Read [references/tcl-api.md](references/tcl-api.md) before issuing candidate or application commands.

## Bundled files

- [scripts/autopfm.tcl](scripts/autopfm.tcl) — prototype implementation of the `::vitis::pfm::*` Tcl API ([VITIS-16733](https://jira.xilinx.com/browse/VITIS-16733)). Source this before using any `::vitis::pfm::*` command (Step 0).
- [references/tcl-api.md](references/tcl-api.md) — inspection/application API reference.

### 0. Source the PFM Tcl API

The `::vitis::pfm::*` procedures are not yet part of a standard Vivado install, so source the bundled implementation into the Vivado Tcl interpreter first. Use the absolute path to this skill's `scripts/autopfm.tcl`:

```tcl
source /home/nshirazi/AgenticAI/Vision/.claude/skills/soc-orchestration/vitis-platform/scripts/autopfm.tcl
```

Verify the namespace loaded before proceeding:

```tcl
info procs ::vitis::pfm::get_memory_candidates
```

If this returns empty, stop and resolve the source error before continuing. (Once the API ships natively in Vivado, this step becomes a no-op and can be skipped.)

## Workflow

Maintain progress across turns and resume at the first unfinished step.

### 1. Require an open block design

Ask the user to open in Vivado the block design they want to use. Stop until they confirm it is open. Then verify when possible:

```tcl
current_project
current_bd_design
```

Do not proceed if either command returns empty or errors.

### 2. Identify and configure the platform

Obtain a platform identifier in exactly this form:

```text
vendor:board:name:major.minor
```

Require nonempty `vendor`, `board`, and `name` fields and integer `major` and `minor` components. Ask for a corrected value if invalid. Treat the `name` field as the XSA basename. Confirm before overwriting an existing XSA.

Apply the settings. `PFM_NAME` is a property of the block-design **file** object
(not the `current_bd_design` object), and the embedded design-intent is set with
`platform.design_intent.embedded` (there is no `platform.type` project property in
current Vivado):

```tcl
set bd_file [get_files [get_property FILE_NAME [current_bd_design]]]
set_property PFM_NAME {vendor:board:name:major.minor} $bd_file
set_property platform.design_intent.embedded true [current_project]
```

Use braces around the identifier after substituting the validated value.

### 3. Discover, explain, and select candidates

Run all five discovery functions and retain their returned list elements unchanged:

```tcl
set memory_candidates   [::vitis::pfm::get_memory_candidates]
set control_candidates  [::vitis::pfm::get_control_candidates]
set clock_candidates    [::vitis::pfm::get_clock_candidates]
set interrupt_candidates [::vitis::pfm::get_interrupt_candidates]
set stream_candidates   [::vitis::pfm::get_stream_candidates]
list memory $memory_candidates control $control_candidates clock $clock_candidates interrupt $interrupt_candidates stream $stream_candidates
```

Present every candidate, grouped by category and numbered from zero. Explain its `cell`, `kind`, and `resource` in design-specific terms. Also explain the cross-category roles:

- Control paths let software or a processing system configure accelerators.
- Memory paths give accelerators access to buffers and addressable storage.
- Clocks and their associated resets define timing/reset domains for platform logic.
- Interrupts let hardware signal asynchronous events to software.
- Streams expose direct AXI4-Stream data paths; they complement rather than replace memory-mapped control and memory.

Explain observed relationships from shared cells/resources and connectivity, but do not claim connectivity absent from the returned dictionaries.

Ask the user which numbered candidates to apply and ask for required per-candidate values. They may select any or all categories. If the user says they do not care, requests defaults, or delegates the choice, select every candidate and use these deterministic defaults:

- Memory: unique `sptag` values `MEMORY0`, `MEMORY1`, ... and `auto preferred`.
- Control: unique `sptag` values `CONTROL0`, `CONTROL1`, ... and `auto preferred`.
- Clock: unique IDs starting at `0`; set `is_default true` only on the first clock and `false` on the rest.
- Interrupt: unique IDs starting at `0`; omit `range`.
- Stream: unique `sptag` values `STREAM0`, `STREAM1`, ....

If more than 128 interrupt candidates are selected, do not silently truncate them: ask the user to select at most 128 because interrupt IDs are limited to 0 through 127.

### 4. Apply selections and export

Pass each selected candidate's original list element directly to its matching `set_*` function. Do not reconstruct or edit candidate dictionaries. Example indexing pattern:

```tcl
::vitis::pfm::set_memory [lindex $memory_candidates 0] [dict create sptag MEMORY0 auto preferred]
::vitis::pfm::set_control [lindex $control_candidates 0] [dict create sptag CONTROL0 auto preferred]
::vitis::pfm::set_clock [lindex $clock_candidates 0] [dict create id 0 is_default true]
::vitis::pfm::set_interrupt [lindex $interrupt_candidates 0] [dict create id 0]
::vitis::pfm::set_stream [lindex $stream_candidates 0] [dict create sptag STREAM0]
```

Construct one call per selection using the user's values or the defaults above. Validate all application arguments against the API reference before execution.

Generate the current block design and write the XSA using the `name` component of `PFM_NAME`:

```tcl
set bd_file [get_files [get_property FILE_NAME [current_bd_design]]]
generate_target all $bd_file
write_hw_platform -force -file {name.xsa}
```

Report the resulting XSA path returned or implied by Vivado. If a command fails, stop, report the exact error and the last successful step, and resolve that error before continuing. Never report conversion as complete unless `write_hw_platform` succeeds.
