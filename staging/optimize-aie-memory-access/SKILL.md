---
name: optimize-aie-memory-access
description: >-
  Optimizes AI Engine kernel memory access patterns by replacing index-multiply
  address computations (e.g., ptr[i * STRIDE]) with pointer-stride arithmetic
  (pointer increment by a constant each iteration). Eliminates per-iteration
  scalar multiply instructions that consume cycles on the scalar processor.
  Applicable to column-major/row-major matrix traversal, strided array access,
  and nested loops where one index dimension maps to a fixed stride. Use when:
  loop bodies compute element addresses using index * constant multiplications,
  accessing columns of a matrix stored in column-major order, iterating through
  rows of a row-major matrix, or any case where address calculation uses a
  loop-variable multiply. Trigger on: "pointer stride", "avoid multiply",
  "column pointer", "index multiply", "address computation", "pointer increment",
  "memory access optimization", "eliminate scalar multiply".
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
# Optimize AIE: Pointer-Stride Memory Access

Replace index-multiply address computations with pointer-stride increments to
eliminate per-iteration scalar multiply instructions on the AIE scalar processor.

---

## When to Apply

This optimization applies when code computes addresses using **loop index × constant**:

1. **Column access in column-major matrix** (most common):
   ```cpp
   for (unsigned col = 0; col < N; col++) {
       cfloat* p = &M[col * N];  // scalar multiply each iteration
       process(p);
   }
   ```

2. **Nested loops with two index dimensions**:
   ```cpp
   for (unsigned i = 0; i < N; i++) {
       for (unsigned j = i + 1; j < N; j++) {
           cfloat* col_i = &M[i * N];  // multiply in outer loop
           cfloat* col_j = &M[j * N];  // multiply in inner loop
       }
   }
   ```

3. **Strided array access**:
   ```cpp
   for (unsigned k = 0; k < COUNT; k++) {
       process(&buffer[k * STRIDE]);  // multiply each iteration
   }
   ```

---

## Benefits

| Benefit | Description |
|---------|-------------|
| **Eliminates scalar multiply** | Replaces `index * N` with pointer `+= N` (add vs multiply) |
| **Reduces instruction count** | One add instruction vs multiply + add for address computation |
| **Frees scalar ALU** | Multiply unit available for other computations in the same cycle |
| **Better scheduling** | Simpler pointer update allows tighter loop scheduling |

On AIE, a scalar multiply takes 1 cycle but occupies the scalar multiplier unit.
A pointer add takes 1 cycle on the simpler add unit, freeing the multiplier for
data-path computations.

---

## Transformation Patterns

### Pattern 1: Single Loop Column Traversal

**Before:**
```cpp
for (unsigned k = 0; k < N; k++) {
    cfloat* col = &M[k * N];
    // ... use col ...
}
```

**After:**
```cpp
cfloat* col = M;
for (unsigned k = 0; k < N; k++) {
    // ... use col ...
    col += N;
}
```

---

### Pattern 2: Nested Loops (Outer + Inner Stride)

When both loop indices map to column offsets:

**Before:**
```cpp
for (unsigned i = 0; i < N - 1; i++) {
    for (unsigned j = i + 1; j < N; j++) {
        cfloat* col_i = &M[i * N];  // outer index multiply
        cfloat* col_j = &M[j * N];  // inner index multiply
        process(col_i, col_j);
    }
}
```

**After:**
```cpp
cfloat* col_i = M;
for (unsigned i = 0; i < N - 1; i++) {
    cfloat* col_j = col_i + N;  // starts one column past col_i
    for (unsigned j = i + 1; j < N; j++) {
        process(col_i, col_j);
        col_j += N;             // advance to next column
    }
    col_i += N;                 // advance outer pointer
}
```

Key insight: the inner pointer `col_j` is initialized relative to `col_i`
(one column ahead), eliminating the need for any multiply.

---

### Pattern 3: Multiple Arrays with Same Index Pattern

When the same loop indexes into multiple arrays:

**Before:**
```cpp
for (unsigned i = 0; i < N - 1; i++) {
    for (unsigned j = i + 1; j < N; j++) {
        cfloat* col_ai = &A[i * N];
        cfloat* col_aj = &A[j * N];
        cfloat* col_bi = &B[i * N];
        cfloat* col_bj = &B[j * N];
        process(col_ai, col_aj, col_bi, col_bj);
    }
}
```

**After:**
```cpp
cfloat* col_ai = A;
cfloat* col_bi = B;
for (unsigned i = 0; i < N - 1; i++) {
    cfloat* col_aj = col_ai + N;
    cfloat* col_bj = col_bi + N;
    for (unsigned j = i + 1; j < N; j++) {
        process(col_ai, col_aj, col_bi, col_bj);
        col_aj += N;
        col_bj += N;
    }
    col_ai += N;
    col_bi += N;
}
```

---

### Pattern 4: Loop with Early-Exit (continue)

When the inner loop has a `continue` statement, the pointer must still be
advanced on the skip path:

**Before:**
```cpp
for (unsigned j = 0; j < N; j++) {
    cfloat* col = &M[j * N];
    if (skip_condition) continue;
    process(col);
}
```

**After:**
```cpp
cfloat* col = M;
for (unsigned j = 0; j < N; j++) {
    if (skip_condition) { col += N; continue; }
    process(col);
    col += N;
}
```

Alternative (cleaner): advance unconditionally at loop bottom:
```cpp
cfloat* col = M;
for (unsigned j = 0; j < N; j++) {
    if (!skip_condition) {
        process(col);
    }
    col += N;
}
```

---

## When NOT to Apply

| Condition | Reason |
|-----------|--------|
| Index is data-dependent (e.g., `arr[lookup[k] * N]`) | Can't predict stride at compile time |
| Loop accesses non-sequential indices (sorting, permutation) | Stride isn't constant |
| Compiler already strength-reduces the multiply | Check assembly; modern compilers may optimize this |
| Single iteration or very short loop (N ≤ 3) | Overhead of extra pointer variable exceeds benefit |

---

## Verification Checklist

After applying this optimization:

1. **Check `continue` paths**: Every `continue` must still advance the pointer
2. **Check `break` paths**: Pointer state after break must be consistent
3. **Check loop re-entry**: For nested sweeps (outer loop resets), ensure
   pointers are re-initialized at the proper scope
4. **Validate results**: Run x86sim and compare against golden reference

---

## Relationship to Other Skills

- **`optimize-aie-diagonal-matrix-init`**: Uses pointer stride `+= (N+1)` for
  diagonal traversal — a special case of this pattern where stride ≠ column width.
- **`create-kernel-cpp`**: Generated kernel code may use index-multiply patterns
  that can be optimized with this skill post-generation.
- **`extract-aie-loop-ii`**: After applying this optimization, re-extract loop II
  to verify the scalar multiply was eliminated from the critical path.
