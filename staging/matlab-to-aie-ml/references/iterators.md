<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# AIE-ML Iterator Types Reference

## Overview

AIE-ML uses the same iterator API as AIE but operates on 512-bit vectors (doubled width). All iterator concepts apply identically — the difference is in the vector size parameter.

---

## Iterator Types

### 1. Vector Iterator (`aie::begin_vector<N>`)

Sequential access, reading N elements at a time (N chosen for 512-bit alignment).

```cpp
// AIE-ML: 512-bit vectors
auto iter = aie::begin_vector<16>(in_buffer);   // 16 floats per read (512-bit)
auto iter = aie::begin_vector<32>(in_buffer);   // 32 int16s per read (512-bit)
auto iter = aie::begin_vector<32>(in_buffer);   // 32 bfloat16s per read (512-bit)
auto iter = aie::begin_vector<8>(in_buffer);    // 8 cfloats per read (512-bit)
```

### 2. Restrict Vector Iterator (`aie::begin_restrict_vector<N>`)

```cpp
auto iter_in  = aie::begin_restrict_vector<16>(in_buffer);   // float, no aliasing
auto iter_out = aie::begin_restrict_vector<16>(out_buffer);
```

### 3. Circular Iterator (`aie::circular_iterator<N>`)

```cpp
// Circular access — wraps after 'size' elements
auto coeff_iter = aie::circular_iterator<32>(coeff_ptr, num_taps);  // 32 int16 lanes
```

### 4. Pattern Iterator

```cpp
auto iter = aie::begin_pattern<16>(buffer, pattern_descriptor);
```

---

## AIE-ML Vector Widths by Type

| Data Type | Lanes per 512-bit vector | Iterator `<N>` value |
|---|---|---|
| `int4` | 128 | 128 |
| `int8` | 64 | 64 |
| `int16` | 32 | 32 |
| `int32` | 16 | 16 |
| `float` | 16 | 16 |
| `bfloat16` | 32 | 32 |
| `cint16` | 16 | 16 |
| `cfloat` | 8 | 8 |

---

## Memory Alignment Requirements (AIE-ML)

- 512-bit vectors: **64-byte alignment** required
- The AIE compiler handles alignment for `input_buffer` / `output_buffer` ports automatically
- For internal arrays: use `alignas(64)` attribute

```cpp
alignas(64) float local_buffer[256];      // 64-byte aligned for 512-bit access
alignas(64) bfloat16 weights[1024];       // 64-byte aligned for bfloat16 vectors
```

---

## Memory Tile Iterators

When data is staged in memory tiles, the compute kernel still uses standard iterators on its local buffer. The DMA handles the transfer from memory tile to compute tile memory. From the kernel's perspective, data appears in the input buffer as normal.

```cpp
// Kernel code is unaware of memory tile — same iterator pattern
auto pA = aie::begin_vector<32>(in_A);  // Memory tile DMA filled this buffer
```

**The graph configuration handles memory tile setup** (not the kernel):
```cpp
// In KERNEL_graph.h — memory tile staging
shared_buffer<bfloat16> staging_A;
staging_A = shared_buffer<bfloat16>::create({TOTAL_SIZE}, 1, 1);
```

---

## Examples: AIE-ML Iterators

### bfloat16 GEMM with 32 Lanes

```cpp
void BF16GemmKernel::run(
    input_buffer<bfloat16, extents<M * N>>& __restrict in_A,
    input_buffer<bfloat16, extents<N * L>>& __restrict in_B,
    output_buffer<bfloat16, extents<M * L>>& __restrict out_C)
{
    constexpr unsigned LANES = 32;

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

            for (unsigned k = 0; k < N; k++) {
                bfloat16 a_val = /* extract from A row */;
                auto b_vec = *pB;
                pB += L / LANES;
                acc = aie::mac(acc, aie::broadcast<bfloat16, LANES>(a_val), b_vec);
            }

            *pC++ = acc.to_vector<bfloat16>();
        }
        pA += N / LANES;
    }
}
```

### Large Data with Memory Tile Staging

```cpp
// Kernel sees standard buffers — memory tile is transparent
void LargeGemmKernel::run(
    input_buffer<float, extents<TILE_M * TILE_N>>& __restrict in_A_tile,
    input_buffer<float, extents<TILE_N * TILE_L>>& __restrict in_B_tile,
    output_buffer<float, extents<TILE_M * TILE_L>>& __restrict out_C_tile)
{
    // Process one tile — memory tile DMA delivers tiles sequentially
    auto pA = aie::begin_vector<16>(in_A_tile);
    auto pB = aie::begin_vector<16>(in_B_tile);
    auto pC = aie::begin_vector<16>(out_C_tile);

    // Standard vectorized compute on tile...
}
```

---

## TODO: Fill in additional AIE-ML iterator details

<!--
Add here:
- Memory tile DMA tiling parameter syntax
- 2D/3D DMA pattern configuration for iterating over large matrices
- Sparse data iterators (if different from standard)
- Performance characteristics of different iterator types on AIE-ML
-->
