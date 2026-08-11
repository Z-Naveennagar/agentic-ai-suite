<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# AIE-ML v2 Architecture Reference (AM027 v1.1)

Source: Versal Adaptive SoC AIE-ML v2 Architecture Manual (AM027), October 2025

## Tile Overview

- **Processor**: VLIW, SIMD vector unit with enhanced ML/AI datapath
- **Data memory**: 64 KB per tile (8 banks × 8 KB each, 256-bit wide)
- **Accessible memory**: 4 memory modules = 256 KB total (own + 3 neighbors, shared)
- **Program memory**: 16 KB
- **Accumulator lanes**: 64 lanes × 32-bit OR 32 lanes × 64-bit
- **Key delta vs. AIE-ML**: Doubled accumulator width, doubled intra-array stream bandwidth, new data types (float16, float8, MX block floating point), 50% sparsity support

## Streams and Interfaces

| Interface | Width | Count per Tile | Bandwidth |
|-----------|-------|----------------|-----------|
| AXI4-Stream input | 64-bit | 1 | 8 GB/s @ 1 GHz |
| AXI4-Stream output | 64-bit | 1 | 8 GB/s @ 1 GHz |
| Memory interface | 256-bit | Multiple ports | 200+ GB/s aggregate |

- Intra-array stream switch: **64-bit AXI4-Stream crossbar** @ AIE-ML v2 clock (**doubled** vs. AIE/AIE-ML)
- PL interface (PLIO): **64-bit** @ PL clock (500 MHz for -1L) = **4 GB/s per stream**
- Per-column PL interface: 8 streams PL→AIE + 6 streams AIE→PL (same as AIE-ML)
- Per-column bandwidth: 32 GB/s PL→AIE, 24 GB/s AIE→PL

## Memory Tiles

- **Capacity**: 512 KB per memory tile
- **DMA channels**: 12 (8 can access neighboring memory tiles)
- **Stream interface**: 6 × MM2S and S2MM channels with 64-bit stream interfaces
- **Purpose**: Large weight storage for ML, deep coefficient banks, ping-pong buffering
- Depending on device, one or two rows of memory tiles

## MAC Table (Table 7 from AM027)

Peak multiply-accumulate operations per clock cycle:

| Precision 1 | Precision 2 | Accum Lanes | Accum Bits | MACs/cycle |
|-------------|-------------|-------------|------------|------------|
| int8 | int8 | 64 | 32 | 512 |
| int16 | int16 | 64 | 32 | 128 |
| int16 | int16 | 32 | 64 | 128 |
| int32 | int16 | 32 | 64 | 64 |
| bfloat16 | bfloat16 | 32 | float32 | 256 |
| float16 | float16 | 32 | float32 | 256 |
| float8 (E4M3) | float8 (E4M3) | 64 | float32 | 512 |
| MX6 | MX6 | 64 | float32 | 1024 |
| MX9 | MX9 | 64 | float32 | 512 |

### Notes on Data Types
- **MX block floating point** (MX4, MX6, MX9): Microscaling format for ML — shared exponent across a block of mantissas. Highest throughput format.
- **float8 (E4M3 / E5M2)**: 8-bit floating point variants for inference
- **50% sparsity**: Hardware support for structured sparsity — effectively doubles throughput for sparse models
- **int32 × int32**: Can be emulated by decomposition into int32 × int16 operations
- **4-bit × 4-bit**: Can be emulated

### Common Data Type Quick Reference

| Use Case | Typical Types | MACs/cycle |
|----------|---------------|------------|
| ML inference (INT8) | int8 × int8 | 512 |
| ML inference (sparse INT8) | int8 × int8 (50% sparse) | ~1024 effective |
| DSP filtering (16-bit) | int16 × int16 | 128 |
| Wideband DSP (32-bit coeff) | int32 × int16 | 64 |
| Neural network (bfloat16) | bfloat16 × bfloat16 | 256 |
| Neural network (float16) | float16 × float16 | 256 |
| Ultra-low-precision ML | float8 × float8 | 512 |
| MX compressed weights | MX6 × MX6 | 1024 |

## Clock Speeds by Speed Grade (from DS1021)

| Speed Grade | Voltage (VCC_AIE) | AIE-ML v2 FMAX | PL Interface FMAX |
|-------------|-------------------|----------------|-------------------|
| -2M | 0.80V | 1250 MHz | 625 MHz |
| -1M | 0.80V | 1200 MHz | 600 MHz |
| -2LLI | 0.725V | 1050 MHz | 525 MHz |
| -2L | 0.70V | 1050 MHz | 525 MHz |
| -1L | 0.70V | 1000 MHz | 500 MHz |

Note: -1L devices support dual-voltage operation (VCC_AIE at 0.70V standard or 0.80V overdrive).

## Memory Architecture Details

- Each tile's data memory: 8 banks × 8 KB = 64 KB
- Bank width: 256 bits (32 bytes)
- Tile can access 4 memory modules (own + neighbors): 256 KB total addressable
- Same memory tile structure as AIE-ML (512 KB, 12 DMA channels)
- Enhanced DMA with 6 MM2S + 6 S2MM channels per memory tile

## Devices with AIE-ML v2 Architecture

| Device | AIE-ML v2 Tiles | Memory Tiles | Notes |
|--------|----------------|--------------|-------|
| XC2VE3304 | TBD | TBD | Versal AI Edge Gen 2 |
| XC2VE3358 | TBD | TBD | Versal AI Edge Gen 2 |
| XC2VE3504 | TBD | TBD | Versal AI Edge Gen 2 (mid-range) |
| XC2VE3558 | TBD | TBD | Versal AI Edge Gen 2 |
| XC2VE3804 | TBD | TBD | Versal AI Edge Gen 2 (largest) |
| XC2VE3858 | TBD | TBD | Versal AI Edge Gen 2 |

Note: Exact tile counts not available in DS1021 — see DS950 for authoritative resource counts.
Relative sizing from PL interface bandwidth (DS1021 Table 77):
- 2VE3304/3358: 280 GB/s PL→AIE (smallest)
- 2VE3504/3558: 720 GB/s PL→AIE (mid)
- 2VE3804/3858: 1080 GB/s PL→AIE (largest)
