---
name: matlab-to-aie-vectorize
description: >-
  Maps MATLAB operations to AIE SIMD vectorized loop structures using the AIE API.
  Consumes the analysis report from matlab-to-aie-analyze and produces a vectorized
  pseudo-code specification showing loop nesting, iterator types, intrinsic calls
  (aie::mul, aie::mac, aie::add), and accumulator management. Handles data layout
  decisions (row-major, column-major, padding) and memory access pattern optimization.
  Use when: mapping analyzed MATLAB operations to vectorized AIE loops, choosing
  iterators, or determining SIMD decomposition strategy.
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
# MATLAB-to-AIE: Vectorize

Map analyzed MATLAB operations to AIE SIMD vectorized loop structures with embedded iterators and API intrinsic calls.

---

## Prerequisites

- Analysis report from `matlab-to-aie-analyze` is available (operation class, dimensions, tiling strategy, data types)
- Target architecture is known (AIE, AIE-ML, or AIE-ML v2) — determines vector width and available intrinsics
- The calling meta-skill's `references/api-intrinsics.md` and `references/iterators.md` have been loaded

---

## Workflow

### Step 1: Determine Vector Width and Lanes

Based on target architecture and data type, determine the number of parallel lanes:

| Data Type | AIE (256-bit vector) | AIE-ML (512-bit vector) | AIE-ML v2 (512-bit vector) |
|---|---|---|---|
| `int8` | 32 lanes | 64 lanes | 64 lanes |
| `int16` | 16 lanes | 32 lanes | 32 lanes |
| `int32` | 8 lanes | 16 lanes | 16 lanes |
| `float` | 8 lanes | 16 lanes | 16 lanes |
| `bfloat16` | N/A | 32 lanes | 32 lanes |
| `cint16` | 8 lanes | 16 lanes | 16 lanes |
| `cfloat` | 4 lanes | 8 lanes | 8 lanes |

**CRITICAL**: The vector width determines the inner loop unrolling factor. All vectorized operations process exactly this many elements per intrinsic call.

### Step 2: Select Iterator Types

Based on the data access patterns from the analysis report, select appropriate AIE API iterators:

| Access Pattern | Iterator Type | Usage |
|---|---|---|
| Sequential read (contiguous) | `aie::begin_vector<N>(ptr)` | Straight-through buffer access |
| Sequential read (restrict) | `aie::begin_restrict_vector<N>(ptr)` | When compiler needs aliasing guarantee |
| Circular buffer access | `aie::circular_iterator<N>(ptr, size)` | FIR coefficient cycling, ping-pong |
| Strided access (skip elements) | `aie::begin_pattern<N>(ptr, pattern)` | Column access in row-major matrix |
| Random/indexed access | Direct pointer arithmetic | Avoid if possible — kills performance |

**Rules for iterator selection**:
1. **Always prefer iterators over raw pointer arithmetic** — iterators enable compiler auto-scheduling
2. **Use `restrict` variants** when input and output buffers are guaranteed non-overlapping
3. **Use circular iterators** for filter coefficients and any repeating access pattern
4. **For matrix column access**: Either transpose the data layout or use a strided pattern iterator

### Step 3: Map Operations to Intrinsics

For each operation in the analysis report, select the AIE API intrinsic:

#### Multiply-Accumulate (GEMM, FIR, Dot Product)

```
MATLAB: C = A * B  (or conv, or dot)
AIE:    acc = aie::mac(acc, vec_a, vec_b)
```

- Initialize accumulator: `aie::accum<AccType, Lanes> acc; acc = aie::zeros<AccType, Lanes>();`
- Accumulate: `acc = aie::mac(acc, vec_a, vec_b)`
- Final result: `auto result = acc.to_vector<OutType>(shift);` (for fixed-point)
- Final result: `auto result = acc.to_vector<OutType>();` (for floating-point)

#### Element-wise Operations

```
MATLAB: C = A .* B     →  AIE: auto c = aie::mul(a, b)
MATLAB: C = A + B      →  AIE: auto c = aie::add(a, b)
MATLAB: C = A - B      →  AIE: auto c = aie::sub(a, b)
MATLAB: C = A .* s     →  AIE: auto c = aie::mul(a, scalar)  (broadcast)
```

