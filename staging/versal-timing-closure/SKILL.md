---
name: versal-timing-closure
description: >
  Drives the end-to-end Versal Adaptive SoC timing-closure flow (UG1788) on any
  Versal device via the Vivado MCP server. Runs the full implementation flow
  (opt_design -> place_design -> phys_opt_design -> route_design), applies
  report_qor_suggestions, diagnoses the dominant timing limiter (logic delay,
  net delay/congestion, clock skew, clock uncertainty, or hold), and iterates
  directives/strategies autonomously until timing closes. Delegates per-stage
  analysis to congestion-analysis, opt-design-analysis, phys-opt-design-analysis,
  and timing-methodology-checks. Use when the user asks to "close timing",
  "timing closure", "meet timing", "fix WNS/WHS", "my design fails timing",
  "run UG1788 flow", "baseline timing", "reduce timing violations", "improve QoR",
  "pick a place/route directive", "run report_qor_assessment", "drive
  place and route to close timing", "launch parallel LSF implementation runs",
  "relaunch from the post-opt DCP", or "over-constrain a clock to close a small
  setup gap" on a Versal design. Honors a strict NO-timing-exceptions policy
  (never adds false_path/clock_groups/max_delay to mask violations).
version: 1.1.0
vivado_version: 2025.2+
categories: [implementation, timing, closure, orchestrator]
device_families: [versal]
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
# Versal Timing Closure (UG1788) — End-to-End Flow Driver

**Purpose:** Autonomously close timing on a Versal design by driving the Vivado
implementation flow, applying QoR suggestions, diagnosing the dominant limiter, and
iterating directives — per the *Versal Adaptive SoC Timing Closure Quick Reference
Guide (UG1788)*.

**Output:** `vivado_agentic_ai_reports/versal-timing-closure/` — per-stage
`<stage>_*.rpt` (qor_assessment/suggestions, timing_summary, design_analysis,
methodology, clock_interaction, utilization, control_sets, high_fanout,
route_status), `iteration_log.csv` (one row/attempt: directives, WNS, WHS,
congestion), and `TIMING_CLOSURE_REPORT.md` (copy-pasteable fixes with ACTUAL
names + the closure decision trail).

