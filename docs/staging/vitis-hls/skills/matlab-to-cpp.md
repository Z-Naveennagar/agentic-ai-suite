<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# /matlab-to-cpp — MATLAB to Frame-Based C++

Converts a sample-based MATLAB algorithm into frame-based C++ code suitable for HLS compilation, with bit-exact verification against the original MATLAB output at every stage.

| Field | Value |
|-------|-------|
| **Argument hint** | `<matlab-file.m> [part=<fpga-part>] [clock=<ns>] [throughput=<target>]` |
| **Bundle path** | `vitis-hls-ai-assistant-skills/matlab-to-cpp/SKILL.md` |
| **Hands off to** | [`/hls-architect`](hls-architect.md) |

## Where It Fits

```
MATLAB algorithm (.m) ──▶ /matlab-to-cpp ──▶ frame-based kernel.cpp + tb.cpp ──▶ /hls-architect
```

## What It Produces

```
design/
  golden/          # matlab_input.bin, matlab_golden.bin
  sample_based/    # Line-by-line MATLAB semantics preservation
  frame_based/     # Frame-based port for HLS
    kernel.cpp     # ← Key artifact: passes same golden as original MATLAB
    testbench.cpp
    ...
```

## Seven-Step Process

1. **Setup** — Verifies Vitis, MATLAB, and OpenCV availability; exports environment variables
2. **Capture golden** — Runs MATLAB testbench, saves binary outputs (`matlab_input.bin`, `matlab_golden.bin`)
3. **Refactor 1: Sample-based C++** — Creates a line-by-line C++ port preserving MATLAB indexing and semantics
4. **Range analysis** — Determines appropriate `ap_fixed<W,I>` types from observed variable ranges
5. **Refactor 2: Frame-based C++** — Restructures code into the loop shape HLS requires while applying selected fixed-point types
6. **Verify** — Confirms frame-based output achieves bit-exact match with golden results
7. **Hand off** — Passes verified code to `/hls-architect` with captured parameters

!!! info "Why Two Refactors?"
    The sample-based step preserves MATLAB semantics so any divergence (off-by-one, wraparound, saturation) is caught before HLS-shape changes are introduced.

## Guardrails

- Never proceeds without locating MATLAB/Vitis tooling
- Never proceeds past range analysis without bit-exact sample-based match
- Never proceeds to `/hls-architect` without bit-exact frame-based match

## Out of Scope

- HLS macro-architecture selection (owned by [`/hls-architect`](hls-architect.md))
- Pragma tuning (owned by [`/hls-optimize`](hls-optimize.md))

## Example

```
cd examples/edge-detection
/matlab-to-cpp rgbEdgeDetector 4400 FPS part=xczu9eg-ffvb1156-2-e clock=3.3
```

<p class="sphinxhide" align="center"><sub>Copyright © 2026 Advanced Micro Devices, Inc</sub></p>
<p class="sphinxhide" align="center"><sup><a href="https://www.amd.com/en/corporate/copyright">Terms and Conditions</a></sup></p>
