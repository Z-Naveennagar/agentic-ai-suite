<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 streaming video test-pattern generator

Create a Vivado 2025.2 project for the Kria KV260 (`xck26-sfvc784-2LV-c`,
board part `xilinx.com:kv260_som:part0:1.4`). Apply the PS board preset and
construct a valid IP Integrator video pipeline around a handwritten
SystemVerilog AXI4-Stream RGB888 color-bar generator.

The enabled generator must emit eight vertical bars (white, yellow, cyan,
green, magenta, red, blue, black), assert `TUSER[0]` on the first pixel of
each frame, and assert `TLAST` on the final pixel of each line. Runtime width
and height inputs define the active frame. It must hold data and sidebands
stable under downstream backpressure and resume without skipping or
duplicating pixels. Use a 100 MHz PS-derived PL/control clock, Video Timing
Controller or equivalent video timing/control IP, AXI video connectivity,
and PS-accessible control. Do not use HLS for the generator.

Independently verify colors, coordinates, frame/line sidebands, multiple
frames, and randomized stalls. Validate the block design, synthesize,
implement, generate a bitstream, and export a bitstream-bearing XSA. The
regression must not require a display.
