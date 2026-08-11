<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

---
name: control-set-analysis
description: "Analyzes control-set fragmentation by module in a post-opt Vivado DCP and ranks modules where CE/SR logic should be pushed into datapath. Use when packing density is poor due to many small control sets. Produces per-module metrics, low-fanout control-signal candidates, and remap tags."
argument-hint: "<path-to-dcp> (required - a post-opt/placed .dcp). Optional: max_lut=<N> (partition the hierarchy so each module is the largest instance with <= N LUTs, default 5000) min_lut=<N> (drop modules with fewer LUTs from the ranked tables, default 500) fanout_max=<N> (a CE/SR control signal is fragmenting/actionable if it drives <= N FFs in the module, default 4) topn=<N> (how many top modules to rank and drill control signals for, default 30)"
---

# Control-Set Fragmentation Analysis

Find the **modules whose FF population is fragmented across many small control
sets** - the ones that pack and place poorly - and rank them as candidates to
**move control logic (clock-enable / reset / localized decode) into the
datapath** so their FFs collapse onto a few shared control sets.

## Why this matters (the correlation)
A **control set** = the unique combination of **{ Clock, Clock-Enable (CE),
Set/Reset (SR) }**. On the FPGA, **FFs can only pack into the same SLICE if they
share a control set.** Every distinct control set partitions the FF population
into a smaller packable bucket.

```
  FFs per Control Set = Total FFs / Unique Control Sets   (~ how many FFs can pack together)
```
- **Module A** - 10,000 FFs, 10 control sets -> 1000 FF/CS: broadly shared
  enables/resets, good packing potential.
- **Module B** - 10,000 FFs, 200 control sets -> 50 FF/CS: fragmented into many
  small buckets; even with enough FFs, the placer has few chances to co-locate/pack.

The key idea: **detect the Module-B-like modules and push their control logic into
the datapath.** Those are usually a small number of modules dominated by remap
logic, localized decode, unique CEs, or generated resets - much stronger
candidates for control->datapath transformation than modules that merely have a
large control-set count.

## Metrics (overall and per module)
- **Control-set count**, **FF count**, **FFs / control set**
- **Largest control-set size**, **Median control-set size**, **size histogram**
- **Fragmentation Index** = `1 - (largest_CS_FFs / total_FFs)`
  (0.2 = one big control set dominates = low fragmentation; 0.95 = many small
  ones = high fragmentation)
- **Control-set density** = `Control_sets / FFs`
- **Priority** = `FF_count x density` (== the module's control-set count; a size-
  weighted alternative view).
- **Score** = `frag x density x log2(FF_count)` - **the primary ranking**. It
  combines fragmentation *quality* (frag, density) with module *size* (log2 FF, so
  big modules matter but sublinearly). Modules that are both fragmented AND large
  enough to matter rise to the top.

## Method
1. Collect FFs (`IS_SEQUENTIAL && REF_NAME =~ FD*`).
2. Resolve each FF's control set = `{ clk | ce | sr }`:
   - **clock** via `all_registers -clock <clk>` (indexed/fast, avoids walking the
     clock spine),
   - **CE / SR nets** via a **net-pivot** (iterate the driving nets, one
     `get_pins -leaf` + one vectorized `get_property PARENT_CELL` per net) -
     **POWER/GROUND const nets are skipped** (CE=VCC -> "1" always-enabled;
     SR=GND -> "0" no-reset) to avoid the huge universal VCC/GND fanout.
3. **Partition the hierarchy by size**: count LUTs under every hierarchical
   instance, and set each FF's **module** = the *shallowest ancestor whose LUT
   count `<= MAX_LUT` (~5000)* - i.e. the largest instance still under the cap.
   This yields uniformly right-sized (~5K-LUT) modules instead of a few giant
   top-level blocks. Tally control-set sizes overall and per module.
