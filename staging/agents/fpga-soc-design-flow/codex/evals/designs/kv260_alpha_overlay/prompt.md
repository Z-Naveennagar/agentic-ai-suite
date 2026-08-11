<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 alpha overlay

Create a Vivado 2025.2 KV260 design containing kv260_alpha_overlay. Each transfer carries foreground RGB888, background RGB888 and an eight-bit foreground alpha. For every color channel compute (alpha*foreground + (255-alpha)*background + 127)/255 using unsigned arithmetic. Preserve user and last.

Use a one-entry elastic stage, sustain one pixel per clock, and hold all output fields stable during stalls. Integrate through the KV260 PS preset with a 100 MHz PL clock, DMA-fed streams, VIO and ILA. Use RTL, not HLS. Verify alpha 0 and 255, rounding, primary colors, randomized pixels, sidebands and backpressure. Generate a bitstream and XSA without programming hardware.
