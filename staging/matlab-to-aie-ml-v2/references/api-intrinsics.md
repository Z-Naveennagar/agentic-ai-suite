<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# AIE-ML v2 API Intrinsics Reference

## Overview

AIE-ML v2 uses the same AIE API as AIE-ML. The key difference is **improved throughput** for fp32 operations and **enhanced shuffle/permute** — the intrinsic function signatures are identical.

---

## Vector Arithmetic (Same API as AIE-ML)

### Multiply

```cpp
// Vector × Vector — 512-bit vectors (same syntax as AIE-ML)
aie::vector<float, 16> c = aie::mul(a, b);           // 16 float lanes — FULL THROUGHPUT on v2
aie::accum<acc64, 32> acc = aie::mul(a, b);           // 32 int16 lanes
aie::accum<accfloat, 32> acc = aie::mul(a, b);        // 32 bfloat16 lanes

// Vector × Scalar
aie::vector<float, 16> c = aie::mul(a, scalar);
```

### Multiply-Accumulate (MAC) — Key fp32 Improvement

```cpp
// fp32 MAC — full throughput on AIE-ML v2 (16 MACs/cycle sustained)
aie::accum<accfloat, 16> acc = aie::zeros<accfloat, 16>();
acc = aie::mac(acc, vec_a, vec_b);   // No pipeline bubbles on v2!

// bfloat16 MAC (same as AIE-ML)
aie::accum<accfloat, 32> acc = aie::zeros<accfloat, 32>();
acc = aie::mac(acc, bf16_a, bf16_b);  // 32 bfloat16 lanes

// int16 MAC (same as AIE-ML)
aie::accum<acc64, 32> acc = aie::zeros<acc64, 32>();
acc = aie::mac(acc, int16_a, int16_b);  // 32 int16 lanes
```

**AIE-ML v2 advantage**: On AIE-ML (2nd gen), back-to-back fp32 MACs could have pipeline stalls in certain patterns. On AIE-ML v2, fp32 vector MAC achieves sustained peak throughput without pipeline bubbles.

### Addition / Subtraction

```cpp
aie::vector<float, 16> c = aie::add(a, b);
aie::vector<bfloat16, 32> c = aie::add(a, b);
aie::vector<int16, 32> c = aie::add(a, b);
aie::vector<float, 16> c = aie::sub(a, b);
```

### Accumulator Operations

```cpp
// Same API as AIE-ML
aie::accum<accfloat, 16> acc = aie::zeros<accfloat, 16>();
aie::vector<float, 16> result = acc.to_vector<float>();
aie::vector<bfloat16, 32> result = acc.to_vector<bfloat16>();
aie::vector<int16, 32> result = acc.to_vector<int16>(SHIFT);
```

### Reduction

```cpp
float sum = aie::reduce_add(vec);
float min_val = aie::reduce_min(vec);
float max_val = aie::reduce_max(vec);
```

### Comparison / Selection

```cpp
aie::vector<float, 16> c = aie::max(a, b);
aie::vector<float, 16> c = aie::min(a, b);
aie::vector<float, 16> c = aie::abs(a);
aie::mask<16> m = aie::lt(a, b);
aie::vector<float, 16> c = aie::select(a, b, m);
```

## Enhanced Shuffle/Permute (AIE-ML v2 Improved)

The API is the same but executes faster on AIE-ML v2:

```cpp
// Interleave two vectors: take alternating elements
auto [even, odd] = aie::interleave_zip(vec_a, vec_b, 1);

// Deinterleave: split interleaved data
auto [part_a, part_b] = aie::interleave_unzip(vec, 1);

// Shuffle with custom pattern
auto result = aie::shuffle_down(vec, shift_amount);
auto result = aie::shuffle_up(vec, shift_amount);

// Rotate elements within vector
auto result = aie::shuffle_down_rotate(vec, rotate_amount);
```

**AIE-ML v2 advantage**: These shuffle operations have **reduced latency** compared to AIE-ML, making data reorganization (e.g., matrix transpose) more efficient.

### Matrix Transpose Pattern (leveraging enhanced shuffle)

```cpp
// Transpose a 4×4 float block using shuffles (more efficient on v2)
// Load 4 rows:
auto row0 = *pA++;  // [a00, a01, a02, a03, ...]
auto row1 = *pA++;  // [a10, a11, a12, a13, ...]
auto row2 = *pA++;  // [a20, a21, a22, a23, ...]
auto row3 = *pA++;  // [a30, a31, a32, a33, ...]

// Interleave to form columns (enhanced shuffle speed on v2)
auto [t0, t1] = aie::interleave_zip(row0, row2, 1);
auto [t2, t3] = aie::interleave_zip(row1, row3, 1);
auto [col0, col2] = aie::interleave_zip(t0, t2, 1);
auto [col1, col3] = aie::interleave_zip(t1, t3, 1);
```

## bfloat16 Operations (Same as AIE-ML)

```cpp
aie::accum<accfloat, 32> acc = aie::zeros<accfloat, 32>();
acc = aie::mac(acc, bf16_a, bf16_b);
aie::vector<bfloat16, 32> result = acc.to_vector<bfloat16>();

// Type conversion
aie::vector<bfloat16, 32> bf = aie::to_bfloat16(float_vec_lo, float_vec_hi);
aie::vector<float, 16> f = aie::to_float(bfloat_vec);
```

## Sparse Matrix Operations (Same as AIE-ML)

```cpp
acc = aie::mac(acc, sparse_a, dense_b);
```

## Type Conversion

```cpp
aie::vector<int16, 32> i = aie::to_fixed<int16>(float_vec, FRAC_BITS);
aie::vector<float, 16> f = aie::to_float(int_vec, FRAC_BITS);
aie::vector<bfloat16, 32> bf = aie::to_bfloat16(float_vec_lo, float_vec_hi);
```

---

## TODO: Fill in AIE-ML v2 specific intrinsics

<!--
Add here:
- Any new intrinsics unique to AIE-ML v2 (not in AIE-ML)
- Detailed shuffle/permute operation set with cycle counts
- fp32 MAC pipeline details (what enables full throughput)
- Any updated intrinsic signatures or new overloads
-->
