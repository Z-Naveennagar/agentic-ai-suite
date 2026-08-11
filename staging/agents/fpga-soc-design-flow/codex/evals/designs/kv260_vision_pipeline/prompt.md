<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 integrated streaming vision pipeline

Create a Vivado 2025.2 project for the Kria KV260 (`xck26-sfvc784-2LV-c`,
board part `xilinx.com:kv260_som:part0:1.4`). Apply the PS board preset and
construct a valid IP Integrator MIPI-to-DDR/display vision pipeline.

Author a handwritten SystemVerilog AXI4-Stream RGB888 kernel that converts
to BT.601 integer grayscale, forms a 3x3 Sobel gradient after two buffered
lines, thresholds `abs(Gx)+abs(Gy)`, and applies a causal three-pixel
horizontal binary dilation (current or either of the previous two threshold
results). It emits one binary byte (`0xFF` or `0x00`) for every input pixel
with X>=2 and Y>=2. Assert output SOF on the first such pixel and preserve
TLAST on the final produced pixel of every produced line. Runtime width does
not exceed `MAX_WIDTH`. All state and sidebands must remain correct under
backpressure.

Integrate MIPI CSI-2 Receiver/D-PHY ingress, AXI VDMA or framebuffer access
to PS DDR, and an HDMI/display output subsystem or appropriate KV260 display
path. Use a 100 MHz PS-derived control clock, PS-accessible control,
SmartConnect, and safe resets. The custom kernel must be RTL, not HLS.
Physical camera and display hardware must not be needed for regression.

Independently verify the exact streaming image model, border removal,
threshold/dilation behavior, sidebands, and randomized stalls. Validate the
block design, synthesize, implement, create a bitstream, and export a
bitstream-bearing XSA.
