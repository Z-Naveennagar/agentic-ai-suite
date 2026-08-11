<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# MATLAB to AIE-ML v2 Translation Examples

## Example 1: Matrix Multiply (GEMM) — fp32 Full Throughput

### MATLAB Reference

```matlab
function C = gemm(A, B)
    C = A * B;  % A [M×N], B [N×L], C [M×L], single precision
end
```

### AIE-ML v2 Kernel (float, 16 lanes, full-throughput MAC)

```cpp
// gemm_fp32_kernel.h
#pragma once
#include <adf.h>
#include <aie_api/aie.hpp>
#include <aie_api/utils.hpp>

using namespace adf;

template <unsigned M, unsigned N, unsigned L>
class GemmFP32Kernel {
public:
    void run(input_buffer<float, extents<M * N>>& __restrict in_A,
             input_buffer<float, extents<N * L>>& __restrict in_B,
             output_buffer<float, extents<M * L>>& __restrict out_C);

    static void registerKernelClass() {
        REGISTER_FUNCTION(GemmFP32Kernel::run);
    }
};
```

```cpp
// gemm_fp32_kernel.cpp
#include "gemm_fp32_kernel.h"

template <unsigned M, unsigned N, unsigned L>
void GemmFP32Kernel<M, N, L>::run(
    input_buffer<float, extents<M * N>>& __restrict in_A,
    input_buffer<float, extents<N * L>>& __restrict in_B,
    output_buffer<float, extents<M * L>>& __restrict out_C)
{
    constexpr unsigned LANES = 16;  // 16 float lanes, FULL throughput on v2

    auto pA = aie::begin_vector<LANES>(in_A);
    auto pC = aie::begin_vector<LANES>(out_C);

    for (unsigned i = 0; i < M; i++) {
        for (unsigned j = 0; j < L; j += LANES)
            chess_prepare_for_pipelining
        {
            aie::accum<accfloat, LANES> acc;
            acc = aie::zeros<accfloat, LANES>();

            auto pB = aie::begin_vector<LANES>(in_B);
            pB += j / LANES;

            // Inner MAC loop — 16 MACs/cycle SUSTAINED on AIE-ML v2
            // No pipeline bubbles unlike AIE-ML for fp32
            for (unsigned k = 0; k < N; k++) {
                float a_val = aie::get<float>(*(pA + k / LANES), k % LANES);
                auto b_vec = *pB;
                pB += L / LANES;

                acc = aie::mac(acc, aie::broadcast<float, LANES>(a_val), b_vec);
            }

            *pC++ = acc.to_vector<float>();
        }
        pA += N / LANES;
    }
}
```

**v2 advantage**: Identical code to AIE-ML but achieves higher sustained throughput. The fp32 MAC pipeline on v2 has no bubbles, so the same kernel runs faster without code changes.

---

## Example 2: Matrix Transpose — Enhanced Shuffle

### MATLAB Reference

```matlab
function B = transpose_mat(A)
    B = A.';  % Transpose M×N → N×M
end
```

### AIE-ML v2 Kernel (float, leveraging enhanced shuffle)

```cpp
// transpose_kernel.cpp — enhanced shuffle makes this faster on v2
template <unsigned M, unsigned N>
void TransposeKernel<M, N>::run(
    input_buffer<float, extents<M * N>>& __restrict in_A,
    output_buffer<float, extents<N * M>>& __restrict out_AT)
{
    constexpr unsigned LANES = 16;
    constexpr unsigned BLOCK = 4;  // Process 4×LANES blocks

    auto pA = aie::begin_vector<LANES>(in_A);
    auto pAT = aie::begin_vector<LANES>(out_AT);

    // Process in BLOCK×LANES sub-matrices
    for (unsigned bi = 0; bi < M; bi += BLOCK) {
        for (unsigned bj = 0; bj < N; bj += LANES)
            chess_prepare_for_pipelining
        {
            // Load BLOCK rows of LANES elements
            aie::vector<float, LANES> rows[BLOCK];
            for (unsigned r = 0; r < BLOCK; r++) {
                rows[r] = *(pA + (bi + r) * (N / LANES) + bj / LANES);
            }

            // Transpose via interleave_zip (FASTER on v2)
            auto [t0, t1] = aie::interleave_zip(rows[0], rows[2], 1);
            auto [t2, t3] = aie::interleave_zip(rows[1], rows[3], 1);
            auto [col0, col2] = aie::interleave_zip(t0, t2, 1);
            auto [col1, col3] = aie::interleave_zip(t1, t3, 1);

            // Store transposed columns as rows of output
            // (Output addressing is strided — using pattern iterator would be ideal)
            *(pAT + (bj + 0) * (M / LANES) + bi / LANES) = col0;
            *(pAT + (bj + 1) * (M / LANES) + bi / LANES) = col1;
            *(pAT + (bj + 2) * (M / LANES) + bi / LANES) = col2;
            *(pAT + (bj + 3) * (M / LANES) + bi / LANES) = col3;
        }
    }
}
```

**v2 advantage**: `interleave_zip` and other shuffle operations execute with lower latency on v2, making transpose operations significantly cheaper.

---

## Example 3: GEMM + ReLU Fused Pipeline — fp32

### MATLAB Reference

```matlab
function C = gemm_relu(A, B)
    % C = max(A * B, 0) — GEMM followed by ReLU activation
    C = max(A * B, 0);
end
```

### AIE-ML v2 Kernel (fused, float, 16 lanes)

