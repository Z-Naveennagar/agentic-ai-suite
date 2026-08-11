<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

---
name: retiming-opportunities
description: "Identifies safe forward/backward retiming opportunities and forward-merge candidates in pre-place Vivado netlists. Use when deep logic imbalance limits Fmax. Produces ranked retiming candidates and optional placer retiming tags."
argument-hint: "<path-to-dcp> (required — a pre-place opt .dcp). Optional: ll_min=<N> (deep-logic threshold, default 8) slack_max=<ns> (logic-path window, default 0.2) bram_slack_max=<ns> (wider window for BRAM/URAM paths, default 0.5) clock=<name> (restrict to one clock)"
---

# Retiming Opportunity Identification

Analyze a Vivado Design Checkpoint (DCP) to find where **register retiming** can
improve timing (reduce logic levels on critical paths) or reduce area (collapse
parallel input registers), and **tag candidates for the placer to retime**.

**Primary target = the PRE-PLACE netlist** (a post-`opt_design` `_opt.dcp`).
The user supplies the DCP path — there is no built-in default.
Retiming candidates are identified structurally (register topology + combinational
depth) and tagged with `PSIP_RETIMING_FORWARD` / `PSIP_RETIMING_BACKWARD` so the
**placer** performs the retiming during placement. A placed/routed DCP is only
needed as an optional refinement to rank by real slack / delay dominance.

## When to Use
- User asks to find **retiming opportunities** / **register retiming** on a DCP
- User wants to **reduce logic levels** / rebalance deep combinational paths
- User asks about **backward** or **forward** retiming, register merging, or FF-count reduction
- User wants to know **which deep paths can be retimed vs which need RTL pipelining**
- User wants to tag cells with `PSIP_RETIMING_FORWARD` / identify un-retimed headroom

## Goal
Analyze register topology, combinational depth, clock domains, and constraints on
the pre-place netlist to produce **actionable, ranked** retiming recommendations
(and placer tags) that reduce logic levels / balance path depth and raise Fmax
**while preserving functional correctness**. Never recommend a move that changes
protocol/interface timing or externally-visible latency.

## HARD SAFETY RULES — never recommend retiming that crosses these
A candidate is DISQUALIFIED (drop it, do not rank it) if the path or its
registers touch any of:
- **Timing exceptions** — endpoints on a `set_multicycle_path` or `set_false_path`
  (check `get_property` / `report_exceptions`; any exception on the start/end).
- **Asynchronous clock boundaries** — launch clock != capture clock and they are
  not synchronous/same-domain.
- **CDC synchronizers** — cells with `ASYNC_REG==TRUE`, or in a synchronizer chain.
- **Reset synchronizers** — reset-sync FF chains.
- **Black boxes** — endpoints inside a black box / no editable netlist.
- **User-marked logic** — `DONT_TOUCH==TRUE` or `MARK_DEBUG==TRUE` on any cell on
  the path (respect user intent).
- **IO boundary flops** — flops directly on a top-level port path, unless the user
  explicitly allows it.

Clock-domain rules (strict):
- **Only retime WITHIN the same clock domain.** Launch clock == capture clock.
- **Never move registers across generated clocks, divided clocks, or asynchronous
  clocks** unless functional equivalence can be proven.
- Retiming must be **latency-preserving** (move existing registers) — if it would
  change I/O latency of a protocol, do not recommend it.

## Retimeability criteria — flag a candidate ONLY IF all of these hold
**Do NOT identify a retiming opportunity merely because a path is timing-critical.**
A register relocation must **demonstrably improve logic balance across adjacent
pipeline stages**. Always evaluate the stage BEFORE and AFTER the candidate
register (`prev_FF -> FFx -> next_FF`) and require ALL of:
1. **Structural imbalance** between adjacent stages — one stage is materially
   deeper / tighter than its neighbor. If all adjacent stages are within a small
   slack window (or equal depth), there is nothing to rebalance -> **REJECT**.
