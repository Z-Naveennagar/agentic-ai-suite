<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 Synchronous FIFO

Create a handwritten SystemVerilog synchronous FIFO with 32-bit data and depth 16. Provide registered read data, full and empty flags, and a five-bit occupancy level. A write occurs only when not full and a read only when not empty. Simultaneous accepted read and write preserve occupancy. Reset is active-low and synchronous.

Integrate the FIFO in Vivado IP Integrator using the Zynq UltraScale+ MPSoC KV260 board preset. Supply a 100 MHz PL clock and synchronized active-low reset from the PS. Connect data/control/status through suitable AXI GPIO or equivalent AXI/IP-integrator interfaces. Produce a validated block design, bitstream, and XSA.

Use handwritten RTL only; do not use HLS or a FIFO generator. Verify ordering, boundary flags, rejected overflow/underflow, level accounting, pointer wrap, and simultaneous read/write. Target `xck26-sfvc784-2LV-c`, board part `xilinx.com:kv260_som:part0:1.4`, with Vivado 2025.2.
