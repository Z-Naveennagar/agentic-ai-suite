---
name: matlab-to-aie-ml-v2
description: >-
  Port MATLAB vector/matrix/DSP operations to AI Engine-ML v2 (AIE-ML v2) kernels
  with vectorized SIMD loops using the AIE API. Performs deep analysis of MATLAB
  code, maps operations to 512-bit vector intrinsics with fp32 vector MAC support,
  generates kernel C++ with embedded iterators, creates full project scaffold
  (graph, app, config, Makefile), and validates against MATLAB golden reference.
  Targets AIE-ML v2 architecture (Versal Premium Gen 2, e.g., VEK385/XCVE3858).
  Supports bfloat16, fp32 vector MAC, enhanced DMA, and larger memory.
  Use when: user wants to port MATLAB to AIE-ML v2, needs fp32 vector MAC, wants
  latest AIE generation, or targets VEK385. Trigger on: "port to AIE-ML v2",
  "MATLAB to AIE-ML v2", "AIE-ML v2 kernel", "VEK385", "XCVE3858", "fp32 MAC",
  "AIE v2".
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
# MATLAB to AIE-ML v2 (AI Engine-ML v2)

Port MATLAB vector/matrix/DSP operations to AI Engine-ML v2 (AIE-ML v2) kernels targeting the Versal Premium Gen 2 series (XCVE3858 / VEK385 class devices).

---

## Architecture Overview

This skill targets the **AIE-ML v2 (3rd generation)** architecture:
- **Vector width**: 512-bit (16× float, 32× int16, 32× bfloat16)
- **fp32 Vector MAC**: Native float32 multiply-accumulate in vector unit (improved from AIE-ML)
- **Accumulator**: 512-bit (enhanced precision)
- **Local data memory**: 64 KB per compute tile
- **Memory tiles**: 512 KB dedicated memory tiles (enhanced DMA)
- **Program memory**: 16 KB per tile
- **Cascade width**: 512-bit
- **Supported data types**: int4, int8, int16, int32, float, bfloat16, cint16, cint32, cfloat
- **Enhanced features**: Improved shuffle/permute, faster DMA, fp32 vector MAC

Load architecture-specific reference files before proceeding:
- [./references/arch-capabilities.md](./references/arch-capabilities.md)
- [./references/api-intrinsics.md](./references/api-intrinsics.md)
- [./references/iterators.md](./references/iterators.md)
- [./references/tiling-strategies.md](./references/tiling-strategies.md)
- [./references/translation-examples.md](./references/translation-examples.md)

---

## Key Differences from AIE-ML (2nd Gen)

| Feature | AIE-ML | AIE-ML v2 |
|---|---|---|
| fp32 Vector MAC | Partial (limited throughput) | **Full throughput fp32 vector MAC** |
| DMA efficiency | Standard | **Enhanced DMA with lower latency** |
| Shuffle/permute | Standard | **Enhanced shuffle/permute operations** |
| Memory tile DMA | 2D/3D tiling | **Improved 2D/3D with faster reconfiguration** |
| Power efficiency | Baseline | **Improved performance/watt** |

---

## Workflow

Execute the following sub-skills in sequence. Each sub-skill produces artifacts consumed by the next.

### Step 1: Analyze MATLAB Code

Invoke `matlab-to-aie-analyze` skill with the user's MATLAB source files.

**Before invoking**, ask the user:
1. **"Which MATLAB function(s) should I port?"** — Get the file path(s)
2. **"What is the target data type?"** — Options: float, cfloat, int16, cint16, bfloat16
   - Note: AIE-ML v2 excels at **fp32** due to improved vector MAC — recommend float for high-precision applications
3. **"What are the working dimensions?"** — e.g., matrix sizes, FFT length
4. **"Should the design use memory tiles?"** — Recommend YES for data > 64 KB

Pass the architecture constraint: **512-bit vector width, 64 KB local memory, memory tiles available, fp32 vector MAC**.

### Step 2: Vectorize for AIE-ML v2

Invoke `matlab-to-aie-vectorize` skill with the analysis report.

Load [./references/api-intrinsics.md](./references/api-intrinsics.md) and [./references/iterators.md](./references/iterators.md) and provide to the vectorize sub-skill as architecture context.

**AIE-ML v2 specific advantages**:
- fp32 vector MAC at full throughput: 16 float MACs/cycle (improved pipeline)
- Enhanced shuffle enables more efficient transpose and permute operations
- Faster DMA reduces data staging overhead

### Step 3: Generate Kernel

Invoke `matlab-to-aie-kernel` skill with the vectorization specification.

**AIE-ML v2 specific notes**:
- Include `<adf.h>`, `<aie_api/aie.hpp>`, and `<aie_api/utils.hpp>`
- Kernel header uses `.h` extension (NOT `.hpp`)
- Constructor must set `aie::set_rounding()` and `aie::set_saturation()`
- Accumulator types: Same as AIE-ML (`accfloat` for float/bfloat16, `acc64` for int16)
- fp32 can achieve full vector MAC throughput — no need to fall back to bfloat16 for performance in many cases
- Enhanced shuffle operations for matrix transpose

**IMPORTANT**: The `matlab-to-aie-kernel` skill will automatically apply applicable
optimization skills during code generation based on the analysis report's "Optimization
Opportunities" section. The following optimizations are applied inline:

