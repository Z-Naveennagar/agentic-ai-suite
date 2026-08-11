<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# CASE_LIBRARY.md — Mined TSR Evidence for Versal Timing Closure

Real-world evidence distilled from Vivado_FIS / *Vivado - Timing Closure* TSR escalations (SME customer cases), **filtered to the Versal-relevant subset** (**60** cases with confirmed-Versal parts or explicit Versal architectural signals, drawn from a 189-case all-family corpus). Use this to (a) **rank levers by what actually worked**, and (b) **cite a precedent** when picking a fix in [REFERENCE.md](REFERENCE.md). Names in recipes are design-specific — adapt to the actual names from *this* design's reports.


> **Anonymized.** Customer/program/engineer names and real netlist hierarchy have been redacted (`[redacted]`, `<design_path>`, `$design_nets`). What remains is the transferable *technique* — directives, properties, and constraint patterns. Replace placeholders with the actual names from *this* design's reports.

> Source of truth + full corpus (189 cases, extracted Tcl, downloaded reports) lives outside the skill in the data-mining workspace; refresh this file from there. Structured lookup: [closure_cases.csv](closure_cases.csv).

> **Scope — Versal only.** The source TSR query is not device-filtered, so the full 189-case corpus also contains UltraScale+/UltraScale/7-series and pre-2019 (pre-Versal-silicon) escalations. This shipped library is filtered to the **60 cases with positive Versal evidence** — an authoritative Versal part number, or an explicit Versal architectural signal in the narrative (NoC NMU/NSU, DDRMC, AI Engine, a Versal part token). Provably / likely non-Versal cases are excluded here (retained in the workspace corpus for provenance). Breakdown: 58 versal, 2 unknown (`unknown` here = Versal-signalled but no part number in the ticket text; the part lives only in the design's DCP/data-dir).

## How to use this at runtime
1. Diagnose the dominant limiter on this design (per SKILL.md decision tree).
2. Find that limiter in the **Evidence-Ranked Levers** table → note the REFERENCE.md section and how often it was the real fix.
3. If a flagship recipe matches the failure signature, adapt its Tcl.
4. Honor guardrails: never mask real paths (`false_path`/`clock_groups`); remove any `set_clock_uncertainty` over-constraint before sign-off.
5. **Translate classic directives.** Versal uses the **Advanced Flow** (always-on from 2024.2). Older recipes may name classic `place_design -directive` values that no longer exist (e.g. `AltSpreadLogic_high`, `ExtraNetDelay_high`, `SSI_SpreadSLLs`). Map them to the Advanced-Flow base directive + `-subdirective`/`-net_delay_weight` via [REFERENCE.md](REFERENCE.md) §*Versal Advanced Flow Directive Mapping* before running — the classic name will error otherwise.

## Evidence-Ranked Levers (frequency across 60 Versal-relevant cases)

| Technique | Cases | REFERENCE.md | Notes |
|-----------|------:|--------------|-------|
| `congestion` | 47 | §3 Net Delay / Congestion | Most common limiter; pair SpreadLogic family + floorplanning. |
| `ExtraNetDelay` | 35 | §3 | place/route -directive ExtraNetDelay/AggressiveExplore/Explore. |
| `phys_opt` | 34 | §2/§3 | Extra phys_opt passes (retime/replicate/hold). |
| `block_inference` | 33 | §2 Logic Delay | DSP/BRAM/URAM cascade + register retiming to cut logic levels. |
| `clock_skew_route` | 26 | §4 Clock Skew | Clock root / CLOCK_DELAY_GROUP / BUFGCE placement. |
| `replication` | 22 | §3 | Replicate high-fanout drivers (MAX_FANOUT / phys_opt force_replication). |
| `SLR_assignment` | 21 | §6 SLR Crossing | Constrain/minimize SLR crossings of critical nets (SSI). |
| `pblock_floorplan` | 21 | §10 Floorplanning | Localize critical logic / relieve congestion. |
| `noc_qos` | 15 | Versal NoC | Versal-specific: NoC QoS / NMU-NSU / DDRMC. |
| `high_fanout` | 14 | §3 | Diagnose HFNs first (report_high_fanout_nets). |
| `opt_directive` | 12 | §2 | opt_design -directive ExploreArea / resynth_remap. |
| `route_directive` | 10 | §3 | route_design -directive Explore/AggressiveExplore. |
| `place_directive` | 10 | §3/§10 | place_design -directive (SpreadLogic/ExtraNetDelay/Explore). |
| `dont_touch` | 9 | §2 | Protect structures opt would dissolve. |
| `USER_CLUSTER` | 7 | §3 (group logic) | Keep a critical FF→LUT→FF shape placed together. |
| `qor_suggestions` | 7 | §0 QoR Assessment | report_qor_suggestions → apply .rqs before P&R. |
| `USER_CROSSING_SLR` | 6 | §6 | Force/forbid Laguna crossing on specific nets. |
| `clock_uncertainty_OC` | 5 | §5 Clock Uncertainty | Temporary OC to guide P&R; REMOVE before sign-off. |
| `false_path_groups` | 4 | §7 Async (CAUTION — guardrail) | COUNTER-EXAMPLE — skill must NOT mask real paths. |
| `incremental` | 4 | Alt Flows | Preserve a good run, re-converge. |
| `LOC_constraint` | 2 | §10 | Hard LOC clocking/critical primitives. |

> Caveat: techniques are detected by *mention anywhere* in a case, so counts are directional. The quantified table and recipes below are the high-confidence signal.

## Ground-Truth Before→After (from ticket design data)

WNS/WHS parsed directly from the SME's own runs (Public Data Directory). Shows the real recovered margin and peak congestion.

| Ticket | Device | Place WNS | Route WNS before→after | Cong |
|--------|--------|----------:|------------------------|:----:|
| [TSR-978309](https://jira.xilinx.com/browse/TSR-978309) | — | -1.099 | -0.483 → -0.099 | 6 |
| [TSR-975804](https://jira.xilinx.com/browse/TSR-975804) | xcvh1542 | -1.047 | -0.084 → -0.084 | — |
| [TSR-976779](https://jira.xilinx.com/browse/TSR-976779) | xcvh1522 | -0.952 | -0.076 → -0.001 | — |
| [TSR-975381](https://jira.xilinx.com/browse/TSR-975381) | — | -0.929 | -0.280 → +0.000 | — |
| [TSR-976094](https://jira.xilinx.com/browse/TSR-976094) | — | -0.702 | -0.046 → +0.000 | — |
| [TSR-977086](https://jira.xilinx.com/browse/TSR-977086) | — | — | +0.000 → +0.000 | — |

**Pattern:** route WNS routinely degrades vs the post-physopt margin — closure came from **placement-quality** levers (USER_CLUSTER, SLR control, floorplan) and **named directive sweeps** (classic `AltSpreadLogic_high` → Advanced-Flow `place_design -directive Default -subdirective {Floorplan.ForceSpreading.high …}`; per-design `*_best` runs), not more opt.

## Flagship Versal Recipes

### [TSR-978309](https://jira.xilinx.com/browse/TSR-978309) — 1.6T Ethernet design VP1802 Timing Closure - version 2

**Limiter/techniques:** USER_CLUSTER, USER_CROSSING_SLR, SLR_assignment, pblock_floorplan, clock_uncertainty_OC, replication, high_fanout, congestion

**Result:** route WNS -0.483 → -0.099; congestion Level 6

**Root cause (SME):** Placer was doing a terrible job with placement of FF->LUT->FF->Loads in tx_flex_clk domain. The LUT->FF shape was being placed in SLR3 but the driver FF and loads of the last FF were placed in SLR2. While this did meet timing post-place/physopt, router ended up doing a very minor detour that cause i…

**Key Tcl (adapt names):**
```tcl
set_property USER_CROSSING_SLR 0 $design_nets
set_property USER_CLUSTER uc_group_1 [get_cells <design_path>]
set_clock_uncertainty -setup 0.350 -from [get_clocks TxClk312] -to [get_clocks TxClk312]
set_clock_uncertainty -setup 0.150 -from [get_clocks rx_flex_clk] -to [get_clocks rx_flex_clk]
set_clock_uncertainty -setup 0.200 -from [get_clocks tx_flex_clk] -to [get_clocks tx_flex_clk]
set_clock_uncertainty -setup 0.200 -from [get_clocks RxClk312] -to [get_clocks RxClk312]
set_clock_uncertainty -setup 0.200 -from [get_clocks SYS_CLK_POS1] -to [get_clocks SYS_CLK_POS1]
add_cells_to_pblock [get_pblocks pblock_pcs_mii_pipe]  [get_cells -hierarchical -filter {NAME =~ <design_path>]
```

**Design data:** https://jira.xilinx.com/public/bugcases/TSR/978000-978999/978309/

### [TSR-975381](https://jira.xilinx.com/browse/TSR-975381) — Versal timing closure

**Limiter/techniques:** USER_CLUSTER, pblock_floorplan, replication, high_fanout, congestion

**Result:** route WNS -0.280 → +0.000

**Root cause (SME):** Few observations from analysing the best run in 2022.1.1 (WNS=-0.087 | TNS=-52.595) * Preroute/Postphysopt timing: WNS: -0.100ns TNS: -309ns, 7 failing endpoints. * 1 clk group failing - clk_491. * Mainly Failing paths ending in URAM/BRAM !image-2023-05-04-14-07-13-840.png|width=1037,height=91! * Po…

**Key Tcl (adapt names):**
```tcl
opt_design -hier_fanout_limit 512
route_design -directive Explore
opt_design -directive Explore
opt_design -hier_fanout_limit 512
opt_design -srl_remap_modes \{{max_depth_srl_to_ffs 3}} -sweep
place_design -directive ExtraNetDelay_low
phys_opt_design -directive AggressiveExplore
route_design -directive AggressiveExplore -tns_cleanup
```

**Design data:** https://jira.xilinx.com/public/bugcases/TSR/975000-975999/975381/

### [TSR-976094](https://jira.xilinx.com/browse/TSR-976094) — Timing closure - [redacted] program: 4x100G over 6G demo (VP1802)

**Limiter/techniques:** USER_CLUSTER, SLR_assignment, pblock_floorplan, clock_uncertainty_OC, replication, high_fanout, congestion

**Result:** route WNS -0.046 → +0.000

**Root cause (SME):** Hi , From our last discussion, you mentioned using DON’T_TOUCH on the NOCs as below could be the workaround to avoid the NOC error that was reported in previous comments. set_property DONT_TOUCH TRUE [get_cells <design_path>/axi_nsu*] set_property DONT_TOUCH TRUE [get_cells <design_path>/axi_noc*] s…

**Key Tcl (adapt names):**
```tcl
set_property DONT_TOUCH TRUE [get_cells <design_path>/axi_nsu*]
set_property DONT_TOUCH TRUE [get_cells <design_path>/axi_noc*]
set_property DONT_TOUCH TRUE [get_cells <design_path>/axi_mmu*]
opt_design -directive Explore
opt_design -hier_fanout_limit 512
opt_design -srl_remap_modes {{max_depth_srl_to_ffs 3}} -sweep
place_design -directive ExtraPostPlacementOpt
phys_opt_design -directive AggressiveExplore
```

**Design data:** https://jira.xilinx.com/public/bugcases/TSR/976000-976999/976094/

### [TSR-976779](https://jira.xilinx.com/browse/TSR-976779) — Timing Closure 390 MHz

**Limiter/techniques:** replication, congestion

**Result:** route WNS -0.076 → -0.001

**Root cause (SME):** Update from [redacted] found 2 issues after adopting [redacted] flow on [redacted] program. 1.Based on [redacted]’s tcl scripts, customer and I can reproduce the same result which of WNS/TNS is -0.042/-66.638. However, customer just did a slight tweak and found the timing result had changed. Line 13…

**Key Tcl (adapt names):**
```tcl
place_design -directive SSI_SpreadLogic_high
phys_opt_design -directive Explore
phys_opt_design -directive AggressiveExplore
route_design -directive NoTimingRelaxation -tns_cleanup
route_design -directive NotimingRelaxation -tns_cleanup
```

**Design data:** https://jira.xilinx.com/public/bugcases/TSR/976000-976999/976779/

### [TSR-975804](https://jira.xilinx.com/browse/TSR-975804) — Vivado struggling to create good partition for 2-SLR HBM design

**Limiter/techniques:** SLR_assignment, congestion

**Result:** route WNS -0.084 → -0.084

**Root cause (SME):** internal::clktree_show -net <design_path> ClockTopo Net: 5098763 <design_path> net ptr: <design_path> topo ptr: <design_path> Net Delay Type: Estimate Deskew Mode: Off Max GCLK Delay: 2.76648,3.04836,3.87854,4.12782 Source Region: X0Y0 Track: 17 Site: BUFGCE_X0Y17 isHSRSource: 1 HRouteTrack: 5 Root …

**Key Tcl (adapt names):**
```tcl
set_property BLI TRUE [get_cells -filter \{REF_NAME =~ FD*} -of [get_pins -leaf -filter \{DIRECTION==OUT} -of [get_nets -of [get_pins <design_obj>]
set_property CLKOUT2_PHASE $design_nets $design_nets
```

**Design data:** https://jira.xilinx.com/public/bugcases/TSR/975000-975999/975804/

---
*Generated from the TSR mining corpus. To refresh: re-run the mining pipeline, then `generate_skill_assets.py`.*
