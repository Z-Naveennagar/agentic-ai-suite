<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Versal Hard-Block Boundary Guidelines

Sources: the generated IP configuration plus the applicable NoC, AI Engine, DDRMC, GT, and
PCIe/CPM product guides. These interfaces vary by device, IP mode, data width, clocking, and
optional channel configuration; do not turn one configuration into a universal rule.

## HB-1 — Honor generated AXI/NoC contracts

Use the generated address map, width, burst, ordering, clock, reset, and QoS requirements.
Never assume fixed NoC or memory latency. Preserve ready/valid backpressure and verify with the
appropriate protocol and traffic tools.

## HB-2 — Match the configured AI Engine PL interface

Use the exact PLIO/stream/window width, clock, framing, and sidebands generated for the graph.
Not every AIE connection uses `TLAST` or `TKEEP`; include them only when the configured
interface contract defines them.

## HB-3 — Use the supported DDRMC/NoC access path

Do not recreate memory-controller behavior in soft RTL. Align bursts and addresses to the
configured interface and test concurrency, backpressure, error responses, and calibration or
reset sequencing.

## HB-4 — Follow the GT wizard/IP user-interface contract

Process parallel data in the documented user clock domain and wait for the required reset-done,
alignment, and link-status signals. PCS/scrambler/gearbox logic can be legitimate on the user
interface; the requirement is to meet the generated latency, clocking, and timing contract,
not a blanket ban on combinational logic.

## HB-5 — Follow the selected PCIe/CPM mode

BAR/configuration, bridge, DMA, and AXI responsibilities depend on the selected CPM/PCIe
subsystem mode. Keep logic in the subsystem only when the generated architecture assigns it
there. Verify tags, ordering, resets, backpressure, errors, and completion behavior.

## Checklist

- [ ] The generated IP configuration is the source of truth for width, clock, reset, and sidebands.
- [ ] No fixed-latency assumption replaces ready/valid behavior.
- [ ] Optional framing signals are required by the configured interface before being mandated.
- [ ] GT/PCIe logic follows the selected wizard/subsystem mode.
- [ ] Protocol and reset-sequencing tests cover backpressure and error cases.
