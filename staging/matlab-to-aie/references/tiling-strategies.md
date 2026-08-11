<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# AIE Tiling Strategies

## Overview

Tiling is the process of partitioning a large computation into smaller chunks that fit in the AIE tile's local memory (32 KB for AIE). Each kernel invocation processes one tile of the output.

---

## GEMM Tiling (C = A × B)

### Strategy: Output-Stationary Tiling

Partition the output matrix C into tiles of size `Mt × Lt`. Each kernel invocation computes one output tile by accumulating over the full N (inner) dimension.

```
Output C [M × L]:
┌──────────────────────────────┐
│  Tile(0,0)  │  Tile(0,1)  │ ...
│  [Mt × Lt]  │  [Mt × Lt]  │
├─────────────┼─────────────┤
│  Tile(1,0)  │  Tile(1,1)  │ ...
│  [Mt × Lt]  │  [Mt × Lt]  │
└─────────────┴─────────────┘

Per invocation:
  - Load: A_tile [Mt × N] + B_tile [N × Lt]
  - Compute: C_tile = A_tile × B_tile  (accumulate over N)
  - Store: C_tile [Mt × Lt]
```

### Memory Budget Calculation

```
Input A tile: Mt × N × sizeof(type) bytes
Input B tile: N × Lt × sizeof(type) bytes
Output C tile: Mt × Lt × sizeof(type) bytes
Total: (Mt×N + N×Lt + Mt×Lt) × sizeof(type) ≤ 28 KB
```

### Recommended Tile Sizes (AIE, 256-bit vector = 8 float lanes)

| M×N×L | Mt | Lt | N (full) | Memory (float) | Notes |
|---|---|---|---|---|---|
| 64×128×32 | 8 | 8 | 128 | (8×128 + 128×8 + 8×8)×4 = 8.5 KB | Fits easily |
| 128×256×128 | 8 | 8 | 256 | (8×256 + 256×8 + 8×8)×4 = 16.5 KB | Fits |
| 256×512×256 | 4 | 8 | 512 | (4×512 + 512×8 + 4×8)×4 = 24.4 KB | Tight fit |

**Rules of thumb**:
- Lt should be a multiple of vector lanes (8 for float, 16 for int16)
- Mt × Lt determines the number of accumulators needed — keep ≤ 8 for register pressure
- If N is too large, split N into chunks with intermediate accumulation

### Vectorized Inner Loop (GEMM)

```
for each output row i in [0, Mt):
    acc[i] = zeros
    for k in [0, N) step LANES:
        vec_a = load A[i, k:k+LANES]     // row of A
        vec_b = load B[k:k+LANES, j]     // column of B (or transposed row)
        acc[i] = mac(acc[i], vec_a, vec_b)
    store C[i, j_tile:j_tile+Lt] = acc[i].to_vector()
```

---

## FIR / Convolution Tiling

### Strategy: Streaming Window

Process `W` output samples per kernel invocation. Input window is `W + T - 1` samples (where T = number of taps).

```
Input window: [W + T - 1] samples
Coefficients: [T] taps (stored locally, accessed circularly)
Output: [W] samples

Memory budget:
  Input: (W + T - 1) × sizeof(type)
  Coefficients: T × sizeof(type)
  Output: W × sizeof(type)
```

### Recommended Window Sizes

| Filter Taps (T) | Window Size (W) | Memory (int16) | Notes |
|---|---|---|---|
| 16 | 256 | (272 + 16 + 256)×2 = 1.1 KB | Very light |
| 64 | 256 | (320 + 64 + 256)×2 = 1.3 KB | Light |
| 256 | 512 | (768 + 256 + 512)×2 = 3.1 KB | Moderate |
| 1024 | 512 | (1536 + 1024 + 512)×2 = 6.1 KB | Heavy |

### Vectorized FIR Loop

```
for each output sample group [n, n+LANES):
    acc = zeros
    for t in [0, T) step LANES:
        data = load input[n+t : n+t+LANES]   // sliding window
        coeff = load coeffs[t : t+LANES]      // circular
        acc = mac(acc, data, coeff)
    store output[n:n+LANES] = acc.to_vector(shift)
```

---

## FFT Tiling

### Strategy: Radix-2 or Radix-4 Butterfly

For an N-point FFT, process in stages. Each stage has N/2 butterflies (radix-2) or N/4 butterflies (radix-4).

```
Radix-2 butterfly:
  X[k]     = E[k] + W_N^k × O[k]
  X[k+N/2] = E[k] - W_N^k × O[k]

Where:
  E[k] = even-indexed input
  O[k] = odd-indexed input
  W_N^k = twiddle factor (complex exponential)
```

### Memory Budget (FFT)

```
Input: N × sizeof(cfloat)
Twiddle factors: N/2 × sizeof(cfloat) per stage
Output: N × sizeof(cfloat) (in-place or separate buffer)
```

### Recommended FFT Sizes per Tile

| Point Size | Stages | Memory (cfloat=8B) | Notes |
|---|---|---|---|
| 64 | 6 | 64×8 + 32×8 = 768 B | Trivial |
| 256 | 8 | 256×8 + 128×8 = 3 KB | Easy |
| 1024 | 10 | 1024×8 + 512×8 = 12 KB | Moderate |
| 4096 | 12 | 4096×8 + 2048×8 = 48 KB | Exceeds 32KB — split across tiles |

**For FFTs exceeding local memory**: Split into stages across multiple tiles using cascade or buffer connections.

---

## Element-wise Tiling

### Strategy: Simple Chunking

Process `C` elements per kernel invocation. No tiling complexity — just chunk the array.

```
Chunk size C: limited by memory budget
  Input A: C × sizeof(type)
  Input B: C × sizeof(type) (if binary op)
  Output: C × sizeof(type)
  Total: 2C or 3C × sizeof(type) ≤ 28 KB
```

**Recommended chunk sizes**:
- float: C = 2048 elements (24 KB for A+B+C)
- int16: C = 4096 elements (24 KB for A+B+C)

---

## Multi-Tile Strategies

When a computation exceeds single-tile capacity:

### Cascade (Horizontal Chaining)
- Tiles pass partial results via 384-bit cascade link
- 1-cycle latency between adjacent tiles
- **Use for**: Deep accumulation (e.g., large FIR, long GEMM inner dimension)
- Each tile accumulates a portion of the reduction, passes result to next tile

### Buffer Sharing (Memory Overlap)
- Adjacent tiles share memory banks
- One tile writes, neighbor reads
- **Use for**: Pipeline stages (e.g., FFT stage 1 → stage 2)

### Broadcast (Same Input to Multiple Tiles)
- Shared memory read by multiple tiles
- **Use for**: Tiled GEMM where A matrix row is shared across column of output tiles

---

## TODO: Fill in additional tiling details

<!--
Add here:
- Specific tiling configurations validated on hardware
- Performance measurements (cycles per tile) for reference designs
- Bank conflict avoidance in tiling layouts
- Ping-pong buffer tiling patterns (overlap compute with DMA)
- Tiling for transpose operations
-->
