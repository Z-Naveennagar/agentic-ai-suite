<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 temporal motion detector

Create a Vivado 2025.2 KV260 design containing `kv260_motion_detector`. The
public RTL kernel accepts paired current-frame and reference-frame 8-bit
pixels. For every accepted pair, compute the unsigned absolute difference and
assert `m_motion` when the difference is greater than or equal to the supplied
threshold. Preserve `user` and `last`.

Implement a one-entry ready/valid output stage. Hold all output fields stable
under backpressure and stall input only when that stage cannot advance.
Integrate the kernel with the KV260 PS preset, a 100 MHz PL clock, a
DMA-backed synthetic paired-frame source, and the standard VIO/ILA hardware
test shell. Physical AR1335/AP1302 capture and frame-buffer management are
platform work and are outside the deterministic public-kernel oracle. Use
direct RTL, not HLS. Verify threshold boundaries, absolute-difference
direction, metadata preservation, bubbles, and output stalls. Generate a
bitstream and XSA without programming hardware.
