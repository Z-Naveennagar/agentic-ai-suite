<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
# globaltonemapping — HDR to LDR tone mapping baseline

Vitis Vision (xf_opencv) L1 baseline example for **Global Tone Mapping (GTM)** - converts High Dynamic Range images to Low Dynamic Range displays.

> **Baseline design:** NPPC=1, no optimizations. This is the starting point for `/hls-optimize` skill.

---

## Files

| File | Role |
|---|---|
| [`xf_gtm_accel.cpp`](xf_gtm_accel.cpp)   | Top-level HLS kernel with AXI interfaces |
| [`xf_gtm_tb.cpp`](xf_gtm_tb.cpp)         | C testbench — OpenCV reference comparison |
| [`xf_config_params.h`](xf_config_params.h) | Design parameters (HEIGHT=168, WIDTH=256, **NPPC=1**) |
| [`ltm_input_s.png`](ltm_input_s.png)     | Test input image (168×256 HDR PNG) |
| [`hls_config.tmpl`](hls_config.tmpl)     | HLS configuration template |
| [`gen_config.sh`](gen_config.sh)         | Script to generate hls_config.cfg |

---

## Prerequisites

Set OpenCV paths in your environment:
```bash
export OPENCV_INCLUDE=/path/to/opencv/include/opencv4
export OPENCV_LIB=/path/to/opencv/lib
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$OPENCV_LIB
```

The testbench includes `opencv2/{core,imgproc,imgcodecs,highgui,video}` (via
`include/xf_headers.hpp`), and `sim.ldflags` also links `flann` + `features2d`,
so all seven of those modules must be present in your OpenCV build.

**If csim fails to link with `undefined reference to ...@GLIBCXX_3.4.29`** (or
any `GLIBCXX_`/`CXXABI_` version above 3.4.25): Vitis HLS compiles csim with its
own bundled clang + libstdc++, which ships `GLIBCXX` only up to 3.4.25, while a
modern OpenCV needs more. Point the link at the system libstdc++ instead:
```bash
export OPENCV_LDFLAGS_EXTRA="/usr/lib/x86_64-linux-gnu/libstdc++.so.6 -Wl,-rpath,$OPENCV_LIB"
```
`gen_config.sh` appends this to the csim/cosim/sim `ldflags`. Leaving it unset
changes nothing, so it is safe to ignore where the host OpenCV already matches.

> **Do not** use an OpenCV built against a different glibc than the host's (e.g.
> a Nix-provided one on a non-NixOS machine). It will link but fail at runtime
> with `version 'GLIBC_ABI_GNU2_TLS' not found`, and forcing a foreign loader or
> overriding `LD_LIBRARY_PATH` to work around it crashes the Vitis tools
> themselves. Build/install an OpenCV that targets the host glibc.

Then generate the HLS configuration:
```bash
./gen_config.sh
```

---

## How to run the design

In Claude Code, from this design directory:

```
/hls-optimize  xf_gtm_accel.cpp  Reduce true-latency by 2x while using no more than 1.5x the resources
```

The skill chain will:

1. [`/hls-optimize`](../../skills/hls-optimize/SKILL.md) — analyze baseline, apply optimizations (parallel processing with NPPC=2/4, pragmas), iterate until 2× latency reduction met
