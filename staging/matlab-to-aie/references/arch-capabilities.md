<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# AIE Architecture Capabilities

## Overview

| Property | Value |
|---|---|
| Generation | AIE (1st generation) |
| Representative devices | XCVC1902 (VCK190) |
| Tile type | AI Engine Tile |
| Vector unit width | 256-bit |
| Scalar unit | 32-bit VLIW |
| Local data memory | 32 KB (8 banks × 4 KB) |
| Program memory | 16 KB |
| Clock frequency | Up to 1.25 GHz |
| Cascade width | 384-bit |
| Memory banks | 8 per tile |

## Supported Data Types

| Type | Width | Vector Lanes (256-bit) | Accumulator |
|---|---|---|---|
| `int8` | 8-bit | 32 | `acc48` |
| `int16` | 16-bit | 16 | `acc48` |
| `int32` | 32-bit | 8 | `acc80` |
| `float` | 32-bit | 8 | `accfloat` |
| `cint16` | 32-bit (16+16) | 8 | `cacc48` |
| `cint32` | 64-bit (32+32) | 4 | `cacc80` |
| `cfloat` | 64-bit (32+32) | 4 | `caccfloat` |

**NOT supported on AIE (1st gen)**:
- `bfloat16` (requires AIE-ML or AIE-ML v2)
- Sparse matrix operations (requires AIE-ML or AIE-ML v2)
- Memory tiles (requires AIE-ML or AIE-ML v2)

## Compute Throughput (per tile per cycle)

| Operation | int8 | int16 | int32 | float |
|---|---|---|---|---|
| MACs | 128 | 16 | 8 | 8 |
| Multiplications | 128 | 16 | 8 | 8 |
| Additions | 32 | 16 | 8 | 8 |

## Memory Architecture

- **Data memory**: 32 KB split into 8 banks (4 KB each)
- **Bank conflicts**: Accessing two addresses in the same bank in the same cycle stalls the pipeline
- **Ping-pong buffers**: Hardware supports double-buffering for overlapping compute with I/O
- **DMA channels**: 2 input + 2 output DMA channels per tile for data movement
- **Cascade interface**: 384-bit direct connection between horizontally adjacent tiles (1 cycle latency)

## Memory Budget for Kernel Design

When designing tiling strategy, account for:
- Input buffer(s): Must fit in local memory
- Output buffer: Must fit in local memory
- Coefficient storage (if applicable): Fits in local memory
- Stack: 2 KB default
- **Total available for buffers**: ~28-30 KB (after stack/overhead)

## Tile Array Organization

- 2D array of tiles (rows × columns)
- Each tile has 4 neighbors: N, S, E, W
- Cascade connections: horizontal only (E↔W)
- Memory sharing: each tile can access its own memory + neighbor's memory (with bank conflict rules)

---

## TODO: Fill in additional architecture-specific details

<!-- 
Add here:
- Specific AIE instruction set constraints
- Scheduling rules (operations that can execute in parallel)
- Known limitations or errata
- Platform-specific constraints (VCK190 tile count, PLIO count, etc.)
-->
