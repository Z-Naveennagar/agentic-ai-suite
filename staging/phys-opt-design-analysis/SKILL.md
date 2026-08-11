---
name: phys-opt-design-analysis
description: >-
  Analyze phys_opt_design log for replication counts, retiming moves,
  hold-fix LUT1 insertions, per-iteration WNS/TNS trends, and blocking
  properties that prevent physical optimization — then provide actionable
  recommendations (directive selection, additional passes, constraint fixes).
  Use when users want to understand phys_opt results, diagnose ineffective
  optimization passes, choose better directives, or need guidance on what
  to run next.
version: 3.0.0
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
# phys_opt_design Analysis & Recommendations

> **Why terminal grep, not read_file?** Vivado log files contain thousands of IP/XDC/IP_Flow
> warning lines from all phases. Using `read_file` or `grep_search` on `.log` files pulls
> these into context, wasting 10x+ tokens. Use `run_in_terminal` with `grep`/`sed` instead.

> **Why scope to phys_opt section?** Vivado logs contain output from all phases (synthesis,
> link, opt_design, place, route, phys_opt). The phys_opt_design section is delimited by
> `Command: phys_opt_design` (start) and `phys_opt_design completed` or
> `phys_opt_design: Time` (end). Scope every grep using:
> ```
> sed -n '/Command: phys_opt_design/,/phys_opt_design.*Time/p' <logfile> | grep ...
> ```
> Without this, `[Physopt 32-*]` messages from post-route phys_opt contaminate results.

**Prerequisites:** `phys_opt_design` must have been run; implementation log accessible.

**Do NOT use this skill if:** design is not placed, or you are analyzing synthesis/opt_design/routing (use those skills instead).

**Full message catalog:** See [message-reference.md](message-reference.md) for the complete categorized list of all `[Physopt 32-*]` messages with descriptions and resolutions.

---

## Efficiency Guidelines

- **Pass `session_id`** to every `vivado_execute` call when a Vivado session is active.
- **Write reports to file** using Vivado's `-file` flag — do not dump full report content in chat. Give a short summary only.
- **Read reports efficiently** — use `grep`, `sed`, or `awk` via terminal to extract specific sections from report files instead of reading entire files into context. Use `wc -l` + `head` to check size/structure first. Full `read_file` is fine only for small reports (<200 lines).
- **Do NOT** use `shell ls`, `shell find`, or `shell glob` to locate files.
- **Do NOT** use Vivado Tcl (`exec cat`, `open`, `read`) to read files. Use your file reader tool or `grep`/`sed` via terminal.
- **Do NOT** retry a failed Tcl command with different syntax. Report the error and stop or proceed to the next step.

---

## Workflow

Execute steps sequentially — Vivado's Tcl process is single-threaded, so parallel calls serialize and produce confusing interleaved output.

The workflow is incomplete until both REPORT.md and report_data.json exist. Write both files before narrating or summarizing — invoke the write tool first, then give a short summary.

### Step 1: Extract Log Data via Terminal Grep

All commands below use a `sed -n` scope to extract only the phys_opt_design section.

**Step 1a — Command + timing summary + status (do this FIRST):**
```bash
sed -n '/Command: phys_opt_design/,/phys_opt_design.*Time/p' <logfile> | grep -E "Command: phys_opt|phys_opt_design completed|phys_opt_design.*Time|Physopt 32-668|Physopt 32-669|Physopt 32-603|Physopt 32-619"
```
Key IDs:
- `[Physopt 32-668]` = Current timing summary (WNS/TNS/WHS/THS) — appears at start and between iterations
- `[Physopt 32-669]` = Post-optimization timing summary (with WHS/THS)
- `[Physopt 32-603]` = Post-optimization timing summary (WNS/TNS only)
- `[Physopt 32-619]` = Estimated timing summary

