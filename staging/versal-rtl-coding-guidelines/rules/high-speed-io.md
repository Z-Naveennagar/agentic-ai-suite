<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# High-Speed I/O Datapath Guidelines

Sources: the configured JESD204, Aurora, SDI, Interlaken, GT, or other link product guide.
Alignment, gearbox, lane deskew, and status semantics are protocol/IP specific.

## HSIO-1 — Consume the IP's defined aligned interface

Hold downstream traffic until the IP reports the required reset/alignment/link-ready state.
Do not add a second generic alignment barrel after an output that the configured IP already
presents as aligned. Add soft alignment only when the product guide assigns that function to
user logic.

## HSIO-2 — Cross clock/rate boundaries with supported elastic storage

Use the IP's elastic buffer or a correctly configured sync/async FIFO. Define reset order,
clock tolerance, overflow/underflow, and clock-correction behavior. Preserve scoped CDC
constraints.

## HSIO-3 — Define gearbox ordering and framing

Specify bit/byte/lane order, valid-byte semantics, block boundaries, and slip behavior. Verify
continuous traffic, partial blocks, pauses, reset, and loss/reacquisition of alignment.

## HSIO-4 — Deskew lanes before combining them

Use the protocol/IP lane alignment mechanism and combine lanes only after every required lane
is ready. Test injected per-lane skew, lane loss, recovery, and metadata alignment.

## Checklist

- [ ] User logic consumes the exact aligned/unaligned interface defined by the IP configuration.
- [ ] Elastic storage matches the clock and rate relationship.
- [ ] Gearbox bit/lane order and framing are explicitly tested.
- [ ] Lane combination waits for the documented deskew/readiness condition.
- [ ] Reset, link loss, and reacquisition behavior are verified.
