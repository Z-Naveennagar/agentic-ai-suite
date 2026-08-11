<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Device Profiles for Timing Closure

Device-agnostic closure still needs device-specific knobs. The orchestrator (Phase 5) reads
this table to (a) decide whether `Partition` is even possible, (b) pick the right floorplan
remedy, and (c) set realistic congestion/utilization thresholds. The `qor-classification`
skill auto-detects the device string from the timing report header; this file tells the
orchestrator what that device *implies*.

## Quick lookup

| Family | Example parts | SLRs | Partition class possible? | Cross-die register | Notes |
|---|---|---|---|---|---|
| **Zynq UltraScale+** | xck26 (Kria K26), xczu7ev, xczu9eg | 1 (most) | No (single-SLR) | n/a | Treat `Partition` score as 0; congestion/timing dominate |
| **Zynq US+ (large)** | xczu19eg, xczu11eg | 2–3 | Yes | Laguna (`SLLREG`) | Use `device-floorplan` for SLR pblocks |
| **UltraScale** | xcvu095, xcku115 | 2–4 | Yes | Laguna | Higher congestion sensitivity |
| **Virtex US+** | xcvu9p, xcvu13p, xcvu19p | 3–4 | Yes | Laguna | SLR-crossing nets must be registered both sides |
| **Versal AI Core** | xcvc1902 | 1–2 (SSIT on larger) | Sometimes | SLR boundary / NoC | NoC offloads long routes; LOOKAHEAD limits apply |
| **Versal Premium** | xcvp1502, xcvp1802 | multi | Yes | SLR + NoC | Use NoC for cross-die data; pblock the rest |

## Single-SLR rule (critical)
On single-SLR parts (xck26 and most mid-size Zynq US+ / small Versal), **never** classify a
miss as `Partition`. The `qor-classification` scorer already zeroes `Partition` unless the
device string matches a known multi-SLR part — keep that invariant when extending the list.

## Per-family closure knobs

### Zynq UltraScale+ (e.g. xck26 / Kria)
- Congestion remedy: `place_design -directive AltSpreadLogic_high`, `phys_opt_design -directive AggressiveExplore`.
- Timing remedy: retiming (`RQS_NETLIST-10` / synth `-retiming`), pipeline insertion, `phys_opt` fanout opt.
- Utilization ceiling: aim < 80% LUT per clock region; URAM/BRAM pressure common in CNN layers.
- Default clk source is `clk_pl_0` from the PS — clock constraint issues show up as `RQS_XDC`.

### Versal (AI Core / Premium)
- Prefer the **NoC** for long cross-region data paths before resorting to pblocks.
- Watch DSP58/DSP_CPLX cascades and URAM cascade limits (see `versal-rtl-design-advisories`).
- `LOOKAHEAD` and imux/omux limits differ from UltraScale+ — congestion thresholds run ~1 level lower.
- Multi-SLR Versal: register SLR-crossing nets on both sides; use SLR pblocks via `device-floorplan`.

### UltraScale / Virtex US+ (multi-SLR)
- SLR-crossing paths must use **Laguna** registers; an unregistered SLR crossing is a top
  `Partition` signal alongside the RQA SLR/pblock review flag.
- Floorplan with `device-floorplan` to keep related logic in one SLR.

## Where the orchestrator uses this
1. **Classification sanity:** if `qor-classification` returns `Partition` on a single-SLR part,
   downgrade to the next class (this should not happen given the scorer guard, but verify).
2. **Remedy selection:** map the family + class to the concrete directive / skill in
   `closure-pattern-library.md`.
3. **Threshold tuning:** Versal congestion level ≥4 is already concerning; UltraScale+ ≥5.
