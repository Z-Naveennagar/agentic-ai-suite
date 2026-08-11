---
name: matlab-to-aie-kernel
description: >-
  Generates AI Engine kernel source files (.h and .cpp) from the vectorization
  specification produced by matlab-to-aie-vectorize. Creates kernel class with
  proper port declarations, constructor, and run() method containing vectorized
  for-loops with embedded AIE API iterators and SIMD intrinsics (aie::mul,
  aie::mac, aie::add, etc.). Use when: generating the actual C++ kernel
  implementation for an AI Engine design ported from MATLAB.
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# MATLAB-to-AIE: Kernel

Generate kernel header (.h) and source (.cpp) files implementing the vectorized AIE computation.

---

## Prerequisites

- Vectorization specification from `matlab-to-aie-vectorize` is available
- Target architecture and data types are determined
- The calling meta-skill's `references/api-intrinsics.md` and `references/iterators.md` have been loaded for architecture-specific syntax

---

## Workflow

### Step 1: Determine Kernel Interface

From the vectorization specification, determine:

1. **Kernel name**: Derived from the MATLAB function name (e.g., `gemm` → `GemmKernel`)
2. **Template parameters**: Dimensions that should be configurable (M, N, L, etc.)
3. **Input ports**: One per input buffer/stream
4. **Output ports**: One per output buffer/stream
5. **Port types**: `input_buffer<T>` / `output_buffer<T>` for windowed I/O, or `input_stream<T>` / `output_stream<T>` for streaming

**Port sizing rules**:
- Buffer size = number of elements per kernel invocation × sizeof(element)
- For tiled GEMM: input_A = Mt × N elements, input_B = N × Lt elements, output_C = Mt × Lt elements
- For FIR: input = window_size + num_taps - 1 elements, output = window_size elements

### Step 2: Generate Kernel Header (.h)

Create the kernel header file with the following structure.
**This must follow the `create-kernel-hpp` foundational skill pattern.**

```cpp
// <kernel_name>.h
// AI Engine kernel ported from MATLAB: <matlab_function_name>.m
// Target architecture: <AIE | AIE-ML | AIE-ML v2>
//
// Copyright (C) <year>, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

#pragma once
#include <adf.h>
#include <aie_api/aie.hpp>
#include <aie_api/utils.hpp>
using namespace adf;

class KernelName {
public:
    // Port sizing definitions (one per port)
    static constexpr unsigned NSAMP_IN_A  = Mt * N;    // # elements per invocation
    static constexpr unsigned NSAMP_IN_B  = N * Lt;
    static constexpr unsigned NSAMP_OUT_C = Mt * Lt;

    // Constructor:
    KernelName(void);

    // Kernel Signature:
    void run(input_buffer<float>& __restrict in_A,
             input_buffer<float>& __restrict in_B,
             output_buffer<float>& __restrict out_C);

    // Register Kernel:
    static void registerKernelClass(void)
    {
        REGISTER_FUNCTION(KernelName::run);
    }
};
```

**CRITICAL rules for the header** (aligned to `create-kernel-hpp`):
- Always use `#pragma once` for include guards
- Always include `<adf.h>`, `<aie_api/aie.hpp>`, and `<aie_api/utils.hpp>`
- Always add `using namespace adf;` after the includes
- Use `.h` extension for the header file (not `.hpp`)
- Define port sizing as `static constexpr unsigned NSAMP_<PORTNAME>` class members
- Always define a constructor (even if the body is simple)
- Buffer ports use `input_buffer<T>&` / `output_buffer<T>&` without template `extents<>` — the graph sets buffer dimensions
- Use `__restrict` on buffer references to enable compiler optimization
- `registerKernelClass()` must use `REGISTER_FUNCTION` macro
- If the kernel requires lookup tables, follow the LUT pattern from `create-kernel-hpp`

### Step 3: Generate Kernel Source (.cpp)

Create the kernel source file implementing the vectorized computation.
**This must follow the `create-kernel-cpp` foundational skill pattern.**

