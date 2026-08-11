<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

---
name: adaptive-physopt-overconstrain
description: 'Runs selective clock-uncertainty over-constraint and iterative AggressiveExplore phys_opt on a post-place Vivado DCP. Use when recovering WNS/TNS without changing clock periods. Produces per-iteration QoR comparisons and the best checkpoint recommendation.'
argument-hint: '<post_place.dcp> [conservative|balanced|aggressive] [max_iter]'
---

# Adaptive Post-Place PhysOpt Over-Constrain

Improve post-placement QoR by applying controlled, **selective** over-constraints
to a post-place DCP, running multiple physically-aware `phys_opt_design` passes,
analyzing timing deltas after each pass, and stopping when improvement converges.

## When to Use
- You have a post-place (or routed) Vivado checkpoint with setup timing violations.
- You want to recover WNS/TNS without editing the actual clock period.
- You want a deterministic, congestion-aware, multi-pass phys-opt exploration.

## Inputs
- Post-place DCP (required)
- Aggressiveness level: `conservative` | `balanced` (default) | `aggressive`
- Optional: explicit clock list (default = auto-detect violating clocks)
- Optional: max iterations (default 6)

## Key Principle — DO NOT over-constrain all clocks
Over-constrain **only** the clocks that contribute to setup violations. First run
baseline timing, identify clocks with negative WNS / significant TNS / many failing
endpoints, and apply uncertainty to *those clocks only*. Over-constraining is done
through **clock uncertainty**, never by modifying the clock period.

## Procedure

Source the automation in a Vivado batch (or interactive) session:

```
vivado -mode batch -source ./scripts/adaptive_physopt.tcl \
       -tclargs -dcp <post_place.dcp> -mode balanced -max_iter 6
```

Script arguments:

| Arg | Default | Meaning |
|-----|---------|---------|
| `-dcp <path>` | (required) | post-place checkpoint |
| `-mode <m>` | `balanced` | `conservative` \| `balanced` \| `aggressive` |
| `-clocks {c1 c2}` | auto | explicit clocks; default = auto-detect violating |
| `-max_iter <N>` | `6` | max AggressiveExplore passes |
| `-out_dir <dir>` | `./physopt_run` | output directory |

### Phase 1 — Baseline Characterization
1. `open_checkpoint <post_place.dcp>`
2. `report_timing_summary -file baseline_timing.rpt`
3. Capture baseline **WNS**, **TNS**, **failing endpoints**, and **congestion**
   (`report_design_analysis -congestion`; level 0–7, high if ≥ 5).

### Phase 2 — Selective Dynamic Over-Constraining
1. Identify violating clocks (per-clock WNS < 0).
2. Compute setup uncertainty as a percentage of each clock's own period:

   | Mode | Setup uncertainty |
   |------|-------------------|
   | conservative | 2% of clock period |
   | balanced (default) | 5% of clock period |
   | aggressive | 8–10% of clock period |

3. Apply uncertainty **only** to violating clocks:
   `set_clock_uncertainty -setup <value> [get_clocks <violating_clock>]`

**Guardrails**
- Never exceed 10% tightening on any clock.
- If baseline congestion is high (level ≥ 5), do **not** apply any over-constraining.
- If congestion rises significantly during optimization, remove the temporary
  uncertainty and stop iterating.
- High-congestion designs run a **single** phys-opt pass only (no multi-pass loop).

### Phase 3 — Multi-Pass PhysOpt Exploration
Use a single proven directive (`AggressiveExplore`) — no parallel directive search.
For each iteration:
```
phys_opt_design -directive AggressiveExplore
write_checkpoint iteration_<N>.dcp
report_timing_summary -file iteration_<N>_timing.rpt
```
Continue additional `AggressiveExplore` passes **while measurable improvement** is
observed. After the best candidate is chosen, remove the temporary over-constraint:
```
set_clock_uncertainty -setup 0.0 [get_clocks <violating_clock>]
```
so final signoff uses the original constraints.

### Phase 4 — Adaptive Decision Engine
Score each candidate:
```
Score = 0.5 * WNS_improvement
      + 0.3 * TNS_improvement
      + 0.2 * Endpoint_reduction
```
Apply penalties for: increased congestion, excessive buffering (cell-count growth),
and runtime explosion. Select the best-scoring candidate.

### Phase 5 — Iterative Refinement
Continue with **another** `AggressiveExplore` round (same directive, no switching) if:
```
WNS improvement > 20 ps  OR  TNS improvement > 5%
```
Terminate when:
```
ΔWNS < 5 ps  AND  ΔTNS < 1%
```
…or when convergence / excessive congestion is reached.

## Outputs
Written to the run output directory (default `./physopt_run/`):
- Best optimized DCP (`best.dcp`)
- `baseline_timing.rpt` and per-iteration timing summaries
- `physopt_comparison.rpt` — comparison table of all passes (WNS/TNS/eps/cong/score)
- `physopt_summary.txt` — recommended final directive sequence + decisions log

## Files
- Automation: [scripts/adaptive_physopt.tcl](./scripts/adaptive_physopt.tcl)

## Expected Benefits
- Improved WNS/TNS recovery after placement
- More deterministic phys-opt convergence
- Reduced manual experimentation; automatic best-candidate selection
- Reusable across designs and technology nodes
