<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 I2S Receiver

Create a handwritten SystemVerilog stereo I2S receiver named `kv260_i2s_receiver`. The I2S inputs are synchronous to the PL clock for this kernel boundary. Sample serial data on detected BCLK rising edges, discard the one-bit I2S delay after each LRCLK channel transition, shift 16 bits MSB first, and publish a complete left/right pair through `sample_valid/sample_ready`. Hold the completed pair stable under backpressure. Reset or disable clears all partial frame state.

Integrate the kernel with the KV260 Zynq UltraScale+ MPSoC board preset in Vivado IP Integrator. Use a 100 MHz PS-generated PL clock and synchronized active-low reset, with suitable synchronization/staging at any physical I2S boundary. Add VIO control and a deterministic on-chip serial stimulus shell plus ILA observation of BCLK, LRCLK, serial data, output validity, completion, pass, and error status. Generate a validated block design, bitstream, matching LTX, and XSA.

Use handwritten RTL only. Verify channel alignment, signed bit preservation, the one-bit I2S delay, output backpressure, disable, and reset. Target `xck26-sfvc784-2LV-c`, board part `xilinx.com:kv260_som:part0:1.4`, with Vivado 2025.2. Do not program hardware.