**This skill is an orchestrator.** It drives the flow and delegates deep analysis
to leaf skills. See [Delegation](#delegation-to-leaf-skills).

**Scaffold, not a cage.** This skill carries the UG1788 methodology, a set of
*tested* levers, guardrails, and bundled Tcl — it is **not** an exhaustive
rulebook. **Diagnose the dominant limiter on _this_ design first**, then choose or
adapt a lever; never apply a fix just because it's "next in the table." If the
right fix isn't here, use `vivado_doc_search` + the per-stage **Document Map**
(REFERENCE.md) to pull the authoritative guide and reason from it — inventing a
sound, design-specific lever is encouraged. **Only the guardrails are hard rules:**
never add exceptions to mask real paths; always remove an over-constraint before
sign-off; never claim closure without the honest verification gates.

---

## Table of Contents
- [Prerequisites](#prerequisites)
- [Vivado MCP Tools](#vivado-mcp-tools)
- [Efficiency Guidelines](#efficiency-guidelines)
- [Device-Independence Rules](#device-independence-rules)
- [Workflow](#workflow-autonomous)
- [Limiter Decision Tree](#limiter-decision-tree)
- [Control Knobs by Limiter](#control-knobs-by-limiter-the-full-surface--directives-are-only-one-layer)
- [Directive Iteration Strategy](#directive-iteration-strategy)
- [Delegation to Leaf Skills](#delegation-to-leaf-skills)
- [Design-Specific Fix Rules](#mandatory-design-specific-fix-rules)
- [Error Handling](#error-handling)
- [Validation](#validation)
- [References](#references)

---

## Prerequisites

| Requirement | Details |
|---|---|
| Vivado version | 2025.2 or later (UG1788 v2025.2 baseline) |
| Target family | **Any Versal** Adaptive SoC (xcv*, monolithic or SSI/multi-SLR). No part is hard-coded. |
| Design state | A loaded design at any stage: post-synth, post-opt, post-place, or post-route (project `.xpr` or checkpoint `.dcp`). |
| Open project | A Vivado project (`.xpr`) or one or more checkpoints (`.dcp`) available in the working directory. |
| Vivado session | Connected via the Vivado MCP server (`vivado_start` / `vivado_connect`). |
| Constraints | Realistic clock constraints applied (UG1788 Initial Design Checks gate). |

---

## Vivado MCP Tools

This skill runs **entirely through the Vivado MCP server** — for **both** analysis
**and** parallel job launch. All Tcl/reporting goes through `vivado_execute`; all
parallel runs go through `vivado_lsf`. **Never** shell out to a standalone `vivado`
binary, a raw `bsub`, or a batch script — even an LSF node is driven by passing its
returned `session_id` to `vivado_execute` (so analysis on LSF nodes is MCP too).

| MCP tool | Use |
|---|---|
| `vivado_start(working_dir=<cwd>)` | Start a fresh Vivado Tcl session. Returns a `session_id`. |
| `vivado_connect(...)` | Attach to an already-running Vivado session instead of starting one. |
| `vivado_execute(session_id=<id>, tcl_command="...", timeout_seconds=<n>)` | Run one atomic Tcl command. Pass `session_id` on **every** call. |
| `vivado_doc_search("<query>")` | Look up unfamiliar directive names, property values, or report options (e.g. "place_design directives", "GCLK_DESKEW", "USER_CLOCK_VTREE_TYPE"). No `session_id` needed. **Use this instead of guessing or retrying syntax.** |
| `vivado_lsf(action=start, working_dir=<cwd>, session_type="general", memory="32g", slots=8)` | Submit a Vivado session on an **LSF** node **via the MCP server** (never raw `bsub`). `memory` = GB string (`"32g"`); `slots` = CPU cores (8). Returns a `session_id` you then drive with `vivado_execute`. `action=status` polls PEND/RUN/DONE/EXIT; `action=kill` retires a job. Size to the design and run **multiple runs in parallel** (see *Parallel Runs via LSF*). |
| `vivado_stop(session_id=<id>)` | Stop the session when the flow is complete. |

> **Unsure about a command, directive, property, or option?** Call
> `vivado_doc_search` first. Never retry a failed Tcl command with invented
> syntax — look it up, then proceed.

---

## Efficiency Guidelines

- **Pass `session_id`** to every `vivado_execute` call.
- **Write reports to file** with Vivado's `-file` flag — never dump full report
  bodies into chat. Summarize in one or two lines.
- **Read reports efficiently** — `grep`/`sed`/`awk` via terminal to pull sections;
  `wc -l` + `head` to size first; full `read_file` only for reports <200 lines.
- **Do NOT** use `shell ls`/`find`/`glob` to locate files, or Vivado Tcl (`exec cat`,
  `open`, `read`) to read them — use your file reader or `grep`/`sed`.
- **Do NOT** retry a failed Tcl command with different syntax. Call
  `vivado_doc_search`, report the error, then proceed.
- **Long-running stages need explicit timeouts**: pass `timeout_seconds=18000` for
  `opt_design`/`place_design`/`phys_opt_design`/`route_design`.

---

## Device-Independence Rules

This skill targets **all Versal devices**. Detect the device context at runtime;
never hard-code a part, SLR count, or clock name.

| Detect at runtime | How | Gates which techniques |
|---|---|---|
| Part / speed grade | `get_property PART [current_design]` | Logic-level / Fmax thresholds |
| SLR count (SSI vs monolithic) | `set n [llength [get_slrs]]` | SSI-only techniques below |
| Clock names | `get_clocks` | All clock fixes use actual names |
| Utilization per SLR | `report_utilization -slr` (if `n>1`) | Congestion / floorplan guidance |

**SSI-only techniques** (apply **only** when `[llength [get_slrs]] > 1`):
`USER_SLR_ASSIGNMENT`, SLR Pblocks, calibrated deskew (`GCLK_DESKEW CALIBRATED`),
`USER_CLOCK_VTREE_TYPE interSLR`, SLR-boundary pipelining. On monolithic Versal
parts, skip these and focus on logic/net/clock techniques.

---

## Workflow (Autonomous)

**⚠️ CRITICAL: Execute steps SEQUENTIALLY. Wait for each `vivado_execute` to
complete before issuing the next.** Long stages run for minutes to hours.

**⚠️ The workflow is incomplete until `TIMING_CLOSURE_REPORT.md` exists.** Do not
end your turn before invoking the write tool to create it. Do not narrate ("Now
generating...") before writing — invoke the write tool first, then summarize.

```
Versal Timing Closure Progress:
- [ ] Step 1: Connect MCP, open design, detect stage/part/SLRs/clocks
- [ ] Step 2: Initial Design Checks (report_qor_assessment + qor_suggestions)
- [ ] Step 3: opt_design (+ apply QoR suggestions)  [delegate: opt-design-analysis]
- [ ] Step 4: place_design -> baseline reports  [delegate: congestion-analysis, timing-methodology-checks]
- [ ] Step 5: phys_opt_design (setup/hold)  [delegate: phys-opt-design-analysis]
- [ ] Step 6: route_design -> verify fully routed -> post-route baseline
- [ ] Step 7: Diagnose dominant limiter (decision tree) + apply fixes
- [ ] Step 8: Iterate directive/strategy; log QoR; loop until target met
- [ ] Step 9: Write TIMING_CLOSURE_REPORT.md, then short summary
```

### Step 1: Connect, Open Design, Detect Context (single call)

Start (or connect to) the MCP session, then open the design and capture context.
Workspace auto-detect handles both `.dcp` and project flows.

```tcl
set dcp [lindex [glob -nocomplain *.dcp] 0]; if {$dcp != ""} { open_checkpoint $dcp } elseif {[catch {current_design}]} { open_run impl_1 }; file mkdir vivado_agentic_ai_reports/versal-timing-closure; set part [get_property PART [current_design]]; set nslr [llength [get_slrs]]; puts "Design:[current_design] Part:$part SLRs:$nslr Mode:[get_property DESIGN_MODE [current_design]] Clocks:[llength [get_clocks]]"
```

If multiple checkpoints exist (e.g. a regression with `post_place.dcp`,
`post_route.dcp`), pick the **earliest unclosed** stage to resume from, or ask
which to drive if ambiguous.

### Step 2: Initial Design Checks (gate before implementing)

Per UG1788 *Initial Design Checks*: before spending P&R runtime, review
utilization, logic levels, SLR/Pblock budgets, clock constraints, **control sets**
(>7.5%) and **high-fanout reset/CE nets** (bundle emits `*_control_sets.rpt` + `*_high_fanout.rpt`; REFERENCE §8–§9).

```tcl
source skills/vivado/versal-timing-closure/tcl/baseline_reports.tcl; vtc_baseline_reports initial vivado_agentic_ai_reports/versal-timing-closure
```

Then read `report_qor_assessment`'s **Overall Assessment Score** (1–5) and any
`REVIEW` rows; read `report_qor_suggestions`. Score meaning:
`1`=won't implement, `2`=implements but won't meet timing, `3`=likely miss,
`4`=likely meet, `5`=will meet. If score ≤ 2, fix flagged items (constraints,
utilization, SLR overflow) **before** proceeding — see [REFERENCE.md](REFERENCE.md).

Apply automatable suggestions:
```tcl
report_qor_suggestions -file vivado_agentic_ai_reports/versal-timing-closure/qor_suggestions.rqs; read_qor_suggestions vivado_agentic_ai_reports/versal-timing-closure/qor_suggestions.rqs
```

### Step 3: opt_design + QoR Suggestions

Only if the design is pre-opt (`DESIGN_MODE`/state indicates synthesized, not yet
optimized). Otherwise skip to Step 4.

```tcl
opt_design; write_checkpoint -force vivado_agentic_ai_reports/versal-timing-closure/post_opt.dcp
```
`timeout_seconds=18000`. **Delegate** the opt log to **opt-design-analysis** to
confirm retarget/propconst/sweep/remap behaved and no `DONT_TOUCH`/`MARK_DEBUG`
blocked optimization.

### Step 4: place_design + Baseline

Pick the placer directive from [Directive Iteration Strategy](#directive-iteration-strategy)
(start `Default`, escalate on failure). Add `-net_delay_weight {medium|high}` to
penalize long/high-fanout nets when net delay dominates.

```tcl
place_design -directive [actual_place_directive]; source skills/vivado/versal-timing-closure/tcl/baseline_reports.tcl; vtc_baseline_reports postplace vivado_agentic_ai_reports/versal-timing-closure
```
`timeout_seconds=18000`. Pre-route, **WNS should be ~0**; large negatives signal
sub-optimal placement (util/congestion/logic-levels/skew). **Delegate** to
**congestion-analysis** (post-place reports) and **timing-methodology-checks**.

### Step 5: phys_opt_design

Run physical optimization. For setup, use `-directive Explore` (escalate to
`AggressiveExplore`). For large estimated hold (WHS < -0.75 ns *before routing*),
run a hold-fix pass instead — **`-hold_fix` / `-aggressive_hold_fix` cannot be
combined with `-directive`** (UG1788).

```tcl
phys_opt_design -directive Explore; source skills/vivado/versal-timing-closure/tcl/baseline_reports.tcl; vtc_baseline_reports postphysopt vivado_agentic_ai_reports/versal-timing-closure
```
Hold-fix variant (separate run, no `-directive`):
```tcl
phys_opt_design -hold_fix
```
`timeout_seconds=18000`. **Delegate** to **phys-opt-design-analysis** (replication,
retiming, LUT1 hold inserts, per-iteration WNS/TNS). Ensure as many paths as
possible meet timing before routing so the router can spend skew on the rest.

### Step 6: route_design + Verify Fully Routed

```tcl
route_design -directive [actual_route_directive]; source skills/vivado/versal-timing-closure/tcl/baseline_reports.tcl; vtc_baseline_reports postroute vivado_agentic_ai_reports/versal-timing-closure
```
`timeout_seconds=18000`. **First verify full routing** via `report_route_status`
(the bundle writes `postroute_route_status.rpt`) — unrouted nets invalidate
timing. For small residual setup violations (> -0.100 ns), run a post-route
`phys_opt_design`:
```tcl
phys_opt_design; source skills/vivado/versal-timing-closure/tcl/baseline_reports.tcl; vtc_baseline_reports final vivado_agentic_ai_reports/versal-timing-closure
```

### Step 7: Diagnose the Dominant Limiter

From the post-place/post-route `report_design_analysis` and `report_timing_summary`,
classify the worst paths and follow the [Limiter Decision Tree](#limiter-decision-tree),
then consult [Control Knobs by Limiter](#control-knobs-by-limiter-the-full-surface--directives-are-only-one-layer)
for the **full set of knobs** (placement/clock/fanout/structural constraints — not just
directives) to turn for that limiter. Extract **actual** clock names, cell paths, and
net names for fixes. Apply automatable fixes (properties/constraints) and record
RTL-level recommendations that need user action. Full catalog: [REFERENCE.md](REFERENCE.md); for
which lever most often closed real Versal escalations (plus before→after
evidence and adaptable recipes), see [CASE_LIBRARY.md](CASE_LIBRARY.md).

### Step 8: Iterate

Append a row to `iteration_log.csv` (attempt, directives, WNS, WHS, congestion
level, score). Choose the next directive/strategy per
[Directive Iteration Strategy](#directive-iteration-strategy). Re-run from the
appropriate stage (place or route). Loop until WNS ≥ 0 and WHS ≥ 0 (or the user's
target), or until directive options are exhausted — then report remaining
violations with RTL/constraint recommendations.

### Step 9: Generate the Report

**Action:** invoke the write tool to create
`vivado_agentic_ai_reports/versal-timing-closure/TIMING_CLOSURE_REPORT.md` using
[TEMPLATES.md](TEMPLATES.md). Include the iteration log, final QoR, and a
**📋 Copy-Paste Fix** block (ACTUAL names) for every applied/recommended fix.
**Order:** write the file first, *then* give a short chat summary. Do not output
the report as chat text.

---

## Limiter Decision Tree

Use the worst-path header from `report_timing_summary` / `report_design_analysis`
(Logic Delay, Net/Route Delay, Clock Skew, Clock Uncertainty) plus WHS to pick a
branch, then open the matching REFERENCE section for techniques + copy-paste fixes.

> **Load only the routed section (progressive disclosure).** REFERENCE.md is a
> ~600-line catalog — do **not** read it whole. Once the tree/matrix names a section,
> extract just that slice by header, e.g. `sed -n '/^## 4\./,/^## /p' REFERENCE.md`
> (or view the §N line range). The matrix routes one limiter → one section, so a
> single section read gives you all the sibling knobs needed to choose between them.
> Pull a second section only for a cross-cutting limiter (congestion → §3 **and**
> §8/§9/§10).

```
Is the design fully routed? ── No ──> congestion likely; go to NET DELAY branch
        │ Yes
        ▼
WHS < 0 (hold)? ── Yes ──> HOLD branch (REF §1; fix hold BEFORE setup, UG1788)
        │ No
        ▼
Which contributes most to the worst setup path?
  ├─ Logic Delay / many logic levels ─> LOGIC DELAY branch (REF §2)
  ├─ Net/Route Delay (detours) ───────> NET DELAY / CONGESTION branch (REF §3;
  │     + control sets §8, reset fanout §9, floorplan §10)
  ├─ Clock Skew ──────────────────────> CLOCK SKEW / TOPOLOGY branch (REF §4)
  └─ Clock Uncertainty ───────────────> CLOCK UNCERTAINTY branch (REF §5)

Truly asynchronous clocks (different primary clocks, no common node, real CDC
circuitry)? ──> RTL/CDC design fact, not a P&R lever. Timing exceptions
(set_clock_groups / set_false_path / set_max_delay) may ONLY be added with explicit
user approval AND proper CDC synchronizers (REF §7) — see the Guardrail below.
By default DO NOT add them; flag the path for the user.
```

---

## Control Knobs by Limiter (the full surface — directives are only one layer)

The decision tree classifies the limiter (picks the **row**); this matrix says **how to
choose a knob within that row.** Selection is **signal-driven, then cost-ordered**:
first read the **Selection signal** column — the observable from a `report_*` that points
to a *specific* knob — then escalate **cheap → expensive** (directive → constraint →
structural). Don't sweep blindly: a knob is justified by a measured trigger. Open the
cited REFERENCE.md section for the full numbered procedure + copy-paste Tcl.

| Limiter | Selection signal (observe → pick) | 1. Effort / directive | 2. Constraint knobs (targeted) | 3. Structural / RTL |
|---------|-----------------------------------|-----------------------|--------------------------------|---------------------|
| **Hold (WHS<0)** §1 | WHS<0 at all → fix hold first; large pre-route WHS (< −0.75) → aggressive | `phys_opt_design -hold_fix` → `-aggressive_hold_fix` | (avoid new long detours) | `set_multicycle_path -hold` only on genuine MCP paths |
| **Logic Delay** §2 | `report_design_analysis -routes` level count high → remap; path scattered across regions → cluster; feedback/deep path → RTL | `opt_design -remap` → `-resynth_remap`; `phys_opt Aggressive*` | `LUT_REMAP`, `SRL_STAGES_TO_INPUT`, `DOA/DOB_REG`; **`USER_CLUSTER`** if the FF→LUT→FF path is physically spread | Pipeline / retiming; DSP/BRAM/URAM cascade |
| **Net Delay / Congestion** §3 | util>70–80% → lower util/move SLR; **specific HFN** on path → fanout knob; Rent>0.65 or >15k-cell hier → synth routability; LUT-combine>40% → SOFT_HLUTNM; residual local hotspot → floorplan | `Explore -net_delay_weight high`; `route AlternateCLBRouting`; `Congestion_SpreadLogic_*` | **Fanout:** `MAX_FANOUT_MODE`/`FORCE_MAX_FANOUT`/`EQUIVALENT_DRIVER_OPT`. **Ctrl sets §8:** `CONTROL_SET_REMAP`, `BLOCK_SYNTH` thresh. **LUT-combine:** `reset SOFT_HLUTNM`. **Floorplan §10:** `USER_CLUSTER`→soft→hard Pblock | `BLOCK_SYNTH.STRATEGY ALTERNATE_ROUTABILITY`; reset fanout §9 |
| **Clock Skew** §4 | `report_clock_utilization`: root off-center from loads → `USER_CLOCK_ROOT`; two clocks must track → `CLOCK_DELAY_GROUP`; sync ratio 2/4/8 same source → MBUFG; <4000 I/O loads → `CLOCK_LOW_FANOUT` | (placer picks root by default) | **`USER_CLOCK_ROOT`**, `CLOCK_DELAY_GROUP`, `GCLK_DESKEW`(CALIBRATED/OFF), `CLOCK_LOW_FANOUT`, `CLOCK_BUFFER_TYPE`, `MBUFG` | Balance clock-tree loads; remove logic from clock path |
| **Clock Uncertainty** §5 | RAM-heavy clock region → tune URAA; small persistent **sync** gap on one clock-pair → OC | — | `USER_RAM_AVERAGE_ACTIVITY`; **targeted `set_clock_uncertainty` OC** (remove before sign-off) | Reduce jitter sources; review CDC |
| **SLR Crossing (SSI)** §6 | `report_utilization -slr` imbalance → balance/assign; net crosses SLR repeatedly → `USER_CROSSING_SLR`; clock crosses SLR → vtree/deskew | `Performance_BalanceSLRs` / `Floorplan.BalancedSLR` | **`USER_SLR_ASSIGNMENT`**(soft)→`USER_CROSSING_SLR`→SLR Pblock; `MAX_FANOUT_MODE SLR`; `USER_CLOCK_VTREE_TYPE interSLR`, `GCLK_DESKEW CALIBRATED` | SLR-boundary / auto-pipelining (Laguna), AXI register slice |

**Tie-breakers when several knobs fit:**
1. **Measured trigger wins** — pick the knob whose Selection signal you actually observe; never apply a knob speculatively "because it's in the list."
2. **Cheapest that addresses the signal** — directive before constraint before RTL; soft before hard (REF §10 ladder).
3. **Most local** — a knob scoped to the failing net/cell/region (`USER_CLOCK_ROOT`, `MAX_FANOUT_MODE`, `USER_CLUSTER`) beats a global re-roll, because it leaves the rest of the design's QoR intact.
4. **Precedent frequency** — when still tied, prefer the lever the TSR evidence shows closed real cases most often ([CASE_LIBRARY.md](CASE_LIBRARY.md) lever table).
5. **One change at a time** — apply, re-run from the post-opt DCP, log WNS/WHS/cong in `iteration_log.csv`, keep it only if it helped; otherwise revert before trying the next. This keeps cause→effect attributable.

**Eliminators (never pick, regardless of signal):** timing exceptions on real
sync/same-domain paths (guardrail below); hard Pblock dragging 0-logic boundary regs
(anti-pattern below); classic directives invalid in the Advanced Flow (REF mapping).
Confirm exact property names/values for the installed version with `vivado_doc_search`
(canonical: UG903 constraints, UG912 properties).

---

## ⚠️ No-Timing-Exceptions Guardrail

**Never use timing exceptions to make a real, same-domain or synchronous path
"pass".** `set_false_path`, `set_clock_groups`, `set_max_delay -datapath_only`,
and `set_multicycle_path` hide the violation rather than fix it — closing timing
by adding them ships a broken design.

- **Default = OFF.** Add a new timing exception only if the user explicitly
  approves it AND the path is a genuine async CDC with proper synchronizers
  (XPM_CDC / async FIFO).
- **Pre-existing exceptions** (IP/source XDC in the checkpoint) are fine — but
  prove the closure flow added **zero** new ones (`report_exceptions`; see
  *Honest Sign-off*).
- The legitimate lever for a persistent small **synchronous** setup gap is a
  **targeted over-constraint removed before sign-off** (next), NOT an exception.

---

## Directive Iteration Strategy

This is the **effort dimension of knob column 1** in the *Control Knobs by Limiter*
matrix above — escalate directive effort only after a cheaper attempt fails, **and
prefer a targeted constraint knob (matrix columns 2–3) over a further directive sweep
once these plateau.** Record every attempt in `iteration_log.csv`. Confirm exact
directive spellings with `vivado_doc_search` ("place_design directives",
"route_design directives") for the installed version.

| Attempt | place_design | phys_opt_design | route_design | When |
|---|---|---|---|---|
| 1 (baseline) | `Default` | `Explore` | `Default` | First pass |
| 2 (congestion) | `Explore` (+ `-net_delay_weight high`) | `AggressiveExplore` | `Explore` | Net-delay/congestion limited |
| 3 (Fmax) | `Explore -subdirective {GPlace.ExtraTimingOpt.high}` / `AggressiveExplore` | `AggressiveExplore` | `AggressiveExplore` | Logic/skew limited, small gap |
| 4 (hold) | (keep best) | `-hold_fix` then `-aggressive_hold_fix` (no `-directive`) | `Default` | WHS-limited pre-route |
| 5 (overconstrain) | best place dir | `AggressiveExplore` | best route dir | Persistent SMALL synchronous setup gap on a known clock-pair group — use the **targeted OC lever** below (NOT a timing exception) |

Also iterate **strategies** (Congestion_*, Performance_*) and floorplanning (SLR assignment → 2 Pblocks) per UG1788 when directives plateau.

> **Floorplan anti-pattern (learned):** Do NOT add hard per-bank Pblocks to drag
> **0-logic boundary registers** (e.g. Versal XPHY `*_bli_*` FDREs feeding
> `pll_clkoutphy_*`) toward their hard block — it moves them AWAY from the clock
> root and starves the local fabric, inducing congestion (observed level 5, WNS ≈
> −0.6, strictly worse). For that path class the OC lever wins, not floorplanning.
> Reserve Pblocks for large logic clusters that genuinely benefit from locality.

---

## Iterate by Relaunching from the Post-opt DCP (NOT in-memory re-run)

**Do NOT close timing by calling `place_design`/`route_design` repeatedly on the
same in-memory design** — stages are order-dependent and re-running on a bad
placement compounds noise. Treat the **post-opt checkpoint** as the fixed start and
**relaunch a fresh run from it** per directive/strategy combo:

```tcl
opt_design; write_checkpoint -force vivado_agentic_ai_reports/versal-timing-closure/post_opt.dcp
```
Every attempt is then `open_checkpoint post_opt.dcp` → directives/constraints →
place → phys_opt → route → sign-off — independent, comparable, parallel-safe.

## Parallel Runs via LSF

Run independent attempts **concurrently** on LSF nodes (each `32g`/`8` slots), keep the winner.

1. **Recon once**: open post-opt DCP, capture part/SLRs/clocks/util, filter RQS, write `post_opt.dcp`.
2. **Fan out**: `vivado_lsf(action=start, working_dir=<cwd>, session_type="general", memory="32g", slots=8)`
   once per hedged attempt (e.g. `Default`; `Explore + GPlace.ReduceCongestion`;
   `AggressiveExplore + Floorplan.BalancedSLR`; `Explore -net_delay_weight high`).
   Drive **each** returned `session_id` via `vivado_execute` to `open_checkpoint
   post_opt.dcp` and source the **same** flow script — same DCP, parallel.
3. **Monitor**: `vivado_lsf(action=status)` + tail each log. `vivado_execute` may
   return `NO_RESPONSE` during a long server-side stage — poll, do **not** retry.
4. **Compare, keep the winner**, retire the rest (`vivado_lsf(action=kill)`); use
   **subagents** to babysit runs in parallel.

## Targeted Over-constraint Lever (honest, exception-free)

When a small setup gap persists on a SPECIFIC, identifiable **synchronous**
clock-pair group (classic case: 0-logic structural paths limited by route delay +
launch/capture clock imbalance, RQS `CLOCK-5_1`), tighten **only those pairs**
during P&R, then **remove the tightening before sign-off**:

```tcl
# Apply OC on ONLY the failing launch->capture clock pairs (actual names), P&R, remove, sign off.
set VTC_OC_FROM_PAT {*_rxclk}; set VTC_OC_TO_PAT {pll_clkoutphy*}; set VTC_OC_VALUE 0.100; set VTC_PLACE_ARGS {-directive AggressiveExplore}; set VTC_ROUTE_ARGS {-directive AggressiveExplore}; source skills/vivado/versal-timing-closure/tcl/overconstrain_flow.tcl; vtc_overconstrain_flow
```

- Apply `set_clock_uncertainty -setup <amt> -from <launch> -to <capture>` on the
  ACTUAL failing pairs (NOT whole clocks). Start small (≈0.05–0.15 ns); escalate
  to ~0.5 ns only if needed. It biases the co-optimized placer+router to shorten
  those routes / rebalance skew — a **tightening, not an exception**.
- **Always remove it before sign-off** (`reset_clock_uncertainty -setup` on the
  same pairs). Bundled `overconstrain_flow.tcl` does apply→P&R→remove→sign-off in
  one call.

## Honest Sign-off & Verification Gates

A run is only "closed" when an **independent, exception-free** check passes. Open
the candidate `*_closed.dcp` in a clean session and run:

```tcl
source skills/vivado/versal-timing-closure/tcl/verify_signoff.tcl; vtc_verify_signoff vivado_agentic_ai_reports/versal-timing-closure
```

Gates (ALL must hold):

| Gate | Pass condition | How |
|---|---|---|
| Setup met | `WNS ≥ 0` (TNS = 0) | `report_timing_summary` |
| Hold met | `WHS ≥ 0` (THS = 0) | `report_timing_summary` |
| OC removed | Worst-path **user uncertainty UU = 0** (only inherent jitter remains) | `report_timing -of_objects <worst path>` |
| Fully routed | 0 failed/unrouted nets | `report_route_status` |
| No new exceptions | Closure flow added **zero** false_path/clock_groups/max_delay/multicycle (any present are PRE-EXISTING IP/source XDC) | `report_exceptions` + diff vs. input DCP |
| Residual WPWS characterized | Any `WPWS < 0` traced to **structural hard-IP** (GT/XPHY/MBUFG/PCIe min-period or max-skew) = out of P&R scope, not a closure failure | `report_pulse_width -all_violators` |

Report residual structural WPWS honestly as out-of-scope (needs RTL/IP/clock-spec
changes), never as a P&R bug and never hidden.

---

## Delegation to Leaf Skills

This skill drives the flow; the leaf skills do the deep per-stage analysis. Invoke
them on the reports this skill already generated (they read existing reports — no
re-run needed).

| After stage | Delegate to | What it adds |
|---|---|---|
| opt_design | **opt-design-analysis** | retarget/propconst/sweep/remap stats; DONT_TOUCH/MARK_DEBUG blockers; directive advice |
| place_design (post-place) | **congestion-analysis** | congestion heatmap, Rent exponent, util histograms, directive recommendation |
| place_design / route_design | **timing-methodology-checks** | TIMING-* methodology violations + XDC/RTL fixes |
| phys_opt_design | **phys-opt-design-analysis** | replication, retiming, LUT1 hold inserts, WNS/TNS trend |

Feed their findings back into Step 7 (limiter diagnosis) and Step 8 (next directive).

---

## ⚠️ MANDATORY: Design-Specific Fix Rules

**All fixes MUST use ACTUAL names from the design. NO generic placeholders.**

| Rule | ❌ WRONG | ✅ CORRECT (example) |
|------|----------|------------|
| Clock names | `clk_a`, `clk_b` | `txoutclk_out[0]`, `app_clk` |
| Cell paths | `xx/ramb18_inst` | `fpga1/dp_core/buf_ram_reg` |
| Net names | `<highFanoutNet>` | `fpga1/ctrl/rst_n_net` |
| Pblock / SLR | `<slr>` | `SLR1`, `pblock_dp_core` |
| Directives | `<directive>` | `AggressiveExplore` |
| Part | `xcvh1542...` (hard-coded) | `[get_property PART [current_design]]` |

Extract actual names from `report_design_analysis` / `report_timing_summary`
before writing any fix into `TIMING_CLOSURE_REPORT.md`.

---

## Error Handling

| Error | Symptom | Action |
|-------|---------|--------|
| No design open | `ERROR: No current design` | `open_checkpoint <dcp>` or `open_run impl_1`/`synth_1` |
| Wrong stage for command | `route_design` before place | Run the missing upstream stage first |
| `-hold_fix` + `-directive` | `phys_opt_design` errors | Run hold-fix as a separate pass without `-directive` (UG1788) |
| Unknown directive/property | Tcl reports invalid value | `vivado_doc_search` the exact name; do **not** guess/retry |
| Not fully routed | `report_route_status` shows unrouted nets | Re-route (different directive) before trusting timing |
| Stage timeout | place/route exceeds timeout | Increase `timeout_seconds` (18000) or reduce congestion first |
| Constraints unrealistic | QoR score ≤ 2, huge WNS pre-place | Fix constraints/util (Initial Design Checks) before iterating directives |

---

## Validation

```tcl
set d vivado_agentic_ai_reports/versal-timing-closure; if {[file exists $d/postroute_route_status.rpt] && [file exists $d/final_timing_summary.rpt]} { puts "OK route+timing reports present" }
```
Success: per-stage `.rpt` files exist, `iteration_log.csv` records the attempts,
`TIMING_CLOSURE_REPORT.md` exists with copy-pasteable fixes using ACTUAL design
names, and final WNS ≥ 0 and WHS ≥ 0 (or remaining violations are reported with
RTL/constraint recommendations).

---

## References

UG1788 is the orchestrating quick-reference; it points to the guides below per
stage (see the **Document Map** in [REFERENCE.md](REFERENCE.md); `vivado_doc_search` for version-exact syntax).

- **UG1788** — Versal Timing Closure Quick Reference (this flow's spine).
- **UG903** — *Using Constraints* — **canonical XDC reference**: timing constraints
  (clocks, I/O delay, exceptions) AND physical constraints (`LOC`, `BEL`, `PROHIBIT`,
  Pblocks/`resize_pblock`, `CONTAIN_ROUTING`). The definitive "how to write any
  constraint" guide.
- **UG912** — *Properties Reference Guide* — **canonical property/value reference**:
  every placement/timing property the skill sets (`IS_SOFT`, `USER_CLUSTER`,
  `USER_SLR_ASSIGNMENT`, `RLOC`/`RLOC_ORIGIN`, `MAX_FANOUT`/`MAX_FANOUT_MODE`,
  `GCLK_DESKEW`, `USER_CLOCK_ROOT`, `CLOCK_DELAY_GROUP`, `DONT_TOUCH`). Use to confirm
  exact spelling/legal values for the installed version.
- **UG1388** — Versal System Integration & Validation (SLR floorplan, exceptions).
- **UG1387** — Versal HW/IP/Platform Methodology (RTL: control sets, reset coding).
- **UG949** — UltraFast Design Methodology (general timing/floorplan guidance).
- **UG906** — Design Analysis & Closure (`report_qor_assessment/_suggestions`).
- **UG904** — Implementation (place/phys_opt/route directives, remap, control-set).
- **UG901** — Synthesis (retiming, `PerformanceOptimized`, `SRL_STYLE`).
- **AM003** — Versal Clocking Resources (clock buffers, GCLK deskew, RAM-induced GCLK
  jitter, `USER_RAM_AVERAGE_ACTIVITY`).
- **UG1344** — Versal Prime Series Libraries (XPM_CDC / async FIFO).

> **On the Quick Reference vs. the full picture:** UG1788 (the doc you start from) is a
> 1-page *navigator*, not the complete constraint catalog. It deliberately defers the
> "all constraints" detail to **UG903 (write any constraint) + UG912 (every property's
> legal values)**, with **AM003** for Versal clocking and **UG1387/UG1388** for the
> Versal-specific RTL/SLR/NoC layer. When in doubt about a constraint's exact syntax or
> legal values for the installed Vivado, query `vivado_doc_search` (it indexes all of
> the above) rather than relying on the Quick Reference alone.
