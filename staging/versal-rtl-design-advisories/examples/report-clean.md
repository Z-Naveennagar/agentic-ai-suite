<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Versal RTL Design Advisories Report

| Field | Value |
|-------|-------|
| Project | example_project |
| Top Module | top |
| Part | xcvc1902-vsva2197-2MP-e-S |
| Date | 2026-05-11 |
| Checks Run | 32 of 42 applicable |

## Summary

| Severity | Count |
|----------|:-----:|
| HIGH     | 0     |
| MEDIUM   | 0     |
| LOW      | 0     |
| PASS     | 32    |
| SKIPPED  | 10    |

**No issues found.**

## Categories Not Applicable

The following checks were skipped because the design does not use the relevant resources:

- **Steps 2–3 (DSP/DSPCPLX):** Design contains no DSP58 or DSPCPLX primitives
- **Step 9 (US+ Migration):** Design is not migrating from UltraScale+

## Checks Passed

| Check | Category | Result |
|-------|----------|--------|
| M1 | Memory | PASS — URAM read_latency=5, cascade_height=4 |
| M3 | Memory | PASS — All URAM 2P memories use read-first mode |
| M6 | Memory | PASS — `ram_decomp = "area"` present on all URAM arrays |
| M7 | Memory | PASS — Write-first URAMs have matching enable/reset |
| M8 | Memory | PASS — No combinational feedback in BRAM patterns |
| M9 | Memory | PASS — No shallow RAMs (<64 entries) in BRAM |
| A1 | Carry | PASS — No legacy CARRY4/CARRY8 instantiations |
| A2 | Carry | PASS — No LOOKAHEAD8 on critical paths |
| S1 | Style | PASS — No VHDL counter anti-patterns |
| S2 | Style | PASS — FSMs have explicit encoding attributes |
| S3 | Style | PASS — All registers under reset or have INIT |
| S4 | Style | PASS — No duplicate module names |
| S5 | Style | PASS — Control set count within limits |
| S6 | Style | PASS — FSMs use multi-process style |
| T1 | Timing | PASS — Pipeline registers on long paths |
| T2 | Timing | PASS — No debug cores present |
| T3 | Timing | PASS — I/O delays account for BUFGCE |
| T4 | Timing | PASS — No buses wider than 256 bits |
| T5 | Timing | PASS — Reset fanout managed |
| T6 | Timing | PASS — No LOC+BUFG conflicts |
| B1 | Safety | PASS — No cascaded BRAMs with const-prop risk |

## Recommendations

No action items — design follows Versal RTL design advisories.
