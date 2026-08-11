<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# AIE API Intrinsics Reference

## Vector Arithmetic

### Multiply

```cpp
// Vector × Vector (element-wise)
aie::vector<float, 8> c = aie::mul(a, b);          // float × float → float
aie::accum<acc48, 16> acc = aie::mul(a, b);         // int16 × int16 → acc48
aie::accum<cacc48, 8> acc = aie::mul(a, b);         // cint16 × cint16 → cacc48

// Vector × Scalar (broadcast)
aie::vector<float, 8> c = aie::mul(a, scalar);      // float vec × float scalar
aie::accum<acc48, 16> acc = aie::mul(a, scalar);    // int16 vec × int16 scalar
```

### Multiply-Accumulate (MAC)

```cpp
// Accumulate: acc += a * b
acc = aie::mac(acc, a, b);        // acc48 += int16 × int16
acc = aie::mac(acc, a, b);        // accfloat += float × float
acc = aie::mac(acc, a, b);        // cacc48 += cint16 × cint16

// Multiply-subtract: acc -= a * b
acc = aie::msc(acc, a, b);
```

### Addition / Subtraction

```cpp
aie::vector<float, 8> c = aie::add(a, b);     // element-wise add
aie::vector<float, 8> c = aie::sub(a, b);     // element-wise subtract
aie::vector<int16, 16> c = aie::add(a, b);    // int16 add
```

### Accumulator Operations

```cpp
// Initialize to zero
aie::accum<acc48, 16> acc;
acc = aie::zeros<acc48, 16>();

// Convert accumulator to vector (with shift for fixed-point)
aie::vector<int16, 16> result = acc.to_vector<int16>(SHIFT);   // right-shift by SHIFT bits
aie::vector<float, 8> result = acc.to_vector<float>();          // no shift for float

// Accumulator from vector (upcast)
acc.from_vector(vec, SHIFT);   // left-shift input by SHIFT before storing in acc
```

### Reduction

```cpp
// Sum all lanes
float sum = aie::reduce_add(vec);       // float vector → scalar sum
int32_t sum = aie::reduce_add(vec);     // int16 vector → int32 scalar sum

// Min/Max across lanes
float min_val = aie::reduce_min(vec);
float max_val = aie::reduce_max(vec);
```

### Comparison / Selection

```cpp
aie::vector<float, 8> c = aie::max(a, b);     // element-wise max
aie::vector<float, 8> c = aie::min(a, b);     // element-wise min
aie::vector<float, 8> c = aie::abs(a);        // element-wise absolute value
aie::mask<8> m = aie::lt(a, b);               // element-wise less-than → mask
aie::vector<float, 8> c = aie::select(a, b, m);  // select based on mask
```

### Shift (Fixed-Point)

```cpp
aie::vector<int16, 16> c = aie::downshift(a, SHIFT);  // arithmetic right shift
aie::vector<int16, 16> c = aie::upshift(a, SHIFT);    // left shift
```

## Matrix Multiply (Sliding Window)

For GEMM-style operations with specific data arrangements:

```cpp
// 4×4 int16 matrix multiply (specialized intrinsic)
// Produces 4 output elements from 4×4 input tile × 4-element vector
acc = aie::sliding_mul<4, 4>(coeff_vec, data_vec);
```

**Note**: `sliding_mul` has specific lane/column requirements per data type. Consult architecture manual for valid configurations.

## Type Conversion

```cpp
// Floating to integer
aie::vector<int16, 16> i = aie::to_fixed<int16>(float_vec, FRAC_BITS);

// Integer to floating
aie::vector<float, 8> f = aie::to_float(int_vec, FRAC_BITS);
```

---

## TODO: Fill in additional intrinsics

<!--
Add here:
- Complete sliding_mul configurations for AIE
- Shuffle/interleave operations
- Conjugate operations for complex types
- FFT butterfly primitives
- Any AIE-specific intrinsic variants not in the common AIE API
-->
