<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Packet-Processing Guidelines

Sources: UG1037/AMBA AXI4-Stream behavior and the applicable Ethernet/MRMAC/CMAC/Vitis
networking product guides.

## PKT-1 — Treat packet metadata as part of the beat

Capture and propagate `TDATA`, `TKEEP`, `TLAST`, and all applicable sidebands together on a
ready/valid handshake. Hold them stable during backpressure and test partial final beats.

## PKT-2 — Pipeline parsing with explicit stage records

Define a typed record or explicit signal bundle for each parser stage. Register both the beat
and derived metadata under the same elastic-stage enable. Do not use undeclared placeholders
such as `s1_data` or `{meta_pipe}` in a golden example.

For each stage, specify byte order, header offset, validity, truncation/error behavior, and
latency. Test VLAN/options/extension headers or reject them explicitly.

## PKT-3 — Map lookup storage according to access semantics

Use BRAM/UltraRAM for supported synchronous tables and CAM/hash IP or a documented architecture
where associative behavior is required. A wide equality tree or a `ram_style` attribute does
not guarantee the intended hardware. Verify collision, update, and miss behavior.

## PKT-4 — Keep edits, length, and checksums consistent

When inserting/removing headers, pipeline shift/merge logic and update `TKEEP`, `TLAST`, length,
checksums, and metadata under the same handshake. Test minimum/maximum packets, partial beats,
backpressure at each edit boundary, and malformed inputs.

## Checklist

- [ ] Payload and all sidebands advance atomically.
- [ ] Parser stages use declared, compilable metadata bundles.
- [ ] Table architecture matches required lookup/update semantics.
- [ ] Header edits update framing, length, and checksums coherently.
- [ ] Randomized-backpressure and packet-corner-case tests pass.
