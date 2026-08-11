<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 Debouncer and Edge Counter

Create a handwritten SystemVerilog kernel that synchronizes a noisy single-bit input, accepts a new state only after it remains stable for a configurable number of clocks, emits a one-cycle pulse for each accepted rising edge, and counts accepted rising edges in a 32-bit counter. Reset is active-low and synchronous.

Integrate the kernel in Vivado IP Integrator using the Zynq UltraScale+ MPSoC KV260 board preset. Supply a 100 MHz PL clock and synchronized active-low reset from the PS. Connect the input, debounced state, pulse, and count through suitable AXI GPIO or equivalent AXI/IP-integrator interfaces. Produce a validated block design, bitstream, and XSA.

Use handwritten RTL only; do not use HLS. Verify short glitches are rejected, stable transitions are accepted once, and falling transitions do not increment the count. Target `xck26-sfvc784-2LV-c`, board part `xilinx.com:kv260_som:part0:1.4`, with Vivado 2025.2.
