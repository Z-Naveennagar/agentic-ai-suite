<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

Create a KV260 Adaptive SoC design containing a bounded, directly verifiable streaming 3x3 Sobel kernel. The public handwritten RTL module `kv260_sobel_filter` accepts one packed 3x3 window of unsigned 8-bit pixels per transfer, ordered row-major with the top-left pixel in bits `[7:0]`. It also accepts `line_start`, `line_end`, and `border`. For non-border windows compute signed Sobel `Gx` and `Gy`, output `min(255, abs(Gx)+abs(Gy))`, and preserve the line-control signals. For `border=1`, output exactly zero. Use a one-entry elastic pipeline that remains stable under output backpressure and can sustain one window per cycle.

Use the KV260 Zynq UltraScale+ MPSoC board preset, a 100 MHz PS-generated PL clock, synchronized reset, and an IP Integrator data path suitable for DMA-fed packed windows and returned results. The bounded public kernel deliberately excludes line buffering so its functional contract is independent and practical for cocotb; any system-side packing adapter belongs to platform integration. Do not use HLS.

Provide deterministic cocotb verification with constant, horizontal-edge, vertical-edge, diagonal/random windows, saturation, border behavior, line-control preservation, and randomized backpressure. Validate the block design with Vivado 2025.2, implement for `xck26-sfvc784-2LV-c`, and generate a bitstream and exported XSA. Do not program the board.
