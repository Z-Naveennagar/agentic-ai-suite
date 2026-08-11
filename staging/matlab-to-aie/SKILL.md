---
name: matlab-to-aie
description: >-
  Port MATLAB vector/matrix/DSP operations to AI Engine (AIE) kernels with
  vectorized SIMD loops using the AIE API. Performs deep analysis of MATLAB code,
  maps operations to 256-bit vector intrinsics (aie::mul, aie::mac, aie::add),
  generates kernel C++ with embedded iterators, creates full project scaffold
  (graph, app, config, Makefile), and validates against MATLAB golden reference.
  Targets AIE architecture (Versal AI Core series, e.g., VCK190/XCVC1902).
  Use when: user wants to port MATLAB to AIE, convert MATLAB to AI Engine,
  create a vectorized AIE kernel from MATLAB, or implement MATLAB algorithm on
  Versal AI Core. Trigger on: "port to AIE", "MATLAB to AIE", "AI Engine kernel",
  "vectorize for AIE", "XCVC1902", "VCK190".
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
# MATLAB to AIE (AI Engine)

Port MATLAB vector/matrix/DSP operations to AI Engine (AIE) kernels targeting the Versal AI Core series (XCVC1902 / VCK190 class devices).

---

## Architecture Overview

This skill targets the **AIE (1st generation)** architecture:
- **Vector width**: 256-bit (8× float, 16× int16, 4× cfloat)
- **Accumulator**: 384-bit (acc48 for int, accfloat for float)
- **Local data memory**: 32 KB per tile (8 banks)
- **Program memory**: 16 KB per tile
- **Cascade width**: 384-bit between adjacent tiles
- **Supported data types**: int8, int16, int32, float, cint16, cint32, cfloat

Load architecture-specific reference files before proceeding:
- [./references/arch-capabilities.md](./references/arch-capabilities.md)
- [./references/api-intrinsics.md](./references/api-intrinsics.md)
- [./references/iterators.md](./references/iterators.md)
- [./references/tiling-strategies.md](./references/tiling-strategies.md)
- [./references/translation-examples.md](./references/translation-examples.md)

---

## Workflow

Execute the following sub-skills in sequence. Each sub-skill produces artifacts consumed by the next.

### Step 1: Analyze MATLAB Code

Invoke `matlab-to-aie-analyze` skill with the user's MATLAB source files.

**Before invoking**, ask the user:
1. **"Which MATLAB function(s) should I port?"** — Get the file path(s)
2. **"What is the target data type?"** — Options: float, cfloat, int16, cint16
   - Note: bfloat16 is NOT supported on AIE (1st gen) — if user requests bfloat16, redirect to `matlab-to-aie-ml` or `matlab-to-aie-ml-v2`
3. **"What are the working dimensions?"** — e.g., matrix sizes M×N×L, FFT point size, filter length

Pass the architecture constraint: **256-bit vector width, 32 KB local memory**.

### Step 2: Vectorize for AIE

Invoke `matlab-to-aie-vectorize` skill with the analysis report.

Load [./references/api-intrinsics.md](./references/api-intrinsics.md) and [./references/iterators.md](./references/iterators.md) and provide to the vectorize sub-skill as architecture context.

**AIE-specific constraints**:
- Maximum 8 float lanes or 16 int16 lanes per vector operation
- Accumulator width: 48-bit for integer MAC, floating-point accumulator for float
- Inner loop should target 1 MAC per cycle (theoretical throughput: 8 FP32 MACs/cycle or 16 INT16 MACs/cycle)

### Step 3: Generate Kernel

Invoke `matlab-to-aie-kernel` skill with the vectorization specification.

**AIE-specific notes**:
- Include `<adf.h>`, `<aie_api/aie.hpp>`, and `<aie_api/utils.hpp>`
- Accumulator type: `aie::accum<accfloat, 8>` for float, `aie::accum<acc48, 16>` for int16
- Use `chess_prepare_for_pipelining` on inner loops
- Kernel header uses `.h` extension (NOT `.hpp`)
- Constructor must set `aie::set_rounding()` and `aie::set_saturation()`

**IMPORTANT**: The `matlab-to-aie-kernel` skill will automatically apply applicable
optimization skills during code generation based on the analysis report's "Optimization
Opportunities" section. The following optimizations are applied inline — not as a
separate post-processing step:

