<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 Bayer demosaic kernel

Create a Vivado 2025.2 KV260 design containing kv260_bayer_demosaic. Each accepted transfer supplies a packed row-major 3x3 window of eight-bit Bayer samples, top-left in bits 7:0, plus the center-pixel phase: 0=R, 1=G on an R row, 2=G on a B row, 3=B. Compute a bilinear RGB888 result. At R or B centers, interpolate G from the four axial neighbors and the opposite color from four corners. At G centers, interpolate the missing colors from the appropriate horizontal or vertical pair. Use truncating integer averages.

Preserve user and last through a one-entry elastic stage and remain stable under backpressure. Integrate with the KV260 PS, 100 MHz PL clock, DMA, VIO and ILA. Use RTL, not HLS. Verify all phases, boundaries, randomized windows, sidebands, and stalls. Generate a bitstream and XSA without programming hardware.
