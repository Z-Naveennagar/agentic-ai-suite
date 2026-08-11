<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 Audio Peak Meter

Create a handwritten SystemVerilog windowed audio peak meter named `kv260_audio_peak_meter`. Compute the unsigned absolute magnitude of each accepted signed 16-bit input, treating `-32768` as magnitude 32768. After exactly `WINDOW_SIZE` accepted samples, publish the maximum magnitude through `peak_valid/peak_ready`, then begin a fresh window. Input bubbles do not advance the window, and an unconsumed report stalls new input while remaining stable.

Integrate the kernel in Vivado IP Integrator with the KV260 Zynq UltraScale+ MPSoC board preset, a 100 MHz PS-generated PL clock, synchronized active-low reset, and PS-accessible stream/status paths. Add VIO self-test controls and ILA probes for input magnitude, window completion, peak report, handshakes, pass, and error status. Produce a validated block design, bitstream, matching LTX, and XSA.

Use handwritten RTL only. Verify positive and negative magnitudes, `-32768`, bubbles, exact window boundaries, report backpressure, and reset. Target `xck26-sfvc784-2LV-c`, board part `xilinx.com:kv260_som:part0:1.4`, with Vivado 2025.2. Do not program hardware.
