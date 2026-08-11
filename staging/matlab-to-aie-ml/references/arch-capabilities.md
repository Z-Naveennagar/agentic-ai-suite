<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# AIE-ML Architecture Capabilities

## Overview

| Property | Value |
|---|---|
| Generation | AIE-ML (2nd generation) |
| Representative devices | XCVE2802 (VEK280) |
| Tile types | Compute Tile + **Memory Tile** |
| Vector unit width | 512-bit |
| Scalar unit | 32-bit |
| Local data memory | 64 KB per compute tile |
| Memory tile | 512 KB per memory tile |
| Program memory | 16 KB per tile |
| Clock frequency | Up to 1.25 GHz |
| Cascade width | 512-bit |
| Memory banks | 8 per compute tile |

## Supported Data Types

| Type | Width | Vector Lanes (512-bit) | Accumulator |
|---|---|---|---|
| `int4` | 4-bit | 128 | `acc32` |
| `int8` | 8-bit | 64 | `acc32` |
| `int16` | 16-bit | 32 | `acc64` |
| `int32` | 32-bit | 16 | `acc64` |
| `float` | 32-bit | 16 | `accfloat` |
| `bfloat16` | 16-bit | 32 | `accfloat` |
| `cint16` | 32-bit (16+16) | 16 | `cacc64` |
| `cint32` | 64-bit (32+32) | 8 | `cacc64` |
| `cfloat` | 64-bit (32+32) | 8 | `caccfloat` |

**New in AIE-ML (not available in AIE 1st gen)**:
- `bfloat16` — 16-bit brain floating-point with native MAC support
- `int4` — 4-bit integer for ultra-low-precision inference
- Sparse matrix operations — native support for sparse data encoding
- Memory tiles — 512 KB dedicated memory blocks for data staging

## Compute Throughput (per compute tile per cycle)

| Operation | int4 | int8 | int16 | int32 | float | bfloat16 |
|---|---|---|---|---|---|---|
| MACs | 512 | 256 | 32 | 16 | 16 | 32 |
| Add/Sub | 128 | 64 | 32 | 16 | 16 | 32 |

## Memory Architecture

### Compute Tile Memory
- **Data memory**: 64 KB (8 banks × 8 KB each)
- **Doubled from AIE**: 2× the local memory of 1st gen
- **Bank width**: 256-bit per bank per cycle
- **Ping-pong**: Hardware double-buffering for overlapping DMA with compute

### Memory Tiles
- **Capacity**: 512 KB per memory tile
- **Purpose**: Large data staging between DDR/PL and compute tiles
- **DMA engines**: Programmable DMA with tiling/striding support
- **Connectivity**: Connected to adjacent compute tiles via AXI-Stream
- **Use cases**: 
  - Staging large matrices that don't fit in 64 KB compute tile memory
  - Implementing multi-dimensional DMA patterns (2D/3D tiling)
  - Shared data between multiple compute tiles

### Memory Tile DMA Tiling

```
Memory tile DMA supports:
- 2D tiling: Extract sub-blocks from large matrices
- 3D tiling: Iterate over batches of 2D tiles
- Stride support: Non-contiguous access patterns
- Wrap/repeat: Circular buffering at DMA level
```

## Cascade Interface
- **Width**: 512-bit (vs 384-bit in AIE)
- **Direction**: Horizontal (E↔W) between adjacent compute tiles
- **Latency**: 1 cycle
- **Use**: Pass partial accumulation results between tiles without memory

## Sparse Matrix Support

AIE-ML natively supports sparse data encoding:
- Sparse MAC operations that skip zero-valued elements
- Compressed sparse format for weights/coefficients  
- Up to 2× effective throughput for ≥50% sparse data

---

## TODO: Fill in additional AIE-ML architecture details

<!--
Add here:
- Specific memory tile DMA configuration syntax
- Sparse matrix encoding format details
- Tile array dimensions for VEK280
- PLIO count and constraints for VEK280 (16 PLIOs)
- Detailed bank conflict rules for 64 KB memory
- AIE-ML specific scheduling constraints
- Power/thermal considerations
-->
