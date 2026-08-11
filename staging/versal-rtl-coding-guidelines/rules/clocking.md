<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Clocking Guidelines

Sources: UG1387 clocking methodology and UG949 clock-enable/clock-network guidance.

## CLK-1 — Use clock enables instead of fabric-gated clocks

Do not create clocks with LUT/AND logic. Use the dedicated register CE for fine-grained
activity control. For a real clock stop, use a supported global clock buffer such as BUFGCE
and meet its enable requirements.

## CLK-2 — Use dedicated clock-generation and distribution resources

Do not clock logic from a divider register merely because it toggles at the desired rate. Use
a clock enable when a new domain is unnecessary; otherwise use the supported MMCM/PLL/DPLL or
clock-buffer divide resource and create the corresponding generated-clock constraint.

## CLK-3 — Keep enable logic reviewable

High-fanout, deeply decoded enables can become timing and control-set problems. Register or
pipeline enable computation when latency permits, share compatible control signals, and let
Vivado optimize/replicate legal drivers. Do not impose a universal fanout threshold.

## Verification

Use Vivado's clock and methodology reports rather than ad-hoc `get_cells -of [get_nets ...]`
queries, which can mix drivers and loads and misclassify clock sources:

```tcl
report_clock_networks -file <report_dir>/clock_networks.rpt
report_methodology -file <report_dir>/methodology.rpt
report_control_sets -file <report_dir>/control_sets.rpt
report_high_fanout_nets -file <report_dir>/high_fanout.rpt
```

Confirm that each clock has the intended primary/generated constraint, reaches sequential
clock pins through supported clock resources, and has no unintended LUT logic on its network.

## Checklist

- [ ] No LUT/AND-gated clocks exist.
- [ ] Divided clocks use dedicated resources and generated-clock constraints, or are replaced by enables.
- [ ] BUFGCE enables follow the documented clock-buffer requirements.
- [ ] Enable/control-set and high-fanout findings are measured and resolved after implementation.
