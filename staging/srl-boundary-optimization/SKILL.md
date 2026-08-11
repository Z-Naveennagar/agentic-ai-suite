<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

---
name: srl-boundary-optimization
description: "Finds SRL boundaries in post-opt/pre-place Vivado DCPs that should be converted to register boundaries for better timing optimization. Use when SRL start/end boundaries are critical or hard-block-adjacent. Produces prioritized candidates and an SRL tagging script."
argument-hint: "<path-to-dcp> (required - a post-opt/pre-place .dcp; timing is ESTIMATED pre-route). Optional env: SRLB_SLACK_MAX=<ns> (P2/P3 gate: flag SRL<->FF paths with slack <= this = failing + near-meeting, default 0.300) SRLB_HB_MAX_LEVELS=<N> (P1 SRL<->HB logic-level bound, 0 = unbounded = pull ALL SRL<->HB, default 0) SRLB_MAX_PATHS=<N> (cap on -from/-to timing queries, default 20000) SRLB_HIGH_FANOUT=<N> (P6 SRL-Q fanout threshold, default 1000) SRLB_MED_FANOUT=<N> (near-fanout note, default 100) SRLB_SCOPE=<hier-prefix> (only SRLs under this hierarchy - a FAST way to validate on a portion; default whole design) SRLB_DO_PARTITION=<0|1> (flag cross-DFX-partition boundaries, default 1) SRLB_WARMUP=<0|1> (run a throwaway get_timing_paths to trigger update_timing, default 1) SRLB_DO_SHALLOW=<0|1> (P8: flag shallow SRLs with depth<=SHALLOW_DEPTH and tag SRL_TO_REG, default 1) SRLB_SHALLOW_DEPTH=<N> (P8: max SRL depth treated as shallow, default 2)"
---

# SRL Boundary Optimization Advisor

Find the **timing-unfriendly SRL boundaries** in a **post-opt / pre-place** design and
recommend turning them into clean **register-to-register** boundaries by **pulling a
register out of the SRL** (`SRL_STAGES_TO_REG_INPUT` / `SRL_STAGES_TO_REG_OUTPUT`).
The value is spotting where an SRL sits on a path as a **startpoint or endpoint** and
making that path bounded by real flops, so retiming, register balancing, replication
and placement can all work on it.

## Why this matters
A shift-register-lookup (`SRL16E` / `SRLC32E`, `PRIMITIVE_TYPE CLB.SRL.*`) is great
for area but is a **poor timing boundary**:
- As a **startpoint**, its `Q` clock-to-out plus downstream logic must fit in one
  period - and the tools **cannot retime or replicate through an SRL** like a flop.
- As an **endpoint**, the setup at its `D` pin bounds the incoming path, again with
  no retiming freedom.
- When the SRL's neighbor is a **hard block** (BRAM/URAM/DSP/GT/MRMAC/DCMAC/PCIe/
  CPM/HSC), placement is **fixed** and routing flexibility is low, so an SRL boundary
  there is the **highest closure risk** - and should be registered *regardless of the
  current (estimated) slack*.

Pulling the boundary register **out of the SRL** converts `SRL -> logic -> Reg` /
`Reg -> logic -> SRL` into `Reg -> logic -> Reg`, which the tools can optimize normally.

## Detection priorities (highest first) - HYBRID, neighbor-driven
| Pri | Boundary | Gate | Recommendation / tag |
|-----|----------|------|----------------------|
| **P1** | **SRL <-> HARD BLOCK** - SRL `Q` reaches a hard-block input (`SRL -> N*LUT -> HB`), or a hard-block output reaches SRL `D` (`HB -> N*LUT -> SRL`) | **STRUCTURAL - no timing/slack gate** (hard blocks are fixed-placement; always pull) | `SRL_STAGES_TO_REG_OUTPUT` (SRL->HB) / `SRL_STAGES_TO_REG_INPUT` (HB->SRL), or use the block's native pipeline register |
| **P2** | **SRL -> N*LUT -> FF** (SRL startpoint, FF endpoint) | **TIMING** - slack `<= SLACK_MAX` (failing + near-meeting, default +0.3ns) | `SRL_STAGES_TO_REG_OUTPUT 1` (register the Q side) |
| **P3** | **FF -> N*LUT -> SRL** (FF startpoint, SRL endpoint) | **TIMING** - slack `<= SLACK_MAX` | `SRL_STAGES_TO_REG_INPUT 1` (register the D side) |
| **P5** | **DFX PARTITION BOUNDARY** - SRL and its path neighbor are in different reconfigurable partitions | structural | Register the partition interface (`_OUTPUT`/`_INPUT` per side) |
| **P6** | **HIGH-FANOUT SRL OUTPUT** - SRL `Q` net `FLAT_PIN_COUNT >= HIGH_FANOUT` | structural | `SRL_STAGES_TO_REG_OUTPUT 1` (register for replication) |
| **P8** | **SHALLOW SRL** - SRL depth `<= SHALLOW_DEPTH` (default 2), from the `_srl<N>` cell-name suffix or a constant address-pin value (`depth = addr+1`) | structural | `SRL_TO_REG 1` (convert the WHOLE SRL to registers; supersedes side tags for that cell) |
| **P7** | **GENERAL CLEANUP** - the non-flagged SRL remainder | - | summarized count only (not individually tagged) |