#### Reduction Operations

```
MATLAB: s = sum(x)     →  AIE: auto s = aie::reduce_add(vec)
MATLAB: s = dot(a,b)   →  AIE: acc = aie::mac(acc, vec_a, vec_b); then reduce
```

#### Comparison / Selection

```
MATLAB: C = max(A, B)  →  AIE: auto c = aie::max(a, b)
MATLAB: C = min(A, B)  →  AIE: auto c = aie::min(a, b)
MATLAB: C = abs(A)     →  AIE: auto c = aie::abs(a)
```

### Step 4: Construct Loop Structure

Build the nested loop structure following this pattern:

```
// Outer loops: iterate over output tiles
for (tile_row = 0; tile_row < M/Mt; tile_row++) {
    for (tile_col = 0; tile_col < L/Lt; tile_col++) {

        // Initialize accumulators for this output tile
        accum[0..Mt-1][0..Lt/Lanes-1] = zeros

        // Inner loop: accumulate over reduction dimension
        for (k = 0; k < N; k += vector_width) {

            // Load input vectors using iterators
            vec_a = *iter_a++   // from input A
            vec_b = *iter_b++   // from input B

            // Vectorized compute
            acc[row][col] = aie::mac(acc[row][col], vec_a, vec_b)
        }

        // Store results using output iterator
        *iter_out++ = acc.to_vector<OutType>(shift)
    }
}
```

**Key decisions**:
1. **Which loops are outer (scalar) vs inner (vectorized)?** — The innermost loop that maps to a MAC/vector operation is the vectorized loop
2. **Loop ordering for data locality** — Keep the dimension with contiguous memory access in the innermost loop
3. **Accumulator register pressure** — Don't exceed available accumulator registers (architecture-dependent)

#### Memory Access Pattern Optimization

When designing the loop structure, apply the `optimize-aie-memory-access` principle:
**avoid index-multiply address computations in loop bodies**. Instead, use pointer-stride
increments that advance by a constant each iteration.

**Pattern to AVOID in vectorization spec:**
```
for (col = 0; col < N; col++) {
    ptr = &Matrix[col * N]   // index multiply each iteration!
    ...
}
```

**Pattern to USE:**
```
ptr = Matrix
for (col = 0; col < N; col++) {
    // use ptr
    ptr += N   // pointer stride: add replaces multiply
}
```

For nested loops where both indices map to matrix positions, express inner pointers
relative to outer pointers (e.g., `inner_ptr = outer_ptr + STRIDE`) to eliminate all
multiplies. This maps directly to the `optimize-aie-memory-access` skill patterns.

#### Accumulator Feedback Awareness

When the vectorized inner loop contains a MAC accumulation (`acc = mac(acc, ...)`),
note in the specification whether the **accumulator feedback latency** may exceed the
**resource minimum**:

- AIE (1st gen): fpmac feedback = 4 cycles, resource min often = 2
- AIE-ML: fpmac feedback = 4 cycles
- AIE-ML v2: fpmac feedback = 2 cycles

If the inner loop is a simple MAC accumulation with trip count ≥ 8, flag it in the
vectorization spec for `optimize-aie-split-accumulator` treatment (N=2 split)
during kernel generation. The `matlab-to-aie-kernel` skill will apply the split.

### Step 5: Handle Data Layout

Determine if data layout transformation is needed:

| Scenario | Solution |
|---|---|
| Both inputs row-major, reduction along columns | No transform needed for A; transpose B or use column iterator |
| Column-major input from MATLAB | Transpose on host before sending to AIE, or adapt iterator pattern |
| Output needs specific layout for downstream | May need post-processing shuffle |

