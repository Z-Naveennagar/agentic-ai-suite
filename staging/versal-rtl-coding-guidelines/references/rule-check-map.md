<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Rule-to-Verification Map

Map each RTL rule to evidence that Vivado can provide and to any required functional test.
Run design commands separately when required by the connected execution tool. Structural
counts never replace protocol, safety, or security verification.

| Rule group | Structural evidence | Required additional evidence |
|---|---|---|
| Reset | `report_control_sets`, `report_methodology`, DSP/RAM register properties | Reset sequencing and recovery simulation |
| Clocking | `report_clock_networks`, `report_methodology` | Clock-source and IP clocking contract review |
| Memory | BRAM/URAM primitive groups, output-register/write-mode properties | Collision-mode and reset-behavior simulation |
| DSP | DSP primitive subgroup and configured A/B/M/P registers | Latency/arithmetic simulation; cascade connectivity when intended |
| FSM | synthesis FSM extraction and `FSM_ENCODING`/`FSM_SAFE_STATE` | Illegal-state injection or formal recovery proof |
| CDC/XPM | `report_cdc`, `ASYNC_REG`, scoped XPM constraints, exception coverage | Handshake/FIFO/protocol simulation or formal checks |
| General RTL | lint, latch subgroup, control sets, high fanout | Behavioral regression |
| AXI/interfaces | combinational-loop checks | AXI protocol checker and randomized backpressure |
| Timing | logic-level distribution and timing summary | Required clock/latency acceptance |
| Reliability | ECC configuration and three distinct redundancy cones | Fault injection, voter/common-mode analysis, physical separation |
| Security | preservation/configuration evidence only | Threat model, zeroization test, information-flow and side-channel review |
| Domain datapaths | utilization, fanout, CDC, timing | Framing, ordering, numerical, and backpressure tests |

## Lint

Use a standalone lint operation with the actual top and part:

```tcl
synth_design -lint -rtl -top <top> -part <part> -file <report_dir>/lint.rpt
```

## Primitive summary

Run after synthesis:

```tcl
set bram [get_cells -hier -filter {PRIMITIVE_GROUP == BLOCKRAM && PRIMITIVE_SUBGROUP == BRAM}]
set uram [get_cells -hier -filter {PRIMITIVE_GROUP == BLOCKRAM && PRIMITIVE_SUBGROUP == URAM}]
set dsp  [get_cells -hier -filter {PRIMITIVE_GROUP == ARITHMETIC && PRIMITIVE_SUBGROUP == DSP}]
set lat  [get_cells -hier -filter {PRIMITIVE_GROUP == REGISTER && PRIMITIVE_SUBGROUP == LATCH}]
set asr  [get_cells -hier -filter {ASYNC_REG == TRUE}]
list BRAM [llength $bram] URAM [llength $uram] DSP [llength $dsp] LATCH [llength $lat] ASYNC_REG [llength $asr]
```

Compare counts and properties with the design intent. Zero latches is expected unless a latch
is explicitly required. A nonzero BRAM, URAM, DSP, `ASYNC_REG`, or `DONT_TOUCH` count is not
on its own a pass condition.

## Methodology and timing

```tcl
report_control_sets -file <report_dir>/control_sets.rpt
report_clock_networks -file <report_dir>/clock_networks.rpt
report_high_fanout_nets -file <report_dir>/high_fanout.rpt
report_design_analysis -logic_level_distribution -file <report_dir>/logic_levels.rpt
report_exceptions -coverage -file <report_dir>/exceptions_coverage.rpt
report_cdc -details -file <report_dir>/cdc.rpt
report_methodology -file <report_dir>/methodology.rpt
report_timing_summary -file <report_dir>/timing_summary.rpt
```

Pass only when critical findings and mismatches are resolved or documented, required timing
is met, CDC exceptions do not override each other, and the appropriate functional tests pass.
