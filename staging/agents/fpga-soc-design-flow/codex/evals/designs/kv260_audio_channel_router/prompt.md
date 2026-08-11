<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 Audio Channel Router

Create a handwritten SystemVerilog stereo channel router named `kv260_audio_channel_router`. On each accepted pair, route according to `route_select`: `0` passes left/right, `1` swaps them, `2` copies left to both outputs, and `3` copies right to both outputs. Preserve all signed 16-bit patterns exactly. Implement a one-entry elastic ready/valid output that sustains one pair per clock and remains stable under backpressure.

Integrate the kernel in Vivado IP Integrator with the KV260 Zynq UltraScale+ MPSoC board preset, a 100 MHz PS-generated PL clock, synchronized active-low reset, and PS-accessible stream/control paths. Include VIO self-test controls and ILA probes for route selection, both input and output channels, handshakes, completion, pass, and error status. Produce a validated block design, bitstream, matching LTX, and XSA.

Use handwritten RTL only. Verify all four modes, signed bit-pattern preservation, full-rate mode changes, backpressure stability, and reset. Target `xck26-sfvc784-2LV-c`, board part `xilinx.com:kv260_som:part0:1.4`, with Vivado 2025.2. Do not program hardware.