| Optimization Skill | Applied When |
|---|---|
| `optimize-aie-scalar-divide` | MATLAB code contains `x / y` on runtime float values |
| `optimize-aie-memory-access` | Matrix column/row traversal with index computation |
| `optimize-aie-diagonal-matrix-init` | `eye(N)`, `V = I`, diagonal matrix creation |
| `optimize-aie-diagonal-matrix-extract` | `diag(A)`, singular value extraction |
| `optimize-aie-buffers-to-parameters` | Large working arrays (> 256 bytes) in kernel |
| `optimize-aie-split-accumulator` | MAC inner loops where feedback latency > resource min |

### Step 4: Determine Target Board

**Before generating the project scaffold**, ask the user:

> **"Which target board/part are you using?"**

| Board | Part | Platform |
|---|---|---|
| VCK190 | `xcvc1902-vsva2197-2MP-e-S` | `xilinx_vck190_base_202410_1` |
| VMK180 | `xcvm1802-vsva2197-2MP-e-S` | `xilinx_vmk180_base_202410_1` |

**Default**: VCK190 (`xcvc1902-vsva2197-2MP-e-S`) if user does not specify.

Pass the selected part to the graph sub-skill (it will be set as the `PART` variable in the Makefile).

### Step 5: Generate Project Scaffold

Invoke `matlab-to-aie-graph` skill with the board/part from Step 4.

**AIE-specific settings**:
- Part: user-selected from Step 4 (default `xcvc1902-vsva2197-2MP-e-S`) — goes in Makefile `PART_USE` variable, passed as `--part=${PART_USE}` in `AIE_FLAGS`
- PLIO width: 128-bit recommended for maximum bandwidth
- Stack size: 2048 bytes default (increase for deep recursion or large locals)
- Output files: `<kernel>_graph.h`, `<kernel>_app.cpp`, `<kernel>_app.aiecst`, `aie.cfg`, `Makefile`

### Step 6: Validate

Invoke `matlab-to-aie-validate` skill.

Generate test data from MATLAB, run x86sim, compare against golden.

---

## Decision Points

| Condition | Action |
|---|---|
| User requests bfloat16 | Redirect to `matlab-to-aie-ml` or `matlab-to-aie-ml-v2` |
| Data exceeds 32 KB local memory | Recommend tiling or multi-kernel graph |
| Matrix too large for single tile | Suggest cascade of tiles or split into multiple kernels |
| User has existing graph/Makefile | Skip Step 4, integrate kernel into existing project |
| User only wants kernel code | Stop after Step 3 |

---

## Additional Resources

For more AIE design patterns and examples, reference:
- [Vitis Tutorials - AIE Design Tutorials](https://github.com/Xilinx/Vitis-Tutorials/tree/2025.2/AI_Engine_Development/AIE/Design_Tutorials)
- AMD/Xilinx AIE API documentation (search with `vivado_doc_search` if available)

---

## Quick Reference: AIE Lanes by Type

| Data Type | Vector Lanes | Accumulator | MACs/cycle |
|---|---|---|---|
| `int8` | 32 | acc48 | 128 (with 4×4) |
| `int16` | 16 | acc48 | 16 |
| `int32` | 8 | acc80 | 8 |
| `float` | 8 | accfloat | 8 |
| `cint16` | 8 | cacc48 | 8 |
| `cfloat` | 4 | caccfloat | 4 |

---

## Integrated Optimization Skills

The following optimization skills are automatically invoked during kernel code generation
(Step 3) when the MATLAB analysis report identifies applicable patterns. They are NOT
run as a separate post-processing pass — they are applied inline during initial code
generation to produce optimized kernel code from the start.

| Skill | Purpose | Trigger |
|---|---|---|
| `optimize-aie-scalar-divide` | Replace `/` with `aie::inv()` hardware intrinsic | Division on runtime float values |
| `optimize-aie-memory-access` | Replace `ptr[i*N]` with pointer-stride increment | Matrix traversal loops |
| `optimize-aie-diagonal-matrix-init` | Vectorized zero-fill + diagonal stride writes | `eye(N)`, identity matrix init |
| `optimize-aie-diagonal-matrix-extract` | Strided-pointer diagonal read | `diag(A)`, eigenvalue/singular value output |
| `optimize-aie-buffers-to-parameters` | Move large arrays to `REGISTER_PARAMETER` | Working buffers > 256 bytes |
| `optimize-aie-split-accumulator` | Split MAC into N=2 independent accumulators | Inner loop II limited by MAC latency |

For post-generation performance analysis, also use `extract-aie-loop-ii` to verify
that the generated kernel achieves expected initiation intervals after compilation.
