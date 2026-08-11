<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# RTL and XDC Pairing

Select CDC constraints path by path. An asynchronous clock relationship does not by itself
justify one blanket exception for every crossing. Sources: UG903 timing constraints and
UG949/UG1387 sections "Defining Clock Groups and CDC Constraints", "Constraints on
Individual CDC Paths", and "Clock Exceptions Precedence Over set_max_delay".

## Required decision sequence

1. Inventory every path between each clock pair and classify the CDC structure.
2. Prefer supported XPM CDC/FIFO structures where they match the protocol. Preserve their
   scoped constraints.
3. Use `set_max_delay -datapath_only` only where crossing latency must be bounded. A common
   starting value is the source period; for a large clock ratio, the minimum source/destination
   period can be appropriate. Derive the value from actual clock objects.
4. Use `set_bus_skew` where the protocol requires bounded relative arrival, such as a
   Gray-coded bus. Derive its value from the receiving protocol and clock period; do not copy
   the max-delay value automatically.
5. Use a point-to-point `set_false_path` only for paths that do not need latency control.
6. Do not apply `set_clock_groups` between two clocks if any crossing between them uses
   `set_max_delay -datapath_only`. `set_clock_groups` and overlapping `set_false_path`
   constraints have higher precedence and make the max delay ineffective.
7. Verify that each `get_*` collection is nonempty before applying a constraint.
8. Run `report_exceptions -coverage`, `report_methodology`, and `report_cdc` after constraints
   are loaded.

## Single-bit synchronizer

A recognized two-flop synchronizer needs an `ASYNC_REG` structure. Its timing exception
choice depends on latency intent:

- Use a point-to-point false path when the crossing does not need latency control.
- Use a point-to-point max-delay constraint when physical latency must be bounded.
- Do not constrain from an entire source clock when only one source register drives the
  synchronizer. Resolve the actual launch cells and the first synchronizer stage.

Illustrative Tcl; replace every object and period with resolved design objects:

```tcl
set src_regs  [get_cells -quiet {u_src/status_reg}]
set sync_dpin [get_pins  -quiet {u_sync/sync_ff_reg[0]/D}]
if {![llength $src_regs] || ![llength $sync_dpin]} { error "CDC constraint objects not found" }
set_max_delay -datapath_only -from $src_regs -to $sync_dpin <derived_ns>
```

## Gray-coded bus

Constrain the actual source Gray registers to the first destination synchronizer stage. Apply
max delay and/or bus skew according to the protocol analysis:

```tcl
set gray_src [get_cells -quiet {u_fifo/wr_ptr_gray_reg[*]}]
set gray_dst [get_cells -quiet {u_fifo/wr_ptr_sync_reg[*]}]
if {![llength $gray_src] || ![llength $gray_dst]} { error "Gray CDC objects not found" }
set_max_delay -datapath_only -from $gray_src -to $gray_dst <source_period_ns>
set_bus_skew -from $gray_src -to $gray_dst <derived_skew_ns>
```

XPM CDC and FIFO macros carry scoped constraints. Do not add a blanket `set_clock_groups`
that overrides those constraints.

## Multicycle paths

Use multicycle constraints only when the launch/capture protocol genuinely provides multiple
cycles. Pair setup `N` with hold `N-1`, scope both endpoints, and verify coverage:

```tcl
set_multicycle_path 2 -setup -from <launch_cells> -to <capture_cells>
set_multicycle_path 1 -hold  -from <launch_cells> -to <capture_cells>
```

Never use a multicycle path solely to silence a timing failure.

## Static controls and resets

Do not automatically false-path a mode signal, reset-synchronizer output, or asynchronous
reset port. First prove the signal's behavior and check the IP/reset methodology:

- A reset-synchronizer output is synchronous control in its destination domain and must not be
  labeled static merely because its source was asynchronous.
- Asynchronous assertion and synchronous deassertion require a recognized reset synchronizer
  and recovery/removal analysis. Apply only the scoped exception recommended for that
  structure or IP configuration.
- A quasi-static control still needs a defined capture protocol. Use a false path only when
  the design contract proves that timing is irrelevant.

## Acceptance gate

Require all of the following for the scoped design:

```tcl
report_exceptions -coverage -file <report_dir>/exceptions_coverage.rpt
report_methodology -file <report_dir>/methodology.rpt
report_cdc -details -file <report_dir>/cdc.rpt
```

Review overridden exceptions, unconstrained endpoints, missing synchronizers, fanout from the
first synchronization stage, and unsafe multi-bit structures. Report files are evidence; the
crossing protocol must also be verified by simulation or formal analysis where applicable.
