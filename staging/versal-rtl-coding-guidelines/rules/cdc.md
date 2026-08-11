<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Clock-Domain Crossing Guidelines

Sources: UG949/UG1387 CDC methodology, UG903 timing constraints, and XPM CDC documentation.
Pair this file with [../references/rtl-xdc-pairing.md](../references/rtl-xdc-pairing.md).

## CDC-1 — Synchronize a single-bit level with a recognized structure

Use at least two destination-domain stages and mark the synchronizer registers `ASYNC_REG`.
The first stage must not drive destination logic other than the subsequent synchronizer stage.

```systemverilog
(* ASYNC_REG = "TRUE" *) logic [1:0] sync_ff;

always_ff @(posedge dst_clk)
  sync_ff <= {sync_ff[0], src_level};

assign dst_level = sync_ff[1];
```

Select a point-to-point false path or `set_max_delay -datapath_only` according to whether
latency must be bounded. Do not automatically use one exception for every synchronizer.

## CDC-2 — Use a protocol for multi-bit data

Do not synchronize only a `valid` bit and sample an unrelated unsynchronized bus unless a
complete bundled-data protocol proves the source bus remains stable for the required interval
and acknowledges consumption. A two-flop synchronizer per bit does not preserve word
coherency.

Use one of:

- `xpm_cdc_handshake` for a bounded request/acknowledge transfer;
- `xpm_fifo_async` for streaming or queued data;
- a documented Gray-coded transfer where only one bit changes per update; or
- a complete source-hold/request/acknowledge implementation verified by assertions.

## CDC-3 — Use Gray code only with the matching protocol

Register the Gray value in the source domain, synchronize each Gray bit with an `ASYNC_REG`
chain, and decode only after synchronization. Constrain latency and/or skew according to
UG949/UG903 and verify the constraint is not overridden.

Gray coding prevents multi-bit transitions in the encoded counter; it does not make arbitrary
payload buses safe.

## CDC-4 — Synchronize reset deassertion per destination domain

For asynchronous assertion/synchronous deassertion, use a recognized reset synchronizer for
each destination clock. Do not distribute one synchronized reset across unrelated clocks.
Review recovery/removal and do not automatically false-path the synchronized reset output.

## Verification

```tcl
report_cdc -details -file <report_dir>/cdc.rpt
report_exceptions -coverage -file <report_dir>/exceptions_coverage.rpt
report_methodology -file <report_dir>/methodology.rpt
```

Also verify handshakes, pulse capture, FIFO behavior, reset release, and multi-bit coherency in
simulation or formal analysis.

## Checklist

- [ ] Every crossing is classified as level, pulse, bundled data, Gray bus, handshake, FIFO, or reset.
- [ ] Single-bit synchronizers have at least two stages and `ASYNC_REG`.
- [ ] The first synchronizer stage has no unrelated fanout or combinational logic.
- [ ] Multi-bit transfers use a complete protocol rather than independently synchronized data bits.
- [ ] XPM scoped constraints are preserved.
- [ ] Exceptions are point-to-point where max-delay and false-path requirements coexist.
- [ ] Exception coverage, methodology, CDC, and functional checks pass.
