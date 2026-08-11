<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 color-correction matrix

Create a KV260 Vivado 2025.2 design containing kv260_color_correction. For each RGB888 transfer apply the signed Q1.7 matrix R'=(144R-16G+64)>>7, G'=(-8R+136G+64)>>7, B'=(-16G+144B+64)>>7, saturating each result to 0 through 255. Preserve user and last.

The RTL must use a one-entry elastic stage, sustain one pixel per clock, and hold output stable while stalled. Integrate through the KV260 PS preset with a 100 MHz PL clock, DMA stimulus, VIO and ILA. Do not use HLS. Verify identity-adjacent colors, clipping, randomized RGB values, sidebands and backpressure. Generate a bitstream and XSA without programming the board.
