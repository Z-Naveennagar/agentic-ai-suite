<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# RF and Wide-Datapath Guidelines

Sources: the applicable RF Data Converter product guide and UG949/UG1387 timing methodology.
The RFdc stream width, sample packing, I/Q order, and flow-control behavior depend on IP
configuration; obtain them from the generated IP interface contract.

## RF-1 — Consume the complete configured transfer

Decode every configured sample lane with explicit width, signedness, and ordering. Advance
state only on the interface's actual transfer event. For a standard backpressured AXI stream,
that event is `TVALID && TREADY`; if a configured RFdc interface does not permit arbitrary
backpressure, insert the required buffering and follow its product-guide rules.

## RF-2 — Keep I/Q and metadata latency identical

Pipeline I, Q, valid, channel ID, timestamps, and framing through identical elastic stages.
Test lane order, sign extension, decimation/interpolation modes, and reset/startup alignment.

## RF-3 — Treat wide-bus fanout as measured implementation data

A 1024-bit bus or one shared enable is not automatically a violation. Pipeline according to
logic depth and placement, then use `report_high_fanout_nets`, timing, congestion, and physical
optimization reports. Apply `max_fanout` or manual replication only with a measured reason.

## RF-4 — Use supported buffering for rate or width conversion

Use an elastic buffer, sync FIFO, or async FIFO according to whether clock domains differ.
Define packing order and overflow/underflow behavior. Preserve XPM/IP constraints and test
continuous traffic plus worst-case backpressure/rate mismatch.

## Checklist

- [ ] Stream width and lane order match the generated RFdc configuration.
- [ ] State advances on the actual transfer contract.
- [ ] I/Q and metadata remain cycle-aligned.
- [ ] Fanout/logic-depth changes are report-driven.
- [ ] Gearbox/FIFO rate, reset, and overflow behavior are tested.
