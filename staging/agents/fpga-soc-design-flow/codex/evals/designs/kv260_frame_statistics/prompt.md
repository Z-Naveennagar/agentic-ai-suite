<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 frame statistics accumulator

Create a Vivado 2025.2 KV260 design containing `kv260_frame_statistics`.
Accepted 8-bit samples carry explicit frame-first and frame-last flags. Emit
one result per frame containing the minimum, maximum, integer-truncated mean,
and sample count. Frame-first discards prior partial state before including
that same sample; frame-last includes that same sample in the result.

Hold the one-entry result stage stable under backpressure and stall input when
the result stage cannot advance. Integrate with the KV260 PS preset, a 100 MHz
PL clock, deterministic DMA-fed samples, and standard VIO/ILA hardware-test
instrumentation. Physical camera capture and live scene interpretation remain
outside the public-kernel oracle. Use direct RTL, not HLS. Verify singleton,
constant, ramp, boundary-valued, consecutive frames, and output stalls.
Generate a bitstream and XSA without programming hardware.
