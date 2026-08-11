<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 3x3 binary morphology

Create a Vivado 2025.2 KV260 design containing kv260_morphology_3x3. Each transfer supplies a packed 3x3 binary window. When s_dilate is one, output the OR of all nine bits; otherwise output their AND for erosion. The platform owns line buffering and border padding.

Preserve user and last through a one-entry elastic stage, sustain one window per clock, and hold output stable while stalled. Integrate with the KV260 PS preset, a 100 MHz PL clock, DMA, VIO and ILA. Use RTL, not HLS. Exhaustively verify all 512 windows in both modes with sidebands and randomized backpressure. Generate a bitstream and XSA without programming hardware.
