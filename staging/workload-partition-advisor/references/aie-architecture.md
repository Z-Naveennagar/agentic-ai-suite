<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# AIE Architecture Reference (AM009 v1.4)

Source: Versal Adaptive SoC AI Engine Architecture Manual (AM009), February 2026

## Tile Overview

- **Processor**: 7-way VLIW, SIMD vector unit
- **Data memory**: 32 KB per tile (8 banks × 4 KB each, 256-bit wide)
- **Accessible memory**: 4 memory modules = 128 KB total (own + 3 neighbors, shared)
- **Program memory**: 16 KB
- **Vector register file**: 8 × 256-bit (or 4 × 512-bit views)
- **Accumulator**: 4 × 384-bit (or 8 × 48-bit lanes)
- **Load/Store**: Two 256-bit loads + one 256-bit store per cycle

## Streams and Interfaces

| Interface | Width | Count per Tile | Bandwidth |
|-----------|-------|----------------|-----------|
| AXI4-Stream input | 32-bit | 2 | 4 GB/s each @ 1 GHz |
| AXI4-Stream output | 32-bit | 2 | 4 GB/s each @ 1 GHz |
| Cascade | 384-bit | 1 in + 1 out | 48 GB/s @ 1 GHz |
| Memory load ports | 256-bit | 2 | 64 GB/s total @ 1 GHz |
| Memory store port | 256-bit | 1 | 32 GB/s @ 1 GHz |

- Intra-array stream switch: **32-bit AXI4-Stream crossbar** @ AIE clock
- PL interface (PLIO): **64-bit** @ PL clock (500 MHz for -1L) = **4 GB/s per stream**
- Per-column PL interface: 8 streams PL→AIE + 6 streams AIE→PL

## MAC Table (Table 7 from AM009)

Peak multiply-accumulate operations per clock cycle:

| X Operand | Z Operand | Output Precision | MACs/cycle |
|-----------|-----------|-----------------|------------|
| int8 real | int8 real | acc48 real | 128 |
| int16 real | int8 real | acc48 real | 64 |
| int16 real | int16 real | acc48 real | 32 |
| int16 real | int16 complex | acc48 complex | 16 |
| int16 complex | int16 real | acc48 complex | 16 |
| int16 complex | int16 complex | acc48 complex | 8 |
| int16 real | int32 real | acc48/80 real | 16 |
| int16 complex | int32 real | acc48/80 complex | 8 |
| int16 complex | int32 complex | acc48/80 complex | 4 |
| int32 real | int16 real | acc48/80 real | 16 |
| int32 complex | int16 complex | acc48/80 complex | 4 |
| int32 real | int32 real | acc80 real | 8 |
| int32 complex | int32 complex | acc80 complex | 2 |
| float32 | float32 | float32 | 8 |

### Common Data Type Quick Reference

| Use Case | Typical Types | MACs/cycle |
|----------|---------------|------------|
| Narrowband FIR (data×coeff) | cint16 × int16 | 16 |
| Wideband FIR (data×coeff) | cint16 × int32 | 8 |
| Real filtering | int16 × int16 | 32 |
| Complex-to-complex | cint16 × cint16 | 8 |
| Floating-point DSP | float × float | 8 |
| Low-precision ML | int8 × int8 | 128 |

## Clock Speeds by Speed Grade (from DS957)

| Speed Grade | Voltage (VCCINT) | AIE FMAX | PL Interface FMAX |
|-------------|-----------------|----------|-------------------|
| -2H | 0.88V | 1300 MHz | 650 MHz |
| -2M | 0.80V | 1250 MHz | 625 MHz |
| -1M | 0.80V | 1150 MHz | 575 MHz |
| -2LLI | 0.725V | 1050 MHz | 525 MHz |
| -2L | 0.70V | 1050 MHz | 525 MHz |
| -1L | 0.70V | 1000 MHz | 500 MHz |

## Memory Architecture Details

- Each tile's data memory: 8 banks × 4 KB = 32 KB
- Bank width: 256 bits (32 bytes) — one access per bank per cycle
- Tile can access 4 memory modules (own tile + up to 3 neighbors): 128 KB total addressable
- **Bank conflict**: Two accesses to the same bank in the same cycle cause a stall
- ECC protection on all data memory
- Ping-pong buffers: framework-managed double-buffering for streaming I/O

## Devices with AIE Architecture

| Device | Board | AIE Tiles | Columns | Rows |
|--------|-------|-----------|---------|------|
| XCVC1902 | VCK190 | 400 | 50 | 8 |
| XCVC1802 | — | 400 | 50 | 8 |
| XCVC1702 | — | 400 | 50 | 8 |
| XCVC1502 | — | 400 | 50 | 8 |

Note: VC2602/VC2802 devices use AIE-ML architecture (see aie-ml-architecture.md).
Authoritative tile counts: DS950 (Versal Architecture and Product Data Sheet: Overview).
