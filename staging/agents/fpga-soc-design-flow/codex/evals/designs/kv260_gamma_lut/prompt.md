<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 gamma lookup transform

Create a Vivado 2025.2 KV260 design containing kv260_gamma_lut. Map each accepted eight-bit sample through the deterministic gamma-2 table function y=(x*x+255)>>8. This exact integer function defines all 256 table entries and produces an eight-bit result. Preserve user and last.

Implement the table transform as synthesizable RTL behind a one-entry elastic stage. Sustain one sample per clock and remain stable under backpressure. Integrate with the KV260 PS preset, 100 MHz PL clock, DMA, VIO and ILA. Do not use HLS. Verify all 256 input codes, sidebands, bubbles and stalls. Generate a bitstream and XSA without programming hardware.