**Step 1b — Per-phase optimization counts (only if summary insufficient):**
```bash
sed -n '/Command: phys_opt_design/,/phys_opt_design.*Time/p' <logfile> | grep -E "Physopt 32-(232|661|665|666|608|775|234|76|1032|1030|1033|457|527|942|1306|1323|1332|1395|1398|1402|1411|1488|1489)"
```

**Step 1c — Blocking/skipped messages:**
```bash
sed -n '/Command: phys_opt_design/,/phys_opt_design.*Time/p' <logfile> | grep -E "Physopt 32-(745|670|846|526|456|677|65|68|69|943|949|1307|1308|1334|1401|1123|960|571|607|1031|1359|1360)"
```

**Step 1d — Directive and threading info:**
```bash
sed -n '/Command: phys_opt_design/,/phys_opt_design.*Time/p' <logfile> | grep -E "Vivado_Tcl 4-(137|232|383|521|1435)|Physopt 32-721"
```
- `[Vivado_Tcl 4-137]` = Directive used
- `[Vivado_Tcl 4-383]` = WNS >= 0, all physical synthesis skipped
- `[Vivado_Tcl 4-232]` = No setup violation, netlist not modified
- `[Vivado_Tcl 4-521]` = iPhys_opt summary (changes tried/applied)
- `[Physopt 32-721]` = Multithreading CPU count

**Grep mistakes to avoid** (each matches synthesis/link/placement lines, wasting 5-15K tokens):
- Do NOT `grep "Phase" <logfile>` — matches all placement/routing phases
- Do NOT `grep "WNS\|TNS" <logfile>` — matches route/place timing summaries
- Do NOT `grep "replication\|replicated" <logfile>` — matches synthesis and place log lines
- Do NOT `grep "Physopt" <logfile>` without scoping — phys_opt messages appear in post-route phys_opt too

---

### Message ID Reference

