<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Device Catalog

Versal devices with AI Engine arrays, organized by architecture generation.

## Architecture Identification

| Architecture | Series | Prefix | Introduced |
|---|---|---|---|
| AIE (original) | Versal AI Core (1st gen) | XCVC15xx, XCVC18xx, XCVC19xx | 2020 |
| AIE-ML | Versal AI Core (VC26/28), AI Edge | XCVC26xx, XCVC28xx, XCVE | 2022 |
| AIE-ML v2 | Versal AI Edge Gen 2 | XC2VE | 2025 |

## AIE Devices (AM009 Architecture)

| Device | Board/Kit | AIE Tiles | Columns × Rows | PL Interface Columns |
|--------|-----------|-----------|----------------|---------------------|
| XCVC1902 | VCK190 | 400 | 50 × 8 | 50 |
| XCVC1802 | — | 400 | 50 × 8 | 50 |
| XCVC1702 | — | 400 | 50 × 8 | 50 |
| XCVC1502 | — | 400 | 50 × 8 | 50 |

## AIE-ML Devices (AM020 Architecture)

| Device | Board/Kit | AIE-ML Tiles | Memory Tiles | Columns |
|--------|-----------|-------------|--------------|---------|
| XCVE2802 | VEK280 | 304 | 38 | 38 |
| XCVE2602 | — | 304 | 38 | 38 |
| XCVE2302 | VEK240 | 34 | 8 | 8 |
| XCVE2202 | — | 34 | 8 | 8 |
| XCVE2102 | — | 16 | 4 | 4 |
| XCVE2002 | — | 8 | 2 | 2 |
| XCVE1752 | — | 16 | 4 | 4 |
| XCVC2802 | — | 304 | 38 | 38 |
| XCVC2602 | — | 304 | 38 | 38 |

## AIE-ML v2 Devices (AM027 Architecture)

| Device | Board/Kit | AIE-ML v2 Tiles | Memory Tiles | Relative Size |
|--------|-----------|----------------|--------------|---------------|
| XC2VE3804 | — | TBD | TBD | Largest (1080 GB/s PL BW) |
| XC2VE3858 | — | TBD | TBD | Largest |
| XC2VE3504 | — | TBD | TBD | Mid (720 GB/s PL BW) |
| XC2VE3558 | — | TBD | TBD | Mid |
| XC2VE3304 | — | TBD | TBD | Smallest (280 GB/s PL BW) |
| XC2VE3358 | — | TBD | TBD | Smallest |

Note: Exact tile counts from DS950. Relative sizing inferred from PL interface total bandwidth in DS1021 Table 77.

## Clock Speeds by Architecture and Speed Grade

### AIE (DS957)

| Speed Grade | VCCINT | AIE FMAX | PL Interface FMAX |
|-------------|--------|----------|-------------------|
| -2H | 0.88V | 1300 MHz | 650 MHz |
| -2M | 0.80V | 1250 MHz | 625 MHz |
| -1M | 0.80V | 1150 MHz | 575 MHz |
| -2LLI | 0.725V | 1050 MHz | 525 MHz |
| -2L | 0.70V | 1050 MHz | 525 MHz |
| -1L | 0.70V | 1000 MHz | 500 MHz |

### AIE-ML (DS957/DS958)

| Speed Grade | VCCINT | AIE-ML FMAX | PL Interface FMAX |
|-------------|--------|-------------|-------------------|
| -2H | 0.88V | 1300 MHz | 650 MHz |
| -2M | 0.80V | 1250 MHz | 625 MHz |
| -1M | 0.80V | 1150 MHz | 575 MHz |
| -2LLI | 0.725V | 1050 MHz | 525 MHz |
| -2L | 0.70V | 1050 MHz | 525 MHz |
| -1L | 0.70V | 1000 MHz | 500 MHz |

### AIE-ML v2 (DS1021)

