<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 PL Counter

Create a handwritten SystemVerilog 32-bit counter kernel for the Kria KV260. The counter increments on each enabled clock, clears synchronously, wraps to zero at a configurable terminal value, and emits a one-clock terminal pulse on the wrapping cycle. Reset is active-low and synchronous.

Integrate the kernel in Vivado IP Integrator using the Zynq UltraScale+ MPSoC KV260 board preset. Source a 100 MHz PL clock and synchronized active-low PL reset from the PS. Make the control and status signals accessible through suitable AXI GPIO or equivalent AXI/IP-integrator connections. Produce a validated block design, bitstream, and XSA.

Use handwritten RTL only; do not use HLS. Verify reset, enable hold, clear priority, incrementing, terminal wrap, and pulse width. Target `xck26-sfvc784-2LV-c`, board part `xilinx.com:kv260_som:part0:1.4`, with Vivado 2025.2.