**Padding rules**:
- Input dimensions must be padded to multiples of vector width
- Document required padding in the vectorization spec
- Padding with zeros is safe for MAC operations (doesn't affect result)
- Host code (graph/app) is responsible for padding before sending data to kernel

### Step 6: Produce Vectorization Specification

Output a structured specification:

```
## Vectorization Specification

### Architecture Parameters
- Target: <AIE | AIE-ML | AIE-ML v2>
- Vector width: <N> lanes of <type>
- Accumulator: <type> × <lanes>
- Registers available: <count>

### Loop Structure
```pseudo
// [Describe the complete loop nest with iterator declarations,
//  intrinsic calls, and accumulator management]
```

### Iterator Declarations
- iter_a: <type> — <description of access pattern>
- iter_b: <type> — <description of access pattern>
- iter_out: <type> — <description of access pattern>

### Intrinsics Used
- aie::mac(acc, a, b) — <count> calls per inner iteration
- aie::add(a, b) — <count> calls (if element-wise post-processing)
- acc.to_vector<T>(shift) — <count> calls per output tile

### Data Layout Requirements
- Input A: <layout, padding requirements>
- Input B: <layout, padding requirements>
- Output C: <layout>

### Performance Estimate
- MACs per kernel invocation: <count>
- Vector operations per invocation: <count>
- Estimated cycles (at 1 GHz): <count>
- Theoretical throughput: <ops/sec>

### Optimization Flags (from analysis report)
- Apply scalar-divide replacement: <yes/no — list division expressions>
- Apply pointer-stride memory access: <yes/no — list index-multiply patterns>
- Apply diagonal-matrix-init: <yes/no — list identity/diagonal init patterns>
- Apply diagonal-matrix-extract: <yes/no — list diagonal extraction patterns>
- Apply buffers-to-parameters: <yes/no — list large working buffers with sizes>
- Apply split-accumulator: <yes/no — list MAC inner loops with trip counts>
```

---

## Operation-Specific Vectorization Patterns

### GEMM (C = A × B)

**Strategy**: Outer-product or inner-product formulation depending on tile shape.

**Inner-product (row × column)**:
- For each output element C[i][j]: accumulate A[i][k] × B[k][j] for k = 0..N-1
- Vectorize along k: load vector of A row, load vector of B column, MAC into accumulator
- After full k sweep, store scalar result

**Outer-product (column × row)**:
- For each k: compute rank-1 update A[:,k] × B[k,:] and add to C
- Vectorize along output columns: load scalar A[i][k], load vector of B[k][j:j+V], MAC

**Tiled approach (recommended)**:
- Process Mt rows × Lt columns of output per invocation
- For each k chunk: load Mt×chunk of A and chunk×Lt of B, accumulate
- Store Mt×Lt output tile

### FIR / Convolution

**Strategy**: Sliding window with coefficient cycling.

```pseudo
auto coeff_iter = aie::circular_iterator<Lanes>(coeffs, num_taps)
auto data_iter = aie::begin_vector<Lanes>(input_window)
acc = zeros
for (tap = 0; tap < num_taps; tap++) {
    acc = aie::mac(acc, *data_iter++, *coeff_iter++)
}
*out_iter++ = acc.to_vector<OutType>(shift)
// Advance input window by 1 sample, repeat for next output
```

### Element-wise (C = A op B)

**Strategy**: Simple vectorized sweep.

```pseudo
auto iter_a = aie::begin_vector<Lanes>(input_a)
auto iter_b = aie::begin_vector<Lanes>(input_b)
auto iter_c = aie::begin_vector<Lanes>(output_c)
for (i = 0; i < num_elements / Lanes; i++) {
    *iter_c++ = aie::mul(*iter_a++, *iter_b++)  // or add, sub, etc.
}
```

### FFT (Radix-2 Butterfly)

**Strategy**: Butterfly operations with twiddle factor multiplication.

```pseudo
// For each stage s = 0 .. log2(N)-1:
//   For each butterfly group:
//     Load even/odd pairs
//     Multiply odd by twiddle: aie::mul(odd, twiddle)
//     Add/subtract: even + product, even - product
//     Store results
```

---

## Pass to Next Sub-Skill

After producing the vectorization specification, the next step is `matlab-to-aie-kernel`, which takes the loop structure and iterator/intrinsic selections and generates the actual kernel `.h` and `.cpp` files.