```cpp
// <kernel_name>.cpp
// AI Engine kernel implementation
// Ported from MATLAB: <matlab_function_name>.m
//
// Copyright (C) <year>, Advanced Micro Devices, Inc. All rights reserved.
// SPDX-License-Identifier: MIT

#include <adf.h>
#include <aie_api/aie.hpp>
#include <aie_api/utils.hpp>
#include "<kernel_name>.h"

// ------------------------------------------------------------
// Constructor
// ------------------------------------------------------------

KernelName::KernelName(void)
{
    aie::set_rounding(aie::rounding_mode::conv_even);
    aie::set_saturation(aie::saturation_mode::saturate);
}

// ------------------------------------------------------------
// Run
// ------------------------------------------------------------

void KernelName::run(
    input_buffer<float>& __restrict in_A,
    input_buffer<float>& __restrict in_B,
    output_buffer<float>& __restrict out_C)
{
    constexpr unsigned LANES = 8;  // 256-bit / 32-bit

    // === Iterator declarations ===
    auto pA = aie::begin_vector<LANES>(in_A);
    auto pB = aie::begin_vector<LANES>(in_B);
    auto pC = aie::begin_vector<LANES>(out_C);

    // === Outer loop: iterate over output tiles ===
    for (unsigned i = 0; i < OUTER_BOUND; i++)
        chess_prepare_for_pipelining
    {
        // === Initialize accumulator ===
        aie::accum<accfloat, LANES> acc;
        acc = aie::zeros<accfloat, LANES>();

        // === Inner loop: vectorized compute ===
        for (unsigned k = 0; k < INNER_BOUND; k++)
            chess_prepare_for_pipelining
        {
            // Load vectors via iterators
            auto vec_a = *pA++;
            auto vec_b = *pB++;

            // Vectorized MAC
            acc = aie::mac(acc, vec_a, vec_b);
        }

        // === Store result via output iterator ===
        *pC++ = acc.to_vector<float>(SHIFT);  // fixed-point
        // OR: *pC++ = acc.to_vector<float>();  // floating-point
    }
}
```

**CRITICAL code generation rules** (aligned to `create-kernel-cpp`):

1. **Always include a constructor** that sets `aie::set_rounding()` and `aie::set_saturation()` — this ensures deterministic fixed-point behavior even for floating-point kernels
2. **All memory access via iterators** — NEVER use raw `ptr[index]` style addressing
3. **`chess_prepare_for_pipelining`** — Add to every inner loop to enable software pipelining
4. **Accumulator initialization** — Always zero-initialize before accumulation loops
5. **Accumulator-to-vector conversion**:
   - Fixed-point: `.to_vector<T>(shift)` where shift = number of fractional bits to discard
   - Floating-point: `.to_vector<T>()` (no shift needed)
6. **Loop bounds must be compile-time constants or class constexpr members** for best performance
7. **No dynamic memory allocation** — All buffers are port-provided
8. **Include files**: `<adf.h>`, `<aie_api/aie.hpp>`, `<aie_api/utils.hpp>`, and the kernel `.h` header
9. **Use `.cpp` extension** for the source file

### Step 4: Handle Architecture-Specific Patterns

Consult the loaded `references/api-intrinsics.md` for the target architecture to ensure:

- Correct intrinsic function signatures (may differ between AIE generations)
- Correct accumulator types and widths
- Correct vector lane counts
- Any architecture-specific pragmas or attributes

**AIE-specific considerations**:
- 256-bit vectors (8 × float, 16 × int16, 4 × cfloat)
- `acc48` for int16 MAC, `accfloat` for float MAC
- Use `chess_separator_scheduler()` between independent operations if needed

**AIE-ML specific considerations**:
- 512-bit vectors (16 × float, 32 × int16, 32 × bfloat16)
- Memory tile DMA for large data transfers
- Sparse matrix support intrinsics available
- `bfloat16` native type support

**AIE-ML v2 specific considerations**:
- 512-bit vectors with fp32 vector MAC support
- Enhanced shuffle/permute operations
- Larger local memory (64KB)

### Step 5: Add Pragmas and Optimization Hints

Based on the operation type, add appropriate optimization pragmas:

