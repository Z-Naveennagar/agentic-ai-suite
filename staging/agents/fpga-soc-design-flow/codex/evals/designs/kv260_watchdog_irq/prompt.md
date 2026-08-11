<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 Watchdog Interrupt

Create a handwritten SystemVerilog reloadable watchdog kernel. While enabled and armed, it counts down from a runtime 32-bit timeout. Expiry emits exactly one interrupt clock and sets a sticky expiry flag. Reload restarts and rearms the watchdog; a separate clear removes the sticky flag. Reset is active-low and synchronous.

Integrate the kernel in Vivado IP Integrator using the Zynq UltraScale+ MPSoC KV260 board preset. Supply a 100 MHz PL clock and synchronized active-low reset from the PS. Expose timeout, enable, reload, and clear through an AXI-controlled interface and connect the interrupt to a PS PL-to-PS IRQ input. Produce a validated block design, bitstream, and XSA.

Use handwritten RTL only; do not use HLS. Verify reload, disabled hold, exact expiry latency, one-cycle IRQ, sticky behavior, clear, and rearming. Target `xck26-sfvc784-2LV-c`, board part `xilinx.com:kv260_som:part0:1.4`, with Vivado 2025.2.
