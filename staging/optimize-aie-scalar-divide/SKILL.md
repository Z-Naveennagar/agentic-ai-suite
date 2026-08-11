---
name: optimize-aie-scalar-divide
description: >-
  Replaces floating-point division operations in AI Engine kernels with the
  hardware-accelerated aie::inv() intrinsic. On AIE, scalar float division (x / y)
  compiles to a multi-cycle software library call, while aie::inv(y) executes on
  the non-linear function unit in hardware (single-cycle throughput, few-cycle
  latency). The transformation replaces x / y with x * aie::inv(y), and 1.0f / y
  with aie::inv(y). This provides significant cycle savings for division-heavy
  algorithms. Note that aie::inv() has slightly lower precision than full IEEE-754
  division (~20-bit mantissa accuracy). Use when: kernel contains scalar float
  divides, division is not compile-time constant, and the application can tolerate
  the minor precision reduction. Trigger on: "replace divide", "aie::inv",
  "hardware divide", "scalar division", "non-linear unit", "float divide",
  "division optimization", "eliminate divide".
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
# Optimize AIE: Replace Scalar Division with aie::inv()

Replace floating-point division with the hardware-accelerated `aie::inv()` intrinsic
to eliminate costly software library calls on the AIE scalar processor.

---

## Background

On AI Engine, the scalar processor has **no hardware divide instruction**. When
the compiler encounters `x / y` for floating-point operands, it generates a call
to a multi-cycle software division library routine (~20+ cycles).

The AIE **non-linear function unit** provides `aie::inv(y)` which computes `1/y`
using a hardware lookup table + Newton-Raphson refinement, delivering the result
in a few cycles with single-cycle throughput when pipelined.

---

## When to Apply

| Pattern in Code | Replacement |
|-----------------|-------------|
| `1.0f / y` | `aie::inv(y)` |
| `x / y` | `x * aie::inv(y)` |
| `a / (b * c)` | `a * aie::inv(b * c)` |

Apply when **all** of the following are true:

1. The divisor `y` is **not** a compile-time constant (constant divides are already
   optimized by the compiler to multiply-by-reciprocal)
2. The division is on the critical path or occurs in a frequently-executed loop
3. The application can tolerate ~20-bit mantissa precision (sufficient for most
   signal processing and iterative algorithms)

---

## Do NOT Apply When

| Condition | Reason |
|-----------|--------|
| Divisor is a compile-time constant | Compiler already optimizes to multiply |
| Exact IEEE-754 division is required | `aie::inv()` has reduced precision |
| Integer division | `aie::inv()` is for float only |
| Divisor could be zero | `aie::inv(0)` produces undefined result |
| Divisor is denormalized (very small) | Precision may be insufficient |

---

## Transformation Examples

### Example 1: Simple reciprocal

**Before:**
```cpp
float inv_x = 1.0f / x;
```

**After:**
```cpp
float inv_x = aie::inv(x);
```

### Example 2: Division in expression

**Before:**
```cpp
float tau = (g_jj - g_ii) / (2.0f * abs_g_ij);
```

**After:**
```cpp
float tau = (g_jj - g_ii) * aie::inv(2.0f * abs_g_ij);
```

### Example 3: Ratio computation

**Before:**
```cpp
float t = sign_tau / (abs_tau + aie::sqrt(1.0f + tau * tau));
```

**After:**
```cpp
float t = sign_tau * aie::inv(abs_tau + aie::sqrt(1.0f + tau * tau));
```

### Example 4: Normalization factor

**Before:**
```cpp
float inv_norm = 1.0f / norm;
cfloat scale = {inv_norm, 0.0f};
```

**After:**
```cpp
float inv_norm = aie::inv(norm);
cfloat scale = {inv_norm, 0.0f};
```

---

## Related Hardware Intrinsics

The non-linear function unit also provides these related operations:

| Function | Operation | Use Case |
|----------|-----------|----------|
| `aie::inv(x)` | 1/x | Division replacement |
| `aie::invsqrt(x)` | 1/√x | Normalization (avoids sqrt + divide) |
| `aie::sqrt(x)` | √x | Square root |

### Combining inv and sqrt

When you need `1.0f / sqrt(x)`, use `aie::invsqrt(x)` directly instead of
`aie::inv(aie::sqrt(x))` — it's a single hardware operation:

**Before:**
```cpp
float norm = aie::sqrt(norm_sq);
float inv_norm = 1.0f / norm;
```

**Better (two HW ops):**
```cpp
float norm = aie::sqrt(norm_sq);
float inv_norm = aie::inv(norm);
```

**Best (one HW op, when you only need the reciprocal):**
```cpp
float inv_norm = aie::invsqrt(norm_sq);
```

---

## Precision Characteristics

| Operation | Mantissa Bits | Relative Error |
|-----------|--------------|----------------|
| IEEE-754 divide | 23 bits | ~1.2e-7 |
| `aie::inv()` | ~20 bits | ~1e-6 |
| `aie::invsqrt()` | ~20 bits | ~1e-6 |

For iterative algorithms (SVD, eigenvalue decomposition, Newton methods), the
reduced precision of `aie::inv()` is typically absorbed by subsequent iterations
and does not degrade final accuracy.

---

## Workflow

1. **Identify divides**: Search for `/` operators on float variables
2. **Filter constants**: Skip divides where divisor is a compile-time constant
3. **Check precision needs**: Ensure ~20-bit precision is acceptable
4. **Apply transformation**: Replace `x / y` → `x * aie::inv(y)`
5. **Special case 1/y**: Replace `1.0f / y` → `aie::inv(y)` (simpler)
6. **Validate**: Run x86sim and compare against golden reference

---

## Relationship to Other Skills

- **`create-kernel-cpp`**: Generated kernel code may use division operators that
  can be post-optimized with this skill.
- **`extract-aie-loop-ii`**: Software divide calls appear as large basic blocks.
  After replacing with `aie::inv()`, re-check loop II for improvement.
- **`optimize-aie-memory-access`**: Often combined — once divides are removed from
  the critical path, pointer arithmetic optimizations become the next bottleneck.