2. **Absorbable** — the donor (neighbor) stage has **enough positive setup slack
   (or depth headroom) to absorb** the delay/levels being moved, and stays
   setup-safe afterward. If the neighbor cannot absorb the full movement, retiming
   only shifts / partially relocates the violation -> **REJECT**.
3. **Hold-safe** — minimum hold slack stays above the safety threshold after the
   move (relocating a register can create hold violations).
4. **Reduces the MAXIMUM stage delay** — improves the worst slack of the adjacent
   pair, rather than merely shifting the violation onto the neighbor.

Anti-examples (REJECT):
- `FF1->FF2 = +15ps`, `FF2->FF3 = -40ps` — the neighbor's +15ps cannot absorb the
  40ps deficit; moving delay just relocates the violation onto `FF1->FF2`. REJECT.
- All adjacent stages within a small slack window (already balanced) — no imbalance
  to exploit. REJECT.

On the **PRE-PLACE netlist** use **logic depth** as the proxy: imbalance = adjacent
stage depth difference; "absorbable" = donor stage shallow enough that after moving
k levels its depth stays `<=` the reduced critical depth; "reduces max" = the larger
of the two adjacent stage depths strictly decreases. On a routed DCP use the actual
per-stage setup/hold slack.

## Methodology — 6 steps per checkpoint
**Pre-place netlist flow (default):** the discriminator is **combinational depth /
imbalance**, so run Step 1 (by logic depth), then Steps 4-6, and TAG for the
placer. **Steps 2-3 are the optional routed refinement** — only meaningful when a
placed/routed DCP is available; skip them (or mark N/A) on the pre-place netlist.
1. **Identify worst paths** — sample the **top `DEEP_MAXPATHS` (5000) setup paths
   with slack `< SLACK_MAX` (0.2ns)** so we focus on **failing + near-passing**
   paths (not comfortable ones). On pre-place, rank the resulting FF->FF cones by
   **logic levels** (combinational depth). On a routed DCP, slack is exact.
   **BRAM/URAM exception:** paths touching a block RAM / UltraRAM are additionally
   sampled up to a **wider window `BRAM_SLACK_MAX` (0.5ns)** — a failing block-RAM
   path is already covered by the normal window, but a block-RAM path that already
   *meets* timing with only a **tight positive margin (up to +0.5ns)** is also taken
   as a candidate, because building **extra slack around BRAM/URAM** hard blocks
   helps the downstream P&R tool chain place/route those cells.
2. **Classify each violation** by dominant contributor (from the path's delay
   breakdown):
   - **logic-depth dominated** — high logic-level count, `logic delay` large.
   - **routing dominated** — few logic levels but `route delay` >> `logic delay`.
   - **congestion dominated** — route-dominated AND in a
     `report_design_analysis -congestion` hotspot (adjacent cells still high route).
   - **clock-skew dominated** — large `Clock Path Skew` / negative CPR relative to
     data path.
3. **Gate on logic fraction — only evaluate retiming if `logic delay > 60%` of
   total data-path delay.** Routing/congestion/skew-dominated paths are NOT
   retiming candidates (they need placement/congestion/clock fixes) — report them
   separately, do not recommend retiming for them.
4. **Identify pipeline imbalance** — for a qualifying deep path, compare the logic
   depth on either side of the launch/capture registers. Imbalance (one stage much
   deeper than its neighbor) is what retiming rebalances.
5. **Estimate gain** — approximate post-retiming stage delay by rebalancing the
   cone: `gain ~= logic_delay * (1 - balanced_depth/current_depth)` bounded by the
   neighbor-stage slack you can borrow. A move that cannot borrow slack (deep
   single stage, no neighbor register) yields ~0 from pure retiming -> flag as
   "needs RTL pipelining", not retiming.
