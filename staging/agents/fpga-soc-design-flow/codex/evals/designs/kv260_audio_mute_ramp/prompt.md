<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 Click-Free Audio Mute Ramp

Create a handwritten SystemVerilog mute ramp named `kv260_audio_mute_ramp`. Maintain an integer gain step from 0 through `RAMP_STEPS` (default 8). For each accepted sample, move the gain one step toward zero when muted or toward full scale when unmuted, then scale the signed 16-bit sample by that new step divided by 8. Input bubbles and output backpressure must freeze the ramp. Reset starts fully unmuted.

Integrate the kernel in Vivado IP Integrator with the KV260 Zynq UltraScale+ MPSoC board preset, a 100 MHz PS-generated PL clock, synchronized active-low reset, and PS-accessible stream/control adapters. Add VIO self-test controls and ILA probes for mute, gain step, input/output samples, handshake, completion, pass, and error status. Produce a validated block design, bitstream, matching LTX, and XSA.

Use handwritten RTL only. Verify monotonic mute and unmute sequences, exact fixed-point samples, bubble/stall state retention, endpoint clamping, and reset. Target `xck26-sfvc784-2LV-c`, board part `xilinx.com:kv260_som:part0:1.4`, with Vivado 2025.2. Do not program hardware.
