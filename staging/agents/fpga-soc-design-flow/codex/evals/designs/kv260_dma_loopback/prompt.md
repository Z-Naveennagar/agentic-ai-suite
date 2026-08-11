<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

Create a KV260 Adaptive SoC design for a packet-safe AXI4-Stream transform kernel intended between AXI DMA MM2S and S2MM channels. The public direct-RTL module `kv260_dma_loopback` accepts 32-bit `TDATA`, `TKEEP`, and `TLAST`, transforms every payload word by XOR with configurable `XOR_MASK`, and preserves `TKEEP` and `TLAST`. It must use a one-entry elastic stage, sustain one transfer per cycle, hold all output signals stable under backpressure, and never drop, duplicate, merge, or split packets.

Use the KV260 Zynq UltraScale+ MPSoC board preset, a 100 MHz PS-generated PL clock, synchronized reset, AXI DMA, PS memory-mapped control/data connectivity, and the transform kernel in an IP Integrator MM2S-to-kernel-to-S2MM stream loop. Implement the kernel in handwritten SystemVerilog and do not use HLS.

Provide deterministic cocotb tests with multi-packet traffic, partial final-word `TKEEP`, randomized source gaps, randomized downstream backpressure, and reset flushing. Validate the block design in Vivado 2025.2, implement for `xck26-sfvc784-2LV-c`, and generate both bitstream and exported XSA. Do not program hardware.