| ID | Meaning | Category |
|---|---|---|
| `[Physopt 32-668]` | Current timing summary (WNS/TNS/WHS/THS) | Timing |
| `[Physopt 32-669]` | Post-optimization timing summary (full) | Timing |
| `[Physopt 32-603]` | Post-optimization timing summary (setup only) | Timing |
| `[Physopt 32-619]` | Estimated timing summary | Timing |
| `[Physopt 32-721]` | Multithreading CPU count | Config |
| `[Physopt 32-715]` | Route finalization performed | Config |
| `[Physopt 32-232]` | Net optimization result (created N instances) | Replication |
| `[Physopt 32-661]` | Net optimization result (re-placed N instances) | Replication |
| `[Physopt 32-569]` | Replicated N time(s), created N instances and N nets | Replication |
| `[Physopt 32-571]` | Net not replicated (explains why) | Replication |
| `[Physopt 32-76]` | Fanout optimization candidates identified | Fanout |
| `[Physopt 32-65]` | No nets found for high-fanout optimization | Fanout |
| `[Physopt 32-1353]` | Replicated due to FORCE_MAX_FANOUT/MAX_FANOUT_MODE | Fanout |
| `[Physopt 32-942]` | Forward retiming candidates found | Retiming |
| `[Physopt 32-943]` | No backward retiming candidates | Retiming |
| `[Physopt 32-952]` | Path group WNS improved (retiming) | Retiming |
| `[Physopt 32-953]` | Path group WNS did not improve | Retiming |
| `[Physopt 32-735]` | Net optimization improves timing | Retiming |
| `[Physopt 32-736]` | Net has fanout of one — skip critical-cell opt | Retiming |
| `[Physopt 32-847]` | Processed cell, N register(s) pushed in pipeline | Retiming |
| `[Physopt 32-1306]` | Interconnect retiming candidates identified | Interconnect Retime |
| `[Physopt 32-1307]` | No pins for interconnect retiming | Interconnect Retime |
| `[Physopt 32-1321]` | Processed net, no improvement for load pin | Interconnect Retime |
| `[Physopt 32-1324]` | Optimized net driver forward for load pin | Interconnect Retime |
| `[Physopt 32-1337]` | No improvement through LUT optimization | LUT Opt |
| `[Physopt 32-1332]` | LUT optimization candidates identified | LUT Opt |
| `[Physopt 32-1333]` | No candidate for LUT cascade optimization | LUT Opt |
| `[Physopt 32-1334]` | No candidate for LUT optimization | LUT Opt |
| `[Physopt 32-1336]` | Replaced LUT driver for load pin | LUT Opt |
| `[Physopt 32-1338]` | No improvement through LUT driver pair opt | LUT Opt |
| `[Physopt 32-1331]` | CASC optimization candidates identified | Cascade |
| `[Physopt 32-46]` | Critical-cell optimization candidates | Critical Cell |
| `[Physopt 32-68]` | No nets for critical-cell optimization | Critical Cell |
| `[Physopt 32-1305]` | Cell group optimization candidates | Critical Cell |
| `[Physopt 32-1308]` | No target net for cell group optimization | Critical Cell |
| `[Physopt 32-1323]` | Optimized critical cells for load cluster | Critical Cell |
| `[Physopt 32-601]` | Net driver retimed through logic | Rewire |
| `[Physopt 32-608]` | Optimized net, swapped pins | Rewire |
| `[Physopt 32-606]` | Critical-pin optimization candidate | Rewire |
| `[Physopt 32-607]` | No candidate for critical-pin optimization | Rewire |
| `[Physopt 32-69]` | No nets for rewiring optimization | Rewire |
| `[Physopt 32-670]` | No setup violation — equivalent driver rewiring skipped | Eq. Driver |
| `[Physopt 32-1030]` | Equivalent driver rewiring candidates | Eq. Driver |
| `[Physopt 32-1032]` | Equivalent driver optimization result | Eq. Driver |
| `[Physopt 32-1487]` | Did not optimize equivalent driver group | Eq. Driver |
| `[Physopt 32-1488]` | Optimized equivalent driver group | Eq. Driver |
| `[Physopt 32-1489]` | Optimizing equivalent driver group (in progress) | Eq. Driver |
| `[Physopt 32-665]` | DSP registers pushed out | DSP Reg |
| `[Physopt 32-666]` | Processed DSP cell — no change | DSP Reg |
| `[Physopt 32-456]` | No candidates for DSP register optimization | DSP Reg |
| `[Physopt 32-457]` | DSP register optimization candidates | DSP Reg |
| `[Physopt 32-527]` | BRAM register optimization candidates | BRAM Reg |
| `[Physopt 32-526]` | No candidates for BRAM register optimization | BRAM Reg |
| `[Physopt 32-846]` | No candidates for URAM register optimization | URAM Reg |
| `[Physopt 32-1395]` | MemoryRewireOpt: successfully optimized memory | Memory Rewire |
| `[Physopt 32-1396]` | MemoryRewireOpt: iteration detail (pins, WNS change) | Memory Rewire |
| `[Physopt 32-1397]` | MemoryRewireOpt: failed to optimize memory | Memory Rewire |
| `[Physopt 32-1398]` | MemoryRewireOpt: rewired N pins of memory | Memory Rewire |
| `[Physopt 32-677]` | No candidates for shift register optimization | SRL |
| `[Physopt 32-1401]` | No candidates for shift register optimization | SRL |
| `[Physopt 32-1402]` | Shift register optimization candidates | SRL |
| `[Physopt 32-1123]` | No candidates for shift register to pipeline | SRL |
| `[Physopt 32-1359]` | No control set reduced | Control Set |
| `[Physopt 32-1360]` | Optimized N flops during control set optimization | Control Set |
| `[Physopt 32-45]` | Hold slack optimization candidates identified | Hold Fix |
| `[Physopt 32-234]` | Hold fix result (ZHOLD_DELAYs inserted/calibrated) | Hold Fix |
| `[Physopt 32-960]` | Skip hold-fix: initial WHS does not violate threshold | Hold Fix |
| `[Physopt 32-1411]` | SLR replication candidates identified | SLR |
| `[Physopt 32-1492]` | SLR replication candidate net | SLR |
| `[Physopt 32-949]` | No candidates for dynamic/static region interface replication | DFX |
| `[Physopt 32-745]` | Negative slack too large — optimization skipped | Skip |
| `[Physopt 32-188]` | Rewire margin constraint | Skip |
| `[Physopt 32-1300]` | Found un-routed clock pins on BUFG_FABRIC net | BUFG Fabric |
| `[Physopt 32-1507]` | Replay failed | iPhysOpt |
| `[Physopt 32-775]` | End pass summary (cells created/deleted/moved) | Summary |
| `[Physopt 32-40]` | Design not ready — nets not unrouted (ERROR) | Prerequisite |
| `[Physopt 32-41]` | Design has unplaced instances (ERROR) | Prerequisite |
| `[Physopt 32-199]` | Design not synthesized (ERROR) | Prerequisite |
| `[Physopt 32-558]` | XDC constraint preventing register opt (WARNING) | Constraint |
| `[Physopt 32-559]` | No XDC constraints — forced replication skipped (WARNING) | Constraint |
| `[Physopt 32-722]` | Net with MARK_DEBUG optimized (WARNING) | MARK_DEBUG |
| `[Physopt 32-723]` | ASYNC_REG blocking replication (CRIT_WARN) | ASYNC_REG |
| `[Physopt 32-780]`–`[Physopt 32-781]` | DONT_TOUCH preventing optimization (INFO) | DONT_TOUCH |
| `[Physopt 32-909]` | Non-constant autopipeline input (CRIT_WARN) | AUTOPIPELINE |
| `[Physopt 32-928]`–`[Physopt 32-930]` | Timing degraded before commit (ERROR) | Degradation |
| `[Physopt 32-936]`–`[Physopt 32-937]` | Timing degraded after hold fix (ERROR/WARNING) | Degradation |
| `[Physopt 32-944]` | SLR address net conflict (CRIT_WARN) | SLR |
| `[Physopt 32-954]` | Skip hold fix on Laguna TX→RX paths (CRIT_WARN) | SLR |
| `[Physopt 32-957]` | Cannot fix hold — driver/load in different SLRs (CRIT_WARN) | SLR |
| `[Physopt 32-1005]` | Timing consistency check failed (CRIT_WARN) | Internal |
| `[Physopt 32-1019]` | DONT_TOUCH preventing SLR pipeline insertion (CRIT_WARN) | SLR |
| `[Physopt 32-1020]` | SLR optimization failed (ERROR) | SLR |
| `[Physopt 32-1021]` | Excessive SLL hold fix candidates (WARNING) | Hold Fix |
| `[Physopt 32-1122]`–`[Physopt 32-1129]` | AUTOPIPELINE attribute errors (CRIT_WARN) | AUTOPIPELINE |
| `[Physopt 32-1139]` | Conflicting retiming properties (WARNING) | Retiming |
| `[Physopt 32-1500]`–`[Physopt 32-1501]` | AUTOPIPELINE net issues (CRIT_WARN) | AUTOPIPELINE |
| `[Physopt 32-1523]` | Replay failed for transformation (WARNING) | iPhysOpt |

