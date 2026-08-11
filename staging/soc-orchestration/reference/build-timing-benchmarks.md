<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Build Timing Benchmarks

Reference data for setting `block_until_ms` timeouts and user expectations during
Phase 4 implementation. All numbers are from actual builds on AMD 2025.x tools.

## Vivado Build Durations

| Design Type | Synth Time | Impl Time | Notes |
|-------------|-----------|-----------|-------|
| PL-only (tiny, e.g., blinky counter) | ~20s | ~45s | Minimal design |
| PL-only OOC (medium, e.g., FOC motor) | ~24s | — | OOC synth, no I/O placement |
| PS+PL (timer + IRQ) | ~400s (7 OOC) | ~75s | WNS=6.8ns |
| PS+PL (DMA loopback, 3-master HP) | ~403s (12 OOC) | ~74s | WNS=6.2ns |
| PS+PL (dual-clock video TPG+VDMA+CDC) | ~517s (14 OOC) | ~84s | WNS=1.5ns |
| PS+PL (DPU/complex) | ~10-20min | ~20-40min | Large designs |

## Vitis v++ Link Durations

| Flow | Duration | Breakdown |
|------|----------|-----------|
| Zynq US+ (DPUCZDX8G B512 + 4K video, KV260) | ~25-40min | system_link + VPL synth+impl |
| Versal (AIE+HLS, VCK190 base) | ~15min total | AIE compile ~180s, HLS ~60s, v++ link ~867s (system_link 10s + VPL 857s) |

Post-link QoR from Versal build: WNS=0.132ns, WHS=0.014ns.

## DSP-Heavy Design Observations

DSP-heavy designs (motor control, signal processing) have critical paths through
DSP48E2 cascades (11+ logic levels). At 100MHz this gives ~5ns slack, suggesting
these designs could be pushed to ~200MHz with pipeline register insertion.

Example: FOC current loop — 316 LUTs, 170 FFs, 15 DSPs, 0 BRAMs (very efficient).

## Deployment Artifact Generation

Kria deployment artifacts (bit.bin, dtbo, shell.json): ~2 minutes after v++ link.