4. Compute the metrics per right-sized module (LUTs `MIN_LUT..MAX_LUT`, FF >=
   `MIN_FF`) and rank by **Score = frag x density x log2(FF)** (primary), with a
   secondary **most-fragmented** (lowest FF/CS) view. READ-ONLY - nothing modified.
5. **Exclude already-placed modules.** This is typically a mostly-LOGICAL netlist
   (e.g. a DFX design where only the static shell is placed/routed). A FF is
   "already placed" iff it has a **non-empty `LOC` property** (`get_property -quiet
   LOC $ffs`, vectorized). **Any module that contains a LOC'd cell is dropped**
   from the ranked tables (already committed to placement); the remaining fully-
   logical modules are then ranked. Do **NOT** flag FFs via `IS_ROUTE_FIXED` nets:
   clock/reset nets are route-fixed and would pull in every FF on the clock,
   massively over-counting.
6. **Drill into the identified modules' control signals.** For the top `TOPN`
   candidate modules, enumerate their **CE and SR nets** and each net's **fanout =
   # FFs it drives inside the module**. Nets with **fanout <= `FANOUT_MAX` (default
   4)** are the fragmenting/actionable control signals - each spawns a tiny control
   set and is the thing to fold into the datapath. Control signals whose target
   registers carry **`ASYNC_REG` or `DONT_TOUCH`**, or whose FF/control-net name
   matches the **CDC regex** (`CDC_REGEX`, default catches `*_cdc`, `*sync*`,
   `xpm_cdc`, `*_meta`), are **excluded** (clock-domain-crossing / do-not-
   restructure) and only reported as `protected`.
7. **Gate on D-pin slack.** Folding a CE/SR into the datapath adds a mux delay on
   the FF's **D path**, so it is only safe where the D-pin has setup slack to
   spare. For each low-fanout (unprotected) candidate signal the tool measures the
   **worst setup slack across its target FFs' D pins** (one batched
   `get_timing_paths -delay_type max -nworst 1 -to <D pins>`) and marks the signal
   **`movable`** only when that worst D-pin slack **> `SLACK_MIN` (default 0.5 ns)**.
   Signals with tight/negative D-pin slack are reported but not recommended.
8. **Emit the CONTROL_SET_REMAP tags.** For every movable candidate FF the tool
   writes a ready-to-source `apply_control_set_remap.tcl` that tags the FF by which
   of its control signals are movable: `set_property CONTROL_SET_REMAP ENABLE`
   (clock-enable only), `RESET` (set/reset only), or `ALL` (both) `[get_cells {ff}]`.
   The placer then folds the tagged control into the datapath. Review, source it,
   then re-run placement.

## Interpreting / acting
- Sort by **low FF/CS + high FF count** (or high Fragmentation Index with enough
  FFs). Those modules waste packing capacity.
- Inspect the offending control sets (many size-1..4 sets in the histogram) - they
  usually trace to per-instance enables/resets or decode. Candidates to rewrite so
  the enable/reset becomes datapath mux logic feeding a shared-control-set FF bank.
- Cross-check the overall unique-control-set count against `report_control_sets`.

## Checkpoint stage
Any post-opt netlist (placed or not) - control sets are structural. A placed DCP
is fine; placement is not required for the counts.

## Procedure

### Step 1 - Load the DCP via LSF (never on the login node)
Interactive (csh, RHEL8 pin required):
```
bsub -I -R "select[type=X86_64 && osdistro=rhel && osver=ws8] rusage[mem=60000]" \
     -q long /proj/primebuilds/2026.1_PRIME_daily_latest/installs/lin64/2026.1/Vivado/bin/vivado -mode tcl
```
then `open_checkpoint <dcp>`. Or batch via
[run_control_set_lsf.csh](./scripts/run_control_set_lsf.csh) (opens + runs unattended).