---

### Step 1e — ERRORs, CRITICAL WARNINGs, and actionable WARNINGs:
```bash
# All errors and critical warnings (always check first)
sed -n '/Command: phys_opt_design/,/phys_opt_design.*Time/p' <logfile> | grep -iE "ERROR.*Physopt 32|CRITICAL WARNING.*Physopt 32"
```
```bash
# Prerequisite & critical errors
sed -n '/Command: phys_opt_design/,/phys_opt_design.*Time/p' <logfile> | grep -E "\[Physopt 32-(40|41|199|705|706|769|848|928|929|930|936|1020)\]"
```
```bash
# AUTOPIPELINE errors
sed -n '/Command: phys_opt_design/,/phys_opt_design.*Time/p' <logfile> | grep -E "\[Physopt 32-(909|1122|1124|1125|1126|1127|1128|1129|1500|1501)\]"
```
```bash
# SLR/Laguna, ASYNC_REG, and constraint blocking
sed -n '/Command: phys_opt_design/,/phys_opt_design.*Time/p' <logfile> | grep -E "\[Physopt 32-(723|944|954|957|1019|1045|558|559|780|781)\]"
```
```bash
# Actionable warnings (MARK_DEBUG, rewire skip, hold, retiming, placement)
sed -n '/Command: phys_opt_design/,/phys_opt_design.*Time/p' <logfile> | grep -E "\[Physopt 32-(722|728|729|730|731|732|733|738|743|744|892|937|1005|1021|1139|1325|1523)\]"
```

