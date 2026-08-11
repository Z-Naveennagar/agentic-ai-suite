---
name: optimize-aie-diagonal-matrix-init
description: >-
  Optimizes identity or diagonal matrix initialization in AI Engine kernels by
  replacing scalar nested loops with a two-phase approach: (1) vectorized zero-fill
  of the entire buffer using a single loop with vector stores, then (2) N scalar
  writes to set diagonal elements. Reduces loop overhead from O(N^2) scalar writes
  to O(N^2/LANES) vector writes + O(N) scalar writes. Works for both column-major
  and row-major storage. Use when: initializing identity matrices, diagonal matrices,
  or any sparse-pattern matrix that is mostly zeros with a few non-zero elements at
  known positions. Trigger on: "identity matrix init", "diagonal matrix", "V = I",
  "eye(N)", "initialize identity", "vectorized zero fill".
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
# Optimize AIE: Vectorized Diagonal Matrix Initialization

Replace scalar element-by-element identity/diagonal matrix initialization with a
two-phase approach: vectorized zero-fill followed by scalar diagonal writes.

---

## When to Apply

This optimization applies when code contains any of the following patterns:

1. **Nested loop with conditional** (identity matrix):
   ```cpp
   for (unsigned col = 0; col < N; col++) {
       for (unsigned row = 0; row < N; row++) {
           M[col * N + row] = (row == col) ? cfloat{1.0f, 0.0f} : cfloat{0.0f, 0.0f};
       }
   }
   ```

2. **Nested loop writing a diagonal matrix** (scaled identity):
   ```cpp
   for (unsigned col = 0; col < N; col++) {
       for (unsigned row = 0; row < N; row++) {
           M[col * N + row] = (row == col) ? diag_vals[col] : type{0};
       }
   }
   ```

3. **Any sparse initialization** where most elements are zero and non-zero
   positions are computed from a simple formula.

---

## Benefits

| Benefit | Description |
|---------|-------------|
| **Reduced iteration count** | From N×N scalar writes to N²/LANES vector writes + N scalar writes |
| **Better pipeline utilization** | Zero-fill loop achieves II=1 with `chess_prepare_for_pipelining` |
| **Eliminates branch** | No conditional (ternary) in the inner loop body |
| **No index multiply** | Pointer stride avoids per-iteration `k * N` scalar multiply |
| **Compiler friendliness** | Simple single-purpose loops are easier for the scheduler to optimize |

For a 16×16 cfloat matrix with 4 lanes: 256 scalar writes → 64 vector writes + 16 scalar writes (69% fewer iterations).

---

## Transformation Pattern

### Before (scalar with conditional):

```cpp
// Column-major identity initialization
for (unsigned col = 0; col < N; col++) {
    for (unsigned row = 0; row < N; row++) {
        V[col * N + row] = (row == col) ? cfloat{1.0f, 0.0f} : cfloat{0.0f, 0.0f};
    }
}
```

### After (vectorized zero-fill + scalar diagonal):

```cpp
// Phase 1: Vectorized zero-fill
{
    aie::vector<cfloat, LANES> vzero = aie::zeros<cfloat, LANES>();
    cfloat* pV = V;
    for (unsigned i = 0; i < NN / LANES; i++)
        chess_prepare_for_pipelining
    {
        aie::store_v(pV, vzero);
        pV += LANES;
    }
}
// Phase 2: Set diagonal via pointer stride (avoids index multiply)
cfloat* pDiag = V;
for (unsigned k = 0; k < N; k++) {
    *pDiag = cfloat{1.0f, 0.0f};
    pDiag += (N + 1);  // stride to next diagonal element
}
```

---

## Storage Layout Variants

### Column-Major (Fortran order)

Matrix element (row, col) is stored at index `col * N + row`.
Diagonal element (k, k) is at index `k * N + k = k * (N + 1)`.

```cpp
// Pointer stride = N + 1 (avoids per-iteration index multiply)
type* pDiag = M;
for (unsigned k = 0; k < N; k++) {
    *pDiag = diag_value;
    pDiag += (N + 1);
}
```

### Row-Major (C order)

Matrix element (row, col) is stored at index `row * N + col`.
Diagonal element (k, k) is at index `k * N + k = k * (N + 1)`.

```cpp
// Same pointer stride for square matrices
type* pDiag = M;
for (unsigned k = 0; k < N; k++) {
    *pDiag = diag_value;
    pDiag += (N + 1);
}
```

Note: For square matrices, the diagonal index formula `k * (N + 1)` is identical
regardless of row-major or column-major storage.

---

## Generalized Diagonal Matrix

When diagonal values vary (not identity):

```cpp
// Phase 1: Vectorized zero-fill (same as above)
{
    aie::vector<type, LANES> vzero = aie::zeros<type, LANES>();
    type* pM = M;
    for (unsigned i = 0; i < NN / LANES; i++)
        chess_prepare_for_pipelining
    {
        aie::store_v(pM, vzero);
        pM += LANES;
    }
}
// Phase 2: Set diagonal from an array of values via pointer stride
type* pDiag = M;
for (unsigned k = 0; k < N; k++) {
    *pDiag = diag_vals[k];
    pDiag += (N + 1);
}
```

---

## Data Type Reference

| Type | Lanes (256-bit) | NN/LANES for 16×16 |
|------|-----------------|---------------------|
| `cfloat` (64-bit) | 4 | 64 |
| `float` (32-bit) | 8 | 32 |
| `int32` (32-bit) | 8 | 32 |
| `cint16` (32-bit) | 8 | 32 |
| `int16` (16-bit) | 16 | 16 |
| `cint32` (64-bit) | 4 | 64 |

---

## Decision Points

| Condition | Recommendation |
|-----------|---------------|
| N² ≤ LANES (tiny matrix) | Keep scalar — not worth vectorizing |
| Matrix is dense (most elements non-zero) | Don't use this pattern — fill directly |
| Matrix is identity (all 1's on diagonal) | Use this pattern with constant `{1.0f, 0.0f}` |
| Matrix is scaled identity (λI) | Use this pattern with scalar `λ` on diagonal |
| Matrix is general diagonal | Use this pattern with `diag_vals[k]` array |
| Buffer is a registered parameter | Zero-fill may not be needed if buffer persists between calls — check algorithm requirements |

---

## Relationship to Other Skills

- **`create-kernel-cpp`**: The generated `run()` method may include identity
  initialization that can be optimized with this pattern.
- **`matlab-to-aie-kernel`**: MATLAB `eye(N)` translates to identity
  initialization — apply this optimization in the generated code.
- **`optimize-aie-buffers-to-parameters`**: When buffers are moved to registered
  parameters, they persist across invocations. If V is reinitialized every call,
  this vectorized init is still needed regardless of buffer placement.
