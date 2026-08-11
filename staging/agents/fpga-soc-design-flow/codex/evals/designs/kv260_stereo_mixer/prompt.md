<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 Stereo-to-Mono Mixer

Create a handwritten SystemVerilog streaming stereo mixer named `kv260_stereo_mixer`. For every accepted signed 16-bit left/right pair, compute the exact arithmetic average `(left + right) >>> 1` using a 17-bit intermediate and emit one signed 16-bit mono sample. Implement a one-entry ready/valid elastic output that sustains one pair per clock and remains stable under backpressure.

Integrate the kernel in Vivado IP Integrator with the KV260 Zynq UltraScale+ MPSoC board preset, a 100 MHz PS-generated PL clock, synchronized active-low reset, and PS-accessible streaming infrastructure. Include VIO start/reset/enable controls and ILA observation of stereo inputs, mono output, handshakes, completion, pass, and error status. Produce a validated block design, bitstream, matching LTX, and XSA.

Use handwritten RTL only. Verify same-sign extremes, opposite-sign rounding, randomized signed samples, sustained throughput, backpressure stability, and reset. Target `xck26-sfvc784-2LV-c`, board part `xilinx.com:kv260_som:part0:1.4`, with Vivado 2025.2. Do not program hardware.
