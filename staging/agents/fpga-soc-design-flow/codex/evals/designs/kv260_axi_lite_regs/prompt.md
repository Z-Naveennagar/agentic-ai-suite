<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 AXI4-Lite Register Bank

Create a handwritten SystemVerilog AXI4-Lite subordinate implementing four 32-bit read/write registers. Support independently arriving address and data channels, one outstanding write response, one outstanding read response, and byte write strobes. Invalid or unaligned addresses return `SLVERR`; valid accesses return `OKAY`. Reset is active-low.

Integrate this RTL IP in Vivado IP Integrator using the Zynq UltraScale+ MPSoC KV260 board preset. Drive it from a 100 MHz PS PL clock and synchronized active-low reset, and connect its AXI4-Lite interface to a PS master through SmartConnect or equivalent. Assign an address segment and produce a validated block design, bitstream, and XSA.

Use handwritten RTL only; do not use HLS. Verify independent AW/W ordering, byte strobes, reads, backpressure, and error responses. Target `xck26-sfvc784-2LV-c`, board part `xilinx.com:kv260_som:part0:1.4`, with Vivado 2025.2.
