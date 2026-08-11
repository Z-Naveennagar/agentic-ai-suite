<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 streaming 2x video downscaler

Create a Vivado 2025.2 project for the Kria KV260 (`xck26-sfvc784-2LV-c`,
board part `xilinx.com:kv260_som:part0:1.4`). Apply the PS board preset and
build a valid IP Integrator video path around a handwritten SystemVerilog
2x nearest-neighbor downscaler.

The kernel consumes AXI4-Stream RGB888 and emits pixels at even input X and
even input Y coordinates. Runtime `input_width` is always at least two and
defines output line termination. Preserve frame semantics by asserting
output `TUSER[0]` on the first retained frame pixel and output `TLAST` on the
final retained pixel of each retained line. Correctly absorb discarded
pixels, propagate backpressure for retained pixels, and never reorder or
duplicate output. Use a 100 MHz PS-derived clock, AXI VDMA or Video Frame
Buffer IP to/from PS DDR, AXI4-Stream connectivity, and proper resets. Do
not use HLS for the scaler.

Independently verify even and odd line widths, frame/line sidebands,
coordinate selection, and randomized downstream stalls. Validate the block
design, synthesize, implement, generate a bitstream, and export a
bitstream-bearing XSA. Hidden simulation tests only the custom kernel.
