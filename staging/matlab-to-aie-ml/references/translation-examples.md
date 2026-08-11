<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# MATLAB to AIE-ML Translation Examples

## Example 1: Matrix Multiply (GEMM) — bfloat16

### MATLAB Reference

```matlab
function C = gemm(A, B)
    C = A * B;  % A [M×N], B [N×L], C [M×L]
end
```

### AIE-ML Kernel (bfloat16, 32 lanes)

```cpp
// gemm_bf16_kernel.h
#pragma once
#include <adf.h>
#include <aie_api/aie.hpp>
#include <aie_api/utils.hpp>

using namespace adf;

template <unsigned M, unsigned N, unsigned L>
class GemmBF16Kernel {
public:
    void run(input_buffer<bfloat16, extents<M * N>>& __restrict in_A,
             input_buffer<bfloat16, extents<N * L>>& __restrict in_B,
             output_buffer<bfloat16, extents<M * L>>& __restrict out_C);

    static void registerKernelClass() {
        REGISTER_FUNCTION(GemmBF16Kernel::run);
    }
};
```

```cpp
// gemm_bf16_kernel.cpp
#include "gemm_bf16_kernel.h"

template <unsigned M, unsigned N, unsigned L>
void GemmBF16Kernel<M, N, L>::run(
    input_buffer<bfloat16, extents<M * N>>& __restrict in_A,
    input_buffer<bfloat16, extents<N * L>>& __restrict in_B,
    output_buffer<bfloat16, extents<M * L>>& __restrict out_C)
{
    constexpr unsigned LANES = 32;  // AIE-ML: 32 bfloat16 lanes

    auto pA = aie::begin_vector<LANES>(in_A);
    auto pC = aie::begin_vector<LANES>(out_C);

    for (unsigned i = 0; i < M; i++) {
        for (unsigned j = 0; j < L; j += LANES)
            chess_prepare_for_pipelining
        {
            // Accumulate in float precision (accfloat) for bfloat16 MAC
            aie::accum<accfloat, LANES> acc;
            acc = aie::zeros<accfloat, LANES>();

            auto pB = aie::begin_vector<LANES>(in_B);
            pB += j / LANES;

            for (unsigned k = 0; k < N; k++) {
                bfloat16 a_val = /* extract A[i][k] */;
                auto b_vec = *pB;
                pB += L / LANES;

                acc = aie::mac(acc, aie::broadcast<bfloat16, LANES>(a_val), b_vec);
            }

            // Convert float accumulator back to bfloat16
            *pC++ = acc.to_vector<bfloat16>();
        }
        pA += N / LANES;
    }
}
```

**Key AIE-ML advantage**: 32 bfloat16 MACs per cycle (vs 8 float MACs on AIE 1st gen) — 4× more operations per cycle for reduced-precision inference.

---

## Example 2: Matrix Multiply (GEMM) — float with Memory Tile

### MATLAB Reference

```matlab
function C = gemm(A, B)
    C = A * B;  % Large: A [512×512], B [512×512]
end
```

### AIE-ML Graph with Memory Tile Staging

```cpp
// gemm_bf16_graph.h — uses memory tile for large matrix
#pragma once
#include <adf.h>
#include "gemm_bf16_kernel.h"

class GemmGraph : public graph {
public:
    input_plio in_A, in_B;
    output_plio out_C;
    kernel k;

    // Memory tile buffers for staging large matrices
    shared_buffer<float> mem_A;
    shared_buffer<float> mem_B;

    GemmGraph() {
        k = kernel::create_object<GemmKernel<8, 512, 16>>();  // Tile: 8×512 × 512×16

        // Memory tiles (512 KB each)
        mem_A = shared_buffer<float>::create({512 * 512}, 1, 1);
        mem_B = shared_buffer<float>::create({512 * 512}, 1, 1);

        // PLIO → Memory Tile
        in_A = input_plio::create("in_A", plio_128_bits, "data/input_A.txt");
        in_B = input_plio::create("in_B", plio_128_bits, "data/input_B.txt");
        write_access(mem_A) = in_A.out[0];
        write_access(mem_B) = in_B.out[0];

        // Memory Tile → Compute Tile (with tiling pattern)
        read_access(mem_A) = k.in[0];
        read_access(mem_B) = k.in[1];

        // Output
        out_C = output_plio::create("out_C", plio_128_bits, "data/output_C.txt");
        connect(k.out[0], out_C.in[0]);

        source(k) = "gemm_kernel.cpp";
        runtime<ratio>(k) = 0.9;
    }
};
```

---

## Example 3: Element-wise with bfloat16

### MATLAB Reference

```matlab
function C = relu(A)
    % ReLU activation: C = max(A, 0)
    C = max(A, 0);
end
```

### AIE-ML Kernel (bfloat16, 32 lanes)

