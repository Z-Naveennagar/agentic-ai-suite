<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

Create a KV260 Adaptive SoC design with a 32-bit, depth-16 asynchronous FIFO implemented in handwritten SystemVerilog. The public module `kv260_async_fifo` has independent write and read clocks and resets, binary storage addresses, Gray-coded clock-domain-crossing pointers, two-flop pointer synchronizers, full/empty protection, and registered read data. Accepted writes and reads must be ordered exactly, with no overflow or underflow.

Use the KV260 Zynq UltraScale+ MPSoC board preset. In IP Integrator, generate a 100 MHz PL clock/reset domain and a distinct secondary PL clock/reset domain, and integrate the FIFO as the explicit CDC boundary. The PS preset, reset controllers, and clocking must be represented in the block design. Do not use HLS and do not substitute a catalog FIFO for the required public RTL module.

Provide deterministic cocotb verification with unrelated clock periods, wraparound, full/empty boundary checks, randomized write/read activity, and an ordered scoreboard. Build and validate the block design with Vivado 2025.2, complete implementation for `xck26-sfvc784-2LV-c`, and produce a bitstream and XSA. No board programming is requested.
