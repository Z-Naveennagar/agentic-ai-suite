<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# AIE-ML v2 Architecture Capabilities

## Overview

| Property | Value |
|---|---|
| Generation | AIE-ML v2 (3rd generation) |
| Representative devices | XCVE3858 (VEK385) |
| Tile types | Compute Tile + Memory Tile |
| Vector unit width | 512-bit |
| Scalar unit | 32-bit |
| Local data memory | 64 KB per compute tile |
| Memory tile | 512 KB per memory tile |
| Program memory | 16 KB per tile |
| Clock frequency | Up to 1.25 GHz |
| Cascade width | 512-bit |
| fp32 Vector MAC | **Full throughput** (improved from AIE-ML) |

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

## Key Improvements over AIE-ML

### fp32 Vector MAC
- AIE-ML: fp32 MAC available but with pipeline bubbles reducing effective throughput
- AIE-ML v2: **Full throughput fp32 vector MAC** — 16 float MACs per cycle sustained
- Eliminates the need to convert to bfloat16 for throughput in many floating-point workloads

### Enhanced Shuffle/Permute
- Faster vector element reorganization operations
- More efficient matrix transpose implementation
- Reduced cycle count for data reformatting between compute stages

### Enhanced DMA
- Lower latency memory tile DMA transfers
- Faster DMA reconfiguration between transfer patterns
- Improved overlap of DMA and compute operations
- More efficient 2D/3D tiling patterns

### Power Efficiency
- Improved performance per watt
- More efficient clock gating and power management
- Same compute capability with reduced energy

## Compute Throughput (per compute tile per cycle)

| Operation | int4 | int8 | int16 | int32 | float | bfloat16 |
|---|---|---|---|---|---|---|
| MACs | 512 | 256 | 32 | 16 | **16** | 32 |
| Add/Sub | 128 | 64 | 32 | 16 | 16 | 32 |

**Note**: float MACs at 16/cycle is now **sustained** (no pipeline bubbles), unlike AIE-ML where effective throughput could be lower in certain patterns.

## Memory Architecture

### Compute Tile Memory
- **Data memory**: 64 KB (8 banks × 8 KB each)
- Same capacity as AIE-ML
- Improved memory access scheduling

### Memory Tiles
- **Capacity**: 512 KB per memory tile
- **Enhanced DMA**: Lower latency, faster reconfiguration
- **2D/3D tiling**: Same API as AIE-ML but with improved performance
- **Connectivity**: AXI-Stream to adjacent compute tiles

## Platform Constraints (VEK385)

| Resource | Count |
|---|---|
| Compute tiles | <!-- TODO: fill in --> |
| Memory tiles | <!-- TODO: fill in --> |
| PLIOs | 16 |
| PLIO width | 128-bit max |

---

## TODO: Fill in additional AIE-ML v2 details

<!--
Add here:
- Exact compute tile array dimensions for VEK385
- Specific fp32 MAC pipeline details (what changed from AIE-ML)
- Enhanced shuffle operation specifics
- DMA improvement details (latency numbers)
- Any new instructions or capabilities not in AIE-ML
- Power consumption data
- Thermal constraints
-->