```cpp
template <unsigned N>
void ReluBF16Kernel<N>::run(
    input_buffer<bfloat16, extents<N>>& __restrict in_A,
    output_buffer<bfloat16, extents<N>>& __restrict out_C)
{
    constexpr unsigned LANES = 32;

    auto pA = aie::begin_vector<LANES>(in_A);
    auto pC = aie::begin_vector<LANES>(out_C);

    // Zero vector for comparison
    aie::vector<bfloat16, LANES> zero_vec = aie::broadcast<bfloat16, LANES>(bfloat16(0.0f));

    for (unsigned i = 0; i < N / LANES; i++)
        chess_prepare_for_pipelining
    {
        auto a = *pA++;
        *pC++ = aie::max(a, zero_vec);  // ReLU: max(x, 0)
    }
}
```

---

## Example 4: FIR Filter — int16 with 32 Lanes

### MATLAB Reference

```matlab
function y = fir_filter(x, h)
    y = conv(x, h, 'valid');
end
```

### AIE-ML Kernel (int16, 32 lanes)

```cpp
template <unsigned WINDOW_SIZE, unsigned NUM_TAPS>
void FirKernel<WINDOW_SIZE, NUM_TAPS>::run(
    input_buffer<int16, extents<WINDOW_SIZE + NUM_TAPS - 1>>& __restrict in_data,
    output_buffer<int16, extents<WINDOW_SIZE>>& __restrict out_data)
{
    constexpr unsigned LANES = 32;   // AIE-ML: 32 int16 lanes (vs 16 on AIE)
    constexpr unsigned SHIFT = 15;

    auto pOut = aie::begin_vector<LANES>(out_data);

    for (unsigned n = 0; n < WINDOW_SIZE / LANES; n++)
        chess_prepare_for_pipelining
    {
        aie::accum<acc64, LANES> acc;
        acc = aie::zeros<acc64, LANES>();

        auto pData = aie::begin_vector<LANES>(in_data);
        pData += n;

        auto pCoeff = aie::circular_iterator<LANES>(coeffs_, NUM_TAPS);

        for (unsigned t = 0; t < NUM_TAPS / LANES; t++) {
            acc = aie::mac(acc, *pData++, *pCoeff++);
        }

        *pOut++ = acc.to_vector<int16>(SHIFT);
    }
}
```

**Key AIE-ML advantage**: 32 int16 MAC lanes vs 16 on AIE — processes 2× more samples per inner iteration.

---

## Example 5: Dot Product — float with 16 Lanes

### MATLAB Reference

```matlab
function s = dot_product(a, b)
    s = dot(a, b);
end
```

### AIE-ML Kernel (float, 16 lanes)

```cpp
template <unsigned N>
void DotProductKernel<N>::run(
    input_buffer<float, extents<N>>& __restrict in_A,
    input_buffer<float, extents<N>>& __restrict in_B,
    output_buffer<float, extents<1>>& __restrict out_S)
{
    constexpr unsigned LANES = 16;  // AIE-ML: 16 float lanes (vs 8 on AIE)

    auto pA = aie::begin_vector<LANES>(in_A);
    auto pB = aie::begin_vector<LANES>(in_B);

    aie::accum<accfloat, LANES> acc;
    acc = aie::zeros<accfloat, LANES>();

    for (unsigned i = 0; i < N / LANES; i++)
        chess_prepare_for_pipelining
    {
        acc = aie::mac(acc, *pA++, *pB++);
    }

    aie::vector<float, LANES> partial = acc.to_vector<float>();
    float result = aie::reduce_add(partial);

    auto pC = aie::begin_vector<1>(out_S);
    *pC = aie::broadcast<float, 1>(result);
}
```

---

## Translation Pattern Summary (AIE-ML)

| MATLAB Pattern | AIE-ML Pattern | Lanes |
|---|---|---|
| `A * B` (matmul, float) | `aie::mac()` with `accfloat, 16` | 16 |
| `A * B` (matmul, bfloat16) | `aie::mac()` with `accfloat, 32` | 32 |
| `A * B` (matmul, int16) | `aie::mac()` with `acc64, 32` | 32 |
| `A .* B` (float) | `aie::mul(a, b)` | 16 |
| `A .* B` (bfloat16) | `aie::mul(a, b)` | 32 |
| `max(A, 0)` (ReLU) | `aie::max(a, zero_vec)` | 16/32 |
| `conv(x, h)` (int16) | Sliding window + circular iter + `aie::mac()` | 32 |

---

## TODO: Add more examples

<!--
Add here:
- Sparse GEMM example with sparse encoding
- Multi-tile cascade example
- Memory tile DMA tiling pattern for 2D matrices
- Complex-valued examples (cint16, cfloat)
- FFT butterfly with 512-bit vectors
-->
