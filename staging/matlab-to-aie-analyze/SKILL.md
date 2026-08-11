---
name: matlab-to-aie-analyze
description: >-
  Deep analysis of MATLAB code for porting to AI Engine. Classifies operations
  (GEMM, FIR, FFT, element-wise, dot product, transpose/permute), extracts
  dimensions, data types, loop structures, and data flow dependencies. Determines
  tiling strategy, vector lengths, and accumulation patterns. Outputs a structured
  analysis report consumed by downstream matlab-to-aie sub-skills.
  Use when: user wants to analyze MATLAB code for AIE porting, understand how
  MATLAB maps to vectorized hardware, or get a porting feasibility assessment.
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
# MATLAB-to-AIE: Analyze

Perform deep analysis of MATLAB source code to produce a structured report that guides downstream AIE kernel generation.

---

## Prerequisites

- User has provided one or more `.m` files containing the algorithm to port
- User has specified (or will be asked) the target architecture: AIE, AIE-ML, or AIE-ML v2
- User has specified (or will be asked) the target data type: float, cfloat, int16, cint16, or bfloat16

---

## Workflow

### Step 1: Read MATLAB Source

Read all user-provided `.m` files. Identify:

1. **Entry-point function** — the top-level function to be mapped to a kernel `run()` method
2. **Helper functions** — any sub-functions called (these may become separate kernels or inline logic)
3. **Test harness** — any `test_*.m` or script that exercises the function (used later for golden data)

### Step 2: Classify Operation Type

Examine the MATLAB code and classify into one or more categories:

| Pattern in MATLAB | Operation Class | Typical AIE Mapping |
|---|---|---|
| `A * B` (matrix multiply) | GEMM | Tiled MAC with accumulator |
| `A .* B`, `A + B`, `A - B` | Element-wise | Vector lane-parallel ops |
| `dot(a, b)`, `sum(a .* b)` | Dot product | Reduction with aie::mac |
| `conv(x, h)`, `filter(b, a, x)` | FIR / Convolution | Sliding window MAC |
| `fft(x)`, `ifft(x)` | FFT | Radix-2/4 butterfly |
| `transpose(A)`, `A.'`, `permute(A, ...)` | Transpose/Permute | Shuffle/interleave patterns |
| `abs(x)`, `sqrt(x)`, `x.^2` | Nonlinear element-wise | Scalar or lookup-based |

**CRITICAL**: If the MATLAB code contains multiple operation types (e.g., GEMM followed by element-wise activation), identify the **pipeline of operations** and whether they should be fused into one kernel or split across multiple kernels connected via graph edges.

### Step 3: Extract Dimensions and Data Flow

For each identified operation, extract:

1. **Input dimensions**: Matrix sizes (M×N, N×L), vector lengths, window sizes
2. **Output dimensions**: Resulting matrix/vector sizes
3. **Data dependencies**: Which outputs feed into subsequent operations
4. **Reduction axes**: Which dimensions are summed/accumulated over
5. **Strides and access patterns**: Row-major vs column-major access, strided access, circular access

Document these in the analysis report.

### Step 4: Determine Data Type Mapping

Ask the user if not already specified: **"What is the target data type for the AIE implementation? Options: float, cfloat, int16, cint16, bfloat16"**

Then determine:

| MATLAB Type | Target AIE Type | Accumulator Type | Notes |
|---|---|---|---|
| `single` (real) | `float` | `accfloat` | Direct mapping |
| `single` (complex) | `cfloat` | `caccfloat` | Direct mapping |
| `single` → fixed | `int16` | `acc48` or `acc80` | Requires quantization strategy |
| `single` → fixed (complex) | `cint16` | `cacc48` or `cacc80` | Requires quantization strategy |
| `single` → bfloat | `bfloat16` | `accfloat` | AIE-ML/v2 only |

**If user requests fixed-point (int16/cint16)**:
- Ask: **"What is the expected dynamic range of your data? This determines the fractional bit allocation."**
- Determine scaling factor and fractional bits
- Note any overflow risk from accumulation depth

### Step 5: Determine Tiling Strategy

Based on operation class, dimensions, and target architecture vector width:

#### GEMM Tiling
- **Tile size**: Determined by vector width and available local memory
- **Strategy**: Compute an (Mt × Lt) output tile per kernel invocation
  - Mt = number of output rows processed per call
  - Lt = number of output columns processed per call
  - Inner loop accumulates over N dimension in chunks of vector width
- **Memory constraint**: All tile data must fit in local data memory (32KB for AIE, 64KB for AIE-ML/v2)

#### FIR/Convolution Tiling
- **Window size**: Input samples per kernel invocation
- **Coefficient storage**: Filter taps stored in local memory
- **Strategy**: Streaming window with sliding MAC

#### FFT Tiling
- **Point size**: FFT length (must be power of 2)
- **Radix**: Radix-2 or Radix-4 butterfly
- **Stages**: log2(N) or log4(N) stages, potentially split across multiple tiles

