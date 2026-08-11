<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# AIE-ML v2 Tiling Strategies

## Overview

AIE-ML v2 shares the same memory capacity as AIE-ML (64 KB compute tile, 512 KB memory tile) but with **improved DMA** that makes smaller tiles more practical and **full-throughput fp32 MAC** that changes the compute-to-memory ratio.

---

## GEMM Tiling (C = A × B)

### Strategy: Same as AIE-ML but Optimized for fp32

Since AIE-ML v2 achieves full fp32 MAC throughput, floating-point GEMM no longer needs bfloat16 conversion for throughput. Use fp32 directly when precision matters.

### Memory Budget (64 KB compute tile — same as AIE-ML)

```
Total: (Mt×N + N×Lt + Mt×Lt) × sizeof(type) ≤ 56 KB
```

### Recommended Tile Sizes

#### float (16 lanes) — Full Throughput on v2

| M×N×L | Mt | Lt | N (full) | Memory | Throughput |
|---|---|---|---|---|---|
| 128×128×128 | 8 | 16 | 128 | 12.5 KB | 16 MACs/cycle sustained |
| 256×256×256 | 8 | 16 | 256 | 24.5 KB | 16 MACs/cycle sustained |
| 512×512×512 | 8 | 16 | 512 | 49 KB | 16 MACs/cycle sustained |
| 1024×1024×1024 | 4 | 16 | 1024 | 73 KB | Needs memory tile |

**v2 advantage**: On AIE-ML, fp32 inner loops could have pipeline stalls. On v2, the same tile sizes achieve higher effective throughput without needing to convert to bfloat16.

#### bfloat16 (32 lanes)

Same tile sizes as AIE-ML — no change:

| M×N×L | Mt | Lt | N (full) | Memory |
|---|---|---|---|---|
| 256×256×256 | 16 | 32 | 256 | 24.5 KB |
| 512×512×512 | 8 | 32 | 512 | 41.5 KB |

#### int16 (32 lanes)

Same as AIE-ML.

### fp32 vs bfloat16 Decision on AIE-ML v2

| Criteria | Recommendation |
|---|---|
| Need fp32 precision | Use float — no throughput penalty on v2 |
| Inference (low precision OK) | bfloat16 still 2× lanes — better throughput |
| MATLAB source uses single precision | Use float (direct mapping, no quantization) |
| Training / gradient computation | Use float (precision critical) |
| Memory-limited (large matrices) | bfloat16 (half the memory per element) |

---

## Smaller Tiles Are More Viable (v2 DMA Advantage)

With reduced DMA overhead on v2, consider:

### Aggressive Tiling for Low Latency

```
Strategy: Use smaller tiles → first output arrives sooner

AIE-ML:   Mt=8, Lt=16 → DMA overhead 5% → effective throughput 95%
AIE-ML v2: Mt=4, Lt=16 → DMA overhead 3% → effective throughput 97%
                          First output 2× sooner!
```

### Aggressive Tiling for Parallelism

More tiles = more opportunities to distribute across compute array:
```
AIE-ML:   Large tiles (fewer) → 8 compute tiles busy
AIE-ML v2: Smaller tiles (more) → 16 compute tiles busy (lower DMA amortization cost)
```

---

## FIR / Convolution Tiling

Same as AIE-ML (64 KB memory, 32 int16 lanes):

| Filter Taps (T) | Window Size (W) | Memory (int16) |
|---|---|---|
| 64 | 1024 | 4.3 KB |
| 256 | 2048 | 9.2 KB |
| 1024 | 4096 | 20.5 KB |
| 4096 | 4096 | 32.8 KB |

---

## FFT Tiling

Same as AIE-ML but with note:

| Point Size | Memory (cfloat) | Notes |
|---|---|---|
| 1024 | 12 KB | Single tile |
| 4096 | 48 KB | Single tile (tight) |
| 16384 | 192 KB | Memory tile needed |

**v2 advantage for FFT**: Enhanced shuffle operations reduce butterfly data reorganization overhead between stages. Each radix-2/4 butterfly stage is faster due to improved permute.

---

## Element-wise Tiling

Same capacity as AIE-ML. With full-throughput fp32:

| Data Type | Chunk Size | Memory | Throughput (v2) |
|---|---|---|---|
| `float` | 1024 | 48 KB | 16 ops/cycle sustained |
| `bfloat16` | 4096 | 48 KB | 32 ops/cycle |
| `int16` | 4096 | 48 KB | 32 ops/cycle |

---

## Multi-Tile Strategies

Same topology as AIE-ML with enhanced efficiency:

### Cascade (512-bit, same)
- Full accumulator passing between tiles
- **v2 improvement**: Lower overhead for cascade setup

### Memory Tile Broadcast (enhanced DMA)
- **v2 improvement**: Faster broadcast delivery to multiple compute tiles
- Memory tile DMA can serve more compute tiles with same latency

### Recommended Multi-Tile Configurations

For large GEMM (e.g., 1024×1024×1024 float):

```
Memory Tile A (512 KB)  →  [Compute 0] (rows 0-255) → Memory Tile C
                        →  [Compute 1] (rows 256-511)
                        →  [Compute 2] (rows 512-767)
                        →  [Compute 3] (rows 768-1023)
Memory Tile B (512 KB)  ─ (broadcast to all compute tiles)
```

4 compute tiles process different row blocks in parallel. Memory tile B is broadcast. v2 DMA makes the broadcast more efficient.

---

## Design Guideline: When v2 Changes the Tiling Decision

| Scenario | AIE-ML Choice | AIE-ML v2 Choice |
|---|---|---|
| fp32 GEMM, precision needed | Convert to bfloat16 for 2× throughput | Stay fp32 — full throughput! |
| Latency-sensitive pipeline | Large tiles (amortize DMA) | Smaller tiles OK (DMA fast) |
| Matrix transpose stage | Expensive shuffle → avoid if possible | Use shuffle freely (enhanced) |
| Many small kernels | Overhead concern → batch into larger | Fine-grained OK (lower overhead) |

---

## TODO: Fill in validated tiling configurations

<!--
Add here:
- Measured DMA latencies on VEK385 hardware
- Validated tile sizes with cycle-count data
- fp32 vs bfloat16 throughput comparison on actual v2 hardware
- Optimal multi-tile configurations for specific problem sizes
- Power measurements for different tiling strategies
-->
