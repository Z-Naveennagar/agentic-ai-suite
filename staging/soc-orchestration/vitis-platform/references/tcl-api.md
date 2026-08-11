<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Vitis PFM Tcl API Reference

This skill drives the `::vitis::pfm::*` Tcl API — a concise inspection/application
layer for discovering and assigning Vitis platform (PFM) properties on an open Vivado
block design.

These procedures are a prototype of the standard Vivado API defined by
[VITIS-16733](https://jira.xilinx.com/browse/VITIS-16733). Until they ship as part of a
standard Vivado install, this skill provides them via
[`scripts/autopfm.tcl`](../scripts/autopfm.tcl), which **must be sourced into the Vivado
Tcl interpreter before any `::vitis::pfm::*` command is used** (see SKILL.md Step 0).

All commands run in the context of the current project / current block design. Do not
fabricate results — issue the commands through the Vivado Tcl interface and read back the
actual returns.

## Inspection APIs

Each inspection proc discovers candidate BD objects for a given PFM category and returns a
Tcl **list of dicts**. Pass returned elements **unchanged** to the matching application proc.

| Function | Discovers | Return dict keys |
| --- | --- | --- |
| `::vitis::pfm::get_memory_candidates` | `axi_noc`/`smartconnect` cells that transitively reach `memory`-type address segments or labeled external ports | `cell`, `kind`, `resources` (list of reachable memory resources) |
| `::vitis::pfm::get_control_candidates` | `axi_noc`/`smartconnect` cells reachable from a PS FPD master interface or a labeled external slave port | `cell`, `kind`, `resource` (list of driving interfaces) |
| `::vitis::pfm::get_clock_candidates` | Clock pins that drive a `proc_sys_reset` `slowest_sync_clk` | `cell`, `kind`, `resource` (dict with `clock` pin and `reset` cell) |
| `::vitis::pfm::get_interrupt_candidates` | Undriven pins of type interrupt | `cell`, `kind`, `resource` (interrupt pin) |
| `::vitis::pfm::get_stream_candidates` | Undriven AXI4-Stream master/slave interfaces | `cell`, `kind`, `resource` (AXIS interface) |

- `cell` — the BD cell the property will be set on.
- `kind` — the `name` field of the cell's VLNV.
- `resource` / `resources` — the accessible resource(s) the candidate exposes.

## Application APIs

Each application proc takes **two arguments**: (1) one element returned by the matching
inspection proc, exactly as returned; (2) a dict of additional instructions. Omitted
optional keys are omitted from the underlying `set_property`.

| Function | Instruction dict keys | Sets |
| --- | --- | --- |
| `::vitis::pfm::set_memory` | `sptag` (required); `auto` = `true`/`false`/`preferred` (optional); `hbm` (optional) | `PFM.AXI_PORT` |
| `::vitis::pfm::set_control` | `sptag` (optional); `auto` = `true`/`false`/`preferred` (optional) | `PFM.AXI_PORT` |
| `::vitis::pfm::set_clock` | `id` (required, integer ≥ 0, unique); `is_default` = `true`/`false` (optional) | `PFM.CLOCK` |
| `::vitis::pfm::set_interrupt` | `id` (required, integer 0–127, unique); `range` (optional) | `PFM.IRQ` |
| `::vitis::pfm::set_stream` | `sptag` (required) | `PFM.AXIS_PORT` |

## Usage pattern

```tcl
# 0. Source the API (until it ships in Vivado) — see SKILL.md Step 0
source <skill_dir>/scripts/autopfm.tcl

# 1. Discover
set memory_candidates [::vitis::pfm::get_memory_candidates]

# 2. Apply the first candidate, unchanged, with an instruction dict
::vitis::pfm::set_memory [lindex $memory_candidates 0] [dict create sptag MEMORY0 auto preferred]
```

## Deterministic defaults (when the user delegates the choice)

- Memory: unique `sptag` `MEMORY0`, `MEMORY1`, ...; `auto preferred`.
- Control: unique `sptag` `CONTROL0`, `CONTROL1`, ...; `auto preferred`.
- Clock: unique `id` from `0`; `is_default true` on the first clock only.
- Interrupt: unique `id` from `0`; omit `range`. Max 128 (ids 0–127).
- Stream: unique `sptag` `STREAM0`, `STREAM1`, ...

## Command naming requirements (VITIS-16733)

- Inspection: `::vitis::pfm::get_(memory|control|clock|interrupt|stream)_candidates`
- Application: `::vitis::pfm::set_(memory|control|clock|interrupt|stream)`
