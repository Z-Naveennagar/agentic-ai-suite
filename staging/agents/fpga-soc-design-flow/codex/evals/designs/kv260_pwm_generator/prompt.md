<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 PWM Generator

Create a handwritten SystemVerilog PWM kernel for the Kria KV260. Runtime 32-bit period and duty inputs define the waveform. A zero period forces the output low; zero duty is always low; duty greater than or equal to period is always high. New values may take effect at a period boundary. Reset is active-low and synchronous.

Integrate the kernel in Vivado IP Integrator using the Zynq UltraScale+ MPSoC KV260 board preset. Provide a 100 MHz PL clock and synchronized active-low reset from the PS, and connect period/duty control and PWM observation using suitable AXI GPIO or equivalent AXI/IP-integrator interfaces. Produce a validated block design, bitstream, and XSA.

Use handwritten RTL only; do not use HLS. Verify normal duty cycles and the zero/full-scale corner cases. Target `xck26-sfvc784-2LV-c`, board part `xilinx.com:kv260_som:part0:1.4`, with Vivado 2025.2.
