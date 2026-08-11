<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 MIPI capture preprocessing kernel

Create a Vivado 2025.2 project for the Kria KV260 (`xck26-sfvc784-2LV-c`,
board part `xilinx.com:kv260_som:part0:1.4`). Apply the PS board preset and
construct a valid IP Integrator MIPI CSI-2 capture path.

Author a handwritten SystemVerilog raw Bayer8 preprocessing kernel. Clamp
each sample by `max(sample - BLACK_LEVEL, 0)`, buffer one line, and produce
one 8-bit luma sample per 2x2 Bayer block as the rounded-down average of its
four clamped samples. Inputs have even runtime width not exceeding
`MAX_WIDTH`. Emit SOF on the first produced block and TLAST on the last block
of each produced line. The AXI4-Stream path must be stable under
backpressure.

Integrate the kernel with MIPI CSI-2 Receiver Subsystem and appropriate
D-PHY/video format conversion IP, AXI VDMA or Video Frame Buffer Write into
PS DDR, a 100 MHz PS-derived control clock, AXI control connectivity, and
resets. Isolate unavailable physical sensor pins from regression and do not
require a camera. Do not use HLS for the custom kernel.

Independently verify clamp saturation, 2x2 averaging, sidebands, and stalls.
Validate the block design, synthesize, implement, generate a bitstream, and
export an XSA with the bitstream.
