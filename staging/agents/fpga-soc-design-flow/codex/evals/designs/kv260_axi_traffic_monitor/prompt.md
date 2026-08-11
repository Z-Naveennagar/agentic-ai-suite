<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 AXI traffic monitor kernel

Create a Vivado 2025.2 KV260 design containing `kv260_axi_traffic_monitor`.
The public kernel consumes one abstract monitor event per accepted cycle with
read-beat, write-beat, stall, and snapshot flags. Maintain 32-bit cycle,
read-beat, write-beat, and stall counters. A snapshot event must include its
own flags in the emitted values, then clear the accumulation window.

Use a one-entry ready/valid snapshot stage, hold it stable under backpressure,
and stall event input when it cannot advance. Integrate the kernel beside a
platform-owned AXI monitor adapter in the KV260 block design with a 100 MHz PL
clock, JTAG-to-AXI control, and standard VIO/System-ILA instrumentation. Full
AXI protocol observation and bus attachment are outside the deterministic
public oracle. Use direct RTL, not HLS. Verify empty, mixed, consecutive, and
stalled snapshot windows plus output backpressure. Generate a bitstream and
XSA without programming hardware.
