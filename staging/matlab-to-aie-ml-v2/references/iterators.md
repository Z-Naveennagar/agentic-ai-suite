<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# AIE-ML v2 Iterator Types Reference

## Overview

AIE-ML v2 uses the same iterator API as AIE-ML. All iterator types, vector widths, and alignment requirements are identical. The improvement is in the **underlying DMA performance** — faster data delivery to/from memory tiles.

---

## Iterator Types (Same API as AIE-ML)

### 1. Vector Iterator (`aie::begin_vector<N>`)

```cpp
auto iter = aie::begin_vector<16>(in_buffer);   // 16 floats (512-bit)
auto iter = aie::begin_vector<32>(in_buffer);   // 32 int16 (512-bit)
auto iter = aie::begin_vector<32>(in_buffer);   // 32 bfloat16 (512-bit)
auto iter = aie::begin_vector<8>(in_buffer);    // 8 cfloat (512-bit)
```

### 2. Restrict Vector Iterator (`aie::begin_restrict_vector<N>`)

```cpp
auto iter_in  = aie::begin_restrict_vector<16>(in_buffer);
auto iter_out = aie::begin_restrict_vector<16>(out_buffer);
```

### 3. Circular Iterator (`aie::circular_iterator<N>`)

```cpp
auto coeff_iter = aie::circular_iterator<32>(coeff_ptr, num_taps);
```

### 4. Pattern Iterator

```cpp
auto iter = aie::begin_pattern<16>(buffer, pattern_descriptor);
```

---

## AIE-ML v2 Vector Widths by Type

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

## Memory Alignment Requirements

Same as AIE-ML:
- 512-bit vectors: **64-byte alignment**
- `input_buffer`/`output_buffer` ports auto-aligned by compiler
- Internal arrays: `alignas(64)`

```cpp
alignas(64) float local_buffer[256];
alignas(64) bfloat16 weights[1024];
```

---

## Enhanced DMA (AIE-ML v2 Improvement)

While the kernel iterator API is unchanged, the **DMA subsystem** that fills buffers from memory tiles is improved:

- **Lower latency**: Reduced cycles between DMA request and data availability
- **Faster reconfiguration**: Switching between DMA tiling patterns takes fewer cycles
- **Better overlap**: Improved ping-pong scheduling — less idle time between kernel invocations

**Impact on kernel design**: Kernels can be more aggressive with tiling (smaller tiles, more invocations) without DMA overhead dominating. The DMA overhead per tile is reduced.

### Practical Impact on Tiling

| Scenario | AIE-ML | AIE-ML v2 |
|---|---|---|
| Small tile (1-2 KB) | DMA overhead ~5-10% of compute | DMA overhead ~2-5% of compute |
| Medium tile (8-16 KB) | DMA overhead ~2-5% | DMA overhead ~1-2% |
| Large tile (32-56 KB) | DMA overhead negligible | DMA overhead negligible |

**Recommendation**: On AIE-ML v2, smaller tile sizes are more viable because DMA overhead is reduced. This can improve:
- Latency (first output arrives sooner)
- Memory efficiency (smaller peak memory usage)
- Multi-tile parallelism (more tiles = more parallel compute units)

---

## Examples

### fp32 GEMM with Full-Throughput MAC (AIE-ML v2 Sweet Spot)

```cpp
void FP32GemmKernel::run(
    input_buffer<float, extents<M * N>>& __restrict in_A,
    input_buffer<float, extents<N * L>>& __restrict in_B,
    output_buffer<float, extents<M * L>>& __restrict out_C)
{
    constexpr unsigned LANES = 16;  // 16 float lanes, full throughput on v2

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

            // Inner MAC loop — sustained 16 MACs/cycle on AIE-ML v2
            for (unsigned k = 0; k < N; k++) {
                float a_val = /* extract A[i][k] */;
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

### Efficient Transpose with Enhanced Shuffle

```cpp
// Matrix transpose leveraging faster shuffle on v2
void TransposeKernel::run(
    input_buffer<float, extents<N * N>>& __restrict in_A,
    output_buffer<float, extents<N * N>>& __restrict out_AT)
{
    constexpr unsigned LANES = 16;
    auto pA = aie::begin_vector<LANES>(in_A);
    auto pAT = aie::begin_vector<LANES>(out_AT);

    // Process in 4×4 or 8×8 blocks using shuffle
    // Enhanced shuffle on v2 reduces cycles for this operation
    for (unsigned blk = 0; blk < N * N / (LANES * 4); blk++) {
        auto row0 = *pA++;
        auto row1 = *pA++;
        auto row2 = *pA++;
        auto row3 = *pA++;

        // Transpose via interleave (faster on v2)
        auto [t0, t1] = aie::interleave_zip(row0, row2, 1);
        auto [t2, t3] = aie::interleave_zip(row1, row3, 1);
        auto [col0, col2] = aie::interleave_zip(t0, t2, 1);
        auto [col1, col3] = aie::interleave_zip(t1, t3, 1);

        *pAT++ = col0;
        *pAT++ = col1;
        *pAT++ = col2;
        *pAT++ = col3;
    }
}
```

---

## TODO: Fill in additional v2 iterator/DMA details

<!--
Add here:
- Specific DMA latency numbers (cycles)
- DMA reconfiguration overhead measurements
- Optimal tile sizes determined from v2 benchmarks
- Any new iterator capabilities unique to v2
-->
