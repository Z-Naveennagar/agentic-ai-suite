---
name: opt-design-analysis
description: Analyze opt_design results for the switches/directive used, per-phase cell add/remove deltas, blocked or skipped optimizations, utilization and control-set QoR changes, and resource-increase root-cause — then provide actionable, goal-driven recommendations (directive/switch selection, constraint fixes, re-run strategies) to reduce area, logic levels, and control sets. Use when users review/summarize opt_design results, ask what it did or why optimizations were skipped, diagnose blocking properties, investigate a significant jump/decrease in logic/utilization/control sets, revisit opt_design after an implementation run missed timing, choose directives, interpret the Change Summary table, or need guidance on what to run next.
version: 5.0.0
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
# opt_design Analysis & Recommendations

> **What opt_design is — and is not.** `opt_design` is a **logic/area optimization** step
> (retarget, propconst, sweep, BUFG, SRL, remap, control-set merge). It is **not**
> timing-driven and does not optimize WNS. This skill reports **logic, area, and
> control-set QoR** only.
>
> **Downstream timing is orchestrator-provided context.** When this skill is invoked
> because an implementation run missed timing, the post-route WNS/TNS is **passed in** by
> the calling agent (see the optional `context` input in Step 0). This skill never computes
> or claims to improve timing — it uses that context only to (a) explain *why* the user is
> looking and (b) prioritize logic-QoR levers (area / logic-levels / control-set reduction)
> that may give the *next* implementation run a better starting point.

> **Why terminal grep, not read_file?** Vivado log files contain thousands of IP/XDC/IP_Flow
> warning lines from all phases. Using `read_file` or `grep_search` on `.log` files pulls
> these into context, wasting 10x+ tokens. Use `run_in_terminal` with `grep`/`sed` instead —
> it extracts only the relevant lines.

> **Why scope to opt_design section?** Vivado logs contain output from all phases (synthesis,
> link, opt_design, place, route, phys_opt). Several `[Opt 31-*]` IDs appear during
> link_design and place_design too (e.g., `[Opt 31-138]`, `[Opt 31-441]`). "Phase N" lines
> are shared across opt/place/route. Scope every grep to the opt_design section using:
> ```
> sed -n '/Command: opt_design/,/opt_design: Time/p' <logfile> | grep ...
> ```
> The markers are `Command: opt_design` (start) and `opt_design: Time` (end).
> Without this scoping, `[Opt 31-*]` IDs, "Phase", resource terms, and summary tables
> match synthesis/link/placement output and produce 50+ noisy lines.

**Prerequisites:** `opt_design` must have been run; implementation log (vivado.log, runme.log, or run.log) accessible.