#### Element-wise
- **Chunk size**: Number of elements processed per invocation (vector width × number of iterations)
- **Strategy**: Simple vectorized loop, limited only by I/O bandwidth

### Step 6: Identify Optimization Opportunities

Scan the MATLAB code for patterns that map to known AIE optimization skills. Flag these
in the analysis report so that `matlab-to-aie-kernel` can apply them during code generation.

| MATLAB Pattern | Optimization Skill | Detection Rule |
|---|---|---|
| `x / y`, `1/norm`, `a / (b*c)` where divisor is not constant | `optimize-aie-scalar-divide` | Any `/` operator on a runtime-computed float variable |
| `eye(N)`, `V = zeros(N); V(i,i) = 1` | `optimize-aie-diagonal-matrix-init` | Identity matrix creation or diagonal-only initialization |
| `diag(A)`, `s = A(k,k)` for all k | `optimize-aie-diagonal-matrix-extract` | Extracting diagonal elements from a matrix |
| `A(:, k)`, `M(k*N+1:(k+1)*N)` | `optimize-aie-memory-access` | Column/row traversal in nested loops with stride computation |
| Temporary arrays > 256 bytes (e.g., `temp = zeros(N,N)`) | `optimize-aie-buffers-to-parameters` | Working matrices/vectors that map to large stack arrays |
| `C = C + a * B(k,:)` accumulation loop | `optimize-aie-split-accumulator` | Inner loop with running MAC accumulation |

**Composite algorithms**: Many MATLAB algorithms combine several of these patterns.
For example, Jacobi SVD typically requires ALL six optimization skills (division for
rotation angles, diagonal init for V=I, diagonal extract for singular values,
memory access for column traversal, buffers for working matrices, and potentially
split-accumulator for the rotation application loop).

### Step 7: Produce Analysis Report

Output a structured report in the following format:

```
## Analysis Report

### Operation Classification
- Primary operation: <type>
- Secondary operations: <types or "none">
- Pipeline structure: <single kernel | multi-kernel graph>

### Dimensions
- Input A: [M × N] = [<value> × <value>]
- Input B: [N × L] = [<value> × <value>]  (if applicable)
- Output C: [M × L] = [<value> × <value>]
- Reduction axis: <dimension and size>

### Data Type Mapping
- MATLAB source type: <type>
- AIE target type: <type>
- Accumulator type: <type>
- Quantization: <strategy or "N/A for floating-point">

### Tiling Strategy
- Output tile size: [Mt × Lt] = [<value> × <value>]
- Inner accumulation chunk: <vector_width>
- Iterations per tile: <N / vector_width>
- Total tiles: <(M/Mt) × (L/Lt)>

### Memory Budget
- Input buffer A tile: <bytes>
- Input buffer B tile: <bytes>  (if applicable)
- Output buffer C tile: <bytes>
- Total local memory required: <bytes>
- Available local memory: <bytes per architecture>

### Data Access Patterns
- Input A access: <row-major sequential | column-stride | circular>
- Input B access: <column-major sequential | row-stride | circular>
- Output C access: <row-major sequential>
- Recommended iterator types: <list>

### Recommended Architecture Features
- Vector width utilized: <128-bit | 256-bit | 512-bit>
- Accumulator width: <48-bit | 80-bit | floating>
- Memory tiles needed: <yes/no, AIE-ML/v2 only>
- Cascade connections: <yes/no>

### Optimization Opportunities
- Division operations: <yes/no — list MATLAB lines containing / on runtime values>
  → Applicable skill: `optimize-aie-scalar-divide`
- Identity/diagonal matrix initialization: <yes/no — e.g., eye(N), diag(v), V=I>
  → Applicable skill: `optimize-aie-diagonal-matrix-init`
- Diagonal extraction: <yes/no — e.g., diag(A), extracting singular values>
  → Applicable skill: `optimize-aie-diagonal-matrix-extract`
- Large working buffers: <yes/no — list temp matrices/arrays exceeding 256 bytes>
  → Applicable skill: `optimize-aie-buffers-to-parameters`
- MAC-dominated inner loops: <yes/no — accumulation loops over reduction dimension>
  → Applicable skill: `optimize-aie-split-accumulator`
- Matrix column/row traversal with index computation: <yes/no — nested loops over matrix indices>
  → Applicable skill: `optimize-aie-memory-access`
```

---

## Decision Points

- **If memory budget exceeds local memory**: Recommend splitting into smaller tiles or using memory tiles (AIE-ML/v2) or ping-pong buffering
- **If operation is too large for single kernel**: Recommend multi-kernel graph with cascade or buffer connections
- **If MATLAB uses double precision**: Warn user that AIE supports single-precision float maximum; recommend conversion strategy
- **If complex operations detected**: Verify target supports complex types at requested precision

---

## Pass to Next Sub-Skill

After producing the analysis report, the next step in the workflow is `matlab-to-aie-vectorize`, which consumes this report to produce the vectorized loop structure and intrinsic mapping.
