<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# AIE-ML Tiling Strategies

## Overview

AIE-ML has doubled local memory (64 KB) and adds 512 KB memory tiles, enabling significantly larger working sets than AIE (1st gen). Tiling strategy should exploit both compute tile memory and memory tiles.

---

## GEMM Tiling (C = A × B)

### Strategy: Memory Tile Staging + Compute Tile Processing

For large matrices that exceed 64 KB compute tile memory:

```
DDR → Memory Tile (512 KB) → Compute Tile (64 KB) → Memory Tile → DDR
        ↑ DMA tiling                  ↑ Kernel processing
        Stage full rows/blocks        Process one output tile per invocation
```

### Memory Budget Calculation (64 KB compute tile)

```
Input A tile: Mt × N × sizeof(type) bytes
Input B tile: N × Lt × sizeof(type) bytes
Output C tile: Mt × Lt × sizeof(type) bytes
Total: (Mt×N + N×Lt + Mt×Lt) × sizeof(type) ≤ 56 KB (leaving headroom for stack)
```

### Recommended Tile Sizes (AIE-ML, 512-bit vector)

#### float (16 lanes)

| M×N×L | Mt | Lt | N (full) | Memory | Notes |
|---|---|---|---|---|---|
| 128×128×128 | 8 | 16 | 128 | (8×128 + 128×16 + 8×16)×4 = 12.5 KB | Easy |
| 256×256×256 | 8 | 16 | 256 | (8×256 + 256×16 + 8×16)×4 = 24.5 KB | Fits |
| 512×512×512 | 8 | 16 | 512 | (8×512 + 512×16 + 8×16)×4 = 49 KB | Tight |

#### bfloat16 (32 lanes)

| M×N×L | Mt | Lt | N (full) | Memory | Notes |
|---|---|---|---|---|---|
| 128×128×128 | 16 | 32 | 128 | (16×128 + 128×32 + 16×32)×2 = 12.3 KB | Easy |
| 256×256×256 | 16 | 32 | 256 | (16×256 + 256×32 + 16×32)×2 = 24.5 KB | Fits |
| 512×512×512 | 8 | 32 | 512 | (8×512 + 512×32 + 8×32)×2 = 41.5 KB | Fits |

#### int16 (32 lanes)

| M×N×L | Mt | Lt | N (full) | Memory | Notes |
|---|---|---|---|---|---|
| 256×256×256 | 16 | 32 | 256 | (16×256 + 256×32 + 16×32)×2 = 24.5 KB | Fits |
| 512×512×512 | 16 | 32 | 512 | (16×512 + 512×32 + 16×32)×2 = 49 KB | Tight |
| 1024×1024×1024 | 8 | 32 | 1024 | (8×1024 + 1024×32 + 8×32)×2 = 82 KB | Needs mem tile |

### When to Use Memory Tiles

**Use memory tiles when**: Total data per kernel invocation > 64 KB, OR multiple compute tiles need to share the same input data.

**Strategy with memory tiles**:
1. DMA moves full matrix row/block from DDR → Memory Tile
2. Memory Tile DMA extracts sub-tiles → Compute Tile local memory
3. Compute tile processes one output tile
4. Result written back: Compute Tile → Memory Tile → DDR

---

## FIR / Convolution Tiling

### AIE-ML Advantage: Larger Windows

With 64 KB local memory, window sizes can be 2× larger than AIE (1st gen):

| Filter Taps (T) | Window Size (W) | Memory (int16) | Notes |
|---|---|---|---|
| 64 | 1024 | (1088 + 64 + 1024)×2 = 4.3 KB | Light |
| 256 | 2048 | (2304 + 256 + 2048)×2 = 9.2 KB | Moderate |
| 1024 | 4096 | (5120 + 1024 + 4096)×2 = 20.5 KB | Heavy but fits |
| 4096 | 4096 | (8192 + 4096 + 4096)×2 = 32.8 KB | Fits in 64 KB |

### For Very Large Filters (>4096 taps)

Stage filter coefficients in memory tile, stream chunks to compute tile:
- Memory tile holds all coefficients
- Compute tile cycles through coefficient chunks
- Accumulate partial results across chunks

---

## FFT Tiling

### AIE-ML: Larger Point Sizes Per Tile

| Point Size | Memory (cfloat=8B) | Fits in 64 KB? | Notes |
|---|---|---|---|
| 256 | 256×8 + 128×8 = 3 KB | Yes | Single tile |
| 1024 | 1024×8 + 512×8 = 12 KB | Yes | Single tile |
| 4096 | 4096×8 + 2048×8 = 48 KB | Yes | Tight single tile |
| 16384 | 16384×8 + 8192×8 = 192 KB | No → memory tile | Split stages |

### Multi-Tile FFT with Memory Tiles

For FFTs > 4096 points:
1. First stage(s) in compute tile(s)
2. Store intermediate results in memory tile (512 KB)
3. Memory tile DMA reorders data for next stage
4. Continue processing in compute tile(s)

---

## Element-wise Tiling (AIE-ML)

With 64 KB and 32 int16 lanes or 16 float lanes:

| Data Type | Max Chunk (binary op, 3 buffers) | Elements | Vectors/iter |
|---|---|---|---|
| `float` | 56 KB / 12 = 4.6 KB per buf | 1170 | 73 |
| `int16` | 56 KB / 6 = 9.3 KB per buf | 4778 | 149 |
| `bfloat16` | 56 KB / 6 = 9.3 KB per buf | 4778 | 149 |

**Practical recommendation**: Round down to nice multiples of vector lanes:
- float: 1024 elements per chunk (16 KB × 3 = 48 KB)
- int16/bfloat16: 4096 elements per chunk (16 KB × 3 = 48 KB)

---

## Multi-Tile Strategies (AIE-ML)

### Cascade (512-bit)
- **Wider than AIE**: 512-bit cascade link (vs 384-bit)
- Passes full accumulator between tiles in 1 cycle
- **Use for**: Deep reduction (large N in GEMM), multi-stage filters

### Memory Tile Broadcast
- Single memory tile feeds data to multiple compute tiles
- **Use for**: Same input matrix shared across output tile row
- Memory tile DMA handles repetition — compute tiles each process different output tiles

### Compute Tile Array + Memory Tile
```
DDR → Memory Tile(s) → [Compute Tile 0] → Memory Tile → DDR
                      → [Compute Tile 1] →
                      → [Compute Tile 2] →
                      → [Compute Tile 3] →
```

Each compute tile processes a different output tile in parallel.

---

## Sparse GEMM Tiling (AIE-ML specific)

For sparse weight matrices (>50% zeros):
- Sparse encoding eliminates zero multiplications
- Effective throughput: up to 2× dense throughput
- Tiling unchanged, but inner loop iterations reduced proportionally

---

## TODO: Fill in additional tiling details

<!--
Add here:
- Validated tile sizes from real AIE-ML hardware runs
- Memory tile DMA configuration examples for 2D tiling
- Ping-pong buffer scheduling with memory tiles
- Performance comparison: with vs without memory tiles
- Sparse GEMM tiling specifics
-->