Key patterns:
- `[Physopt 32-40]`/`[Physopt 32-41]`/`[Physopt 32-199]` = **Prerequisite errors** — design not ready. Place design first.
- `[Physopt 32-723]` = **ASYNC_REG blocking replication** — remove ASYNC_REG or add DONT_TOUCH.
- `[Physopt 32-909]`/`[Physopt 32-1122]`–`[Physopt 32-1129]`/`[Physopt 32-1500]`–`[Physopt 32-1501]` = **AUTOPIPELINE errors** — fix autopipeline attributes.
- `[Physopt 32-928]`–`[Physopt 32-930]`/`[Physopt 32-936]` = **Timing degradation** — optimization made things worse. Investigate.
- `[Physopt 32-944]`/`[Physopt 32-954]`/`[Physopt 32-957]`/`[Physopt 32-1019]`–`[Physopt 32-1020]` = **SLR/Laguna issues** — fix clocking topology or constraints.
- `[Physopt 32-705]`/`[Physopt 32-706]` = **Clock tree errors** — check clock routing.
- `[Physopt 32-558]`/`[Physopt 32-559]` = **Constraint issues** — XDC timing constraints blocking or missing.
- `[Physopt 32-722]` = **MARK_DEBUG optimized** — add DONT_TOUCH before phys_opt_design.
- `[Physopt 32-780]`/`[Physopt 32-781]` = **DONT_TOUCH blocking** — remove DONT_TOUCH to enable optimization.
- `[Physopt 32-728]`–`[Physopt 32-733]` = **Rewire skip reasons** — explains why rewire was not applied.
- `[Physopt 32-937]`/`[Physopt 32-1021]` = **Hold fix issues** — degradation or excessive candidates.
- `[Physopt 32-1139]` = **Conflicting retiming properties** — remove conflicting attributes.
- `[Physopt 32-1005]` = **Timing consistency check** — may be false positive, can skip with param.
- `[Physopt 32-745]` = Negative slack magnitude too large for optimization — fix at architecture level.
- `[Physopt 32-1507]` = iPhys_opt replay failed — re-run without incremental replay.
- `[Physopt 32-1300]` = Un-routed clock pins on BUFG_FABRIC net — check BUFG_FABRIC placement.
- `[Vivado_Tcl 4-383]` = WNS >= 0, all phys_opt skipped — design already meets timing.

> **Full message catalog with resolutions:** See [message-reference.md](message-reference.md) for all categorized messages.

---

### Step 2: Query Blocking Properties (if Vivado design is open)

Skip this step if only analyzing a log file without an open design.