```cpp
// For latency-critical inner loops:
chess_prepare_for_pipelining
chess_loop_range(MIN, MAX)

// For memory access disambiguation:
// Use aie::begin_restrict_vector<LANES>() for all buffer iterators
// Use __restrict on all buffer parameters

// For loop unrolling (when trip count is small and known):
chess_unroll_loop(FACTOR)
```

### Step 6: Apply Optimization Skills

After generating the initial kernel code, review it against the following optimization
skills and apply any that are relevant to the MATLAB algorithm being ported. Apply these
optimizations directly during code generation — do NOT generate unoptimized code first.

#### 6a. Replace Division with aie::inv() (`optimize-aie-scalar-divide`)

**When to apply**: The MATLAB source contains division operations on runtime-computed
values (e.g., normalization: `x / norm`, ratios: `tau = (a - b) / (2 * c)`,
reciprocals: `1 / x`).

**Action**: In the generated kernel code, replace:
- `x / y` → `x * aie::inv(y)`
- `1.0f / y` → `aie::inv(y)`
- `1.0f / sqrt(x)` → `aie::invsqrt(x)` (single hardware op)

**Do NOT apply** when the divisor is a compile-time constant (the compiler already
optimizes to multiply-by-reciprocal), or when exact IEEE-754 division is required.

See skill `optimize-aie-scalar-divide` for the full pattern and precision characteristics.

#### 6b. Use Pointer-Stride Memory Access (`optimize-aie-memory-access`)

**When to apply**: The generated kernel contains loops that compute memory addresses
using index-multiply expressions, such as:
- Column access in column-major matrix: `&M[col * N]`
- Strided array traversal: `buffer[k * STRIDE]`
- Nested loops with two index dimensions mapping to matrix columns

**Action**: Replace index-multiply address computation with pointer-stride increments:
```cpp
// Before: cfloat* col = &M[k * N];   (scalar multiply each iteration)
// After:
cfloat* col = M;
for (...) {
    // use col
    col += N;  // pointer increment replaces multiply
}
```

For nested loops with inner pointer depending on outer, initialize inner pointer
relative to outer (e.g., `col_j = col_i + N`) to eliminate all multiplies.

See skill `optimize-aie-memory-access` for all transformation patterns including
loops with `continue` or `break`.

#### 6c. Vectorized Diagonal Matrix Initialization (`optimize-aie-diagonal-matrix-init`)

**When to apply**: The MATLAB source uses `eye(N)`, `diag(v)`, or initializes a
matrix with values only on the diagonal (common in SVD, eigenvalue decomposition,
Cholesky factorization initialization).

**Action**: Generate a two-phase initialization:
1. Vectorized zero-fill of the entire buffer using `aie::zeros<T, LANES>()` + `aie::store_v()`
2. Scalar diagonal writes using pointer stride `+= (N + 1)`

```cpp
// Phase 1: Vectorized zero-fill
aie::vector<cfloat, LANES> vzero = aie::zeros<cfloat, LANES>();
cfloat* pV = V;
for (unsigned i = 0; i < NN / LANES; i++) chess_prepare_for_pipelining {
    aie::store_v(pV, vzero);
    pV += LANES;
}
// Phase 2: Set diagonal via pointer stride
cfloat* pDiag = V;
for (unsigned k = 0; k < N; k++) {
    *pDiag = cfloat{1.0f, 0.0f};
    pDiag += (N + 1);
}
```

See skill `optimize-aie-diagonal-matrix-init` for data type reference and decision points.

#### 6d. Diagonal Matrix Extraction (`optimize-aie-diagonal-matrix-extract`)

**When to apply**: The MATLAB source extracts diagonal elements (`diag(A)`,
`S = diag(sigma)`), writes singular values, or outputs eigenvalues from a matrix.

**Action**: Use a single scalar loop with strided pointer `+= (N + 1)` instead of
nested loops or index-multiply expressions:

```cpp
// Extract diagonal from NxN matrix M into output
cfloat* pSrc = M;
for (unsigned k = 0; k < N; k++) {
    *pOut++ = *pSrc;
    pSrc += (N + 1);  // diagonal stride
}
```

See skill `optimize-aie-diagonal-matrix-extract` for patterns involving type
conversion (float→cfloat) and output buffer iterators.

