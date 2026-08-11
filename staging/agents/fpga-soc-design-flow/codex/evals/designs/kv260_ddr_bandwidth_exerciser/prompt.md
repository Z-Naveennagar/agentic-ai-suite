<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 DDR bandwidth exerciser request kernel

Create a Vivado 2025.2 KV260 design containing
`kv260_ddr_bandwidth_exerciser`. On an accepted idle `start`, emit a bounded
ready/valid request sequence beginning at `base_address`, advancing by
`stride_bytes`, and retaining the requested read/write mode. Count only
accepted requests, hold request fields stable during stalls, pulse `done`
after the final request, and complete a zero-beat campaign immediately.

The public RTL is a deterministic request generator, not a DDR controller or
performance promise. Integrate it using IP Integrator with the KV260 PS preset,
a 100 MHz PL clock, a platform-owned AXI/PS-DMA adapter, and the standard
VIO/System-ILA hardware test shell. DDR calibration, arbitration, physical
bandwidth, cache behavior, and Linux software are outside the deterministic
public-kernel oracle. Use direct RTL, not HLS. Generate a bitstream and XSA
without programming hardware.
