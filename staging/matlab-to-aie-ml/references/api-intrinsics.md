<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# AIE-ML API Intrinsics Reference

## Vector Arithmetic

All intrinsics use 512-bit vectors on AIE-ML (doubled from AIE's 256-bit).

### Multiply

```cpp
// Vector × Vector (element-wise) — 512-bit vectors
aie::vector<float, 16> c = aie::mul(a, b);           // 16 float lanes
aie::accum<acc64, 32> acc = aie::mul(a, b);           // 32 int16 lanes → acc64
aie::accum<accfloat, 32> acc = aie::mul(a, b);        // 32 bfloat16 lanes → accfloat

// Vector × Scalar (broadcast)
aie::vector<float, 16> c = aie::mul(a, scalar);
aie::accum<acc64, 32> acc = aie::mul(a, scalar);      // int16 vec × int16 scalar
```

### Multiply-Accumulate (MAC)

```cpp
// Accumulate: acc += a * b
acc = aie::mac(acc, a, b);        // acc64 += int16 × int16 (32 lanes)
acc = aie::mac(acc, a, b);        // accfloat += float × float (16 lanes)
acc = aie::mac(acc, a, b);        // accfloat += bfloat16 × bfloat16 (32 lanes)
acc = aie::mac(acc, a, b);        // cacc64 += cint16 × cint16 (16 lanes)

// Multiply-subtract: acc -= a * b
acc = aie::msc(acc, a, b);
```

### bfloat16 Operations (AIE-ML specific)

```cpp
// bfloat16 multiply-accumulate — accumulates in float precision
aie::accum<accfloat, 32> acc = aie::zeros<accfloat, 32>();
aie::vector<bfloat16, 32> a = *pA++;
aie::vector<bfloat16, 32> b = *pB++;
acc = aie::mac(acc, a, b);

// Convert accumulator to bfloat16 output
aie::vector<bfloat16, 32> result = acc.to_vector<bfloat16>();

// Convert float ↔ bfloat16
aie::vector<bfloat16, 32> bf = aie::to_bfloat16(float_vec);
aie::vector<float, 16> f = aie::to_float(bfloat_vec);  // only converts first 16
```

### Addition / Subtraction

```cpp
aie::vector<float, 16> c = aie::add(a, b);       // 16 float lanes
aie::vector<int16, 32> c = aie::add(a, b);       // 32 int16 lanes
aie::vector<bfloat16, 32> c = aie::add(a, b);    // 32 bfloat16 lanes
aie::vector<float, 16> c = aie::sub(a, b);
```

### Accumulator Operations

```cpp
// Initialize to zero
aie::accum<acc64, 32> acc;
acc = aie::zeros<acc64, 32>();       // 32-lane int accumulator
aie::accum<accfloat, 16> acc;
acc = aie::zeros<accfloat, 16>();    // 16-lane float accumulator
aie::accum<accfloat, 32> acc;
acc = aie::zeros<accfloat, 32>();    // 32-lane bfloat16→float accumulator

// Convert accumulator to vector
aie::vector<int16, 32> result = acc.to_vector<int16>(SHIFT);   // fixed-point
aie::vector<float, 16> result = acc.to_vector<float>();         // float
aie::vector<bfloat16, 32> result = acc.to_vector<bfloat16>();   // bfloat16

// Accumulator from vector
acc.from_vector(vec, SHIFT);
```

### Reduction

```cpp
float sum = aie::reduce_add(vec);           // float 16-lane → scalar
int32_t sum = aie::reduce_add(vec);         // int16 32-lane → int32 scalar
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

### Shift (Fixed-Point)

```cpp
aie::vector<int16, 32> c = aie::downshift(a, SHIFT);
aie::vector<int16, 32> c = aie::upshift(a, SHIFT);
```

## Sparse Matrix Operations (AIE-ML specific)

```cpp
// Sparse MAC — automatically skips zero elements
// Requires sparse encoding format for one operand
acc = aie::mac(acc, sparse_a, dense_b);  // sparse × dense
```

**Sparse encoding**: One operand uses compressed format where zeros are skipped. The hardware decodes and aligns non-zero elements automatically.

## Type Conversion

```cpp
// Float ↔ bfloat16
aie::vector<bfloat16, 32> bf = aie::to_bfloat16(float_vec_lo, float_vec_hi);
aie::vector<float, 16> f = aie::to_float(bfloat_vec);

// Float ↔ integer
aie::vector<int16, 32> i = aie::to_fixed<int16>(float_vec, FRAC_BITS);
aie::vector<float, 16> f = aie::to_float(int_vec, FRAC_BITS);
```

---

## TODO: Fill in additional AIE-ML intrinsics

<!--
Add here:
- Complete sparse MAC API and encoding format
- Shuffle/permute operations specific to 512-bit vectors
- Memory tile DMA intrinsics (if applicable from kernel side)
- Sliding mul configurations for AIE-ML
- Any AIE-ML specific intrinsic variants
-->
