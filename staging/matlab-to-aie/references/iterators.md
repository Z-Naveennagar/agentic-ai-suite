<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# AIE Iterator Types Reference

## Overview

AI Engine kernels must use **embedded iterators** from the AIE API for all memory access instead of raw C-style array indexing. Iterators enable the compiler to schedule memory accesses optimally and avoid bank conflicts.

---

## Iterator Types

### 1. Vector Iterator (`aie::begin_vector<N>`)

Sequential access, reading N elements at a time.

```cpp
// Read sequential vectors from input buffer
auto iter = aie::begin_vector<8>(in_buffer);    // 8 floats per read (256-bit)
auto iter = aie::begin_vector<16>(in_buffer);   // 16 int16s per read (256-bit)

// Usage in loop
for (int i = 0; i < count; i++) {
    aie::vector<float, 8> vec = *iter++;
    // ... process vec ...
}
```

**When to use**: Any contiguous sequential access pattern (most common).

### 2. Restrict Vector Iterator (`aie::begin_restrict_vector<N>`)

Same as vector iterator but guarantees no aliasing with other pointers.

```cpp
auto iter_in  = aie::begin_restrict_vector<8>(in_buffer);
auto iter_out = aie::begin_restrict_vector<8>(out_buffer);
```

**When to use**: When input and output buffers are guaranteed non-overlapping. Enables better compiler scheduling.

### 3. Circular Iterator (`aie::circular_iterator<N>`)

Wraps around to the beginning after reaching the end of the buffer.

```cpp
// Circular access over coefficient buffer (wraps after 'num_taps' elements)
auto coeff_iter = aie::circular_iterator<8>(coeff_ptr, num_taps);

// Each *coeff_iter++ advances, wrapping at buffer end
for (int i = 0; i < output_samples; i++) {
    for (int t = 0; t < num_taps; t++) {
        auto c = *coeff_iter++;  // wraps after num_taps/8 reads
    }
}
```

**When to use**: FIR filter coefficients, any repeating pattern, ping-pong buffer cycling.

### 4. Pattern Iterator (`aie::begin_pattern<N>`)

Strided or custom access pattern.

```cpp
// Strided access: read every K-th vector
// Pattern describes the offset sequence between reads
auto iter = aie::begin_pattern<8>(buffer, pattern_descriptor);
```

**When to use**: Column access in row-major matrix, interleaved data, non-contiguous access.

### 5. Random Access (Direct Pointer) — AVOID

```cpp
// Avoid this pattern — prevents compiler optimization
float* ptr = (float*)in_buffer.data();
float val = ptr[index];  // BAD: random access kills scheduling
```

**When forced to use**: Only for truly irregular access patterns that cannot be expressed with the above iterators. Always prefer iterators.

---

## Iterator for Output Buffers

```cpp
// Write sequential vectors to output buffer
auto out_iter = aie::begin_vector<8>(out_buffer);

// Store result
*out_iter++ = result_vector;
```

---

## Buffer Access Patterns by Operation

| Operation | Input A Pattern | Input B Pattern | Output Pattern |
|---|---|---|---|
| GEMM (inner product) | Row-sequential | Column-strided (or pre-transposed) | Row-sequential |
| GEMM (outer product) | Column-sequential (scalar broadcast) | Row-sequential | Row-sequential (accumulate in-place) |
| FIR / Convolution | Window-sequential (sliding) | Circular (coefficients) | Sequential |
| Element-wise | Sequential | Sequential | Sequential |
| FFT butterfly | Strided (bit-reverse or stage-dependent) | Sequential (twiddles) | Strided |
| Dot product | Sequential | Sequential | Scalar (reduction) |
| Transpose | Row-sequential read | N/A | Column-sequential write (strided) |

---

## Memory Alignment Requirements

- Vector iterators require the buffer start address to be aligned to the vector width
  - 256-bit vectors: 32-byte alignment
- The AIE compiler handles alignment for `input_buffer` / `output_buffer` port types automatically
- For internal arrays declared in the kernel: use `alignas(32)` attribute

```cpp
alignas(32) float local_buffer[256];  // 32-byte aligned for 256-bit vector access
```

---

## Examples

### Sequential Read + Write (Element-wise Operation)

```cpp
void ElementwiseKernel::run(
    input_buffer<float, extents<N>>& __restrict in_A,
    input_buffer<float, extents<N>>& __restrict in_B,
    output_buffer<float, extents<N>>& __restrict out_C)
{
    auto pA = aie::begin_vector<8>(in_A);
    auto pB = aie::begin_vector<8>(in_B);
    auto pC = aie::begin_vector<8>(out_C);

    for (unsigned i = 0; i < N/8; i++)
        chess_prepare_for_pipelining
    {
        auto a = *pA++;
        auto b = *pB++;
        *pC++ = aie::add(a, b);
    }
}
```

### Circular Coefficient Access (FIR)

```cpp
void FirKernel::run(
    input_buffer<int16, extents<WINDOW_SIZE>>& __restrict in_data,
    output_buffer<int16, extents<OUTPUT_SIZE>>& __restrict out_data)
{
    constexpr int LANES = 16;

    // Coefficients stored as class member or local constant
    auto coeff_iter = aie::circular_iterator<LANES>(coeffs, NUM_TAPS);
    auto data_iter = aie::begin_vector<LANES>(in_data);
    auto out_iter = aie::begin_vector<LANES>(out_data);

    for (unsigned n = 0; n < OUTPUT_SIZE / LANES; n++)
        chess_prepare_for_pipelining
    {
        aie::accum<acc48, LANES> acc = aie::zeros<acc48, LANES>();

        for (unsigned t = 0; t < NUM_TAPS / LANES; t++) {
            acc = aie::mac(acc, *data_iter++, *coeff_iter++);
        }

        *out_iter++ = acc.to_vector<int16>(SHIFT);
    }
}
```

---

## TODO: Fill in additional iterator details

<!--
Add here:
- Complete pattern iterator configuration for AIE
- Interleave/deinterleave iterator patterns
- Multi-dimensional iterator support (if available)
- Performance impact of different iterator types (cycles per access)
- Bank conflict avoidance strategies with iterators
-->
