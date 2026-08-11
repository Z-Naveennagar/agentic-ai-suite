<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# /hls-architect — HLS Macro-Architecture

Convert frame-based C++ into a producer-consumer HLS dataflow design — `load_input → compute → store_output`, wrapped in `#pragma HLS DATAFLOW`. The architect chooses macro structure only; pragmas like `PIPELINE` / `UNROLL` are deferred to `/hls-optimize`.

| Field | Value |
|-------|-------|
| **Argument hint** | `[<throughput-target e.g. '140 FPS'>] [part=<fpga-part>] [clock=<ns>]` |
| **Bundle path** | `vitis-hls-ai-assistant-skills/hls-architect/SKILL.md` |
| **Inspired by** | _Parallel Programming for FPGAs_ (Kastner et al.) + AMD UG1399 |
| **Hands off to** | [`/hls-optimize`](hls-optimize.md) |

## Target Shape

```
+--- #pragma HLS DATAFLOW ----------------------------------------+
|  load_input()   stream→  compute()   stream→  store_output()    |
|  m_axi → strm            algorithmic work     strm → m_axi     |
|                                                                  |
|  (if decomposable, hierarchical inner DATAFLOW:)                 |
|    compute_stage1 → compute_stage2 → ... → stageN               |
+-----------------------------------------------------------------+
```

## Allowed Pragmas (Only Four)

The architect is restricted to these four pragmas — everything else is deferred:

- `#pragma HLS DATAFLOW`
- `#pragma HLS INTERFACE ...`
- `#pragma HLS STREAM depth=N`
- `#pragma HLS performance target_ti=N`

## Nine-Step Process

1. **Verify Vitis env** — `$XILINX_VITIS` must be set so `ap_fixed.h` is reachable
2. **Parse arguments** — Split into `THROUGHPUT_TARGET`, `XPART`, `CLOCK_NS`
3. **Input discovery** — Locate (or create) workspace under `design/rearchitect/v1/`
4. **Calculate target_ti** — Calls `/hls-perf-pragma` to cascade throughput target to top function and inner loops
5. **Generate macro-architecture** — Write `kernel_hls.cpp` shaped as load → compute → store inside `#pragma HLS DATAFLOW`
6. **Validate** — Calls analysis skills in sequence:
    - `/hls-synthesizable` — bans dynamic memory, recursion, function pointers, unbounded loops
    - `/hls-dataflow` — canonical-form check (SP/SC, PIPO or `hls::stream`, no feedback)
    - `/hls-burst-inference` — m_axi interfaces will infer real bursts
7. **Compile** — Verify with `g++ -I$XILINX_VITIS/include` to catch `ap_fixed` / `hls::stream` type errors before invoking HLS
8. **Snapshot** — Saves `architect_baseline/` so `/hls-optimize` has a clean rollback point
9. **Hand off** — Calls `/hls-optimize` with the throughput target

## Out of Scope

- Pragmas other than the four listed above
- Algorithmic changes to the source code
- Bit-exact divergence from source

## Example

```
cd examples/hls-intro-matmul
/hls-architect throughput=8x baseline
```

<p class="sphinxhide" align="center"><sub>Copyright © 2026 Advanced Micro Devices, Inc</sub></p>
<p class="sphinxhide" align="center"><sup><a href="https://www.amd.com/en/corporate/copyright">Terms and Conditions</a></sup></p>
