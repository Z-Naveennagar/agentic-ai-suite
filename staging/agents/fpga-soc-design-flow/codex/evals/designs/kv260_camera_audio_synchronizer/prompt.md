<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 camera/audio metadata synchronizer

Create a Vivado 2025.2 KV260 design containing
`kv260_camera_audio_synchronizer`. For each accepted camera/audio metadata
pair, report the camera epoch, signed 65-bit camera-minus-audio timestamp
skew, whether the epochs match, and whether they are aligned. Alignment
requires equal epochs and an absolute timestamp skew less than or equal to the
per-item 32-bit tolerance. Use a one-entry ready/valid output stage and hold
every result field stable under backpressure.

Integrate the kernel using IP Integrator with the KV260 PS preset, a 100 MHz PL
clock, an on-chip deterministic metadata generator, and the standard
VIO/System-ILA hardware test shell. Live camera capture, audio codecs, clock
recovery, timestamp creation, and token pairing are platform work outside the
deterministic public-kernel oracle. Use direct RTL, not HLS. Verify positive
and negative skew, tolerance boundaries, epoch mismatch, bubbles, and output
stalls. Generate a bitstream and XSA without programming hardware.
