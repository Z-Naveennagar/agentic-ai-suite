<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 video cropper

Create a Vivado 2025.2 KV260 design containing kv260_video_cropper. Each input transfer carries RGB888 and explicit x/y coordinates. Retain pixels in the half-open rectangle crop_x0 <= x < crop_x1 and crop_y0 <= y < crop_y1; silently absorb all others. Assert output user on coordinate (crop_x0,crop_y0) and output last on every retained pixel where x equals crop_x1-1.

Use a one-entry output stage. Retained pixels must obey backpressure and remain stable while stalled; discarded pixels may continue to be accepted without disturbing a stalled output. Crop bounds are stable during a frame and satisfy x0<x1 and y0<y1. Integrate with the KV260 PS preset, 100 MHz PL clock, DMA/VDMA, VIO and ILA. Use RTL, not HLS. Verify crop edges, output sidebands, ordering and randomized stalls. Generate a bitstream and XSA without programming hardware.
