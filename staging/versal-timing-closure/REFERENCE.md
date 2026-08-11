<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# REFERENCE.md — UG1788 Limiter → Technique → Fix Catalog

Detailed resolution catalog for `versal-timing-closure`. Each branch maps a
**symptom** (from `report_timing_summary` / `report_design_analysis` /
`report_qor_assessment`) to UG1788 **techniques** and **copy-pasteable** Tcl/XDC.
Replace `[actual_*]` markers with real names extracted from the reports. Confirm
any directive/property spelling with `vivado_doc_search` for the installed
version before applying.

> Items marked **(auto)** can be applied automatically by
> `report_qor_suggestions` / `read_qor_suggestions`.

> **This catalog is a tested starting set, not an exhaustive rulebook.** Diagnose
> the actual limiter on *this* design first, then pick (or adapt) a lever. For
> anything not covered here, use the **Document Map** below + `vivado_doc_search`
> to pull the authoritative source and reason from it.

## Document Map by Design Stage (what to pull at runtime)

UG1788 is a *quick reference* that points to deeper guides per stage. When a
limiter needs more than this catalog gives, `vivado_doc_search` the matching guide
rather than guessing — that is the intended use, and it keeps you current with the
installed Vivado version.

| Stage / limiter you're in | Authoritative guide | Pull for |
|---|---|---|
| Initial Design Checks; QoR score/assessment | **UG906**, UG1388 | `report_qor_assessment` rows, accuracy-by-stage, cross-probing |
| Logic levels / retiming / SRL | **UG901** (synth), **UG904** (impl) | retiming, `SRL_STYLE`, `PerformanceOptimized`, remap |
| Net delay / congestion / directives | **UG904**, UG1388 | place/route/phys_opt directives, congestion strategies |
| Control sets / reset / RTL coding | **UG1387**, UG949 | control-set threshold, `CONTROL_SET_REMAP`, sync-reset coding |
| Clock skew / topology / insertion delay | **AM003**, UG1387 | clock root, `CLOCK_DELAY_GROUP`, `GCLK_DESKEW`, MBUFG |
| Clock uncertainty / RAM jitter | **AM003** | URAA factor, `USER_RAM_AVERAGE_ACTIVITY` |
| SLR crossing / partitioning (SSI) | **UG1388** | soft/hard SLR floorplan, vtree, calibrated deskew, auto-pipeline |
| Async CDC circuitry / exceptions | **UG1344**, UG1388 | XPM_CDC / async FIFO, exception rules (guardrailed — §7) |
| Floorplanning (Pblocks) | **UG906**, UG949 | `create/resize_pblock`, `IS_SOFT`, Pblock guidance |


### Mined precedent evidence — [CASE_LIBRARY.md](CASE_LIBRARY.md)

[CASE_LIBRARY.md](CASE_LIBRARY.md) distills the **Versal-relevant subset (60 cases)
of resolved Vivado_FIS / "Vivado - Timing Closure" TSR escalations** (real SME
customer cases, filtered from a 189-case all-family corpus) into: an
**evidence-ranked lever table** (which technique was actually the fix, and how
often), a **ground-truth before→after WNS/WHS table** parsed from the SMEs' own
runs, and **flagship Versal recipes** with copy-adaptable Tcl. Use it to *rank*
candidate levers and *cite a precedent* once you've diagnosed the limiter here —
then return to the matching section below for the full technique + Tcl. Compact
structured lookup: [closure_cases.csv](closure_cases.csv).


