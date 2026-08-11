<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 Audio Tone Generator

Create a handwritten SystemVerilog phase-accumulator square-wave generator named `kv260_audio_tone_generator`. Each accepted output beat emits positive `amplitude` while phase bit 31 is zero and negative `amplitude` while it is one, then advances the 32-bit phase by `phase_increment`. The ready/valid output must hold phase and data under backpressure. Disabling or resetting clears phase, validity, and output so re-enable starts deterministically at positive amplitude.

Integrate the kernel in Vivado IP Integrator with the KV260 Zynq UltraScale+ MPSoC board preset, a 100 MHz PS-generated PL clock, synchronized active-low reset, AXI-accessible configuration, and stream sink infrastructure. Include VIO self-test controls and ILA probes for phase cadence, output sample, handshake, completion, pass, and error status. Produce a validated block design, bitstream, matching LTX, and XSA.

Use handwritten RTL only. Verify exact phase cadence, polarity, amplitude, backpressure phase hold, deterministic re-enable, and reset. Target `xck26-sfvc784-2LV-c`, board part `xilinx.com:kv260_som:part0:1.4`, with Vivado 2025.2. Do not program hardware.