### Step 2 - Run the detector
```
source detect_control_sets.tcl
run_control_set_analysis <outdir>
```
Env: `MAX_LUT` (module = largest hierarchy instance with <= this many LUTs, default
5000), `MIN_LUT` (drop modules with fewer LUTs from the ranked tables, default 500),
`MIN_FF` (drop modules with fewer FFs, default 200), `FANOUT_MAX` (a CE/SR net is a
fragmenting/actionable control signal if it drives <= this many FFs in the module,
default 4), `TOPN` (how many top modules to rank and to drill control signals for,
default 30), `SLACK_MIN` (min D-pin setup slack in ns for a signal to be called
movable, default 0.5), `CDC_REGEX` (FF/control-net names matching this case-
insensitive regex are treated as protected CDC logic, default
`(cdc|synchroniz|resync|_sync|sync_|_meta|xpm_cdc)`). Modules containing any LOC'd
(already-placed) cell are always excluded.
Lower `MAX_LUT` to descend deeper / get finer modules; raise it for coarser ones.

## Output (4 files in `<outdir>`)
| File | Contents |
|------|----------|
| `control_set_summary.rpt` | OVERALL metrics + control-set-**size histogram**; **TOP right-sized modules by SCORE** (`frag x density x log2(FF)`) and a secondary **most-fragmented** table (modules with any LOC'd cell excluded); then a **PER-MODULE CONTROL-SIGNAL FANOUT** table for the top modules (`loFO_CE`, `loFO_SR` = # CE/SR signals with fanout <= `FANOUT_MAX`; `movCE`, `movSR` = those with worst D-pin slack > `SLACK_MIN` (safe to fold into datapath); `gov_FF` = FFs they govern; `prot_sig` = low-fanout signals skipped for ASYNC_REG/DONT_TOUCH; `histFO1-4` = signal count at fanout 1/2/3/4). |
| `control_set_by_module.csv` | Per module: `ff_count, lut_count, cs_count, ff_per_cs, largest_cs, median_cs, frag_index, cs_density, priority, score, placed_ff, placed_frac` - ranked by `score` (ALL modules, authoritative); also sort by `ff_per_cs` asc for the most fragmented. |
| `control_signals_lowfanout.csv` | Every low-fanout (`<= FANOUT_MAX`) CE/SR control signal in the top modules: `module, kind (CE/SR), net, fanout, protected, worst_dpin_slack_ns, movable` - the actionable list to fold into the datapath. `movable=1` = worst D-pin setup slack > `SLACK_MIN` (safe); `protected=1` = has ASYNC_REG/DONT_TOUCH target (do not touch). |
| `apply_control_set_remap.tcl` | Ready-to-source tags for the movable FFs: `set_property CONTROL_SET_REMAP {ENABLE\|RESET\|ALL} [get_cells {ff}]` (ENABLE = move CE only, RESET = move SR only, ALL = both). Review, `source` it, then re-run placement. |

## Scripts
| Script | Purpose |
|--------|---------|
| [detect_control_sets.tcl](./scripts/detect_control_sets.tcl) | Main detector (read-only): per-FF control set via all_registers (clock) + net-pivot (CE/SR), per-module metrics + ranking. |
| [run_control_set_lsf.csh](./scripts/run_control_set_lsf.csh) | LSF wrapper: open the DCP on RHEL8 and run the detector in batch. |
| [control_set_batch_driver.tcl](./scripts/control_set_batch_driver.tcl) | Batch driver (open_checkpoint + run + DONE marker). |

## Shell notes (csh on this host)
- No bash `2>&1` / `2>/dev/null`; avoid inline `!` (history expansion). `setenv MAX_LUT 5000` before `bsub` (LSF forwards env).
- Interactive `source` of a big tcl floods the terminal capture (echoes the file) - read the RESULT FILES, not the terminal.
- PERF: resolve clocks with `all_registers` and SKIP VCC/GND const nets in the CE/SR pivot - a naive per-FF or clock-spine net-pivot over ~1M FFs is pathologically slow.
