<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Vitis HLS AI Assistant

The Vitis HLS AI Assistant connects to AMD documentation and drives live Vitis Unified IDE sessions (`v++`, `vitis-run`) to automate your HLS component workflow — from C simulation through co-simulation, synthesis, and pragma-driven optimization — all driven by natural language.

## Capabilities

- **MATLAB to C++ Conversion** — Automatically convert sample-based MATLAB algorithms to frame-based C++ with `ap_fixed` types and bit-exact golden verification
- **HLS Architecture Design** — Transform C++ into producer-consumer dataflow with `load_input -> compute -> store_output` wrapped in `#pragma HLS DATAFLOW`
- **Iterative Pragma Optimization** — Tune `PIPELINE`, `UNROLL`, `ARRAY_PARTITION`, and other pragmas one change at a time until throughput targets are met
- **Full Flow Execution** — Run C simulation, synthesis, co-simulation, and implementation via `v++` / `vitis-run`
- **Documentation Search** — Optional RAG-powered search across UG1399, UG1391, HLS Methodology Guide, and pragma reference (requires Vivado MCP Server)

## Example Designs

Three self-contained reference designs demonstrating different skill pipeline paths:

| Example | Skills Used | Target |
|---------|-------------|--------|
| **Matrix Multiplication** — C++ triple-nested loop | `/hls-architect` then `/hls-optimize` | 8x latency improvement |
| **Edge Detection** — MATLAB Sobel RGB edge detector | `/matlab-to-cpp` then `/hls-architect` then `/hls-optimize` | 4400 FPS @ 303 MHz |
| **Global Tone Mapping** — Vitis Vision L1 baseline | `/hls-optimize` | 2x latency reduction |
