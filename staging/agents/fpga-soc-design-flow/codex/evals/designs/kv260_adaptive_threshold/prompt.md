<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 adaptive threshold

Create a Vivado 2025.2 KV260 design containing kv260_adaptive_threshold. Each transfer supplies an eight-bit pixel and its independently computed eight-bit local mean. Emit 0xFF when pixel + threshold_offset is strictly greater than the mean, otherwise emit 0x00. The addition must be nine bits so large offsets cannot wrap.

Preserve user and last through a one-entry elastic stage, sustain one transfer per clock, and hold output stable under backpressure. The system-side local-mean generator belongs to platform integration. Use the KV260 PS preset, a 100 MHz PL clock, DMA, VIO and ILA. Use direct RTL, not HLS. Verify equality, underflow-equivalent cases, maximum values, randomized inputs, sidebands and stalls. Generate a bitstream and XSA without programming hardware.
