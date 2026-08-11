<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

Create a KV260 Adaptive SoC design containing a configurable AXI4-Stream fixed-length packetizer. The public handwritten RTL module `kv260_axis_packetizer` passes a 32-bit payload stream from input to output and generates output `TLAST` on every `WORDS_PER_PACKET`th accepted transfer. It must support continuous one-word-per-cycle traffic, propagate backpressure combinationally, keep data and `TLAST` stable while stalled, and reset packet position synchronously.

Use the KV260 Zynq UltraScale+ MPSoC board preset, a 100 MHz PS-generated PL clock, and synchronized active-high reset. Integrate the packetizer in an IP Integrator AXI DMA MM2S-to-S2MM loopback path, with the packetizer defining output packet boundaries. Keep the function in direct RTL, not HLS.

Provide deterministic cocotb tests for default and sustained traffic behavior, boundary stalls, randomized backpressure, and exact packet-boundary generation. Validate and implement the block design in Vivado 2025.2 for `xck26-sfvc784-2LV-c`, then create a bitstream and exported XSA. Do not program the board.
