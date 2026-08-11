<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 framebuffer stream packing path

Create a Vivado 2025.2 project for the Kria KV260 (`xck26-sfvc784-2LV-c`,
board part `xilinx.com:kv260_som:part0:1.4`). Apply the PS board preset and
build a valid IP Integrator framebuffer path between video streams and PS
DDR.

Author a handwritten SystemVerilog dual-channel kernel. Its capture channel
packs RGB888 into 32-bit XRGB8888 (`0x00RRGGBB`) with all four `TKEEP` bits
set before framebuffer/VDMA writes. Its independent display channel unpacks
the low 24 RGB bits from 32-bit DDR words. Both channels must preserve
`TUSER[0]` SOF and `TLAST` end-of-line, sustain one word per clock, and obey
independent backpressure without cross-coupling. Use a 100 MHz PS-derived
control clock, AXI VDMA or Video Frame Buffer Read/Write IP as available,
AXI SmartConnect, DDR access through the PS, and suitable clock/reset IP.
Do not use HLS for the custom kernel.

Independently verify both directions concurrently, pixel ordering,
sidebands, and unrelated randomized stalls. Validate the block design,
synthesize, implement, generate a bitstream, and export an XSA containing
the bitstream. External memory traffic is not required in hidden simulation.
