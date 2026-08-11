<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

Create a KV260 Adaptive SoC design containing a signed 16-bit, eight-tap streaming FIR filter. The public handwritten RTL kernel `kv260_fir_filter` uses the fixed coefficients `[1, 2, 3, 4, 4, 3, 2, 1]`, accepts a sample when `s_valid` is asserted, and produces the exact signed 36-bit convolution result with a deterministic one-cycle valid pipeline. Reset clears all sample history and output validity. A new input sample may be accepted on every clock.

Use the KV260 Zynq UltraScale+ MPSoC board preset, a 100 MHz PS-generated PL clock, and a synchronized active-high PL reset. Integrate the RTL kernel in an IP Integrator design between AXI DMA-compatible streaming infrastructure, adding only the adapters needed for the public kernel interface. Do not replace the arithmetic with HLS.

Provide deterministic cocotb tests for impulse response, signed corner cases, bubbles, reset/history clearing, and randomized model comparison. Build and validate the block design in Vivado 2025.2, implement it for `xck26-sfvc784-2LV-c`, and generate a bitstream and exported XSA. Do not program hardware.
