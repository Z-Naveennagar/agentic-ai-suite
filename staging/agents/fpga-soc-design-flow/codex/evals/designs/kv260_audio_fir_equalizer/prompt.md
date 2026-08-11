<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 Audio FIR Equalizer

Create a handwritten SystemVerilog five-tap signed audio FIR kernel named `kv260_audio_fir_equalizer`. Use fixed symmetric coefficients `[1, 2, 3, 2, 1]`, accept signed 16-bit samples through ready/valid, and emit the exact signed 20-bit convolution result. Shift history only for accepted samples, so input bubbles do not change the filter state. Use a one-entry elastic output that holds result and filter state under backpressure.

Integrate the kernel in Vivado IP Integrator with the KV260 Zynq UltraScale+ MPSoC board preset, a 100 MHz PS-generated PL clock, synchronized active-low reset, and DMA-compatible stream adapters. Include a VIO-controlled deterministic self-test shell and ILA probes for samples, handshakes, convolution output, completion, pass, and error status. Produce a validated block design, bitstream, matching LTX, and XSA.

Use handwritten RTL only; do not use HLS. Verify impulse response, signed extremes, bubbles, reset/history clearing, backpressure, and seeded model comparison. Target `xck26-sfvc784-2LV-c`, board part `xilinx.com:kv260_som:part0:1.4`, with Vivado 2025.2. Do not program hardware.
