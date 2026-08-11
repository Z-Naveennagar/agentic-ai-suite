<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

Create a KV260 Adaptive SoC design for a byte-wide streaming CRC-32 engine. The public RTL kernel `kv260_crc32_stream` must implement the reflected IEEE CRC-32 polynomial `0xEDB88320`, initialize each frame to `0xFFFFFFFF`, accept one byte per AXI4-Stream transfer, use `TLAST` to end a frame, and publish the final-xor CRC through a valid/ready result channel. It must preserve the result during result-channel backpressure and must not accept a new byte while a completed result is pending.

Use the KV260 board preset for the Zynq UltraScale+ MPSoC PS, generate a 100 MHz PL clock and synchronized active-high PL reset, and integrate the kernel in an IP Integrator block design with an AXI DMA-compatible byte-stream path and appropriate data-width conversion or subset conversion where required. Keep the CRC implementation in handwritten SystemVerilog; do not use HLS.

Provide deterministic cocotb verification including standard CRC vectors, multiple frames, randomized source gaps, and randomized result backpressure. Build and validate the block design in Vivado 2025.2, complete implementation for `xck26-sfvc784-2LV-c`, and produce both a bitstream and exported XSA. No physical board programming is requested.
