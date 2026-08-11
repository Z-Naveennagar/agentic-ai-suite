---
name: optimize-aie-diagonal-matrix-extract
description: >-
  Extracts the diagonal of a matrix stored in column-major (or row-major) order
  using a single scalar for loop with a strided pointer. Replaces nested loops
  or index-multiply expressions (e.g., M[k * N + k] or vector packing with temp
  arrays) with a simple N-iteration loop that reads/writes diagonal elements using
  pointer arithmetic with stride (N+1). Applicable to: writing diagonal values to
  an output buffer, extracting diagonals into a vector, or streaming diagonal
  elements to a PLIO output. Use when: outputting singular values, extracting
  eigenvalues from a diagonal matrix, or reading/writing the diagonal of any NxN
  matrix stored contiguously. Trigger on: "extract diagonal", "diagonal output",
  "write diagonal", "singular values output", "diagonal to vector", "stream diagonal".
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
# Optimize AIE: Diagonal Matrix Extraction via Strided Pointer

Extract or write diagonal elements from a matrix (or flat array) using a single
scalar loop with pointer-stride arithmetic, eliminating index-multiply overhead
and unnecessary temp arrays.

---

## When to Apply

This optimization applies when code does any of the following:

1. **Packs diagonal values through a temp array and nested loops:**
   ```cpp
   for (unsigned i = 0; i < N / LANES; i++) {
       alignas(32) cfloat tmp[LANES];
       for (unsigned l = 0; l < LANES; l++) {
           tmp[l] = {vals[i * LANES + l], 0.0f};  // index multiply!
       }
       *pOut++ = aie::load_v<LANES>(tmp);
   }
   ```

2. **Accesses diagonal elements using index multiplication:**
   ```cpp
   for (unsigned k = 0; k < N; k++) {
       diag[k] = M[k * N + k];  // multiply per iteration
   }
   ```

3. **Extracts a diagonal from a full NxN matrix:**
   ```cpp
   for (unsigned k = 0; k < N; k++) {
       output[k] = matrix[k * (N + 1)];  // still a multiply
   }
   ```

---

## Benefits

| Benefit | Description |
|---------|-------------|
| **Eliminates temp array** | No intermediate buffer allocation on stack |
| **Removes nested loop** | Single N-iteration loop vs nested (N/LANES × LANES) |
| **No index multiply** | Pointer stride avoids `k * N` or `i * LANES + l` |
| **Simpler scheduling** | Compiler can more easily pipeline a single flat loop |

---

## Transformation Patterns

### Pattern 1: Write Flat Array to Output Buffer as cfloat

When source is a contiguous `float[N]` array and destination is a cfloat output
buffer (common for singular values, eigenvalues):

**Before (nested loop + temp array):**
```cpp
for (unsigned i = 0; i < N / LANES; i++)
    chess_prepare_for_pipelining
{
    alignas(32) cfloat s_tmp[LANES];
    for (unsigned l = 0; l < LANES; l++) {
        s_tmp[l] = {S_vals[i * LANES + l], 0.0f};
    }
    *pOut++ = aie::load_v<LANES>(s_tmp);
}
```

**After (single scalar loop with strided pointer):**
```cpp
auto pS = aie::begin(out);
pS += OFFSET;  // advance to correct position in output buffer
float* pSrc = S_vals;
for (unsigned k = 0; k < N; k++) {
    *pS++ = cfloat{*pSrc++, 0.0f};
}
```

---

### Pattern 2: Extract Diagonal from Column-Major Matrix

When extracting diagonal elements from a full NxN matrix into a vector:

**Before (index multiply):**
```cpp
for (unsigned k = 0; k < N; k++) {
    diag[k] = M[k * N + k];  // scalar multiply each iteration
}
```

**After (strided pointer, stride = N+1):**
```cpp
cfloat* pSrc = M;
cfloat* pDst = diag;
for (unsigned k = 0; k < N; k++) {
    *pDst++ = *pSrc;
    pSrc += (N + 1);  // diagonal stride for column-major
}
```

---

### Pattern 3: Write Diagonal to Output Stream

When writing diagonal elements directly to a PLIO output buffer:

**Before:**
```cpp
for (unsigned k = 0; k < N; k++) {
    output_buffer[offset + k] = matrix[k * N + k];
}
```

**After:**
```cpp
auto pOut = aie::begin(out);
pOut += offset;
cfloat* pSrc = matrix;
for (unsigned k = 0; k < N; k++) {
    *pOut++ = *pSrc;
    pSrc += (N + 1);
}
```

---

### Pattern 4: Extract Diagonal of Conceptual Diagonal Matrix

When the diagonal is already stored as a flat 1D array (e.g., singular values)
and needs to be written to output with type conversion:

```cpp
// Source: float S_vals[N] (real singular values)
// Destination: output buffer expecting cfloat (complex format)
auto pOut = aie::begin(out);
pOut += offset;
float* pSrc = S_vals;
for (unsigned k = 0; k < N; k++) {
    *pOut++ = cfloat{*pSrc++, 0.0f};
}
```

No stride needed on source (flat array) — just sequential pointer increment.

---

## Output Buffer Access Patterns

When writing to an `output_buffer`, use the appropriate iterator:

| Access Pattern | Iterator | Usage |
|----------------|----------|-------|
| Scalar (1 element at a time) | `aie::begin(out)` | Diagonal extraction, sparse writes |
| Vector (LANES elements at a time) | `aie::begin_restrict_vector<LANES>(out)` | Bulk contiguous writes |

For mixed access (vector for bulk, scalar for diagonal), use separate scoped
iterators to avoid restrict aliasing issues:

```cpp
// Bulk write (vectorized)
{
    auto pVec = aie::begin_restrict_vector<LANES>(out);
    // ... vector writes ...
}

// Sparse/diagonal write (scalar)
{
    auto pScalar = aie::begin(out);
    pScalar += offset;
    // ... scalar writes ...
}

// Another bulk write (vectorized, different offset)
{
    auto pVec = aie::begin_restrict_vector<LANES>(out);
    pVec += vector_offset;
    // ... vector writes ...
}
```

---

## Diagonal Stride Reference

| Storage Order | Matrix Element (row, col) | Diagonal Index | Stride |
|---------------|--------------------------|----------------|--------|
| Column-major | `col * N + row` | `k * N + k` | N + 1 |
| Row-major | `row * N + col` | `k * N + k` | N + 1 |

Note: For square matrices, the diagonal stride is always **N + 1** regardless
of storage order.

---

## Relationship to Other Skills

- **`optimize-aie-diagonal-matrix-init`**: The inverse operation — writes to
  diagonal positions. Uses the same N+1 stride pattern.
- **`optimize-aie-memory-access`**: General pointer-stride pattern that this
  skill specializes for diagonal access.
- **`optimize-aie-scalar-divide`**: Often combined when extracting singular
  values that are computed via `aie::inv()` or `aie::invsqrt()`.