| Optimization Skill | Applied When |
|---|---|
| `optimize-aie-scalar-divide` | MATLAB code contains `x / y` on runtime float values |
| `optimize-aie-memory-access` | Matrix column/row traversal with index computation |
| `optimize-aie-diagonal-matrix-init` | `eye(N)`, `V = I`, diagonal matrix creation |
| `optimize-aie-diagonal-matrix-extract` | `diag(A)`, singular value extraction |
| `optimize-aie-buffers-to-parameters` | Large working arrays (> 256 bytes) in kernel |
| `optimize-aie-split-accumulator` | MAC inner loops where feedback latency > resource min |

**AIE-ML v2 note on split-accumulator**: On AIE-ML v2, fpmac feedback latency is
reduced to 2 cycles (improved from 4 on AIE/AIE-ML). The split-accumulator optimization
still applies when resource_min=1 (achievable with sequential vector loads), providing
up to 50% effective II reduction for float MAC loops.

### Step 4: Determine Target Board

**Before generating the project scaffold**, ask the user:

> **"Which target board/part are you using?"**

| Board | Part | Platform |
|---|---|---|
| VEK385 | `xcve3858-sfvc784-2MP-e-S` | `xilinx_vek385_base_202410_1` |

**Default**: VEK385 (`xcve3858-sfvc784-2MP-e-S`) if user does not specify.

Pass the selected part to the graph sub-skill (it will be set as the `PART_USE` variable in the Makefile).

### Step 5: Generate Project Scaffold

Invoke `matlab-to-aie-graph` skill with the board/part from Step 4.

**AIE-ML v2 specific settings**:
- Part: user-selected from Step 4 (default `xcve3858-sfvc784-2MP-e-S`) — goes in Makefile `PART_USE` variable, passed as `--part=${PART_USE}` in `AIE_FLAGS`
- Output files: `<kernel>_graph.h`, `<kernel>_app.cpp`, `<kernel>_app.aiecst`, `aie.cfg`, `Makefile`
- Memory tile configuration same as AIE-ML
- PLIO width: 128-bit (16 PLIOs available on VEK385)

### Step 6: Validate

Invoke `matlab-to-aie-validate` skill.

Generate test data from MATLAB, run x86sim, compare against golden.

---

## Decision Points

| Condition | Action |
|---|---|
| User needs highest fp32 throughput | AIE-ML v2 is optimal — use float with vector MAC |
| User requests bfloat16 | Supported (same as AIE-ML) |
| Data exceeds 64 KB | Use memory tiles |
| User has AIE (1st gen) target | Redirect to `matlab-to-aie` |
| User has AIE-ML target | Redirect to `matlab-to-aie-ml` |
| Need efficient matrix transpose | Leverage enhanced shuffle/permute |

---

## When to Choose AIE-ML v2 over AIE-ML

- **fp32-intensive workloads**: AIE-ML v2 has improved fp32 vector MAC pipeline
- **Data-movement-heavy designs**: Enhanced DMA reduces staging latency
- **Designs requiring frequent data reorganization**: Enhanced shuffle/permute
- **Power-sensitive applications**: Better performance/watt

---

## Additional Resources

- [Vitis Tutorials - AIE-ML Design Tutorials](https://github.com/Xilinx/Vitis-Tutorials/tree/2025.2/AI_Engine_Development/AIE-ML/Design_Tutorials)
- [AMD AIE Architecture Comparison](https://docs.amd.com/r/en-US/am027-versal-aie-ml-v2/Comparison-of-AIE-Generations)

---

## Quick Reference: AIE-ML v2 Lanes by Type

| Data Type | Vector Lanes | Accumulator | MACs/cycle |
|---|---|---|---|
| `int4` | 128 | acc32 | 512 (sparse) |
| `int8` | 64 | acc32 | 256 |
| `int16` | 32 | acc64 | 32 |
| `int32` | 16 | acc64 | 16 |
| `float` | 16 | accfloat | **16 (full throughput)** |
| `bfloat16` | 32 | accfloat | 32 |
| `cint16` | 16 | cacc64 | 16 |
| `cfloat` | 8 | caccfloat | 8 |

---

## Integrated Optimization Skills

The following optimization skills are automatically invoked during kernel code generation
(Step 3) when the MATLAB analysis report identifies applicable patterns:

| Skill | Purpose | Trigger |
|---|---|---|
| `optimize-aie-scalar-divide` | Replace `/` with `aie::inv()` hardware intrinsic | Division on runtime float values |
| `optimize-aie-memory-access` | Replace `ptr[i*N]` with pointer-stride increment | Matrix traversal loops |
| `optimize-aie-diagonal-matrix-init` | Vectorized zero-fill + diagonal stride writes | `eye(N)`, identity matrix init |
| `optimize-aie-diagonal-matrix-extract` | Strided-pointer diagonal read | `diag(A)`, eigenvalue/singular value output |
| `optimize-aie-buffers-to-parameters` | Move large arrays to `REGISTER_PARAMETER` | Working buffers > 256 bytes |
| `optimize-aie-split-accumulator` | Split MAC into N=2 independent accumulators | Inner loop II limited by MAC latency |

**AIE-ML v2 optimization notes**:
- `optimize-aie-split-accumulator`: fpmac feedback is 2 cycles (half of AIE/AIE-ML).
  With resource_min=1, N=2 split provides up to 50% II reduction.
- `optimize-aie-scalar-divide`: `aie::inv()` and `aie::invsqrt()` are available on
  all AIE generations with similar precision (~20-bit mantissa).
- `optimize-aie-memory-access`: Particularly important on AIE-ML v2 where the enhanced
  DMA and larger memory enable processing larger matrices — more index-multiply patterns
  arise in the outer loops of larger tiled algorithms.