## Table of Contents
- [0. Initial Design Checks & QoR Assessment](#0-initial-design-checks--qor-assessment)
- [1. Hold Violations (WHS < 0)](#1-hold-violations-whs--0)
- [2. Logic Delay / Logic Levels](#2-logic-delay--logic-levels)
- [3. Net Delay / Congestion](#3-net-delay--congestion)
- [4. Clock Skew & Clock Topology](#4-clock-skew--clock-topology)
- [5. Clock Uncertainty](#5-clock-uncertainty)
- [6. SLR Crossing & Partitioning (SSI only)](#6-slr-crossing--partitioning-ssi-only)
- [7. Asynchronous Clocks](#7-asynchronous-clocks)
- [8. Control Sets (packing / spreading limiter)](#8-control-sets-packing--spreading-limiter)
- [9. Reset Topology](#9-reset-topology)
- [10. Floorplanning (Pblocks)](#10-floorplanning-pblocks)

---

## 0. Initial Design Checks & QoR Assessment

**Symptom:** QoR Assessment Score ≤ 3, or `REVIEW` rows in
`report_qor_assessment`. Score: 1 = won't implement, 2 = implements but misses
timing, 3 = likely miss, 4 = likely meet, 5 = meet. Accuracy by stage: *unplaced*
= util + LUT/net budget (no congestion); *placed* = congestion + tighter skew (no
budget); *routed* = fully accurate.

**Techniques (UG1788 Initial Design Checks):**
- Check clock-frequency constraints are realistic (per kernel, per hierarchy, full design).
- Review utilization, logic levels, and timing constraints before implementing.
- SLR / Pblock budgets are checked automatically; no violation = within limits.

```tcl
# Generate assessment + CSVs for offline analysis; then apply suggestions.
report_qor_assessment -file [actual_dir]/qor_assessment.rpt -csv_output_dir [actual_dir]/qor_csv
set rqs [report_qor_suggestions -file [actual_dir]/qor_suggestions.rpt -return_string]
report_qor_suggestions -file [actual_dir]/qns.rqs
read_qor_suggestions [actual_dir]/qns.rqs    ;# applies (auto) suggestions
# Verify: re-run report_qor_assessment and confirm score increased.
```

---

## 1. Hold Violations (WHS < 0)

**Priority:** UG1788 — fixing hold has **higher priority than setup**; a hold
failure is a functional failure. Resolve large pre-route hold so the router can
focus on Fmax.

**1a. Reduce WHS/THS before routing with LUT1 insertion.**
`-hold_fix` / `-aggressive_hold_fix` **cannot** be combined with `-directive`.
```tcl
phys_opt_design -hold_fix             ;# largest-WHS paths only
# or, for total hold slack at the cost of LUTs + compile time:
phys_opt_design -aggressive_hold_fix
# Verify: report_timing_summary ; check WHS/THS improved, WNS not regressed.
```

**1b. Avoid positive hold requirements from multicycle setup relaxation.**
Always pin **endpoint pins** (not cells/clocks) and balance setup+hold edges:
```tcl
set_multicycle_path -from [get_pins [actual_launch]/C] -to [get_pins [actual_capture]/D] -setup 3
set_multicycle_path -from [get_pins [actual_launch]/C] -to [get_pins [actual_capture]/D] -hold 2
# Constrain the D pin only — NOT the cell (which would also catch the EN pin).
```

---

## 2. Logic Delay / Logic Levels

**Symptom:** Worst path header shows high **Logic Delay**; `report_design_analysis`
Logic Level Distribution shows paths above the per-domain budget.
> Versal note: `LOOKAHEAD8` reports as multiple logic levels but costs ~1–2 LUT
> delays. Use `report_design_analysis -routes` for true level count, and review
> **Routes** rather than Logic Levels on placed/routed designs.

**Techniques:**
- **Retiming** — on by default in synthesis (`-retiming`); for stubborn paths use
  the `PerformanceOptimized` synth directive. **(auto via qor_suggestions)**
- **RTL recode / pipeline** for feedback paths and paths with high levels on pre-
  and post-paths (`report_design_analysis -extend`).
- **Merge small cascaded LUTs** blocked by `KEEP`/`KEEP_HIERARCHY`/`DONT_TOUCH`/
  `MARK_DEBUG` — remove the property and rerun from synth or `opt_design -resynth -remap`. **(auto)**
- **Remap single LOOKAHEAD to LUTs** — `PerformanceOptimized` synth directive. **(auto)**
- **LUT remap / decomposition to cut logic levels** — `opt_design` combines chained
  LUTs into a single LUT (the one furthest downstream in the cone) to reduce depth:
  ```tcl
  opt_design -remap            ;# or -aggressive_remap (more effort), or -resynth_remap
  # Selective: tag only the chains you want collapsed, then opt_design -remap:
  set_property LUT_REMAP TRUE [get_cells [actual_lut_chain_cells]]   ;# (auto via qor_suggestions)
  ```
  Remap replicates a tagged LUT with fanout > 1 before collapsing. Note `LUT_REMAP
  FALSE` does **not** block remap when `opt_design -remap` runs globally.
- **SRL vs FD** — pull a register out of the SRL:
  ```tcl
  # RTL: (* srl_style = "reg_srl_reg" *)  on the shift-register signal
  # Or post-synth property on the SRL cell (confirm name via vivado_doc_search):
  set_property SRL_STAGES_TO_INPUT 1 [get_cells [actual_srl_cell]]
  ```
- **LUT driving CE/S/R pin** — move optimization off the control pin:
  ```tcl
  # RTL attribute on the signal:  (* extract_enable = "no" *)  / (* extract_reset = "no" *)
  # Or post-synth, trigger during opt_design:
  set_property CONTROL_SET_REMAP TRUE [get_cells [actual_reg_cell]]   ;# (auto)
  ```

**Dedicated blocks / macros (DSP, RAMB, URAM, NOC, AIE, GT):** validate pipeline
benefit by enabling optional registers (do **not** bitstream this eval build):
```tcl
set_property -dict {DOA_REG 1 DOB_REG 1} [get_cells [actual_ramb_cell]]
# Verify benefit, then add the equivalent pipeline in RTL.
```

---

## 3. Net Delay / Congestion

**Symptom:** High **Net/Route Delay** with detours around congested regions; the
`route_design` log prints *Initial Estimated Congestion* (Level ≥ 4); or
`report_design_analysis -congestion`. Congestion levels (INT tiles, `2^y × 2^y`):
- **Level 4 (16×16):** small QoR variability.
- **Level 5 (32×32):** sub-optimal placement, QoR variation.
- **Level 6 (64×64):** difficult P&R, long compile, severe QoR loss.
- **Level 7 (128×128)+:** effectively impossible to place/route.

**Techniques (UG1788 order):**
1. **Lower utilization** when overall util > 70–80%: remove functions or move
   modules/kernels to another SLR. Avoid LUT **and** DSP/RAMB/URAM both > 80%; if
   macro util must be high, keep **LUT < 60%** to allow spreading. Check per-SLR
   util with `report_qor_assessment` / `report_utilization -slr` after placement.
2. **Promote non-critical high-fanout nets to global routing:** **(auto)**
   ```tcl
   set_property CLOCK_BUFFER_TYPE BUFG_FABRIC [get_nets [actual_high_fanout_net]]
   ```
3. **Merge synthesis-replicated equivalent nets** — remove `MAX_FANOUT` from RTL/
   XDC, or: **(auto)**
   ```tcl
   set_property EQUIVALENT_DRIVER_OPT merge [get_cells [actual_target_cells]]
   ```
4. **Congestion-aware place directives / strategies:**
   ```tcl
   place_design -directive AggressiveExplore   ;# (see also Explore)
   # plus Congestion_* implementation strategies in project mode
   ```
   Confirm congestion sub-directive availability with `vivado_doc_search
   "place_design directives"` for your version (e.g. ReduceCongestion,
   ForceSpreading).
5. **Group related logic without Pblocks:** **(auto)**
   ```tcl
   set_property USER_CLUSTER [actual_group_name] [get_cells [actual_cells]]
   ```
6. **Congestion-oriented synthesis on a large congested hierarchy** (>15000 cells,
   Rent > 0.65 or avg fanout > 4 from `report_design_analysis -complexity -congestion`):
   ```tcl
   set_property BLOCK_SYNTH.STRATEGY {ALTERNATE_ROUTABILITY} [get_cells [actual_congested_hier]]
   ```
7. **Floorplan with increasing granularity** — start SLR-based, then two Pblocks
   (left/right of the SLR) if more guidance is needed.

**High-fanout nets** (detect with `report_high_fanout_nets`; drive HFNs with a
fabric `FD*` register so phys_opt can replicate/relocate them easily):
```tcl
# Inspect the worst HFNs (per clock region / by load type) before acting:
report_high_fanout_nets -load_types -max_nets 25 -file [actual_dir]/high_fanout.rpt
# Module-based replication at opt_design (driver replicated per N loads):
opt_design -merge_equivalent_drivers -hier_fanout_limit 512
# Cap physical fanout and steer replication by physical attribute:
set_property FORCE_MAX_FANOUT [actual_limit] [get_nets [actual_critical_hf_net]]   ;# (auto)
set_property MAX_FANOUT_MODE CLOCK_REGION [get_nets [actual_hf_net]]   ;# or SLR / MACRO
# phys_opt replicates HF drivers by slack+placement; raise effort or target nets:
phys_opt_design -directive AggressiveFanoutOpt        ;# also Explore / AggressiveExplore
phys_opt_design -force_replication_on_nets [get_nets [report_high_fanout_nets -return_string]]
```
On SSI devices, HF drivers can be replicated **per SLR** and pinned to SLR-aligned
Pblocks with their loads to hide SLR-crossing delay (see §6).

**Control sets** over the 7.5% guideline — see [§8](#8-control-sets-packing--spreading-limiter)
(too many unique control sets force the placer to spread logic → longer nets +
congestion). **Reset fanout** — see [§9](#9-reset-topology).

**LUT combining can *cause* congestion** (it packs LUT pairs into dual-output
slices, raising slice pin connectivity). If LUT combining > 40% in the congested
region, disable it there:
```tcl
# Find combined LUTs (highlight candidates):
select_objects [get_cells -hier -filter {SOFT_HLUTNM != "" || HLUTNM != ""}]
# Disable soft combining on the congested module:
reset_property SOFT_HLUTNM [get_cells -hierarchical -filter {NAME =~ [actual_module]/* && SOFT_HLUTNM != ""}]
# Or, at synthesis, the Flow_AlternateRoutability strategy/directive emits no extra LUT combining.
```

---

## 4. Clock Skew & Clock Topology

**Symptom:** Worst path header shows high **Clock Skew**. **Analyze skew on the
post-place DCP** — phys_opt and the router add useful skew that masks the true
contributors. Survey the clock trees with `report_clock_utilization` (roots,
buffer counts, loads) before applying constraints.

**Techniques:**
- **MBUFG for synchronous clocks** with period ratio 2/4/8 from the same source —
  one MMCM/PLL output into an MBUFG creates a common node near the loads.
- **Eliminate clock-path logic** — `opt_design` cleans clock trees unless
  `DONT_TOUCH` is set. Remove LUTs/combinatorial logic in clock paths; avoid
  cascaded clock buffers (connect in parallel or combine compatible div-1/2/4/8
  buffers into a single MBUFG).
- **Match clock routing** when MBUFG is not possible: **(auto)**
  ```tcl
  set_property CLOCK_DELAY_GROUP [actual_group] [get_nets {[actual_clk1] [actual_clk2]}]
  ```
- **Constrain low-fanout I/O clock loads** (< 4000 loads) next to the I/O bank: **(auto)**
  ```tcl
  set_property CLOCK_LOW_FANOUT TRUE [get_nets [actual_clock_net]]
  ```
- **Place the clock root (`USER_CLOCK_ROOT`)** — usually the placer picks the
  optimal root; override only for a specific critical path/region. Pblock the
  clock's loads, then set the root to a clock region that has the vertical clock
  spine. For SLR crossings, move the root's Y toward the crossing:
  ```tcl
  set_property USER_CLOCK_ROOT [actual_clock_region] [get_nets [actual_clock_net]]
  ```
  If the root is off-center from the loads the placer ignores it and reports the
  optimal choice — read that message rather than fighting it.
- **Reduce clock insertion delay** (more useful than minimizing skew for
  **synchronous CDC** where MBUFG cannot be used and parallel `BUFG_GT` /
  `BUFGCE_DIV` drive the related clocks — exactly the XPHY/serdes case): match the
  routing with `CLOCK_DELAY_GROUP`, **disable the programmable deskew delays**, and
  pin the root next to the loads:
  ```tcl
  set_property CLOCK_DELAY_GROUP [actual_group] [get_nets {[actual_clk1] [actual_clk2]}]
  set_property GCLK_DESKEW OFF [get_nets {[actual_clk1] [actual_clk2]}]   ;# minimize insertion delay
  set_property USER_CLOCK_ROOT [actual_clock_region] [get_nets [actual_clk1]]
  ```

---

## 5. Clock Uncertainty

**Symptom:** Worst path header shows high **Clock Uncertainty**
(`report_clock_uncertainty` for per-path/clock-pair detail).

**Techniques:**
- **MBUFGCE** for synchronous clocks (ratio 2/4/8) from the same MMCM/PLL — drive
  one output into an MBUFGCE to remove ~0.120 ns phase-error uncertainty (use the
  Clocking Wizard to generate the topology).
- **Tune RAM-induced GCLK jitter** — override the default RAM activity model:
  ```tcl
  set_property USER_RAM_AVERAGE_ACTIVITY [actual_raa_pct] [current_design]
  # See AM003 to compute the factor.  Verify with report_clock_uncertainty.
  ```
- **Parallel-buffer synchronous CDC** (separate buffers ⇒ common node before
  buffers ⇒ higher pessimism, hard for high-freq > 400 MHz). Use MBUFG for
  ratio 2/4/8 from the same source. If MBUFG is impossible: add multicycle paths
  on CE-controlled paths, or convert to asynchronous CDC (XPM_CDC / async FIFO)
  with proper exceptions (see §7). Count such paths via `report_timing_summary`
  Inter-Clock Paths or `report_clock_interaction`.

---

## 6. SLR Crossing & Partitioning (SSI only)

**Apply only when `[llength [get_slrs]] > 1`.** Goal: keep each major block inside
one SLR, pipeline the crossings, and balance per-SLR utilization
(`report_qor_assessment` / `report_utilization -slr`).

**Soft partitioning (preferred first) — `USER_SLR_ASSIGNMENT`.** A *soft*
constraint the placer may override to find a legal partition. Applies to
**hierarchical** cells (not leaf cells). Crucially, the detailed placer/phys_opt
may still move pipeline registers **across** the SLR boundary to improve timing —
this is NOT allowed across a Pblock boundary.
```tcl
# SLR name => place the whole cell in that SLR; arbitrary string => placer picks
# one SLR but keeps the cell together (not split). Same string => group together.
set_property USER_SLR_ASSIGNMENT SLR1 [get_cells {[actual_hier1] [actual_hier2]}]
set_property USER_SLR_ASSIGNMENT SLR0 [get_cells [actual_hier3]]
```

**Direct/forbid a specific crossing — `USER_CROSSING_SLR`.** Apply to nets/leaf
pins to force loads into the driver's SLR, or to permit a register chain to cross.

**Hard partitioning — SLR Pblocks.** Use only when soft assignment is
insufficient; a Pblock is a *hard* SLR-partition + global-placement constraint
(blocks the boundary register moves above). See [§10](#10-floorplanning-pblocks).

**Pipeline the crossings.**
- Add **pipeline registers** at major hierarchy / kernel boundaries for long-
  distance and SLR-crossing routing.
- **Auto-pipelining** lets the placer choose the number/location of stages and
  uses **Laguna** registers automatically — enable via `AUTOPIPELINING_*` RTL
  attributes on buses/handshakes, or use an AXI Register Slice configured for the
  SLR crossing. Ensure the extra latency is functionally safe.

**Clock handling across SLRs.**
- **Calibrated deskew** on SLR-crossing clock nets (minimizes skew + inter-SLR
  penalty): **(auto)**
  ```tcl
  set_property GCLK_DESKEW CALIBRATED [get_nets -of [get_pins [actual_bufgce]/O]]
  ```
- If calibrated deskew can't be used, select the vertical clock tree:
  ```tcl
  set_property USER_CLOCK_VTREE_TYPE interSLR [get_nets [actual_clock_net]]
  ```
- Replicate high-fanout drivers per SLR and pin them (with loads) to SLR-aligned
  Pblocks to cut SLR-crossing delay (see §3 `MAX_FANOUT_MODE SLR`).

---

## 7. Asynchronous Clocks

**Symptom:** Source/destination clocks from different primary clocks or with no
common node ⇒ extremely high skew, impossible closure.

> **⚠️ Guardrail — exceptions are OFF by default.** Timing exceptions do not
> improve a design; they hide violations. Add one ONLY when (a) the user
> explicitly approves it, AND (b) the path is a GENUINE asynchronous CDC with
> proper synchronizer circuitry (XPM_CDC / async FIFO) already in place. Never add
> an exception to make a synchronous / same-domain path "pass", and never to mask
> a real setup gap — use the targeted over-constraint lever (removed before
> sign-off) for that. If unsure, FLAG the path for the user; do not constrain it.

```tcl
# ONLY for genuinely independent async domains WITH CDC circuitry, AND with user approval:
set_clock_groups -asynchronous -group [get_clocks [actual_clk_a]] -group [get_clocks [actual_clk_b]]
# Or per-path exceptions (same preconditions):
set_false_path -from [get_clocks [actual_clk_a]] -to [get_clocks [actual_clk_b]]
set_max_delay -datapath_only [actual_value] -from [get_clocks [actual_clk_a]] -to [get_clocks [actual_clk_b]]
```
Pair with proper CDC circuitry (XPM_CDC / async FIFO). See UG1344 (Versal Prime
Series Libraries) and UG1388 (Adding Timing Exceptions Between Asynchronous Clocks).

---

## 8. Control Sets (packing / spreading limiter)

**Symptom:** `report_control_sets -verbose` shows control-set count over the
**7.5%** guideline (whole device or per SLR), or QoR suggestions flag control
sets. A control set = the unique {clock, clock-enable, set/reset} grouping of a
sequential cell. **Versal packing:** a half-slice has two groups of four
registers sharing one clock + one set/reset; each group of four has one CE and may
ignore the set/reset. Too many unique control sets force the placer to spread
logic (and its input LUTs) to less-optimal sites → longer nets, congestion, lower
Fmax, higher power.

**Diagnose, then reduce (UG949/UG1388 order):**
```tcl
report_control_sets -verbose -file [actual_dir]/control_sets.rpt   ;# read the fanout-distribution table
```
1. **Stop over-replicating control signals** — remove `MAX_FANOUT` on CE/S/R in
   RTL/XDC. Let `place_design` do coarse replication and `phys_opt_design
   -directive Explore` do fine replication (prevents equivalent control sets
   crossing each other → congestion). **(auto)**
2. **Raise the synthesis threshold** (globally, or per-module via BLOCK_SYNTH for
   the worst spreaders) — but note it can cost power by removing useful CEs:
   ```tcl
   synth_design -control_set_opt_threshold 16
   set_property BLOCK_SYNTH.CONTROL_SET_OPT_THRESHOLD 16 [get_cells [actual_module]]
   ```
3. **Merge equivalent control sets after synthesis:** **(auto)**
   ```tcl
   opt_design -control_set_merge     ;# or: opt_design -merge_equivalent_drivers
   ```
4. **Remap low-fanout CE/synchronous-reset into the datapath** (combined into the
   D-input LUT where possible — needs a **synchronous** set/reset): **(auto)**
   ```tcl
   set_property CONTROL_SET_REMAP ALL [get_cells [actual_low_fanout_reg]]   ;# ENABLE | RESET | ALL
   ```
5. **RTL hygiene:** avoid low-fanout **asynchronous** set/reset (cannot be moved to
   the datapath, so the threshold option does not help them); don't use both
   active-High and active-Low of one control signal on different cells; only add
   CE/reset where functionally needed (datapaths often self-flush).

---

## 9. Reset Topology

**Symptom:** A reset (or set) net is a top fanout net (`report_high_fanout_nets`),
shows up in congestion/skew, or a mix of sync/async resets blocks DSP/BRAM/SRL
inference (seen in `report_qor_assessment` / utilization). Reset style is an RTL
property — surface it as a recommendation; never mask reset-path failures with
exceptions.

**Principles (UG1387/UG949):**
- **Don't reset just to initialize.** The global GSR sets every register to its
  init value at end-of-configuration (FDRE/FDCE→0, FDSE/FDPE→1), so a power-up
  reset is unnecessary. Resets are usually needed on **control-path** logic, rarely
  on **datapath** logic. Removing unneeded resets lowers reset fanout, frees the
  synthesizer to map to the best resources (incl. DSP/BRAM/SRL), and improves
  Fmax/area/power.
- **Prefer synchronous resets.** They map to more architecture resources, allow
  CONTROL_SET_REMAP into the datapath (§8), don't degrade general-logic Fmax, and
  won't corrupt BRAM/LUTRAM/SRL contents the way async resets can. DSP48/BRAM
  register elements have **synchronous-only** resets — async resets there block
  direct inference.
- **If async reset is required, synchronize its de-assertion** (reset-bridge): the
  release edge must meet recovery/removal timing or the FF can go metastable.
  Assertion may be async; release must be synchronous.
- **Tame a high-fanout reset** like any HFN — drive it from an `FD*`, let
  `place_design`/`phys_opt_design` replicate it (`FORCE_MAX_FANOUT` /
  `MAX_FANOUT_MODE`, §3); do **not** pin `MAX_FANOUT` in RTL.

---

## 10. Floorplanning (Pblocks)

**When:** Only to fix the **worst outliers** (paths with much worse slack / very
high logic levels) or to localize I/O-connected logic for run-to-run
predictability — **never floorplan the whole design.** Soft SLR assignment (§6) is
the lighter first tool.

**Pblocks are SOFT by default** (`IS_SOFT 1`): they guide placement but allow
spill-out for QoR. Make one hard only deliberately:
```tcl
create_pblock [actual_pblock]
add_cells_to_pblock [get_pblocks [actual_pblock]] [get_cells [actual_hier]]
resize_pblock [get_pblocks [actual_pblock]] -add {SLICE_X8Y105:SLICE_X23Y149}
resize_pblock [get_pblocks [actual_pblock]] -add {DSP_X0Y42:DSP_X1Y59}
set_property IS_SOFT 0 [get_pblocks [actual_pblock]]   ;# HARD — use sparingly
```
Tips: keep a Pblock to ~**one clock region** (max placer flexibility); **avoid
overlaps** (shared area congests); **merge** two Pblocks with many interconnecting
signals and **minimize nets crossing** Pblocks; include only the resource types
you want constrained (omit a site type ⇒ that logic floats); **don't straddle the
central configuration block**. When trying a new Vivado version, first compile with
**no/minimal** Pblocks — stale Pblocks can block a better solution.

> **Hard-Pblock anti-pattern (learned):** a hard (`IS_SOFT 0`) per-bank Pblock that
> drags **0-logic** boundary registers (e.g. Versal XPHY `*_bli_*` FDREs →
> `pll_clkoutphy_*`) toward their hard block pulls them AWAY from the clock root and
> starves local fabric → congestion lvl 5, WNS ≈ −0.6 (worse). For that path class
> use the §4 insertion-delay/clock-root levers and the targeted over-constraint, not
> a Pblock.

**Placement-constraint toolbox (soft → hard ladder).** Reach for the *lightest*
tool that fixes the outlier; escalate only on failure. Softer = more placer freedom
= better QoR; hard constraints can starve the placer and *worsen* timing (see
anti-pattern above).

| Constraint | Hard/soft | Scope | Use it to… |
|------------|-----------|-------|------------|
| `USER_CLUSTER <tag>` | soft | hier/leaf cells | Group a critical FF→LUT→FF shape so it places together, **without** locking a region (see §3 item 5). First thing to try for a scattered critical path. |
| `USER_SLR_ASSIGNMENT <slr\|tag>` | soft | hierarchical cells | Steer a block to one SLR but let the placer override (§6). |
| `USER_CROSSING_SLR` | soft | nets/leaf pins | Force loads into the driver's SLR / permit a chain to cross (§6). |
| Pblock, `IS_SOFT 1` (default) | soft | site ranges | Bias a cluster to a region while allowing spill-out for QoR. |
| Pblock, `IS_SOFT 0` | hard | site ranges | Truly contain a cluster (blocks boundary-register moves). Use sparingly. |
| `CONTAIN_ROUTING 1` (on a Pblock) | hard | Pblock | Also keep the cluster's **routing** inside the Pblock (isolation / repeatability). Tightens further — only with a hard Pblock. |
| `EXCLUDE_PLACEMENT 1` (on a Pblock) | hard | Pblock | Reserve the region for the assigned cells only (no other logic placed there). |
| `RLOC` / `RLOC_ORIGIN` (XDC/RTL) | hard-relative | macro cells | Lock *relative* geometry of a hand-built macro (carry chains, systolic cells) while letting the macro float as a unit. |
| `LOC` + `BEL` | hard-absolute | a single cell | Pin one primitive to an exact site/BEL (e.g. a clock buffer, an I/O FF). Last resort for a specific primitive, not bulk logic. |
| `PROHIBIT` | hard | sites/ranges | Forbid placement on specific sites (carve out a keep-out region). |

**Soft-first rule:** try `USER_CLUSTER` → soft Pblock → soft `USER_SLR_ASSIGNMENT`
before any hard (`IS_SOFT 0`, `LOC`/`BEL`, `CONTAIN_ROUTING`, `PROHIBIT`) constraint.
Confirm exact property/value spellings for the installed version with
`vivado_doc_search` (e.g. "Pblock properties", "RLOC", "CONTAIN_ROUTING") — the
canonical sources are **UG903** (*Using Constraints*, how to write the constraint) and
**UG912** (*Properties Reference Guide*, every property's legal values). Remove any
experimental hard constraint that did not help before sign-off.

---

## Versal Advanced Flow Directive Mapping (2024.2+)

**Why this matters here:** From Vivado **2024.2** the **Advanced Flow** is *always*
used for Versal (it does not affect 7 series / UltraScale). Mined TSR recipes —
especially pre-2024.2 cases — may name **classic-flow directives that are no longer
valid `place_design -directive` arguments**. In the Advanced Flow `place_design
-directive` accepts only a small base set (`Explore`, `AggressiveExplore`, `Default`,
`RuntimeOptimized`, `Quick`); the rich behaviors are now a **base directive +
`-subdirective {…}` / `-net_delay_weight`**. **Always translate a classic directive
from a TSR before running it**, or it will error. (Source: UG904 *Directives and
Switches Used by place_design in Advanced Flow* and *Migrating to the Advanced Flow*.)

**`place_design` — classic directive → Advanced Flow invocation**

| Classic `-directive` | Intent | Advanced Flow form |
|----------------------|--------|--------------------|
| `Explore` | perf explore | `Explore` (unchanged) |
| `ExtraNetDelay_high` | inflate net delay (congestion) | `Explore -net_delay_weight high` |
| `ExtraNetDelay_low` | net-delay weighting | `Explore -net_delay_weight low` |
| `AltSpreadLogic_high` | spread logic (congestion) | `Default -subdirective {Floorplan.ForceSpreading.high GPlace.ForceSpreading.high GPlace.ReduceCongestion.high DPlace.ReducePinDensity.high}` |
| `AltSpreadLogic_medium` | spread logic | `Default -subdirective {Floorplan.ForceSpreading.med GPlace.ForceSpreading.med GPlace.ReduceCongestion.med DPlace.ReducePinDensity.med}` |
| `AltSpreadLogic_low` | spread logic | `Default -subdirective {Floorplan.ForceSpreading.low GPlace.ForceSpreading.low GPlace.ReduceCongestion.low DPlace.ReducePinDensity.low}` |
| `SSI_SpreadLogic_high` | SSI spread (multi-die) | `Default -subdirective Floorplan.BalancedSLR.high` |
| `SSI_SpreadLogic_low` | SSI spread | `Default -subdirective Floorplan.BalancedSLR.low` |
| `SSI_BalanceSLRs` | balance SLR utilization | `Explore -subdirective Floorplan.BalancedSLR.high` |
| `SSI_HighUtilSLRs` | high-util SLR | `Explore -subdirective Floorplan.BalancedSLR.low` |
| `WLDrivenBlockPlacement` | wirelength block place | `Explore -subdirective {Floorplan.GPlace.WLDrivenBlockPlacement}` |
| `EarlyBlockPlacement` | early block place | `Explore -subdirective GPlace.EarlyBlockPlacement` |
| `ExtraTimingOpt` | extra timing opt | `Explore -subdirective {Floorplan.ExtraTimingUpdate Floorplan.ExtraTimingOpt.high GPlace.ExtraTimingUpdate GPlace.ExtraTimingOpt.high DPlace.ExtraTimingUpdate DPlace.ExtraTimingOpt.high}` |
| `ExtraPostPlacementOpt` (Retiming) | retiming | `Explore` (retiming runs via `phys_opt_design -directive AlternateFlowWithRetiming`) |

**`route_design` / `phys_opt_design` (Advanced Flow):** congestion strategies route
with `route_design -directive AlternateCLBRouting`; perf with `Explore` /
`AggressiveExplore`; `phys_opt_design` uses `Explore` / `AggressiveExplore` /
`AlternateFlowWithRetiming`.

**Removed / not-applicable in Advanced Flow — do NOT copy from a TSR (they error):**
- `*-directive RQS` (ML strategy) on `opt_design`/`place_design`/`phys_opt_design`/`route_design`.
- `place_design -directive Auto_1 | Auto_2 | Auto_3` (auto directives).
- `power_opt_design` / `set_power_opt` / `report_power_opt` (power opt disabled by migration).
- `read_checkpoint -incremental` / `report_incremental_reuse` (incremental impl unsupported).
- Strategies with no Advanced-Flow equivalent: `Performance_RefinePlacement`,
  `Performance_SpreadSLLs`, `Performance_BalanceSLLs`,
  `Performance_WLBlockPlacementFanoutOpt` → fall back to `Default`/`Explore`.

> P&R data from 2024.1 and earlier **cannot** be reused in the Advanced Flow; a TSR's
> exact saved run is not portable — reuse the *technique*, not the checkpoint. For the
> latest migration details see UG904 *Migrating to the Advanced Flow* and AR 000036830.

---

## Trying Alternative Flows (when directives plateau)

- Iterate `place_design` directives/sub-directives; add `-net_delay_weight
  {medium|high}` to inflate high-fanout / long-distance net estimates.
- Multiple `phys_opt_design` passes (`Explore`, `AggressiveExplore`).
- **Targeted over-constraint (honest, exception-free)** on the SPECIFIC failing
  synchronous clock-pair group — NOT whole clocks, and **removed before
  sign-off**:
  ```tcl
  # Apply only on the actual failing launch->capture pairs during P&R:
  set_clock_uncertainty -setup [actual_amount] -from [get_clocks [actual_launch]] -to [get_clocks [actual_capture]]
  # ... place / phys_opt / route ...
  # Then REMOVE before sign-off (inherent uncertainty only, UU=0):
  reset_clock_uncertainty -setup -from [get_clocks [actual_launch]] -to [get_clocks [actual_capture]]
  ```
  Start small (≈0.05–0.15 ns); escalate up to ~0.5 ns only if needed. The bundled
  `tcl/overconstrain_flow.tcl` does apply→P&R→remove→sign-off in one parameterized
  call; verify with `tcl/verify_signoff.tcl`.
- Raise priority on must-meet clocks:
  ```tcl
  group_path -weight 2 -name [actual_group] -from [get_clocks [actual_critical_clk]]
  ```
- **Tip:** run `report_qor_suggestions` after `opt_design`, `place_design`, and
  `route_design`; **filter** the suggestions (e.g. keep CLOCK_DELAY_GROUP / macro
  anchor-align; drop synth-only or retiming-needs-RTL ones) and apply selectively
  rather than blindly reading the whole `.rqs` back.

---

## Worked Example — XPHY 0-logic boundary paths (the OC lever in practice)

On a large Versal HBM SSI design (logic-heavy, ~72% LUT), the residual setup
fails after a clean AggressiveExplore place+route were **0-logic** boundary paths
`b*_rxclk → pll_clkoutphy_*_DIV4` (3.2 ns / 312.5 MHz), `*_bli_*` FDREs. Root
cause: route delay + structural launch/capture clock imbalance (RQS `CLOCK-5_1`),
not logic. **Hard per-bank Pblocks made it worse** (congestion lvl 5, WNS ≈ −0.6)
by pulling those FFs away from the clock root. The fix that closed it:
AggressiveExplore + `{Floorplan.BalancedSLR.high, GPlace.ReduceCongestion.med}`
with a **targeted OC = 0.10 ns** on the 11 `b*_rxclk → pll_clkoutphy*` pairs,
applied during place/phys_opt/route and **removed before sign-off**. Final
exception-free signoff: WNS +0.001 / WHS +0.005, fully routed; residual
WPWS −0.136 traced to DCMAC serdes max-skew + XPHY/MBUFG min-period = structural
hard-IP, out of P&R scope. This is the generalizable pattern, not the bank names.
