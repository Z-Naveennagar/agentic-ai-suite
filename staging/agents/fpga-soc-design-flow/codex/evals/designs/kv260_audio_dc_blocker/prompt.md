<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 Audio DC Blocker

Create a handwritten SystemVerilog first-order audio DC blocker named `kv260_audio_dc_blocker`. For each accepted signed 16-bit sample, compute `y[n] = x[n] - x[n-1] + ((15 * y[n-1]) >>> 4)` with a signed 24-bit internal state and saturate the published output to signed 16-bit range. Update state only on accepted input. Use a one-entry elastic ready/valid output, and clear both histories on reset.

Integrate the kernel in Vivado IP Integrator with the KV260 Zynq UltraScale+ MPSoC board preset, a 100 MHz PS-generated PL clock, synchronized active-low reset, and DMA-compatible streaming adapters. Include VIO self-test controls and ILA probes for input/output samples, state progression, handshakes, completion, pass, and error status. Produce a validated block design, bitstream, matching LTX, and XSA.

Use handwritten RTL only. Verify constant-input decay, step response, positive and negative saturation, bubbles, backpressure state retention, seeded exact-model agreement, and reset. Target `xck26-sfvc784-2LV-c`, board part `xilinx.com:kv260_som:part0:1.4`, with Vivado 2025.2. Do not program hardware.
