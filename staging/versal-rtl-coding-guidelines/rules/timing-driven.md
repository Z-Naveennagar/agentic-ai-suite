<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Timing-Driven RTL Guidelines

Sources: UG949 timing methodology and UG901 retiming/coding techniques. Preserve functional
latency and throughput while changing structure for QoR.

## TD-1 — Pipeline measured deep logic

Use `report_design_analysis -logic_level_distribution`, timing paths, fan-in, and congestion
to identify deep cones. Balance reductions, arithmetic, encoders, and muxes across pipeline
stages when the interface permits the added latency. Keep valid and metadata aligned.

## TD-2 — Keep retiming candidates compatible

Retiming can be blocked by resets, enables, preservation attributes, hierarchy boundaries, and
resource packing. Remove a reset/enable only when the behavioral contract permits it. Verify
that the selected synthesis/physical optimization actually moved registers and improved the
required path; do not promise retiming from RTL shape alone.

## TD-3 — Balance SRL area against retiming flexibility

Unreset delay chains can infer SRLs, which are area-efficient but constrain retiming through
the chain. Use the documented `SRL_STYLE` intent where necessary and verify actual mapping.
Choose discrete registers on a critical path only when timing evidence justifies the area/power
tradeoff.

## TD-4 — Restructure wide fan-in without changing priority

A balanced or pipelined implementation can improve timing, but a priority chain and a parallel
one-hot selection have different behavior when multiple requests assert. Preserve the stated
arbitration semantics and add assertions for mutual exclusion if the optimized structure
requires it.

## Verification

```tcl
report_design_analysis -logic_level_distribution -file <report_dir>/logic_levels.rpt
report_high_fanout_nets -file <report_dir>/high_fanout.rpt
report_timing_summary -file <report_dir>/timing_summary.rpt
```

Compare pre/post implementation under the same clocks, constraints, strategies, and seed where
possible. Inspect synthesis/physical-optimization logs for retiming and replication evidence.

## Checklist

- [ ] Pipeline changes preserve required latency/throughput or explicitly update the contract.
- [ ] Valid, framing, and metadata remain aligned with data.
- [ ] Retiming/replication is verified from logs/netlist, not assumed.
- [ ] SRL-versus-register mapping matches the measured timing/area tradeoff.
- [ ] Priority and mutual-exclusion semantics survive fan-in restructuring.
