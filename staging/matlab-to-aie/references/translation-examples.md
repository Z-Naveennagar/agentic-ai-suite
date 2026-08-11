<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# MATLAB to AIE Translation Examples

## Example 1: Matrix Multiply (GEMM)

### MATLAB Reference

```matlab
function C = gemm(A, B)
    % C = A * B where A is [M×N], B is [N×L], C is [M×L]
    C = A * B;
end
```

### AIE Kernel (float, 8 lanes)

```cpp
// gemm_kernel.h
#pragma once
#include <adf.h>
#include <aie_api/aie.hpp>
#include <aie_api/utils.hpp>

using namespace adf;

template <unsigned M, unsigned N, unsigned L>
class GemmKernel {
public:
    void run(input_buffer<float, extents<M * N>>& __restrict in_A,
             input_buffer<float, extents<N * L>>& __restrict in_B,
             output_buffer<float, extents<M * L>>& __restrict out_C);

    static void registerKernelClass() {
        REGISTER_FUNCTION(GemmKernel::run);
    }
};
```

```cpp
// gemm_kernel.cpp
#include "gemm_kernel.h"

template <unsigned M, unsigned N, unsigned L>
void GemmKernel<M, N, L>::run(
    input_buffer<float, extents<M * N>>& __restrict in_A,
    input_buffer<float, extents<N * L>>& __restrict in_B,
    output_buffer<float, extents<M * L>>& __restrict out_C)
{
    constexpr unsigned LANES = 8;

    auto pA = aie::begin_vector<LANES>(in_A);
    auto pC = aie::begin_vector<LANES>(out_C);

    // For each row of output
    for (unsigned i = 0; i < M; i++) {
        // For each group of LANES columns in output
        for (unsigned j = 0; j < L; j += LANES)
            chess_prepare_for_pipelining
        {
            aie::accum<accfloat, LANES> acc;
            acc = aie::zeros<accfloat, LANES>();

            auto pB = aie::begin_vector<LANES>(in_B);
            // Advance pB to column j
            pB += j / LANES;

            // Accumulate over N dimension
            for (unsigned k = 0; k < N; k++) {
                // Broadcast A[i][k]
                float a_val = aie::get<float>(*(pA), k % LANES);
                // Load B[k][j:j+LANES]
                auto b_vec = *(pB);
                pB += L / LANES;  // advance to next row of B

                acc = aie::mac(acc, aie::broadcast<float, LANES>(a_val), b_vec);
            }

            *pC++ = acc.to_vector<float>();
        }
        pA += N / LANES;  // advance to next row of A
    }
}
```

**Key translation points**:
- `C = A * B` → Nested loops with `aie::mac()` accumulation
- Matrix indexing → Iterator advancement + `aie::broadcast` for scalar expansion
- Implicit parallelism → Explicit LANES-wide vector operations

---

## Example 2: Element-wise Multiply

### MATLAB Reference

```matlab
function C = elemwise_mul(A, B)
    % C = A .* B (element-wise)
    C = A .* B;
end
```

### AIE Kernel (float, 8 lanes)

```cpp
template <unsigned N>
void ElemMulKernel<N>::run(
    input_buffer<float, extents<N>>& __restrict in_A,
    input_buffer<float, extents<N>>& __restrict in_B,
    output_buffer<float, extents<N>>& __restrict out_C)
{
    constexpr unsigned LANES = 8;

    auto pA = aie::begin_vector<LANES>(in_A);
    auto pB = aie::begin_vector<LANES>(in_B);
    auto pC = aie::begin_vector<LANES>(out_C);

    for (unsigned i = 0; i < N / LANES; i++)
        chess_prepare_for_pipelining
    {
        auto a = *pA++;
        auto b = *pB++;
        *pC++ = aie::mul(a, b);
    }
}
```

**Key translation points**:
- `A .* B` → `aie::mul(a, b)` on vector-width chunks
- Array indexing → Sequential iterator advancement
- Single MATLAB operation → Loop over chunks of LANES elements

---

## Example 3: Dot Product

### MATLAB Reference

```matlab
function s = dot_product(a, b)
    % s = dot(a, b) = sum(a .* b)
    s = dot(a, b);
end
```

### AIE Kernel (float, 8 lanes)

```cpp
template <unsigned N>
void DotProductKernel<N>::run(
    input_buffer<float, extents<N>>& __restrict in_A,
    input_buffer<float, extents<N>>& __restrict in_B,
    output_buffer<float, extents<1>>& __restrict out_S)
{
    constexpr unsigned LANES = 8;

    auto pA = aie::begin_vector<LANES>(in_A);
    auto pB = aie::begin_vector<LANES>(in_B);

    aie::accum<accfloat, LANES> acc;
    acc = aie::zeros<accfloat, LANES>();

    // Vectorized multiply-accumulate
    for (unsigned i = 0; i < N / LANES; i++)
        chess_prepare_for_pipelining
    {
        acc = aie::mac(acc, *pA++, *pB++);
    }

    // Reduce across lanes
    aie::vector<float, LANES> partial = acc.to_vector<float>();
    float result = aie::reduce_add(partial);

    // Store scalar result
    auto pC = aie::begin_vector<1>(out_S);
    *pC = aie::broadcast<float, 1>(result);
}
```