*P4 (cross-SLR SRL paths) is **N/A** on a single-die post-opt DCP and is skipped.*

**Why P1 needs no timing:** a hard block cannot move and has little routing slack, so
an SRL directly bounding one is a closure hazard *even if the estimated pre-place
slack looks fine today*. The user directive is: **if a path's startpoint or endpoint
is a hard macro block and an SRL primitive is on the other side, pull the register.**
Only the **SRL <-> FF** boundaries (P2/P3) are worth gating on timing.

## Method
1. **Collect SRL primitives**: `get_cells -hier -filter {IS_PRIMITIVE && PRIMITIVE_TYPE =~ CLB.SRL.*}`
   (a plain `REF_NAME =~ SRL*` also matches `SRL_FIFO*` **module wrappers** - excluded).
   Build the `Q`/`Q31` (out) and `D` (in) pin collections; and the hard-block `IN`/`OUT`
   pin collections.
2. **Warm up timing**: the **first** `get_timing_paths` triggers a full `update_timing`
   (minutes on a large design); a throwaway `-max_paths 1` pays it once. After warm-up
   every query below runs in seconds.
3. **P1 SRL->HB (structural)**: `get_timing_paths -from <SRL Q> -to <HB IN pins>
   -nworst 1 -max_paths MAX_PATHS` with **no slack bound** - the `-from/-to` constraint
   *is* the structure. Every distinct SRL startpoint is flagged (pull output reg).
4. **P1 HB->SRL (structural)**: `get_timing_paths -from <HB OUT pins> -to <SRL D>` -
   every distinct SRL endpoint is flagged (pull input reg).
5. **P2 SRL->FF (timing)**: `get_timing_paths -from <SRL Q> -slack_lesser_than SLACK_MAX`;
   keep paths whose **endpoint is a regular FF** (HB endpoints belong to P1, SRL
   endpoints are skipped).
6. **P3 FF->SRL (timing)**: `get_timing_paths -to <SRL D> -slack_lesser_than SLACK_MAX`;
   keep paths whose **startpoint is a regular FF**.
