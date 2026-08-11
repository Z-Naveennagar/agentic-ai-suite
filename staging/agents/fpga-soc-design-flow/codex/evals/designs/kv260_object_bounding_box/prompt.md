<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 object bounding-box reducer

Create a Vivado 2025.2 KV260 design containing kv260_object_bounding_box. Accepted samples carry an explicit x/y coordinate, a foreground bit, and frame-first/frame-last flags. For every frame emit exactly one result containing the inclusive minimum and maximum foreground coordinates. Emit found=0 and zero coordinates for an empty frame. Frame-first resets prior state before evaluating that same sample; frame-last includes that same sample in the result.

Hold the result stable under output backpressure and stall input whenever the one-entry result stage cannot advance. Integrate with the KV260 PS preset, a 100 MHz PL clock, DMA-fed masks, VIO and ILA. Use direct RTL, not HLS. Verify singleton, edge-touching, sparse, empty and consecutive frames plus output stalls. Generate a bitstream and XSA without programming hardware.
