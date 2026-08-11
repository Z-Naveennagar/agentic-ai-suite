<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Reset Guidelines

Sources: UG1387/UG949 reset methodology and UG901 register coding techniques.

## RST-1 — Choose reset behavior by resource and function

AMD generally recommends synchronous resets because they give synthesis more flexibility and
can improve packing and QoR. Versal registers can support synchronous and asynchronous reset
behavior; do not claim only one is native. Use asynchronous reset only where the architecture
requires it, and keep reset behavior compatible across registers intended to pack into one
DSP, RAM, or pipeline structure.

## RST-2 — Give reset the intended precedence

When reset must override a clock enable, code reset first so the HDL matches the register
control priority:

```systemverilog
always_ff @(posedge clk) begin
  if (rst)
    q <= '0;
  else if (ce)
    q <= d;
end
```

Verify control sets and surrounding logic with `report_control_sets` and netlist inspection;
`CONTROL_SETS` is not a general per-cell property.

## RST-3 — Reset control state, not every datapath bit

Reset registers whose initial value controls behavior: FSM state, valid flags, protocol state,
and supervisory counters. Wide datapath pipelines can remain unreset when valid/flush logic
prevents stale data from being consumed. Removing reset can permit SRL, DSP, or RAM packing,
but only when the behavioral contract remains correct.

## RST-4 — Keep controls compatible within a packing group

No single register primitive provides every combination of set, reset, enable, polarity, and
clock edge. Avoid describing both set and reset on one register when the desired behavior can
be expressed through data logic. Keep control polarity and clock edge consistent within a
pipeline, packing group, or clock domain. Do not require one polarity and one edge across an
entire multi-domain design.

## RST-5 — Synchronize asynchronous deassertion per clock domain

When asynchronous assertion is required, use a recognized asynchronous-assert/synchronous-
deassert reset synchronizer for each destination clock. Review recovery/removal and companion
constraints according to UG903/UG949; do not automatically false-path the synchronized reset
output.

```systemverilog
(* ASYNC_REG = "TRUE" *) logic [1:0] rst_pipe;
always_ff @(posedge clk or posedge arst) begin
  if (arst)
    rst_pipe <= 2'b11;
  else
    rst_pipe <= {rst_pipe[0], 1'b0};
end
assign rst = rst_pipe[1];
```

## Verification

```tcl
report_control_sets -file <report_dir>/control_sets.rpt
report_methodology -file <report_dir>/methodology.rpt
report_cdc -details -file <report_dir>/cdc.rpt
```

Also simulate reset assertion/deassertion, clock startup, valid flushing, and first legal
transactions.

## Checklist

- [ ] Reset type and polarity are justified per domain/resource.
- [ ] Reset precedence matches the intended clock-enable behavior.
- [ ] Pure datapath registers are reset only when functionally required.
- [ ] Controls are compatible within each packing group.
- [ ] Every asynchronous reset deasserts synchronously in each destination domain.
- [ ] Reset behavior is verified functionally as well as structurally.