7. **Classify the neighbor**: strip the far-end pin name to its owning cell
   (`regsub {/[^/]+$}`) and look up its ref via bulk name->ref maps - `HB:<ref>`,
   `SRL:<ref>`, `FF:<ref>`, `LOGIC:<ref>`. (`STARTPOINT_PIN`/`ENDPOINT_PIN` of a
   sequential cell is its `CLK`/`D` pin, so the SRL is identified by the `-from`/`-to`
   constraint and the *neighbor* is the other end's cell.)
8. **P6 fanout / P5 partition**: `FLAT_PIN_COUNT` on the SRL-Q nets; DFX partition
   compare by name-prefix vs the `HD.RECONFIGURABLE` cells. READ-ONLY - nothing modified.
9. **P8 shallow-SRL depth**: for every SRL compute its depth from the `_srl<N>`
   cell-name suffix (fast, no queries) or, if absent, from the constant address-pin
   value (`depth = addr+1`; a dynamic/addressable address => not shallow). SRLs with
   `depth <= SHALLOW_DEPTH` (default 2) are tagged `SRL_TO_REG 1` to convert the whole
   cell to registers, and are **excluded** from the side-based P1/P2/P3/P6 tags so a
   cell never gets both `SRL_TO_REG` and `SRL_STAGES_TO_REG_*`.

## Timing tags (pulling the register out of the SRL)
```
# register the SRL OUTPUT (Q) side  - SRL->hard-block / SRL->FF / high-fanout
set_property SRL_STAGES_TO_REG_OUTPUT 1 [get_cells {.../last_hop_dir_q_reg[6][2]_srl7}]
# register the SRL INPUT (D) side    - hard-block->SRL / FF->SRL
set_property SRL_STAGES_TO_REG_INPUT  1 [get_cells {.../indir_cmd_final_reg[bypass_lookup]_srl7}]
# convert a SHALLOW SRL (depth <= 2) ENTIRELY to registers  - P8
set_property SRL_TO_REG 1 [get_cells {.../some_shift_reg[3]_srl2}]
```
`get_cells` is given the **raw hierarchical name** (Vivado matches literal `[N]`
bus/generate indices; do **not** backslash-escape them). Both properties are
recognized on `SRL16E`/`SRLC32E` cells; review the generated tags, `source` them, then
re-run place/route.

## How to run
Interactive (design already open, e.g. after `open_checkpoint`):
```
source detect_srl_boundary.tcl
::srlb::run_srl_boundary_analysis <outdir>
```
LSF batch (opens a post-opt/pre-place DCP on a RHEL8 host):
```
bsub -q long -J srlbound -n 2 \
  -R "select[ostype==rhelws810 || ostype==rhelws86 || ostype==rhelws89 || ostype==rhelws87] rusage[mem=65536]" \
  -o <outdir>/srlbound.%J.log \
  ./run_srl_boundary_lsf.csh <dcp> <outdir>
```
Env tunables (LSF forwards them): `SRLB_SLACK_MAX` (0.300 - P2/P3 failing+near-meeting
gate), `SRLB_HB_MAX_LEVELS` (0 = unbounded P1 SRL<->HB; set e.g. 4 to keep only shallow
hard-block boundaries), `SRLB_MAX_PATHS` (20000), `SRLB_HIGH_FANOUT` (1000),
`SRLB_MED_FANOUT` (100), `SRLB_SCOPE` (hierarchy prefix - restrict SRLs to one module
for a **fast portion run**; default whole design), `SRLB_DO_PARTITION` (1),
`SRLB_WARMUP` (1), `SRLB_DO_SHALLOW` (1 - P8 shallow-SRL detection),
`SRLB_SHALLOW_DEPTH` (2 - max SRL depth tagged `SRL_TO_REG`).

## Output (3 files in `<outdir>`)
| File | Contents |
|------|----------|
| `srl_boundary_summary.rpt` | Run config + thresholds (notes estimated pre-route timing); counts by priority (P1 structural, P2/P3 slack<=SLACK_MAX, P5, P6, P8 shallow-SRL->SRL_TO_REG, plus a P7 "not flagged" estimate); analysis time; a ranked top-N table (priority, side, slack, logic levels, neighbor class, SRL). |
| `srl_boundaries.csv` | One row per flagged SRL boundary side: `srl_cell, srl_ref, priority, side (SRL->HB / HB->SRL / SRL->FF / FF->SRL / high-fanout / shallow-srl), slack_ns, logic_levels, neighbor_cell, neighbor_class, fanout, partition, cross_partition, tag_property (SRL_STAGES_TO_REG_OUTPUT / SRL_STAGES_TO_REG_INPUT / SRL_TO_REG), recommendation`. |
| `apply_srl_boundary_tags.tcl` | Ready-to-source tags grouped by priority: `set_property SRL_STAGES_TO_REG_OUTPUT/INPUT 1 [get_cells {<srl>}]` and, for P8, `set_property SRL_TO_REG 1 [get_cells {<srl>}]`. Review, then `source` before re-implementing. |

## Scripts
| Script | Purpose |
|--------|---------|
| [detect_srl_boundary.tcl](./scripts/detect_srl_boundary.tcl) | Main advisor (read-only): SRL collection, timing warm-up, structural P1 SRL<->HB queries, timing-gated P2/P3 SRL<->FF queries, neighbor classification, fanout + partition checks, ranking, tag emission. |
| [run_srl_boundary_lsf.csh](./scripts/run_srl_boundary_lsf.csh) | LSF wrapper: open the DCP on RHEL8 and run the advisor in batch. |
| [srl_boundary_batch_driver.tcl](./scripts/srl_boundary_batch_driver.tcl) | Batch driver (`open_checkpoint` + source + run + `DONE_SRL_BOUNDARY_RUN` marker). |

## Requirements & perf notes
- **Post-opt / pre-place DCP** - timing is **ESTIMATED** (pre-route). Estimated slack
  is enough to rank P2/P3 failing/near-meeting SRL<->FF paths; P1 SRL<->HB does not use
  slack at all. (On a placed+routed DCP the same flow works with real slack.)
- **First `get_timing_paths` = `update_timing`** (can be minutes); `SRLB_WARMUP=1`
  absorbs it once, then the structural (`-from Q -to HB` / `-from HB -to D`) and gated
  (`-slack_lesser_than`) queries each run in a few seconds. Keep `Q`/`D`/HB pins as
  in-scope collections.
- **`STARTPOINT_PIN` of a sequential cell is its `CLK` pin** (not `Q`), and
  `ENDPOINT_PIN` is the `D` pin - so the SRL is identified by the `-from`/`-to`
  constraint, and the neighbor by stripping the *other* end's pin to a cell.
- P1 can flag a large fraction of SRLs (SRLs in FIFOs feed BRAMs). Use
  `SRLB_HB_MAX_LEVELS` to restrict to shallow hard-block boundaries if the count is
  too large for one ECO pass.
- Validate on a `SRLB_SCOPE` sub-hierarchy first before a whole-design run.
- csh host: no bash `2>&1` / `2>/dev/null`; avoid inline `!` (history expansion).
  Interactive `source` of a big tcl floods the terminal - read the **result files**.
