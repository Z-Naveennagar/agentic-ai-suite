<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 RGB-to-grayscale video kernel

Create a Vivado 2025.2 project for the Kria KV260 (`xck26-sfvc784-2LV-c`,
board part `xilinx.com:kv260_som:part0:1.4`). Apply the Zynq UltraScale+
MPSoC/PS board preset and build a valid IP Integrator block design around a
handwritten SystemVerilog AXI4-Stream RGB888-to-gray8 kernel.

The kernel must use the integer BT.601 approximation
`Y = (77*R + 150*G + 29*B + 128) >> 8`, sustain one pixel per clock when not
backpressured, hold all output signals stable while stalled, and preserve
SOF in `TUSER[0]` and end-of-line in `TLAST`. Use a 100 MHz PL/control clock
from the PS, AXI DMA to exercise the stream path from PS DDR, and appropriate
clock/reset and AXI interconnect IP. Do not use HLS for the custom kernel.

Independently verify arithmetic, sideband alignment, and randomized
backpressure. Validate the block design, synthesize, implement, generate a
bitstream, and export an XSA with the bitstream included. No physical board or
video source is required for regression.
