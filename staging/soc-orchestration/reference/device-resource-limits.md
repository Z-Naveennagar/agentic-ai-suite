<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Device Resource Limits and DPU Ceilings

Reference data for Phase 2b combined resource budgeting. The agent MUST consult this
file when a design includes both custom PL blocks and a DPU.

## Device Resource Limits

| Device (Board)   | LUTs  | FFs   | DSPs | BRAM tiles | URAM |
|------------------|-------|-------|------|------------|------|
| xck26 (KV260)    | 117K  | 234K  | 1248 | 144        | 64   |
| xczu7ev (ZCU104) | 230K  | 460K  | 1728 | 312        | 96   |
| xcvc1902 (VCK190)| 899K  | 1799K | 1968 | 967        | 463  |

## DPU Architecture Ceilings for Combined Designs

These ceilings are from verified v++ linked builds that include BOTH a DPU and a
moderate video pipeline. They reflect the full system resource usage (DPU IP + v++
platform interconnect + video pipeline), not just the DPU IP core alone.

| Device (Board)   | Total BRAM | Total URAM | Max DPU with Video Pipeline | Notes |
|------------------|------------|------------|----------------------------|-------|
| xck26 (KV260)    | 144 tiles  | 64         | B512                       | B1024 fails BRAM overflow after v++ interconnect |
| xczu7ev (ZCU104) | 312 tiles  | 96         | B1024                      | B2304 tight on URAM |
| xcvc1902 (VCK190)| 967 tiles  | 463        | B4096                      | Ample headroom |

These ceilings assume a moderate video pipeline (4K MIPI CSI-2 + VPSS + FBW/FBR +
IIC + GPIO ~ 15K LUT, 10 BRAM tiles, 10 URAM) plus ~20 BRAM tiles of v++ interconnect
overhead. Simpler pipelines may allow one tier higher.

## PG338/PG389 IP-Only vs System Total

PG338/PG389 resource numbers are for the DPU IP core only. They do not include
the v++ platform infrastructure (AXI interconnects, clock buffers, register slices,
protocol converters) which adds significant overhead. For example, a B1024 DPU is
listed at ~56 BRAM in PG338, but a complete v++ linked design (DPU + platform
interconnect + memory subsystem) consumes ~82+ BRAM tiles total. Always budget
using post-synthesis system totals from `../estimation/SKILL.md`, not the PG338
IP-only figures, when checking combined resource fit.

## Split Architecture Fallback

If no DPU arch fits with the full pipeline, consider a split architecture:
- Camera capture via V4L2/GStreamer (software, no PL video pipeline)
- DPU-only overlay on base platform
- Document this as a design constraint, not a build failure
