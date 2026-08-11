<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

---
name: hardip-slr-locality
description: "Generates pre-placement USER_CROSSING_SLR=0 constraints for locality-sensitive hard-IP interfaces in a Vivado DCP. Use when cross-SLR routing around fixed hard blocks is hurting timing or congestion. Produces XDC constraints plus locality and cross-SLR risk reports."
argument-hint: "<path-to-pre-place.dcp> (post-opt/pre-place). Optional env: HIPL_MODE=all|crossing (all=constrain every hard-IP interface net [default], crossing=only nets whose fixed LOC endpoints span >1 SLR) HIPL_CONSTRAIN_CLK=<0|1> (also constrain hard-IP clock nets, default 0=report only) HIPL_ALL_PINS=<0|1> (use ALL non-clock signal pins instead of per-class interface patterns, default 0) HIPL_DO_SLR=<0|1> (best-effort fixed-endpoint cross-SLR risk check, default 1) HIPL_SLR_FANOUT_CAP=<N> (skip SLR check on nets with fanout > N, default 2000) HIPL_SCOPE=<hier-prefix> (only hard IPs under this hierarchy) HIPL_CLASSES=<list> (restrict to classes e.g. \"GT NOC CPM\") HIPL_MAX_NETS=<N> (safety cap, default 500000)"
---

# Hard-IP Locality Constraint Generator (pre-placement)

Automatically identify **locality-sensitive interfaces** connected to **fixed-location
hard IP** and apply **`USER_CROSSING_SLR=0`** so Vivado keeps those nets **within one
SLR**. This is a **pre-placement** advisor: selection is **topology-driven** (structural),
not based on routed SLR crossings. Read-only on the design; it only writes report files.

## Why this matters
Cross-SLR routing on interfaces bound to a **fixed-placement** hard block (BRAM, URAM,
GT, MRMAC, DCMAC, NoC, CPM, PCIe, PS, DDRMC, HBM, AI Engine) can **degrade timing
closure, increase congestion, and reduce repeatability**. Because the hard block cannot
move, the *soft* endpoints of its interface should be pulled into the **same SLR**.
`USER_CROSSING_SLR 0` on the interface net tells the placer/router to avoid the crossing.

## Supported hard blocks
`BRAM` `URAM` `GT` (GTM/GTY/GTH/GTF) `MRMAC` `DCMAC` `NoC` `CPM` `PCIe` `PS`
`DDRMC` `HBM` `AIE` (and future hard IP via the ref-pattern / `hb_class` table).

## Critical interfaces (per class)
| Class | Interface pins matched |
|-------|------------------------|
| BRAM / URAM | `ADDR*`, `EN*`, `WE*`, `DIN*` (data/control); `CLK*` reported |
| GT | `TXDATA*`, `RXDATA*`, `*PCS*`, `*PMA*`; `*USERCLK*` reported |
| CPM / PCIe | `*AXI*`, `*DMA*`, `*CQ*`, `*CC*`, `*RQ*`, `*RC*` |
| NoC | `*AXI*` data + address; `*ACLK*` reported |
| MRMAC / DCMAC | `*AXIS*`, `*CTL*`/`*CTRL*`, `*STAT*`, TX/RX; clocks reported |
| PS | `*MAXIGP*`, `*SAXIGP*`, `*AXI*` |
| DDRMC | `*AXI*`, `*ADDR*`, `*CMD*`, `*WDATA*`, `*RDATA*`, `*DQ*` |
| HBM / AIE | `*AXI*` (+ AIE `*STREAM*`/`*MM2S*`/`*S2MM*`) |

Clock-ish pins (`*CLK*`, `*USERCLK*`, `*ACLK*`) are **reported but not constrained** by
default (`HIPL_CONSTRAIN_CLK=1` to include them). Power/ground nets are always skipped.