> **Generate the log with `-debug_log`.** When *you* (or the orchestrator) run `opt_design`
> to produce the log this skill analyzes, add the **`-debug_log`** switch:
> ```tcl
> opt_design -debug_log                      ;# or: opt_design -directive <X> -debug_log
> ```
> Per UG904, `-debug_log` adds messages about logic reduced by constant/loadless removal and,
> crucially, **optimizations prevented by constraints** — the exact detail this skill's
> *blocked ledger* and *constraint-prevented* analysis depends on. Without it those messages
> are absent and the blocked-ledger will under-report. `opt_design` optimizes the in-memory
> design (a second run optimizes the first run's result), so `-debug_log` must run on a
> **freshly (re)synthesized design** — re-run `synth_design` / reload the post-synth DCP first.
> If you are only handed an existing log that lacks `-debug_log`, analyze it as-is and note
> in the report that blocked-optimization detail may be incomplete.

**Do NOT use this skill if:** synthesis is not complete, or you are analyzing placement/routing (use those skills instead).

**Full message catalog:** See [message-reference.md](message-reference.md) for the complete categorized list of all `[Opt 31-*]` messages with descriptions and resolutions.

---

## Efficiency Guidelines

- **Pass `session_id`** to every `vivado_execute` call when a Vivado session is active.
- **Write reports to file** using Vivado's `-file` flag — do not dump full report content in chat. Give a short summary only.
- **Read reports efficiently** — use `grep`, `sed`, or `awk` via terminal to extract specific sections from report files instead of reading entire files into context. Use `wc -l` + `head` to check size/structure first. Full `read_file` is fine only for small reports (<200 lines).
- **Do NOT** use `shell ls`, `shell find`, or `shell glob` to locate files.
- **Do NOT** use Vivado Tcl (`exec cat`, `open`, `read`) to read files. Use your file reader tool or `grep`/`sed` via terminal.
- **Do NOT** retry a failed Tcl command with different syntax. Report the error and stop or proceed to the next step.


## Workflow

Execute steps sequentially — Vivado's Tcl process is single-threaded, so parallel calls serialize and produce confusing interleaved output.

The workflow is incomplete until all three deliverables exist: `report_data.json`, `REPORT.md`, and `dashboard.html` (copied in Step 6). Write `report_data.json` and `REPORT.md` first, then copy the dashboard — invoke the write tool first, then give a short summary. Do not declare the analysis finished while any of the three is missing.

### Step 0: Resolve Inputs & Data Sources

Before analyzing, establish (a) what context the caller provided and (b) which design-data source is available. This determines how rich the analysis can be.

**0a — Optional `context` input (orchestrator-provided, read-only).**

In an agentic flow the calling agent may pass timing/goal context. Treat every field as **read-only** — never compute or override it:

```yaml
context:            # all fields optional
  impl_wns: -0.812          # ns, post-route worst negative slack (from the orchestrator)
  impl_tns: -45.3           # ns, total negative slack
  failing_clock: "clk_core" # optional, dominant failing clock
  user_goal: area | logic_levels | control_sets | runtime | clean   # optimization intent
```
- If `impl_wns < 0` is supplied → frame the report as a **post-timing-failure QoR review** and bias Step 4 recommendations toward area / logic-level / control-set reduction. **Do not** claim opt_design improves timing.
- If no context → run a standalone logic/area analysis (default).

**0b — Resolve the design-data source (checked in order; pick the first that applies):**

1. **Design already open in the active session?** Probe first — this is the common agentic case:
   ```tcl
   set _have_design [expr {[current_design -quiet] ne ""}]
   if {$_have_design} { puts "OPEN: [current_design] @ [get_property DESIGN_MODE [current_design]]" }
   ```
   If open → use it **read-only** (`report_utilization`, `report_control_sets` only). **Never** `open_checkpoint`/`close_design` on a session you did not open — that destroys the user's context.
2. **DCP path(s) provided / discoverable, and no design open?** Then `open_checkpoint <post_opt.dcp>` (and the post-synth DCP too if before/after deltas are wanted).
3. **Neither?** → **log-only mode** (original behavior). Use the log Change Summary for opt_design-attributable deltas; skip absolute utilization/control-set capture and note the limitation in the report.

**Source → available metrics:**

| Source | Before-state | After-state (absolute) | Notes |
|---|---|---|---|
| Design open (post-opt) | log Change Summary | open design `report_utilization` / `report_control_sets` | read-only; before-numbers come from the log |
| Two DCPs (post-synth + post-opt) | post-synth DCP | post-opt DCP | full before/after via `open_checkpoint` each |
| Log only | log Change Summary | — | per-phase deltas only |

Record the resolved mode in `report_data.json` → `metadata.analysis_mode` (`open_design` | `dcp` | `log_only`).

### Step 1: Extract Log Data via Terminal Grep

All commands below use a `sed -n` scope to extract only the opt_design section.

**Step 1a — Command + summary table + status (do this FIRST, usually sufficient):**
```bash
sed -n '/Command: opt_design/,/opt_design: Time/p' <logfile> | grep "Command: opt_design\|opt_design completed\|opt_design: Time" && echo "---" && sed -n '/Command: opt_design/,/opt_design: Time/p' <logfile> | grep -A 20 "Opt_design Change Summary"
```
The summary table has columns: Phase, #Cells Created, #Cells Removed, #Constrained Objects. **Stop here unless more detail is needed.**

**Step 1b — Per-phase detail (only if summary table is missing or user needs specifics):**
```bash
sed -n '/Command: opt_design/,/opt_design: Time/p' <logfile> | grep "\[Opt 31-389\]\|\[Opt 31-49\]\|\[Opt 31-194\]\|\[Opt 31-662\]\|\[Opt 31-1851\]\|\[Opt 31-1834\]\|\[Opt 31-1566\]\|\[Opt 31-138\]\|\[Opt 31-519\]\|\[Opt 31-1077\]\|\[Opt 31-1021\]"
```

**Step 1c — Phase timing (only if user asks about per-phase duration):**
```bash
sed -n '/Command: opt_design/,/opt_design: Time/p' <logfile> | grep -E "^Phase [0-9]+ " | grep -v "Phase [0-9]*\.[0-9]"
```

**Step 1c2 — Message tally (errors / critical warnings / warnings / infos):**

Compute the tally by RE-GREPPING the written log file, scoped to the opt_design
section. Do **not** report counts from messages you watched stream by while
driving Vivado — that live transcript also covers `synth_design`, the report
commands, and the whole-session summary, and will over-count. The counts must
come from the file span between `Command: opt_design` and `opt_design: Time`:
```bash
sed -n '/Command: opt_design/,/opt_design: Time/p' <logfile> | grep -cE "^ERROR:"
sed -n '/Command: opt_design/,/opt_design: Time/p' <logfile> | grep -cE "^CRITICAL WARNING:"
sed -n '/Command: opt_design/,/opt_design: Time/p' <logfile> | grep -cE "^WARNING:"
sed -n '/Command: opt_design/,/opt_design: Time/p' <logfile> | grep -cE "^INFO:"
```
Populate `message_tally` `{errors, critical_warnings, warnings, infos}` from
these four counts exactly.

**Step 1d — Device and context (only if needed for report framing):**

This is the one exception — device info is outside the opt_design section. Use tight patterns:
```bash
grep "set.*FPGA_PART\|link_design -part\|device 'xc" <logfile> | head -3
```
If an `fpga.stats` file exists alongside the log, prefer it for utilization data:
```bash
cat $(dirname <logfile>)/fpga.stats 2>/dev/null | head -20
```

**Grep mistakes to avoid** (each matches synthesis/link/placement lines, wasting 5-15K tokens):
- Do NOT `grep "Phase" <logfile>` — matches all placement/routing phases
- Do NOT `grep -E "Slice LUTs|Slice Registers|Block RAM|URAM|DSP" <logfile>` — matches synthesis inference warnings, URAM cascade messages, parameter bindings (50+ noisy lines)
- Do NOT `grep -E "^Device|^Part|LUT |Register " <logfile>` — matches MUX_RATIO parameters and BRAM/SRL file paths
- Do NOT `grep "BUFG" <logfile>` — matches synthesis BUFG_GT messages
- Do NOT `grep -i "utilization" <logfile>` — matches Tcl comments and config lines
- Do NOT `grep "remap" <logfile>` — matches synthesis remap phase
- Do NOT grep `[Opt 31-441]` unless asked — large SSI designs emit 30+ of these during link_design

**Phase numbers vary** by opt_design sub-commands. Always match by phase name (Retarget, Constant propagation, Sweep, etc.), not number.

**Note on Phase 1 Initialization:** This phase includes Core Generation (MIG/XPHY IP synthesis) and can contain **300+ lines** of IP_Flow warnings, XDC parsing, and DRC messages. Do NOT try to read or grep inside it — it has no useful optimization data.

### Message ID Reference

| ID | Meaning | Self-scoping? |
|---|---|---|
| `[Opt 31-389]` | Per-phase cells created/removed | Yes |
| `[Opt 31-49]` | Retarget count | Yes |
| `[Opt 31-1021]` | Constrained objects blocking optimization | Yes |
| `[Opt 31-194]` | BUFG inserted (with load count) | Yes |
| `[Opt 31-662]` | BUFG phase summary | Yes |
| `[Opt 31-1077]` | CLOCK_LOW_FANOUT BUFG insertions | Yes |
| `[Opt 31-1851]` | Loadless carry chains removed | Yes |
| `[Opt 31-1834]` | Carry chain transformations | Yes |
| `[Opt 31-1566]` | Inverters pulled | Yes |
| `[Opt 31-138]` | Inverters pushed | **No** — also in link_design, place_design |
| `[Opt 31-519]` | Carry remap threshold | Yes |
| `[Opt 31-441]` | BUFG_GT_SYNC insertion (skip) | **No** — 30+ in link_design for SSI |
| `[Opt 31-422]` | SSI partition info (skip) | **No** — 100+ in link_design for SSI |
| `[Opt 31-81]` | set_logic constraint on already-driven pin (CRITICAL WARNING) | Yes |
| `[Opt 31-83]` | Series input buffer detected (parallel IBUFs) | Yes |
| `[Opt 31-217]` | Batch mode enabled | Yes |
| `[Opt 31-282]` | OptMgr initialization | Yes |
| `[Opt 31-288]` | MLO preprocessing start | Yes |
| `[Opt 31-289]` | MLO preprocessing running | Yes |
| `[Opt 31-300]`–`[Opt 31-302]` | Phase completion stats (sub-phase level) | Yes |
| `[Opt 31-1005]` | MUXF optimization candidate count | Yes |
| `[Opt 31-1064]` | MUXF optimization result | Yes |
| `[Opt 31-1384]`–`[Opt 31-1389]` | MUXF per-type stats (MUXF7/F8/F9 created/removed) | Yes |
| `[Opt 31-1561]` | Inverter propagation detail | Yes |
| `[Opt 31-2042]` | BRAM memory optimization action | Yes |
| `[Opt 31-2117]`–`[Opt 31-2118]` | Resynth/remap optimization stats | Yes |
| `[Opt 31-2244]` | LUT decomposition stats | Yes |
| `[Opt 31-1]` | Pin not connected to top-level port (ERROR) | Yes |
| `[Opt 31-2]` | Pin missing connection — no driver (ERROR) | Yes |
| `[Opt 31-66]` | Driverless net — load cell won't work (ERROR) | Yes |
| `[Opt 31-67]` | Cell missing input after trimming (ERROR) | Yes |
| `[Opt 31-78]` | S and R both active on cell (CRIT_WARN) | Yes |
| `[Opt 31-111]` | DONT_TOUCH blocking ZHOLD_DELAY (CRIT_WARN) | Yes |
| `[Opt 31-137]` | Retarget blocked — loads don't share CE/CLR (ERROR) | Yes |
| `[Opt 31-198]` | CARRY4 CI+CYINIT both active (ERROR) | Yes |
| `[Opt 31-214]`–`[Opt 31-215]` | BUFG_GT CE/CLR mismatch (ERROR) | Yes |
| `[Opt 31-232]`–`[Opt 31-233]` | MARK_DEBUG net optimized (WARNING) | Yes |
| `[Opt 31-236]` | Primitives driven by blackboxes (ERROR) | Yes |
| `[Opt 31-257]`–`[Opt 31-261]` | DONT_TOUCH blocking optimization (ERROR) | Yes |
| `[Opt 31-317]` | Failed BUFG/BUFGCE insertion (CRIT_WARN) | Yes |
| `[Opt 31-350]`–`[Opt 31-351]` | Cell not supported for architecture (CRIT_WARN) | Yes |
| `[Opt 31-444]`–`[Opt 31-463]` | BUFMR/BUFR retarget blocked (ERROR) | Yes |
| `[Opt 31-512]`–`[Opt 31-520]` | Carry remap issues (WARNING) | Yes |
| `[Opt 31-1078]`–`[Opt 31-1080]` | Versal migration errors (ERROR) | Yes |
| `[Opt 31-1091]` | MBUFG conversion blocked (ERROR) | Yes |
| `[Opt 31-1557]` | Async flop — control set reduction unsupported (WARNING) | Yes |
| `[Opt 31-1842]`–`[Opt 31-1845]` | Control set reduction failures (WARNING) | Yes |

**"Self-scoping: Yes"** means the ID appears only during opt_design — safe to grep across the full log.
**"Self-scoping: No"** means the ID also appears in other phases — **must** use `sed -n` scoping.

---

### Step 1e — ERRORs, CRITICAL WARNINGs, and actionable WARNINGs:
```bash
# Errors and critical warnings (always check)
sed -n '/Command: opt_design/,/opt_design: Time/p' <logfile> | grep -iE "ERROR.*Opt 31|CRITICAL WARNING.*Opt 31"
```
```bash
# Connectivity & DRC errors
sed -n '/Command: opt_design/,/opt_design: Time/p' <logfile> | grep -E "\[Opt 31-(1|2|7|37|65|66|67|78|82|110|198|236|290|303|304|305|349|377|430|443|504)\]"
```
```bash
# DONT_TOUCH/constraint blocking
sed -n '/Command: opt_design/,/opt_design: Time/p' <logfile> | grep -E "\[Opt 31-(111|257|258|259|260|261|444|445|446|447|448|456|457|458|459|460)\]"
```
```bash
# BUFG/clock, device, and actionable warnings
sed -n '/Command: opt_design/,/opt_design: Time/p' <logfile> | grep -E "\[Opt 31-(137|214|215|317|1091|350|351|1012|1078|1079|1080|232|233|278|295|313|512|513|516|520|1090|1115|1556|1557|1842|1843|1844|1845|2028|2386|2387)\]"
```
```bash
# Previously covered IDs (stats, phases, MUXFs, BRAM, resynth)
sed -n '/Command: opt_design/,/opt_design: Time/p' <logfile> | grep -E "\[Opt 31-(81|83|1005|1064|1384|2042|2117|2244)\]"
```

Key patterns:
- `[Opt 31-1]`/`[Opt 31-2]`/`[Opt 31-66]`/`[Opt 31-67]` = **Connectivity errors** — pins/nets missing drivers. Fix RTL connectivity.
- `[Opt 31-257]`–`[Opt 31-261]` = **DONT_TOUCH blocking** — cells cannot be optimized/removed. Remove DONT_TOUCH or accept.
- `[Opt 31-444]`–`[Opt 31-463]` = **BUFMR/BUFR retarget blocked** — DONT_TOUCH or inversions preventing clock buffer optimization.
- `[Opt 31-214]`/`[Opt 31-215]` = **BUFG_GT CE/CLR mismatch** — all BUFG_GTs from same GT source must share CE/CLR.
- `[Opt 31-137]` = **Retarget blocked** — loads don't share CE/CLR. Fix RTL.
- `[Opt 31-1091]` = **MBUFG conversion blocked** — review MBUFG_GROUP properties and constraints.
- `[Opt 31-78]` = S and R both active on cell — illegal, fix connectivity.
- `[Opt 31-198]` = CARRY4 CI+CYINIT both active — fix design.
- `[Opt 31-350]`/`[Opt 31-351]` = Cell not supported for architecture — replace primitive.
- `[Opt 31-1078]`–`[Opt 31-1080]` = Versal migration errors — attribute/pin not supported.
- `[Opt 31-232]`/`[Opt 31-233]` = MARK_DEBUG nets optimized — add DONT_TOUCH before opt_design.
- `[Opt 31-512]`–`[Opt 31-520]` = Carry remap blocked/skipped — check CARRY_REMAP properties.
- `[Opt 31-1557]`/`[Opt 31-1842]`–`[Opt 31-1845]` = Control set reduction failures.
- `[Opt 31-81]` CRITICAL WARNING = `set_logic_one`/`set_logic_zero` on an already-driven pin. Remove the constraint.
- `[Opt 31-83]` = Series input buffers detected. Fix RTL to avoid chained I/O buffers.
- `[Opt 31-2042]` = BRAM memory optimization (port mapping, power opt actions).
- `[Opt 31-2117]`–`[Opt 31-2118]` = Resynth/remap optimization counts.

> **Full message catalog with resolutions:** See [message-reference.md](message-reference.md) for all categorized messages.

---

### Step 1f: Switch/Directive Tracking & Phase Reconciliation

Capture **exactly what was requested** versus **what actually ran** — this answers "which switches/directive did this run use?" and "did any switch do nothing?".

**1f-1 — Capture the full command line** (the `Command: opt_design ...` line from Step 1a). Parse it into:
- `directive` (e.g. `Explore`, `ExploreArea`, `RuntimeOptimized`, or `Default` if none)
- explicit `switches[]` (e.g. `-control_set_merge`, `-merge_equivalent_drivers`, `-remap`, `-bram_power_opt`, `-hier_fanout_limit <N>`, `-resynth_area`, `-debug_log`)

**1f-2 — Expand the directive** into the optimizations it is expected to enable (use the Directives Reference table in [report-template.md](report-template.md)). Example: `Explore` → retarget, propconst, sweep, BUFG, SRL, MBUFG (Versal); `ExploreArea` → adds Resynthesis (area); `ExploreWithRemap` → adds aggressive remap.

**1f-3 — Reconcile expected vs observed.** Cross-check each expected optimization (from directive + explicit switches) against the phases actually seen in the log (Step 1a/1b). For each, classify:

| Reconciliation outcome | Meaning | Action |
|---|---|---|
| `ran_effective` | phase ran and changed cells (created/removed > 0) | normal |
| `ran_no_effect` | phase ran but 0 cells changed | flag if a switch was *explicitly* requested — the switch did nothing on this netlist |
| `expected_but_absent` | directive/switch implies it, but no phase line found | investigate (blocked, unsupported for arch, or nothing to do) |
| `blocked` | phase present but a `[Opt 31-*]` blocking message fired | feed into Step 1g ledger |

Populate `switch_reconciliation[]` in `report_data.json`. **A switch that produced `ran_no_effect` is actionable feedback** — e.g. `-control_set_merge` with 0 merges means the design has no mergeable control sets; `-remap` with 0 LUT change means remap found no improvement.

### Step 1g: Blocked / Skipped Optimization Ledger

Build an explicit ledger of optimizations that were **prevented**, and why. This directly answers "were any optimizations blocked or skipped?".

For each blocking message found in Step 1e (`[Opt 31-257..261]` DONT_TOUCH, `[Opt 31-232/233]` MARK_DEBUG, `[Opt 31-444..463]` BUFMR/BUFR, `[Opt 31-512..520]` carry remap, `[Opt 31-1557/1842..1845]` control-set, architecture/Versal-unsupported, feedback-loop), record one ledger row:

```
optimization | blocked_by (DONT_TOUCH|MARK_DEBUG|constraint|architecture|feedback_loop|no_candidate)
            | object (cell/net path) | message_id | recoverable? (yes/no) | suggested_fix
```

If `-debug_log` was used, also mine the debug log for objects that blocked optimization (it lists constrained objects explicitly). Populate `blocked_ledger[]` in `report_data.json`. A `recoverable=yes` row (e.g. a non-critical DONT_TOUCH) becomes an Immediate-Fix recommendation in Step 4A.

---

### Step 2: Query DONT_TOUCH / MARK_DEBUG (if Vivado design is open)

Skip this step if only analyzing a log file without an open design.

```tcl
puts "DONT_TOUCH cells: [llength [get_cells -hier -filter {DONT_TOUCH == TRUE}]]"
puts "DONT_TOUCH nets: [llength [get_nets -hier -filter {DONT_TOUCH == TRUE}]]"
puts "MARK_DEBUG nets: [llength [get_nets -hier -filter {MARK_DEBUG == TRUE}]]"
puts "DONT_TOUCH hierarchical: [llength [get_cells -hier -filter {DONT_TOUCH == TRUE && IS_PRIMITIVE == FALSE}]]"
```

---

### Step 2b: Capture Utilization & Control-Set QoR (if a design is reachable)

Run only when Step 0b resolved to `open_design` or `dcp` mode. **Skip in log-only mode** (note the limitation in the report). Use **read-only** report commands — never modify an already-open session.

This is the data that detects a *significant jump or decrease in logic, utilization, or control sets* — the primary reason a user opens this skill after a missed-timing implementation run.

```tcl
# Absolute current (after-opt) resource usage — write to file, parse with grep/sed
report_utilization -file vivado_agentic_ai_reports/opt-design-analysis/util_post_opt.rpt
# Control sets — the count and the unique-control-set breakdown
report_control_sets -verbose -file vivado_agentic_ai_reports/opt-design-analysis/control_sets.rpt
puts "UNIQUE_CONTROL_SETS: [llength [get_property CONTROL_SETS [current_design]]]"
```

**Deltas:**
- *opt_design-attributable delta* always comes from the log Change Summary (per-phase cells created/removed) — valid in every mode.
- *Absolute before/after* utilization/control-set deltas require both post-synth and post-opt data: available only in two-DCP mode. In open-design mode, report after-state absolutes + the log-derived delta, and state that pre-opt absolutes were not captured.

**Significant-change thresholds** (flag in the report when exceeded):

| Metric | Flag threshold |
|---|---|
| LUT / FF / CARRY / MUXF | Δ > 5% of post-synth count |
| Control sets | Δ > 5% **or** absolute count > 5000 |
| Net cell change | net increase > 2% (triggers Step 2c root-cause) |
| Any resource | crossing a device-utilization band (e.g. <80% → >90%) |

### Step 2c: Resource-Increase Root-Cause (only if net cell change > 0)

When opt_design *increased* cell count, attribute the increase so the report explains **why logic went up** (not just that it did). Map the rise to its source phase using the per-phase Change Summary + phase-detail IDs:

| Source | Signature | Logic-levels impact |
|---|---|---|
| BUFG/clock insertion | `[Opt 31-194]`, `[Opt 31-1077]`, BUFG phase created > 0 | low (clocking) |
| HFN split-load / driver replication | split-load phase created > 0, `-hier_fanout_limit` low | neutral (fanout relief) |
| LUT decomposition | `[Opt 31-2244]`, LUT6→LUT5+LUT5 | **adds a logic level** — note for timing context |
| Remap / aggressive remap | `[Opt 31-2117/2118]`, remap phase | can add or remove levels |
| MUXF restructuring | `[Opt 31-1384..1389]` | usually neutral |

Flag any **logic-level-adding** attribution prominently when `context.impl_wns < 0` — it is the legitimate link between an opt_design action and a downstream timing failure.

---

### Step 3: Assess BRAM Power Optimization (if Vivado design is open)

Skip if `-bram_power_opt` was not in the opt_design command and user did not ask.

```tcl
set brams [get_cells -hier -filter {PRIMITIVE_TYPE =~ BMEM.*}]
puts "Total BRAMs: [llength $brams]"
foreach bram $brams {
    if {[get_property WRITE_MODE_A $bram] eq "NO_CHANGE" || [get_property WRITE_MODE_B $bram] eq "NO_CHANGE"} {
        puts "Power-optimized: $bram"
    }
}
```

---

### Step 4: Generate Recommendations

Evaluate each category below. Include applicable items in REPORT.md under the matching tier.

#### 4A — Constraint & Property Fixes

The skill's primary actionable output: copy-pasteable XDC commands based on what the analysis found.

**DONT_TOUCH / MARK_DEBUG blocking optimization:**
If `#Constrained Objects` > 0 in the summary table:
```tcl
# List DONT_TOUCH cells on timing-critical paths
foreach c [get_cells -hier -filter {DONT_TOUCH==TRUE}] {
  set paths [get_timing_paths -through [get_pins -of $c] -max_paths 1 -quiet]
  if {[llength $paths] > 0} {
    set slack [get_property SLACK [lindex $paths 0]]
    if {$slack < 0} { puts "CRITICAL DT: $c slack=$slack" }
  }
}
```
For each cell with negative slack, provide specific XDC fix:
`reset_property DONT_TOUCH [get_cells <actual_cell_path>]`
If set by MARK_DEBUG: `set_property DONT_TOUCH FALSE [get_nets <net>]` (per-net) or `config_flows -mark_debug disable` (global).

#### 4B — Findings & Diagnosis

Report what the log analysis reveals — the analysis skill's unique diagnostic value.

**Effectiveness assessment** (from Change Summary table):
- `#Cells Removed` < 1% of total → "Design already clean — sweep confirms minimal dead logic."
- `#Cells Removed` > 5% of total → "Significant cleanup achieved."
- `#Cells Created` >> `#Cells Removed` (net increase) → "Net cell increase — replication or BUFG insertion dominated."
- Report per-phase breakdown: which phases contributed most, which had zero effect.

**Error/warning triage:**
- For each error/critical warning from Step 1e, report with fix guidance from [message-reference.md](message-reference.md).
- Flag connectivity errors (`[Opt 31-1]`, `[Opt 31-2]`, `[Opt 31-66]`, `[Opt 31-67]`) as blocking — user must fix RTL before re-running.

#### 4C — Next-Run Suggestions (goal-driven, logic/area QoR — NOT timing optimization)

Commands the user can try in the next opt_design iteration. These run on the post-synth
netlist without requiring placement. **opt_design optimizes logic/area/control-sets, not
WNS** — present these as levers that *reduce area, logic levels, or control sets* so the
*next* full implementation has a better starting point. Never describe them as "timing
optimization."

When `context.user_goal` is supplied, rank suggestions for that goal first:

| `user_goal` | Prioritize | Levers |
|---|---|---|
| `area` / failed timing on utilization-heavy design | shrink the netlist | `-remap`, `ExploreArea`, `-resynth_area`, `-merge_equivalent_drivers` |
| `logic_levels` (paths too deep) | fewer LUT levels | re-run **without** aggressive remap/decomposition on critical hierarchy; protect critical paths with DONT_TOUCH; review `-remap` effect from Step 2c |
| `control_sets` | reduce packing pressure | `-control_set_merge` |
| `runtime` | faster opt | `RuntimeOptimized` directive |
| `clean` (default) | dead-logic removal | second `opt_design` pass, `-sweep`, `-propconst` |

| Condition (from analysis) | Suggestion | Rationale |
|-----------|------------|-----------|
| >5000 control sets (Step 2b) | `opt_design -control_set_merge` | Reduces packing pressure → easier placement |
| Net cell increase from replication (Step 2c) | `opt_design -merge_equivalent_drivers` | Merges redundant driver copies → smaller netlist |
| High LUT utilization, `-remap` not used | `opt_design -remap` | Typically 1-3% LUT reduction |
| Utilization-bound + area goal | `opt_design -directive ExploreArea` | Resynthesis-for-area pass |
| Logic-level-adding decomposition flagged (Step 2c) + WNS<0 | re-run without aggressive remap on critical paths | Avoids extra logic level on failing paths |
| BRAMs present, `-bram_power_opt` not used | `opt_design -bram_power_opt` | Power optimization on BRAMs |
| Switch reported `ran_no_effect` (Step 1f) | drop that switch next run | It did nothing on this netlist — saves runtime |
| Need verbose diagnostics | `opt_design -debug_log` | Logs which objects block optimization (feeds Step 1g) |

> **Honesty rule:** if the design missed timing but opt_design already removed dead logic
> and no area/control-set lever applies, say so — do **not** invent an opt_design "fix" for
> a timing problem that belongs to placement/routing or the `versal-timing-closure` skill.

### Step 5: Write Report Files

Write both `report_data.json` and `REPORT.md` to `vivado_agentic_ai_reports/opt-design-analysis/`. Read [report-template.md](report-template.md) for the JSON schema and REPORT.md template.

**Populating Recommendations** — this is what makes the report actionable:
- For each Step 4 condition (4A–4C) that fired, create a recommendation entry.
- In `report_data.json`: populate the `recommendations[]` array. Include `tcl_commands` with the actual Tcl commands from Step 4 using real cell/net names from the design.
- In `REPORT.md`: place each recommendation under the appropriate tier:
  - **Immediate Fixes** → constraint/property changes with copy-pasteable XDC (4A)
  - **Findings & Diagnosis** → effectiveness assessment, error/warning triage (4B)
  - **Next-Run Suggestions** → opt_design commands for future iterations (4C)
  - **Accept / Waive** → MARK_DEBUG or intentional constraints
- Every recommendation should contain a fenced `tcl` code block with a complete, copy-pasteable command so the user can paste it directly into the Vivado Tcl console.
- If no Step 4 conditions fired, write: "No recommendations — all phases completed successfully."

**Populating Errors & Warnings:**
- For each actionable message found in Step 1e, create an entry in `errors_warnings[]` (JSON) and the Errors & Warnings table (REPORT.md).
- The `agent_action` field should describe what the agent did or recommends — referencing the action from [message-reference.md](message-reference.md).

### Step 6: Copy Dashboard

Copy the pre-built dashboard template to the output directory so users can open it in a browser:

```tcl
file copy -force [file join $skill_dir DASHBOARD_TEMPLATE.html] vivado_agentic_ai_reports/opt-design-analysis/dashboard.html
```

The `DASHBOARD_TEMPLATE.html` file lives alongside this SKILL.md in the skill folder. The dashboard is a self-contained HTML file that loads `report_data.json` via `fetch()` at runtime — no generation required, zero token cost.

**Tell the user:** "Open `vivado_agentic_ai_reports/opt-design-analysis/dashboard.html` in a browser to see interactive charts."

---


## Design-Specific Fix Rules

Reports with generic placeholders like `clk_a` or `<net>` are not useful — users can't paste them into Vivado. Extract actual names from the design before generating the report.

| Rule | ❌ WRONG | ✅ CORRECT |
|------|----------|------------|
| Clock names | `clk_a`, `clk_b` | `HOSTCLK`, `GTX_CLK` |
| Cell paths | `*_sync_reg*` | `core_0/host_*_sync_reg*` |
| MMCM pins | `mmcm/CLKOUT0` | `ios_0/mmcm_0/CLKOUT2` |
| Periods | `<period>` | `12.800` |
| Signal names | `signal` | `host_enable` |
| Net names | `<net>` | `core_0/data_valid` |

Extract actual names from Vivado reports/commands **before** generating the REPORT.md. Never use template placeholders in the final output.

---

## Error Handling

| Error | Action |
|---|---|
| No design open | "Open with `open_run impl_1`" |
| Log file not found | Ask user for path to vivado.log or runme.log |
| No opt_design in log | "opt_design has not been run. Run it first." |

---

## Output Files & Templates

See [report-template.md](report-template.md) for the report_data.json schema, REPORT.md template, assessment scoring, optimization phase reference, common issues, and directives reference.