| Speed Grade | VCC_AIE | AIE-ML v2 FMAX | PL Interface FMAX |
|-------------|---------|----------------|-------------------|
| -2M | 0.80V | 1250 MHz | 625 MHz |
| -1M | 0.80V | 1200 MHz | 600 MHz |
| -2LLI | 0.725V | 1050 MHz | 525 MHz |
| -2L | 0.70V | 1050 MHz | 525 MHz |
| -1L | 0.70V | 1000 MHz | 500 MHz |

## PLIO Budget by Device

All architectures: 64-bit PLIO @ PL interface clock = 4 GB/s per stream (at 500 MHz -1L).

| Device | PL Interface Columns | PLIOs In (max) | PLIOs Out (max) | Total BW (PL→AIE, -1L) |
|--------|---------------------|----------------|-----------------|------------------------|
| XCVC1902 | 50 | 400 | 300 | 1600 GB/s |
| XCVE2802 | 28 (active) | 224 | 168 | 896 GB/s |
| XCVE2302 | 8 | 64 | 48 | 256 GB/s |
| XCVE2102 | 4 | 32 | 24 | 128 GB/s |

Note: Not all interface tiles connect to PL. XCVE2802 has 38 columns but only 28 active PL-interface columns (per AM020 p.50).

## Board-to-Device Mapping (Common Eval Kits)

| Evaluation Board | Device | Architecture | Tiles |
|-----------------|--------|--------------|-------|
| VCK190 | XCVC1902 | AIE | 400 |
| VEK280 | XCVE2802 | AIE-ML | 304 |
| VEK240 | XCVE2302 | AIE-ML | 34 |

---

## PL Resource Budgets

Programmable Logic resources per device (source: DS950). Use for PL resource estimation when blocks are assigned to PL.

### AIE Devices (AI Core Series)

| Device | Block RAM (36Kb) | UltraRAM (288Kb) | DSP58 |
|--------|------------------|-------------------|-------|
| XCVC1902 | 967 | 463 | 1,968 |
| XCVC1802 | 967 | 463 | 1,968 |
| XCVC1702 | 596 | 380 | 1,312 |
| XCVC1502 | 596 | 220 | 1,312 |

### AIE-ML Devices (AI Edge Series)

| Device | Block RAM (36Kb) | UltraRAM (288Kb) | DSP58 |
|--------|------------------|-------------------|-------|
| XCVE2802 | 1,302 | 527 | 1,312 |
| XCVE2602 | 1,302 | 527 | 1,312 |
| XCVE2302 | 342 | 128 | 680 |
| XCVE2202 | 342 | 128 | 680 |
| XCVE2102 | 150 | 48 | 312 |
| XCVE2002 | 74 | 24 | 152 |

### AIE-ML v2 Devices (AI Edge Gen 2 Series)

| Device | Block RAM (36Kb) | UltraRAM (288Kb) | DSP58 |
|--------|------------------|-------------------|-------|
| XC2VE3804 | TBD | TBD | TBD |
| XC2VE3504 | TBD | TBD | TBD |
| XC2VE3304 | TBD | TBD | TBD |

Note: AIE-ML v2 PL resource counts pending DS950 update. Use DS950 for exact values.

### PL Resource Capacity Quick Reference

For rough feasibility checks:

| Resource | Per-block capacity | Typical budget (mid-range device) |
|----------|-------------------|-----------------------------------|
| BRAM (36Kb) | 4,608 bytes | ~342–1,302 blocks |
| URAM (288Kb) | 36,864 bytes (36 KB) | ~128–527 blocks |
| DSP58 | 1 multiply-accumulate (27×24) | ~680–1,968 slices |

Note: Do NOT estimate LUT usage — it is too implementation-dependent to predict at system planning stage.

## Selecting a Device

Given a tile estimate from the workload analysis:

1. **Add 20% margin** for routing, debugging, and future growth
2. Find smallest device where: `available_tiles >= tiles_required × 1.2`
3. Verify PLIO budget: `device_PLIOs >= required_PLIOs`
4. Check speed grade supports required clock: `device_FMAX >= required_clock`

If no device fits:
- Recommend the largest available device and flag "exceeds capacity"
- Suggest: reduce precision, exploit symmetry, algorithmic simplification, or split across multiple devices
