<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 Saturating Audio Gain

Create a handwritten SystemVerilog streaming audio gain kernel named `kv260_audio_gain`. Each accepted signed 16-bit sample is multiplied by unsigned Q2.14 `gain_q14`, arithmetic-shifted right by 14, and saturated to signed 16-bit range. Implement a one-entry ready/valid elastic output that holds data stable under backpressure and clears validity on active-low reset.

Integrate the kernel in Vivado IP Integrator with the KV260 Zynq UltraScale+ MPSoC board preset, a 100 MHz PS-generated PL clock, synchronized active-low reset, and PS-accessible AXI4-Stream/control adapters. Include a VIO-controlled deterministic self-test and ILA probes for input/output handshakes, samples, saturation cases, completion, pass, and error status. Produce a validated block design, bitstream, matching LTX, and XSA.

Use handwritten RTL only. Verify zero, half, unity, and greater-than-unity gain, positive and negative saturation, randomized exact-model agreement, reset, and backpressure. Target `xck26-sfvc784-2LV-c`, board part `xilinx.com:kv260_som:part0:1.4`, with Vivado 2025.2. Do not program hardware.
