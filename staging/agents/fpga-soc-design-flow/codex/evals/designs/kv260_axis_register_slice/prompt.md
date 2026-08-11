<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 AXI4-Stream Elastic Register Slice

Create a handwritten SystemVerilog one-entry elastic AXI4-Stream register slice carrying 32-bit `TDATA` and `TLAST`. It must sustain one transfer per clock with no bubbles when downstream is ready, retain data and `TLAST` unchanged under backpressure, and obey active-low reset.

Integrate the kernel in Vivado IP Integrator using the Zynq UltraScale+ MPSoC KV260 board preset. Supply a 100 MHz PL clock and synchronized active-low reset from the PS. Connect the stream slice between suitable AXI4-Stream source and sink infrastructure, with PS-accessible stimulus/observation paths. Produce a validated block design, bitstream, and XSA.

Use handwritten RTL only; do not use HLS. Verify reset, pass-through throughput, backpressure stability, and `TLAST` alignment. Target `xck26-sfvc784-2LV-c`, board part `xilinx.com:kv260_som:part0:1.4`, with Vivado 2025.2.
