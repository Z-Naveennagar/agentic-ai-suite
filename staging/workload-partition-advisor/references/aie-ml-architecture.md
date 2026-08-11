<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# AIE-ML Architecture Reference (AM020 v1.5)

Source: Versal Adaptive SoC AIE-ML Architecture Manual (AM020), February 2026

## Tile Overview

- **Processor**: VLIW, SIMD vector unit with ML-optimized datapath
- **Data memory**: 64 KB per tile (8 banks × 8 KB each, 256-bit wide)
- **Accessible memory**: 4 memory modules = 256 KB total (own + 3 neighbors, shared)
- **Program memory**: 16 KB
- **Accumulator lanes**: 32 lanes × 32-bit OR 16 lanes × 64-bit
- **Load/Store**: High-bandwidth memory interface (200+ GB/s per tile aggregate)

## Streams and Interfaces

| Interface | Width | Count per Tile | Bandwidth |
|-----------|-------|----------------|-----------|
| AXI4-Stream input | 32-bit | 1 | 4 GB/s @ 1 GHz |
| AXI4-Stream output | 32-bit | 1 | 4 GB/s @ 1 GHz |
| Memory interface | 256-bit | Multiple ports | 200+ GB/s aggregate |

- Intra-array stream switch: **32-bit AXI4-Stream crossbar** @ AIE-ML clock
- PL interface (PLIO): **64-bit** @ PL clock (500 MHz for -1L) = **4 GB/s per stream**
- Per-column PL interface: 8 streams PL→AIE-ML + 6 streams AIE-ML→PL
- Per-column bandwidth: 32 GB/s PL→AIE-ML, 24 GB/s AIE-ML→PL

## Memory Tiles

- **Capacity**: 512 KB per memory tile
- **DMA channels**: 12 (8 can access neighboring memory tiles)
- **Purpose**: Large coefficient storage, deep buffering, weight pre-loading for ML
- **Stream interface**: 6 × 64-bit MM2S and S2MM channels
- Located between AIE-ML compute tile rows and the array interface

### Memory Tile → Compute Tile Streaming

- **Stream width**: 32-bit AXI4-Stream @ AIE-ML clock
- **Bandwidth per stream**: 4 bytes × clock (e.g., 5 GB/s @ 1250 MHz, 4 GB/s @ 1 GHz)
- **Use case**: Coefficient delivery from Memory Tiles to compute kernels
- **Constraint**: This per-stream bandwidth is the limiting factor when deciding whether coefficients can reside remotely in Memory Tiles vs. locally in compute tile memory. If the compute tile's coefficient demand rate exceeds the available stream bandwidth, coefficients must be stored locally.

## MAC Table (Table 7 from AM020)

Peak multiply-accumulate operations per clock cycle:

| Precision 1 | Precision 2 | Accum Lanes | Accum Bits | MACs/cycle |
|-------------|-------------|-------------|------------|------------|
| int8 | int8 | 32 | 32 | 256 |
| int16 | int8 | 32 | 32 | 128 |
| int16 | int8 | 16 | 64 | 128 |
| int16 | int16 | 32 | 32 | 64 |
| int16 | int16 | 16 | 64 | 64 |
| int32 | int16 | 16 | 64 | 32 |
| cint16 | cint16 | 8 | 64 | 16 |
| cint32 | cint16 | 8 | 64 | 8 |
| bfloat16 | bfloat16 | 16 | float32 | 32 |

### Notes on Emulated Types
- **int32 × int32**: Emulated at half performance of int32 × int16 → ~16 mults/cycle
- **float32 × float32**: Emulated via bfloat16 decomposition, deviates from IEEE 754

### Common Data Type Quick Reference

| Use Case | Typical Types | MACs/cycle |
|----------|---------------|------------|
| ML inference (INT8) | int8 × int8 | 256 |
| Narrowband FIR | int16 × int16 | 64 |
| Wideband FIR (32-bit coeff) | int32 × int16 | 32 |
| Complex filtering | cint16 × cint16 | 16 |
| Complex wideband | cint32 × cint16 | 8 |
| bfloat16 neural network | bfloat16 × bfloat16 | 32 |

## Clock Speeds by Speed Grade (from DS957/DS958)

| Speed Grade | Voltage (VCCINT) | AIE-ML FMAX | PL Interface FMAX |
|-------------|-----------------|-------------|-------------------|
| -2H | 0.88V | 1300 MHz | 650 MHz |
| -2M | 0.80V | 1250 MHz | 625 MHz |
| -1M | 0.80V | 1150 MHz | 575 MHz |
| -2LLI | 0.725V | 1050 MHz | 525 MHz |
| -2L | 0.70V | 1050 MHz | 525 MHz |
| -1L | 0.70V | 1000 MHz | 500 MHz |

## Memory Architecture Details

- Each tile's data memory: 8 banks × 8 KB = 64 KB
- Bank width: 256 bits (32 bytes)
- Tile can access 4 memory modules (own + neighbors): 256 KB total addressable
- First two banks have lower access latency (optimized for hot data)
- ECC protection on all data and program memory
- Memory-mapped AXI4 access supported for debug and configuration

## Devices with AIE-ML Architecture

| Device | Board | AIE-ML Tiles | Memory Tiles | Columns |
|--------|-------|-------------|--------------|---------|
| XCVE2802 | VEK280 | 304 | 38 | 38 |
| XCVE2602 | — | 304 | 38 | 38 |
| XCVE2302 | VEK240 | 34 | 8 | 8 |
| XCVE2202 | — | 34 | 8 | 8 |
| XCVE2102 | — | 16 | 4 | 4 |
| XCVE2002 | — | 8 | 2 | 2 |
| XCVE1752 | — | 16 | 4 | 4 |
| XCVC2802 | — | 304 | 38 | 38 |
| XCVC2602 | — | 304 | 38 | 38 |

Note: VC2602/VC2802 are AI Core series with AIE-ML (not original AIE).
Authoritative tile counts: DS950 (Versal Architecture and Product Data Sheet: Overview).
