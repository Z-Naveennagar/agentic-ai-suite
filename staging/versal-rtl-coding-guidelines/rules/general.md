<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# General RTL Guidelines

Sources: UG901 HDL coding techniques and UG949/UG1387 control-set, fanout, and methodology
guidance.

## GEN-1 — Avoid unintended latches

Use `always_comb`, assign defaults, and cover every conditional path. Verify the Versal latch
primitive subgroup after synthesis:

```tcl
set latches [get_cells -hier -filter {PRIMITIVE_GROUP == REGISTER && PRIMITIVE_SUBGROUP == LATCH}]
list LATCH [llength $latches]
```

## GEN-2 — Make arithmetic width and signedness explicit

Size constants and intermediate expressions for the intended carry, truncation, rounding, and
sign extension. Treat lint warnings as design questions rather than suppressing them blindly.

## GEN-3 — Use assignment semantics consistently

Use nonblocking assignments for clocked state and blocking assignments for combinational
logic. Do not drive one signal from multiple procedural blocks unless the language construct
and hardware architecture explicitly support it.

## GEN-4 — Control control sets deliberately

Each distinct clock/reset/enable combination can reduce packing flexibility. Share compatible
controls, reset only what requires deterministic state, and code reset/enable priority to
match the hardware intent. Use `report_control_sets`; no universal count is correct for every
design.

## GEN-5 — Measure high fanout before prescribing replication

Registering a control can improve timing, but `max_fanout` is an optimization hint and can
create replicas, control sets, and placement tradeoffs. First use
`report_high_fanout_nets` after placement, preserve replication freedom, and apply a fanout
constraint only with a measured target-specific reason.

## GEN-6 — Keep feedback sequential

Avoid unintended combinational loops. Intentional accumulators, LFSRs, and state feedback must
pass through registers and be tested for the intended initialization and enable behavior.

## GEN-7 — Use language safety features without changing semantics

Use typed enums, `always_ff`, `always_comb`, explicit default assignments, and
``default_nettype none`` where compatible with the source environment. Restore the expected
net type at a file boundary when integration requires it. Use `unique` or `priority` only when
the stated mutual-exclusion/coverage promise is true.

## Checklist

- [ ] No unintended latches or combinational loops remain.
- [ ] Widths, signedness, truncation, rounding, and saturation are explicit.
- [ ] Sequential/combinational assignment semantics are consistent.
- [ ] Control-set and fanout decisions are based on reports, not fixed thresholds.
- [ ] Language assertions such as `unique` match reachable behavior.
- [ ] Behavioral regression passes after every QoR-oriented rewrite.