**Key translation points**:
- `dot(a, b)` → `aie::mac()` loop + `aie::reduce_add()` for final reduction
- Scalar result → First accumulate in LANES-wide vector, then reduce

---

## Example 4: FIR Filter

### MATLAB Reference

```matlab
function y = fir_filter(x, h)
    % y = conv(x, h, 'valid')  — FIR filtering
    y = conv(x, h, 'valid');
end
```

### AIE Kernel (int16, 16 lanes)

```cpp
template <unsigned WINDOW_SIZE, unsigned NUM_TAPS>
void FirKernel<WINDOW_SIZE, NUM_TAPS>::run(
    input_buffer<int16, extents<WINDOW_SIZE + NUM_TAPS - 1>>& __restrict in_data,
    output_buffer<int16, extents<WINDOW_SIZE>>& __restrict out_data)
{
    constexpr unsigned LANES = 16;
    constexpr unsigned SHIFT = 15;  // Q1.15 format

    auto pIn = aie::begin_vector<LANES>(in_data);
    auto pOut = aie::begin_vector<LANES>(out_data);

    // Process LANES output samples at a time
    for (unsigned n = 0; n < WINDOW_SIZE / LANES; n++)
        chess_prepare_for_pipelining
    {
        aie::accum<acc48, LANES> acc;
        acc = aie::zeros<acc48, LANES>();

        auto pData = aie::begin_vector<LANES>(in_data);
        pData += n;  // Start at current output position

        auto pCoeff = aie::circular_iterator<LANES>(coeffs_, NUM_TAPS);

        // Convolve
        for (unsigned t = 0; t < NUM_TAPS / LANES; t++) {
            acc = aie::mac(acc, *pData++, *pCoeff++);
        }

        *pOut++ = acc.to_vector<int16>(SHIFT);
    }
}
```

**Key translation points**:
- `conv(x, h, 'valid')` → Sliding window MAC with circular coefficient iterator
- Filter tap accumulation → `aie::mac()` with acc48 accumulator
- Fixed-point output → `.to_vector<int16>(SHIFT)` to quantize back

---

## Example 5: Vector Addition with Scalar

### MATLAB Reference

```matlab
function B = scale_add(A, alpha, beta)
    % B = alpha * A + beta
    B = alpha * A + beta;
end
```

### AIE Kernel (float, 8 lanes)

```cpp
template <unsigned N>
void ScaleAddKernel<N>::run(
    input_buffer<float, extents<N>>& __restrict in_A,
    output_buffer<float, extents<N>>& __restrict out_B)
{
    constexpr unsigned LANES = 8;
    const float alpha = alpha_;  // stored as class member
    const float beta = beta_;

    auto pA = aie::begin_vector<LANES>(in_A);
    auto pB = aie::begin_vector<LANES>(out_B);

    aie::vector<float, LANES> beta_vec = aie::broadcast<float, LANES>(beta);

    for (unsigned i = 0; i < N / LANES; i++)
        chess_prepare_for_pipelining
    {
        auto a = *pA++;
        auto scaled = aie::mul(a, alpha);     // alpha * A
        *pB++ = aie::add(scaled, beta_vec);   // + beta (broadcast)
    }
}
```

---

## Translation Pattern Summary

| MATLAB Pattern | AIE Pattern |
|---|---|
| `A * B` (matmul) | Nested loops + `aie::mac()` + accumulator |
| `A .* B` | `aie::mul(vec_a, vec_b)` in chunk loop |
| `A + B` | `aie::add(vec_a, vec_b)` in chunk loop |
| `A - B` | `aie::sub(vec_a, vec_b)` in chunk loop |
| `alpha * A` | `aie::mul(vec_a, scalar)` in chunk loop |
| `sum(x)` | `aie::mac()` loop + `aie::reduce_add()` |
| `dot(a, b)` | `aie::mac()` loop + `aie::reduce_add()` |
| `conv(x, h)` | Sliding window + circular iterator + `aie::mac()` |
| `max(A, B)` | `aie::max(vec_a, vec_b)` in chunk loop |
| `abs(A)` | `aie::abs(vec_a)` in chunk loop |
| `A.'` (transpose) | Shuffle/interleave or strided write pattern |

---

## TODO: Add more examples

<!--
Add here:
- FFT butterfly example (radix-2 and radix-4)
- Complex multiply example (cint16 × cint16)
- Matrix transpose example with shuffle operations
- Cascaded multi-kernel example
- Real-world examples from Vitis Tutorials
-->
