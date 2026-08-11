<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 image histogram

Create a Vivado 2025.2 KV260 design containing kv260_image_histogram. Count every accepted eight-bit sample into one of sixteen bins selected by bits 7:4. Expose a combinational query port for a selected bin and a running total. Synchronous active-high clear has priority and zeros all bins and the total in one cycle. The input is always ready outside reset and must count one pixel per cycle.

Implement the histogram in synthesizable SystemVerilog and integrate it with the KV260 PS preset, a 100 MHz PL clock, DMA-fed pixels, VIO control and ILA observation. Do not use HLS. Verify clear priority, every bin, repeated hits, total count, and deterministic randomized traffic. Generate a bitstream and XSA without programming the board.
