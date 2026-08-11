<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 audio/video timestamp correlator

Create a Vivado 2025.2 KV260 design containing `kv260_av_timestamp`. It accepts
one pending video timestamp and one pending audio timestamp on independent
ready/valid channels. Once both are available, emit the pair and the signed
65-bit skew `video_timestamp - audio_timestamp`. Preserve each token until it
is paired, accept either arrival order, and hold the result stable under
backpressure.

Integrate with the KV260 PS preset, a 100 MHz PL clock, platform timestamp
capture logic, and standard VIO/ILA hardware-test instrumentation. Physical
camera/audio clock recovery, CDC, and driver timestamp acquisition are
platform responsibilities outside this deterministic token-correlation
oracle. Use direct RTL, not HLS. Verify simultaneous and staggered arrivals,
positive/negative/zero skew, channel backpressure, and result stalls. Generate
a bitstream and XSA without programming hardware.
