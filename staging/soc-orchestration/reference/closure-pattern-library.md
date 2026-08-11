<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Timing-Closure Pattern Library

Concrete, ordered remedies keyed by the `qor-classification` First-Step class. Phase 5 uses
this as its dispatch table: classify → localize → apply the first untried remedy for the
class → rebuild the affected scope → re-classify. Remedies are ordered cheapest-first.

Each pattern lists: **Signal** (what made the classifier pick it), **Skill/Tool** (who fixes
it), **Action** (the concrete command/directive), **Cost**, and **Exit** (how to know it worked).

---

## CLOCKING  (fix first — a wrong clock invalidates everything downstream)
**Signal:** `RQS_CLOCK*`, `RQS_XDC` (missing/loose constraint), implausibly large/round WNS,
many unconstrained endpoints.

| # | Action | Skill/Tool | Cost | Exit |
|---|---|---|---|---|
| 1 | Verify clock definitions & requirements are intentional (not a typo'd period) | `timing-methodology-checks` | seconds | constraint matches intent |
| 2 | Add missing `create_clock`/`create_generated_clock`, set realistic `set_clock_uncertainty` | xdc edit + re-impl | minutes | unconstrained endpoints → 0 |
| 3 | Fix CDC paths (`set_max_delay -datapath_only`, async groups) | `timing-methodology-checks` | minutes | CDC methodology DRCs clear |

> If the "miss" is a 13 ns WNS on a 3.3 ns clock, it is almost always a constraint bug, **not**
> a fabric problem. Do not pipeline your way out of a constraint error.

## UTILIZATION  (a too-full device cannot be placed/routed cleanly)
**Signal:** peak utilization ≥ 80–90%, `RQS_UTIL*`.

| # | Action | Skill/Tool | Cost | Exit |
|---|---|---|---|---|
| 1 | Identify the dominant resource (LUT/FF/BRAM/DSP/URAM) | `report_utilization` | seconds | resource named |
| 2 | Rebalance HLS area (move buffers BRAM↔URAM, trim AXI FIFOs) | `hls-area-opt` | minutes | peak util < 80% |
| 3 | Re-partition: move a block to PS/AIE or split across a second region | `partitioning` | minutes | budget fits |

## CONGESTION  (local routing resource exhaustion)
**Signal:** congestion level ≥ 4–6, localized CLB congestion DRC, WNS regression place→route,
`RQS_PLACE`/`RQS_CONG`.

| # | Action | Skill/Tool | Cost | Exit |
|---|---|---|---|---|
| 1 | Confirm hotspot region & resource | `congestion-analysis` | 1–2 min | hotspot located |
| 2 | `place_design -directive AltSpreadLogic_high` (or `SSI_SpreadLogic` multi-SLR) | re-place + route | 10–40 min | congestion level drops ≥1 |
| 3 | `phys_opt_design -directive AggressiveExplore`; high-fanout net replication | re-impl | 10–40 min | WNS@route improves |
| 4 | Reduce LUT density in hotspot (re-code/re-partition) | `rtl-elaboration-analysis` / `partitioning` | hours | level < 4 |

## PARTITION  (multi-SLR scatter — multi-SLR devices only)
**Signal:** multi-SLR device **and** RQA SLR/pblock review; worst paths cross SLR/die.

| # | Action | Skill/Tool | Cost | Exit |
|---|---|---|---|---|
| 1 | Confirm worst paths cross an SLR/die boundary | `report_timing` / `device-floorplan` | minutes | crossing confirmed |
| 2 | Register SLR-crossing nets both sides (Laguna) | RTL/xdc | minutes | crossings registered |
| 3 | Create SLR pblocks to localize each block | `device-floorplan` | 10–40 min | block stays in one SLR |
| 4 | (Versal) route long data via NoC instead of fabric | `vitis-platform` / BD | varies | fabric route length drops |

## TIMING  (logic/route delay on critical paths — the residual class)
**Signal:** closed-at-physopt then regressed at route, route% ≥ 75 (net-delay) or high logic
levels (logic-delay), `RQS_NETLIST-10` (retiming).

| Sub-class | Action | Skill/Tool | Cost | Exit |
|---|---|---|---|---|
| `Retiming_Opportunity` | Apply `RQS_NETLIST-10`; synth `-retiming`; rerun phys_opt | `opt-design-analysis` / re-synth | 10–30 min | logic levels drop, WNS@route ≥ 0 |
| `Net_Delay_Dominated` | Pipeline the long net; reduce fanout; floorplan endpoints closer | `phys-opt-design-analysis` | 10–40 min | route% drops |
| `Logic_Delay_Dominated` | Pipeline/retime deep logic; balance LUT levels | `hls-timing-closure` (isolate-and-close) | minutes–hours | logic levels ≤ target |

### The 45% post-physopt regression rule
A design whose `WNS@PhysOpt ≥ 0` but `WNS@Route < 0` lost slack to **routing**, not logic.
Prefer congestion/net-delay remedies (spread placement, pipeline the offending net) over more
logic retiming. The `qor-classification` skill flags this as `closed_at_popt=true` and sets the
sub-class to `Retiming_Opportunity` only when corroborated by high logic levels / `RQS_NETLIST-10`.

---

## Localize-before-fix (from hls-timing-closure)
Before applying any TIMING remedy, **localize the worst path to its owning block**:
1. `report_timing -max_paths 10 -nworst 1` on the routed DCP.
2. Map the startpoint/endpoint cell back to the BD instance / RTL module / HLS kernel.
3. Fix in the **smallest** scope that owns the path (one kernel, one module) and prove it with
   a fast microbenchmark (csim→csynth→OOC P&R) before rebuilding the whole design.

## Apply-suggestions mechanics (RQS)
- Generate once: `report_qor_suggestions -file <out>.rpt` and `write_qor_suggestions <out>.rqs`.
- Re-apply at synth/impl: `read_qor_suggestions <out>.rqs` before `synth_design` / `place_design`
  so RTL-level suggestions (retiming, BRAM packing) take effect.
- Only `Automatic`-eligible suggestions apply directly; manual ones map to actions above.