6. **Rank recommendations** — order by estimated WNS/TNS gain, tagging each as
   FORWARD-merge, BACKWARD-retime (pure-LUT), or PIPELINE (carry/deep-single-stage),
   with the safety checks already applied.

## The three retiming patterns detected

### 1. Forward register-merge (area + timing)
```
 FF_a ─┐                              (comb a)─┐
 FF_b ─┼─►[ LUT ]─► loads    ==>      (comb b)─┼─►[LUT]─►[FF]─► loads
 FF_c ─┘                              (comb c)─┘
 N registered inputs                    1 register on the LUT output
```
A LUT qualifies (strict & safe) when **every** used data input is driven by a
D-FF `Q` with **fanout==1**, there are **>= 2** such FFs, and **all share the
identical control set** — same primitive TYPE (=> same reset value/kind & edge),
same `CLK` net, same `CE` net, same `SET/RESET` net. Constant (`VCC`/`GND`)
inputs are allowed. Then the N input FFs retime forward into ONE output FF
(**saves N-1 FFs**). Functionally exact: `y = LUT(Qa,Qb,..) == FF(LUT(a,b,..))`
under identical control sets.

### 2. Backward / forward retiming on deep logic (timing)
Deep combinational cones (logic levels `>= ll_min`) between a source and a capture
register. **Only the register being MOVED must be a FF** — the OTHER end may be a
BRAM/DSP, because we move the FF *through the LUTs*, never *across* the BRAM/DSP:
- **BACKWARD**: the **capture (endpoint) must be a FF**; the source may be anything.
  Valid: **`BRAM -> N*LUT -> FF`** (pull the capture FF back into the LUT cone to
  shorten the deep incoming stage). Feasible when the FF's outgoing stage is shallow.
- **FORWARD**: the **launch (startpoint) must be a FF**; the destination may be
  anything. Valid: **`FF -> N*LUT -> BRAM`** (push the launch FF forward into the
  cone). Feasible when the FF's incoming stage is shallow.

**Retimeability is decided by the BOUNDARY primitive, not the whole cone:**
- A cone MAY contain lookahead/arithmetic (`LOOKAHEAD8`/`LUTCY1/2`/`LUT6CY`/`CARRY*`)
  and still be retimeable, **as long as the primitive AT the register boundary is a
  PURE LUT** (LUT1-6): for BACKWARD, the last primitive driving the endpoint FF's `D`;
  for FORWARD, the first primitive on the launch FF's `Q`. The FF just moves across
  that pure LUT — carry earlier in the cone is untouched.