```tcl
puts "PHYS_OPT_SKIPPED cells: [llength [get_cells -hier -filter {PHYS_OPT_SKIPPED != {}}]]"
puts "Non-replicable primitives: [llength [get_cells -hier -filter {IS_REPLICABLE == FALSE && IS_PRIMITIVE == TRUE}]]"
puts "DONT_TOUCH cells: [llength [get_cells -hier -filter {DONT_TOUCH == TRUE}]]"
puts "MARK_DEBUG nets: [llength [get_nets -hier -filter {MARK_DEBUG == TRUE}]]"
```

---

### Step 3: Assess Hold-Fix Impact (if hold fix was run)

Skip if `-hold_fix` was not used.

```tcl
# Count LUT1 cells that were inserted for hold fix
set all_lut1 [get_cells -hier -filter {REF_NAME == LUT1}]
puts "Total LUT1: [llength $all_lut1]"
set hold_wns [get_property SLACK [get_timing_paths -max_paths 1 -hold]]
puts "Hold WNS: $hold_wns"
```

From the log, search for `[Physopt 32-234]` which reports ZHOLD_DELAY insertions and calibrations. Each inserted LUT1 adds ~50ps to the data path — excessive hold fix can degrade setup timing.

---

### Step 4: Generate Recommendations

Evaluate each category below. Include applicable items in REPORT.md under the matching tier.

#### 4A — Constraint & Property Fixes

The skill's primary actionable output: copy-pasteable XDC commands and replay script generation.

**DONT_TOUCH / IS_REPLICABLE blocking critical paths:**
If `[Physopt 32-780]`/`[Physopt 32-781]` messages found:
```tcl
foreach c [get_cells -hier -filter {DONT_TOUCH==TRUE}] {
  set paths [get_timing_paths -through [get_pins -of $c] -max_paths 1 -quiet]
  if {[llength $paths] > 0} {
    set slack [get_property SLACK [lindex $paths 0]]
    if {$slack < 0} { puts "BLOCKED: $c slack=$slack" }
  }
}
```
For each blocking cell, provide specific XDC fix:
`reset_property DONT_TOUCH [get_cells <actual_cell>]`
If set by MARK_DEBUG: `set_property DONT_TOUCH FALSE [get_nets <net>]` (per-net) or `config_flows -mark_debug disable` (global).

**Save incremental replay script:**
If any optimization improved timing:
```tcl
write_iphys_opt_tcl iphys_opt_replay.tcl
```
Report: saved replay script for retrofit in next implementation run (see UG904 Retrofitting phys_opt_design).

#### 4B — Findings & Diagnosis

Report what the log analysis reveals — the analysis skill's unique diagnostic value.

**WNS/TNS trend assessment:**
Compare `[Physopt 32-668]` initial WNS with `[Physopt 32-669]`/`[Physopt 32-603]` final WNS.
- Improved >20% → "Optimization effective — design responsive to physical optimization."
- Improved <5% → "Optimization stagnant — current directive had minimal effect."
- Oscillating (alternating improvement/degradation across iterations) → "WNS thrashing — stop iterating. Check for conflicting constraints."
- `[Vivado_Tcl 4-521]` shows 0 changes applied → "Directive was ineffective — no optimizations applied."

**Timing gap too large (`[Physopt 32-745]`):**
If message found: "Timing gap too large for physical optimization. Must fix at architecture/RTL level."
```tcl
report_timing -max_paths 10 -slack_lesser_than -2.0 -file large_violations.rpt
report_design_analysis -logic_level_distribution -file logic_levels.rpt
```
Report worst paths and logic levels — beyond phys_opt scope.

**Hold fix impact:**
If `[Physopt 32-937]` found (setup degraded after hold fix):
```tcl
report_timing -max_paths 10 -file post_holdfix_setup.rpt
report_timing -hold -max_paths 10 -file post_holdfix_hold.rpt
```
Report both setup and hold results with specific degradation amounts.

**Error/warning triage:**
- For each error/critical warning from Step 1e, report with fix guidance from [message-reference.md](message-reference.md).
- Flag prerequisite errors (`[Physopt 32-40]`, `[Physopt 32-41]`, `[Physopt 32-199]`) as blocking.