```cpp
template <unsigned M, unsigned N, unsigned L>
void GemmReluKernel<M, N, L>::run(
    input_buffer<float, extents<M * N>>& __restrict in_A,
    input_buffer<float, extents<N * L>>& __restrict in_B,
    output_buffer<float, extents<M * L>>& __restrict out_C)
{
    constexpr unsigned LANES = 16;

    auto pA = aie::begin_vector<LANES>(in_A);
    auto pC = aie::begin_vector<LANES>(out_C);

    aie::vector<float, LANES> zero_vec = aie::broadcast<float, LANES>(0.0f);

    for (unsigned i = 0; i < M; i++) {
        for (unsigned j = 0; j < L; j += LANES)
            chess_prepare_for_pipelining
        {
            aie::accum<accfloat, LANES> acc;
            acc = aie::zeros<accfloat, LANES>();

            auto pB = aie::begin_vector<LANES>(in_B);
            pB += j / LANES;

            for (unsigned k = 0; k < N; k++) {
                float a_val = aie::get<float>(*(pA + k / LANES), k % LANES);
                auto b_vec = *pB;
                pB += L / LANES;
                acc = aie::mac(acc, aie::broadcast<float, LANES>(a_val), b_vec);
            }

            // Fuse ReLU: max(result, 0) — no extra memory round-trip
            auto result = acc.to_vector<float>();
            *pC++ = aie::max(result, zero_vec);
        }
        pA += N / LANES;
    }
}
```

**Key insight**: Fusing GEMM + element-wise activation into one kernel avoids writing intermediate results to memory. The `aie::max()` adds negligible overhead after the MAC loop. This pattern is very common in ML inference (GEMM → activation).

---

## Example 4: Batched Element-wise — bfloat16 (Same as AIE-ML)

### MATLAB Reference

```matlab
function C = batch_scale(A, scales)
    % C(i,:) = A(i,:) * scales(i) — row-wise scaling
    C = A .* scales;  % scales is column vector, broadcast
end
```

### AIE-ML v2 Kernel (bfloat16, 32 lanes)

```cpp
template <unsigned ROWS, unsigned COLS>
void BatchScaleKernel<ROWS, COLS>::run(
    input_buffer<bfloat16, extents<ROWS * COLS>>& __restrict in_A,
    input_buffer<bfloat16, extents<ROWS>>& __restrict in_scales,
    output_buffer<bfloat16, extents<ROWS * COLS>>& __restrict out_C)
{
    constexpr unsigned LANES = 32;

    auto pA = aie::begin_vector<LANES>(in_A);
    auto pS = aie::begin_vector<1>(in_scales);
    auto pC = aie::begin_vector<LANES>(out_C);

    for (unsigned i = 0; i < ROWS; i++) {
        // Broadcast scale for this row
        bfloat16 scale = aie::get<bfloat16>(*pS++, 0);
        aie::vector<bfloat16, LANES> scale_vec = aie::broadcast<bfloat16, LANES>(scale);

        for (unsigned j = 0; j < COLS / LANES; j++)
            chess_prepare_for_pipelining
        {
            auto a = *pA++;
            *pC++ = aie::mul(a, scale_vec);
        }
    }
}
```

---

## Example 5: Complex Dot Product — cfloat

### MATLAB Reference

```matlab
function s = complex_dot(a, b)
    % s = dot(a, b) for complex vectors = sum(conj(a) .* b)
    s = a' * b;  % Hermitian inner product
end
```

### AIE-ML v2 Kernel (cfloat, 8 lanes)

```cpp
template <unsigned N>
void ComplexDotKernel<N>::run(
    input_buffer<cfloat, extents<N>>& __restrict in_A,
    input_buffer<cfloat, extents<N>>& __restrict in_B,
    output_buffer<cfloat, extents<1>>& __restrict out_S)
{
    constexpr unsigned LANES = 8;  // 8 cfloat lanes (512-bit)

    auto pA = aie::begin_vector<LANES>(in_A);
    auto pB = aie::begin_vector<LANES>(in_B);

    aie::accum<caccfloat, LANES> acc;
    acc = aie::zeros<caccfloat, LANES>();

    for (unsigned i = 0; i < N / LANES; i++)
        chess_prepare_for_pipelining
    {
        auto a = *pA++;
        auto b = *pB++;
        auto a_conj = aie::conj(a);  // Conjugate for Hermitian
        acc = aie::mac(acc, a_conj, b);
    }

    // Reduce across lanes
    aie::vector<cfloat, LANES> partial = acc.to_vector<cfloat>();
    cfloat result = aie::reduce_add(partial);

    auto pC = aie::begin_vector<1>(out_S);
    *pC = aie::broadcast<cfloat, 1>(result);
}
```

---

## Translation Pattern Summary (AIE-ML v2)

| MATLAB Pattern | AIE-ML v2 Recommendation | Key Advantage |
|---|---|---|
| `A * B` (float) | fp32 with 16 lanes | Full MAC throughput (no need for bfloat16) |
| `A * B` (bfloat16) | bfloat16 with 32 lanes | 2× lanes for inference |
| `A.'` (transpose) | Enhanced shuffle | Lower latency permutation |
| `max(A*B, 0)` (GEMM+ReLU) | Fused kernel, fp32 | Full throughput + no memory trip |
| `conv(x, h)` | int16/float with 32/16 lanes | Same as AIE-ML |
| `A' * B` (complex dot) | cfloat with 8 lanes | Native complex MAC |

---

## TODO: Add more v2-specific examples

<!--
Add here:
- Sparse GEMM example leveraging v2 enhancements
- Multi-tile cascade with enhanced DMA
- FFT with enhanced shuffle for butterfly
- Benchmark comparisons: same kernel on AIE-ML vs AIE-ML v2
- Real-world workloads demonstrating v2 advantage
-->
