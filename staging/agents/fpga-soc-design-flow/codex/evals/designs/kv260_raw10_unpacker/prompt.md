<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 RAW10 unpacker

Create a Vivado 2025.2 KV260 design around the handwritten SystemVerilog module kv260_raw10_unpacker. The kernel accepts one standard MIPI RAW10 group per transfer: bytes 0 through 3 contain pixels 0 through 3 bits 9:2, and byte 4 contains their two-bit LSB fields in successive bit pairs. Emit four zero-extended 16-bit pixels packed pixel 0 first in bits 15:0. Preserve user and last, use a one-entry elastic stage, sustain one group per cycle, and hold output stable under backpressure.

Integrate through the KV260 PS preset with a 100 MHz PL clock and DMA-fed stream path. Use direct RTL, not HLS. Independently verify known encodings, randomized pixel groups, sidebands, bubbles, and backpressure. Implement for xck26-sfvc784-2LV-c, generate a bitstream and XSA, and do not program hardware.