#### 4C — Next-Run Suggestions

Commands the user can try in the next phys_opt iteration. Per AMD docs (UG904, UG949), iterative phys_opt_design is an explicitly supported workflow — each pass optimizes the top few percent of failing paths.

| Condition | Suggestion | Rationale |
|-----------|------------|-----------|
| WNS improved >20% | `phys_opt_design -directive <same>` | Good response — another pass likely beneficial |
| Stagnant, paths through LUTs | `phys_opt_design -directive AggressiveExplore` | Switch heuristic for LUT-dominated paths |
| Stagnant, paths through DSP/BRAM | `phys_opt_design -directive AlternateFlowWithRetiming` | Enable retiming through hard blocks |
| Stagnant, SLR crossing paths | `phys_opt_design -directive AlternateReplication` | Different replication heuristic for SLR |
| Replication helped, WNS still negative | `phys_opt_design -force_replication_on_nets [get_nets {<net>}]` | Target specific nets (use actual names) |
| Hold fix degraded setup | Setup first: `phys_opt_design -directive Explore`, then: `phys_opt_design -hold_fix` | Separate setup and hold passes |

### Step 5: Write Report Files

Write both `report_data.json` and `REPORT.md` to `vivado_agentic_ai_reports/phys-opt-design-analysis/`. Read [report-template.md](report-template.md) for the JSON schema and REPORT.md template.

**Populating Recommendations** — this is what makes the report actionable:
- For each Step 4 condition (4A–4C) that fired, create a recommendation entry.
- In `report_data.json`: populate the `recommendations[]` array. Include `tcl_commands` with the actual Tcl commands from Step 4 using real cell/net names from the design.
- In `REPORT.md`: place each recommendation under the appropriate tier:
  - **Immediate Fixes** → constraint/property changes, replay script (4A)
  - **Findings & Diagnosis** → WNS trends, timing gap, hold impact, error triage (4B)
  - **Next-Run Suggestions** → iterative phys_opt commands, directive changes (4C)
  - **Accept / Waive** → MARK_DEBUG or intentional non-replicable cells
- Every recommendation should contain a fenced `tcl` code block with a complete, copy-pasteable command so the user can paste it directly into the Vivado Tcl console.
- If no Step 4 conditions fired, write: "No recommendations — all optimizations completed successfully."

**Populating Errors & Warnings:**
- For each actionable message found in Step 1e, create an entry in `errors_warnings[]` (JSON) and the Errors & Warnings table (REPORT.md).
- The `agent_action` field should describe what the agent did or recommends — referencing the action from [message-reference.md](message-reference.md).

**Saving replay script (4A):**
- If any optimization improved timing, include `write_iphys_opt_tcl` in the Immediate Fixes section.

### Step 6: Copy Dashboard

Copy the pre-built dashboard template to the output directory so users can open it in a browser:

```tcl
file copy -force [file join $skill_dir DASHBOARD_TEMPLATE.html] vivado_agentic_ai_reports/phys-opt-design-analysis/dashboard.html
```

The `DASHBOARD_TEMPLATE.html` file lives alongside this SKILL.md in the skill folder. The dashboard is a self-contained HTML file that loads `report_data.json` via `fetch()` at runtime — no generation required, zero token cost.

**Tell the user:** "Open `vivado_agentic_ai_reports/phys-opt-design-analysis/dashboard.html` in a browser to see interactive charts."

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

---

## Error Handling

| Error | Action |
|---|---|
| No design open | "Open with `open_run impl_1`" |
| Log file not found | Ask user for path to vivado.log or runme.log |
| No phys_opt_design in log | "phys_opt_design has not been run. Run it first." |

---

## Output Files & Templates

See [report-template.md](report-template.md) for the report_data.json schema, REPORT.md template, assessment scoring, optimization phase reference, common issues, and directives reference.
