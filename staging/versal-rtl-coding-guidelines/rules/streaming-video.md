<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Streaming Video Guidelines

Sources: UG1037/AMBA AXI4-Stream behavior and the applicable AMD Video IP product guides.

## VID-1 — Keep framing with each accepted beat

Define the configured meaning of SOF/EOL and propagate `TUSER`, `TLAST`, `TKEEP`, and pixel
payload only on `TVALID && TREADY`. Hold the complete beat stable while stalled.

## VID-2 — Infer line/frame buffers with supported memory templates

Use synchronous BRAM/UltraRAM access, explicit collision semantics, and a latency model that
keeps pixel coordinates and framing aligned. Do not reset the memory array; reset or flush
control/valid state as required.

## VID-3 — Make every pixel stage elastic

A pipeline that updates all registers only from final `m_tready` is not automatically
protocol-safe. Carry a valid bit per stage and advance each stage from its own readiness, or
use a verified AXI Register Slice/FIFO. Express `use_dsp` on real arithmetic objects only;
ellipses are pseudocode, not a golden implementation.

Verify with randomized backpressure, frame-boundary corner cases, and no loss/duplication.

## VID-4 — Cross video clocks with an async FIFO

Use a supported async FIFO or Video Clock Converter structure. Preserve its scoped constraints
and verify reset sequencing, overflow/underflow, SOF/EOL alignment, and rate mismatch.

## Checklist

- [ ] Every accepted beat keeps payload and framing aligned.
- [ ] Line/frame buffers use supported synchronous memory behavior.
- [ ] Every pipeline stage has correct local valid/readiness behavior.
- [ ] Clock crossings use a supported async structure and non-conflicting XDC.
- [ ] Randomized-backpressure and frame-boundary tests pass.
