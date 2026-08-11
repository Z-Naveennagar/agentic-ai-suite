<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

Create a KV260 Adaptive SoC design containing a single-clock, 32-bit, true-dual-port scratchpad memory with 256 words. The public handwritten RTL module `kv260_bram_scratchpad` exposes two symmetric ports, four byte write enables per port, and registered read data. Reads are read-first: on a write cycle each port returns the pre-write word. If both ports write the same byte of the same address in one cycle, port B deterministically wins for the overlapping byte; non-overlapping byte writes from both ports are combined.

Use the KV260 Zynq UltraScale+ MPSoC board preset, a 100 MHz PS-generated PL clock, and synchronized active-high reset. Integrate the scratchpad in IP Integrator with appropriate AXI BRAM-controller or RTL adapter connectivity so PS software can exercise the memory while retaining the required public dual-port RTL component. Use direct RTL and BRAM inference; do not use HLS.

Provide deterministic cocotb verification for byte lanes, independent ports, read-first behavior, same-address non-overlapping writes, port-B collision priority, and randomized model comparison. Build and validate in Vivado 2025.2, implement for `xck26-sfvc784-2LV-c`, and generate a bitstream and XSA. No board programming is requested.