## Flow
1. **Discover hard IP**: `get_cells -hier -filter {IS_PRIMITIVE && (REF_NAME=~...)}`
   then classify each with `hb_class` (drops non-hard-IP matches).
2. **Identify critical interface pins**: per-class `REF_PIN_NAME` patterns (above), or
   ALL non-clock signal pins with `HIPL_ALL_PINS=1`.
3. **Trace the net** incident on each interface pin (`get_nets -of`); dedup; skip
   power/ground; hold clock nets aside.
4. **Classify criticality / risk**: best-effort **cross-SLR risk** from any endpoints
   that already carry a fixed `LOC` (`get_slrs -of` the LOC site) - valid even pre-place
   for anchored hard IP.
5. **Generate constraints**: `set_property USER_CROSSING_SLR 0 [get_nets {<net>}]`.
6. **Report**: locality, cross-SLR risk, coverage statistics + recommendations.

## Example constraint
```tcl
set_property USER_CROSSING_SLR 0 [get_nets {<critical_net>}]
```

## How to run
The checkpoint is already opened by the LSF Vivado job, so just source the advisor and
run it against the open design:
```
source detect_hardip_locality.tcl
::hipl::run_hardip_locality_analysis <outdir>
```

## Modes & tunables (env `HIPL_*`)
| Env | Default | Meaning |
|-----|---------|---------|
| `HIPL_MODE` | `all` | `all` = constrain every hard-IP interface net; `crossing` = only nets whose fixed LOC endpoints span >1 SLR |
| `HIPL_CONSTRAIN_CLK` | `0` | also constrain hard-IP clock nets (else report only) |
| `HIPL_ALL_PINS` | `0` | use ALL non-clock signal pins instead of per-class interface patterns |
| `HIPL_DO_SLR` | `1` | best-effort fixed-endpoint cross-SLR risk check |
| `HIPL_SLR_FANOUT_CAP` | `2000` | skip the SLR check on nets with fanout > N |
| `HIPL_SCOPE` | (all) | only hard IPs under this hierarchy prefix (fast portion run) |
| `HIPL_CLASSES` | (all) | restrict to classes, e.g. `"GT NOC CPM"` |
| `HIPL_MAX_NETS` | `500000` | safety cap on constrained nets |

## Outputs (in `<outdir>`)
| File | Contents |
|------|----------|
| `apply_hardip_locality.xdc` | `set_property USER_CROSSING_SLR 0 [get_nets {<net>}]`, grouped by hard-IP class; cross-SLR-risk nets annotated. **Read this before `place_design`.** |
| `hardip_locality.csv` | One row per constrained net: `net, hardip_class, hardip_cell, interface_pin, direction, fanout, cross_slr, slr_list, constrained`. |
| `hardip_locality.rpt` | Per-class hard-IP instance counts and constrained-net counts. |
| `crossslr_risk.rpt` | Nets whose fixed (LOC-anchored) endpoints already span >1 SLR (best-effort, pre-place). |
| `hardip_locality_summary.rpt` | Coverage statistics per class + recommendations. |

## Scripts
| Script | Purpose |
|--------|---------|
| [detect_hardip_locality.tcl](./scripts/detect_hardip_locality.tcl) | Main advisor (read-only): hard-IP discovery, interface-pin classification, net tracing, cross-SLR risk, XDC + report generation. Run it on the open design via `::hipl::run_hardip_locality_analysis <outdir>`. |

## Notes
- **Pre-placement**: `USER_CROSSING_SLR` is a locality *hint* applied before `place_design`;
  read the generated XDC into the design, then re-run implementation.
- The per-class interface pin patterns are **heuristic** (device pin naming varies);
  tune them or use `HIPL_ALL_PINS=1` / `HIPL_CLASSES` / `HIPL_SCOPE` as needed.
- Clock/global and power/ground nets are excluded from constraints by default.
- csh host: no bash `2>&1` / `2>/dev/null`; a big interactive `source` floods the
  terminal - read the **result files**.