- **Blocked only** when a carry element (`LUT6CY`/`LUTCY`/`LOOKAHEAD8`) sits *directly*
  at the register boundary (the FF can't cross it). A cone whose deep logic is a single
  atomic carry structure needs **RTL pipelining**, not retiming.

### 3. Reset / dominant-value don't-care retiming
When several flops fan into one LUT and a resettable flop drives a **controlling**
LUT input whose controlling value == its reset value, the LUT output is forced
during reset, so every SIBLING flop's reset feeding the same LUT is a DON'T-CARE
and can be dropped/retimed away.

## Critical rules & caveats (read before acting)
- **`_bret` / `_fret` / `_replica` = already retimed / replicated** (timing- or
  fanout-driven). Policy differs by pass:
  - **Forward-MERGE (area):** EXCLUDE them — collapsing timing-retimed FFs to save
    area would undo the retimer's work and regress WNS.
  - **Backward/forward TIMING pass:** INCLUDE them — a `_bret`/`_fret` register that
    *still* shows adjacent-stage imbalance is a valid further-retiming target. The
    ranked report flags such candidates as `(already-retimed cell)`.
- **Retiming is latency-preserving ONLY when moving existing registers** to
  rebalance an imbalanced boundary. A genuinely deep single combinational stage
  with no borrowable neighbor register cannot be shortened by retiming — it needs
  an ADDED pipeline register (RTL / latency change).
- **Control-set match is mandatory** for the forward merge (different CE/SR can't
  fold into one FF).
- **`get_cells` name matching (verified):** full hierarchical names with plain
  bus indices resolve verbatim — `get_cells {a/b[0].c/reg[0][x][14]}` == 1. Do
  NOT escape brackets (`\[` -> 0 matches) and do NOT add `-hier`. Prefer object
  handles (`get_cells -of_objects <pin/net>`) when tagging.
- **Tagging for the PLACER retiming flow (this skill's output):** drive retiming
  inside the placer by tagging the register to move:
  - FORWARD candidate  -> `set_property PSIP_RETIMING_FORWARD TRUE [get_cells {cell_name}]`
  - BACKWARD candidate -> `set_property PSIP_RETIMING_BACKWARD TRUE [get_cells {cell_name}]`
  (internal AMD placer retiming hints, not in public docs.) Tag ONLY registers
  that pass EVERY safety + feasibility check. For a forward-merge, tag the N input
  registers; for a backward-retime, tag the capture register of the deep cone.

## Prerequisites
- The `.dcp` to analyze — **required input, provided by the user** (a pre-place
  opt netlist). Ask for it if not given; do not assume a default path.
- Vivado on an LSF RHEL8 host (see load rule below).

## Checkpoint stage — PRE-PLACE is the focus
- **This skill operates on the PRE-PLACE (opt) netlist.** Retiming candidates are
  purely structural: register topology, control sets, combinational depth (logic
  levels), carry-vs-pure-LUT, and `_bret`/`_fret` headroom. These are exact on the
  opt netlist and are what the placer consumes via the PSIP tags. Rank by
  **combinational depth / imbalance**, not by route delay.
- **Delay-dominance classification (routing / congestion / skew and the >60%
  logic-delay gate) is a SECONDARY, OPTIONAL refinement that needs a PLACED or
  ROUTED checkpoint.** On the pre-place netlist there is no placement/routing, so
  every path is logic-only — use logic depth as the signal and do NOT claim
  route/congestion/skew numbers. If a placed/routed DCP is later provided, apply
  the delay-dominance gate to prioritize which tagged candidates most affect WNS.

## Procedure

### Step 1 — Load the DCP via LSF batch (never on the login node)
Write a small wrapper and submit it (csh shell; RHEL8 pin is required — Vivado
2026.1 needs GLIBC_2.27+, rhelws77 hosts FAIL). See
[run_retiming_lsf.csh](./scripts/run_retiming_lsf.csh):
```bash
bsub -q long -J retime -n 2 \
  -R "select[ostype==rhelws810 || ostype==rhelws86 || ostype==rhelws89 || ostype==rhelws87] rusage[mem=65536]" \
  -o <outdir>/retime.%J.log \
  ./run_retiming_lsf.csh <dcp_path> <outdir>
```
The wrapper runs `vivado -mode batch -source detect_retiming_opportunities.tcl
-tclargs <dcp> <outdir>`. Monitor with `bjobs <jobid>` and `tail -f` the log.
- Vivado: `/proj/primebuilds/2026.1_PRIME_daily_latest/installs/lin64/2026.1/Vivado/bin/vivado`
  (2026.1 opens 2025.2_KSB1-built checkpoints fine). LSF cluster = xsj-tempest.
- Write ALL outputs to files in `<outdir>` (never stream large cell lists to stdout).

### Step 2 — Run the detector
[detect_retiming_opportunities.tcl](./scripts/detect_retiming_opportunities.tcl)
runs the passes and writes:
- `ff_merge_retiming.{rpt,sum}` — forward-merge candidates (per-LUT: #FFin, saved
  FFs, control set, FF cells) + totals (SAFE vs all).
- `deep_paths.{csv,sum}` — per deep cone: `depth_in`, `depth_out(E)`, `depth_in(S)`,
  imbalance, carry?, same-domain?, tagged register + direction; and totals
  (carry->PIPELINE, cross-domain skip, balanced/small-window REJECT, FORWARD/BACKWARD).
- `retiming_candidates.rpt` — **RANKED, REASONED** candidates: estimated logic-levels
  saved, direction, the two adjacent-stage depths, and a one-line justification each.
- `report_timing_<clk>.rpt` — per-clock worst paths (for the routed delay-gate).
- `set_retiming_tags.tcl` — only if `SAVE_TAG=1` (`PSIP_RETIMING_FORWARD`/`BACKWARD`).

Env/arg tunables: `LL_MIN` (deep-logic level threshold, default 8), `IMBAL_MIN`
(min adjacent-stage imbalance, default 3), `DEEP_MAXPATHS` (paths sampled, default
**5000**), `SLACK_MAX` (only consider paths with setup slack `<` this, default
**0.2ns** = failing + near-passing), `BRAM_SLACK_MAX` (wider window for paths that
touch a BRAM/URAM so passing-but-tight block-RAM paths are also considered, default
**0.5ns**), `CLOCK` (restrict to one clock), `SAVE_TAG`
(also emit `set_retiming_tags.tcl` with `PSIP_RETIMING_FORWARD` /
`PSIP_RETIMING_BACKWARD` set_property lines for the validated candidates).

### Step 3 — REASON on each selected candidate (do not just dump the list)
Robustness rule: **every recommendation must be individually justified**, not
flagged only because a threshold passed. Open `retiming_candidates.rpt` (ranked by
levels saved) and for the top candidates confirm & explain, with the numbers:
- **Imbalance is real** — `depth_in` vs the donor depth differ by `>= IMBAL_MIN`;
  state the two adjacent-stage depths.
- **Absorbable & reduces max** — moving `~imbalance/2` levels makes the balanced
  max depth (`newMax`) strictly less than the original critical depth; quote the
  before/after.
- **Pure-LUT & safe** — no carry on the cone; register not `_bret`/`_fret`/
  `DONT_TOUCH`/`ASYNC_REG`; same clock domain.
- **Direction** — FORWARD (launch reg, outgoing stage deep) vs BACKWARD (capture
  reg, incoming stage deep) and WHY that direction rebalances here.
- **Hold caveat** — note hold-slack must be re-verified on a placed/routed DCP.
Reject (and say why) any candidate that only shifts the violation or whose neighbor
cannot absorb the move (the `+15/-40` case).

### Step 4 — Report totals & emit tags
- **Forward-merge**: FFs saved = Σ(#FFin−1), SAFE subset only.
- **Deep logic**: pure-LUT retimeable count vs carry (PIPELINE) count vs
  balanced-reject count vs cross-domain; module hotspots; `_bret`/`_fret` headroom.
- Emit tagging ONLY for the validated set: `PSIP_RETIMING_FORWARD TRUE` on forward
  candidates (forward-merge input regs / launch reg), `PSIP_RETIMING_BACKWARD TRUE`
  on backward candidates (capture reg of a deep pure-LUT cone). Sourceable
  `set_retiming_tags.tcl` (`SAVE_TAG=1`).

## Scripts
| Script | Purpose |
|--------|---------|
| [detect_retiming_opportunities.tcl](./scripts/detect_retiming_opportunities.tcl) | Main detector — all three passes, writes reports. Read-only (no design mutation unless `SAVE_TAG=1`). |
| [run_retiming_lsf.csh](./scripts/run_retiming_lsf.csh) | LSF wrapper: opens the DCP on a RHEL8 host and runs the detector in batch. |

## Shell notes (csh)
- No bash `2>&1` / `2>/dev/null` (use `>&` or omit). No bash `for`. `!` triggers
  history expansion — avoid inline; put Tcl/awk in files.
- Multi-line `awk` with `{}`/`if` breaks csh — always `awk -f file.awk`.
