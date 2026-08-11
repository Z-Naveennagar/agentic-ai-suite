<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 I2S Transmitter

Create a handwritten SystemVerilog stereo I2S transmitter named `kv260_i2s_transmitter`. It accepts one signed 16-bit left/right sample pair through `sample_valid/sample_ready`, serializes MSB first, holds LRCLK low for the left word and high for the right word, and inserts the mandatory one-bit I2S delay at the start of each channel. `CLK_DIV` defines the number of PL clocks per BCLK half-period. `busy` remains asserted for the complete frame. Disabling or resetting the kernel returns BCLK, LRCLK, and serial data low.

Integrate the kernel with the KV260 Zynq UltraScale+ MPSoC board preset in Vivado IP Integrator. Use a 100 MHz PS-generated PL clock and synchronized active-low reset, with PS-accessible control/sample staging. Add a VIO-driven deterministic self-test shell and ILA probes for start, serial clock, channel select, serial data, completion, pass, and error status. Generate a validated block design, bitstream, matching LTX, and XSA.

Use handwritten RTL only. Verify framing, MSB order, one-bit channel delays, ready/busy behavior, disable safety, and reset. Target `xck26-sfvc784-2LV-c`, board part `xilinx.com:kv260_som:part0:1.4`, with Vivado 2025.2. Do not program hardware.