#### 6e. Move Large Buffers to Registered Parameters (`optimize-aie-buffers-to-parameters`)

**When to apply**: The generated kernel `run()` method declares large `alignas` arrays
on the stack (total > 256 bytes), OR the algorithm requires working buffers that would
inflate `stacksize` in aie.cfg, OR the user needs placement control over buffers for
memory banking optimization.

**Action**:
1. Move `alignas(32) type buffer[SIZE]` declarations from `run()` to class data members
   declared as array references: `alignas(32) type (&buf)[SIZE];`
2. Add `REGISTER_PARAMETER(buf)` in `registerKernelClass()`
3. Update constructor to accept array references
4. Update graph to pass `std::vector<type>` via `kernel::create_object<>()`
5. Reduce `stacksize` in aie.cfg back to default (2048)

**NOTE**: When this optimization is applied, also update the graph header file
(generated by `matlab-to-aie-graph`) to declare the backing vectors and pass them
to the kernel constructor.

See skill `optimize-aie-buffers-to-parameters` for complete header/source/graph
transformation patterns and constraint file placement control.

#### 6f. Split Accumulator for MAC-Bound Loops (`optimize-aie-split-accumulator`)

**When to apply**: The kernel contains an inner loop with `acc = aie::mac(acc, ...)`
where the MAC feedback latency exceeds the resource minimum:
- AIE (1st gen): 4-cycle fpmac latency vs resource_min=2 → apply with N=2
- AIE-ML: 4-cycle fpmac latency vs resource_min=2 → apply with N=2
- AIE-ML v2: 2-cycle fpmac latency vs resource_min=1 → apply with N=2

**Action**: Split into N=2 independent accumulators with a 2x-unrolled loop body:
```cpp
aie::accum<accfloat, LANES> acc0, acc1;
acc0 = aie::zeros<accfloat, LANES>();
acc1 = aie::zeros<accfloat, LANES>();
for (unsigned k = 0; k < N; k += 2) chess_prepare_for_pipelining {
    // Even → acc0
    acc0 = aie::mac(acc0, ...);
    // Odd → acc1
    acc1 = aie::mac(acc1, ...);
}
auto result = aie::add(acc0.to_vector<float>(), acc1.to_vector<float>());
```

**Do NOT apply** when the loop is already resource-limited, or when N=4 is tempting
(N=4 is empirically worse for broadcast-scalar × vector GEMM patterns on AIE1).

See skill `optimize-aie-split-accumulator` for full pattern, verification steps,
and expected improvement tables.

---

### Optimization Applicability by MATLAB Pattern

| MATLAB Pattern | Applicable Optimization Skills |
|---|---|
| `A * B` (GEMM) | split-accumulator, memory-access, buffers-to-parameters |
| `eye(N)`, `V = I` | diagonal-matrix-init |
| `diag(A)`, `svd` output | diagonal-matrix-extract |
| `x / y`, `1/norm` | scalar-divide |
| `chol(A)` (Cholesky) | scalar-divide, memory-access, buffers-to-parameters |
| `svd(A)` (Jacobi SVD) | scalar-divide, diagonal-matrix-init, diagonal-matrix-extract, memory-access, buffers-to-parameters |
| `conv(x, h)` (FIR) | split-accumulator |
| Element-wise with division | scalar-divide |
| Large working arrays | buffers-to-parameters |

### Step 7: Validate Generated Code

Before presenting the kernel to the user, verify:

1. All parameters are used consistently between .h and .cpp
2. Buffer sizes match the analysis report dimensions
3. Iterator types match the access patterns from vectorization spec
4. Accumulator type matches the data type and architecture
5. Loop bounds are consistent with tiling strategy
6. No raw pointer arithmetic is used (all access via iterators)

---

## Output Files

The kernel sub-skill produces two files:

1. **`<kernel_name>.h`** — Kernel class declaration with ports, sizing, and registration
2. **`<kernel_name>.cpp`** — Kernel implementation with constructor + vectorized loops

These files are placed in the user's project directory (typically the project root).

---

## Pass to Next Sub-Skill

After generating kernel files, the next step is `matlab-to-aie-graph`, which creates the graph definition, application wrapper, compiler configuration, and Makefile.
