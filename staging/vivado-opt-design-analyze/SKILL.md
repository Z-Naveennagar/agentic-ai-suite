---
name: vivado-opt-design-analyze
description: Analyze opt_design log for per-phase optimization stats (retarget, propconst, sweep, BUFG, shift-reg, remap), DONT_TOUCH/MARK_DEBUG conflicts, BRAM power opt, and control set merging — then provide actionable recommendations (directive selection, constraint fixes, re-run strategies). Use when users review/summarize opt_design results, ask what it did or why optimizations were skipped, diagnose blocking properties, choose directives, interpret the Change Summary table, or need guidance on what to run next.
version: 4.0.0
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
# opt_design Analysis & Recommendations

> **TOOL CONSTRAINT (NON-NEGOTIABLE):**
> For ALL log file data extraction, you **MUST** use `run_in_terminal` with `grep` or `sed`.
> You **MUST NOT** use `read_file` or `grep_search` on `.log` files — these return hundreds of IP/XDC/IP_Flow warning lines, wasting 10x+ tokens.
> If you already have line numbers from a prior search, **do NOT read those lines**. Use the grep commands below instead.

> **SCOPING CONSTRAINT (NON-NEGOTIABLE):**
> Vivado log files contain output from **all** phases (synthesis, link, opt_design, place, route, phys_opt).
> Several `[Opt 31-*]` message IDs appear in **link_design** and **place_design** too (e.g., `[Opt 31-138]`, `[Opt 31-441]`).
> "Phase N" lines are shared across opt/place/route.
> The opt_design section is delimited by `Command: opt_design` (start) and `opt_design: Time` (end — one line after `opt_design completed successfully`).
> **ALL greps MUST be scoped** to this section using:
> ```
> sed -n '/Command: opt_design/,/opt_design: Time/p' <logfile> | grep ...
> ```
> **NEVER** grep the full log file directly — not even for `[Opt 31-*]` IDs, "Phase", "Opt_design Change Summary", or resource terms (`URAM`, `DSP`, `Slice LUTs`, `Block RAM`) — these match synthesis/link/placement output and produce 50+ noisy lines.

**Prerequisites:** `opt_design` must have been run; implementation log (vivado.log, runme.log, or run.log) accessible.

**Do NOT use this skill if:** synthesis is not complete, or you are analyzing placement/routing (use those skills instead).

---

## Efficiency Guidelines

- **Pass `session_id`** to every `vivado_execute` call when a Vivado session is active.
- **Write reports to file** using Vivado's `-file` flag — do not dump full report content in chat. Give a short summary only.
- **Read reports efficiently** — use `grep`, `sed`, or `awk` via terminal to extract specific sections from report files instead of reading entire files into context. Use `wc -l` + `head` to check size/structure first. Full `read_file` is fine only for small reports (<200 lines).
- **Do NOT** use `shell ls`, `shell find`, or `shell glob` to locate files.
- **Do NOT** use Vivado Tcl (`exec cat`, `open`, `read`) to read files. Use your file reader tool or `grep`/`sed` via terminal.
- **Do NOT** retry a failed Tcl command with different syntax. Report the error and stop or proceed to the next step.


## Workflow

**⚠️ CRITICAL: Execute steps SEQUENTIALLY.** Wait for each `vivado_execute` command to complete before proceeding. The Vivado Tcl process is single-threaded — parallel calls will serialize and may cause confusing interleaved output.

**⚠️ The workflow is incomplete until BOTH REPORT.md AND dashboard.html exist.** Do not end your turn before writing all three output files (REPORT.md, report_data.json, dashboard.html). Do not narrate ("Now generating...") or summarize before writing — invoke the write tool first. Only after all files are written, give a short summary.

### Step 1: Extract Log Data via Terminal Grep

All commands below use a `sed -n` scope to extract only the opt_design section. The markers are:
- **Start:** `Command: opt_design` (logged when Vivado begins the command)
- **End:** `opt_design: Time` (logged one line after `opt_design completed successfully`, includes runtime/memory)

**Step 1a — Command + summary table + status (do this FIRST, usually sufficient):**
```bash
sed -n '/Command: opt_design/,/opt_design: Time/p' <logfile> | grep "Command: opt_design\|opt_design completed\|opt_design: Time" && echo "---" && sed -n '/Command: opt_design/,/opt_design: Time/p' <logfile> | grep -A 20 "Opt_design Change Summary"
```
The summary table has columns: Phase, #Cells Created, #Cells Removed, #Constrained Objects. **Stop here unless more detail is needed.**

> **TIP:** If the summary table shows **non-zero constrained objects** and `-debug_log` was NOT in the command, recommend the user re-run with `-debug_log` to identify which specific cells/nets are blocked. If `-debug_log` WAS used, proceed to Step 1f.

**Step 1b — Per-phase detail (only if summary table is missing or user needs specifics):**
```bash
sed -n '/Command: opt_design/,/opt_design: Time/p' <logfile> | grep "\[Opt 31-389\]\|\[Opt 31-49\]\|\[Opt 31-194\]\|\[Opt 31-662\]\|\[Opt 31-1851\]\|\[Opt 31-1834\]\|\[Opt 31-1566\]\|\[Opt 31-138\]\|\[Opt 31-519\]\|\[Opt 31-1077\]\|\[Opt 31-1021\]"
```

**Step 1c — Phase timing (only if user asks about per-phase duration):**
```bash
sed -n '/Command: opt_design/,/opt_design: Time/p' <logfile> | grep -E "^Phase [0-9]+ " | grep -v "Phase [0-9]*\.[0-9]"
```

**Step 1d — Device and context (only if needed for report framing):**

This is the one exception — device info is outside the opt_design section. Use tight patterns:
```bash
grep "set.*FPGA_PART\|link_design -part\|device 'xc" <logfile> | head -3
```
If an `fpga.stats` file exists alongside the log, prefer it for utilization data:
```bash
cat $(dirname <logfile>)/fpga.stats 2>/dev/null | head -20
```

**Grep anti-patterns (MANDATORY — violating these wastes 5-15K tokens):**
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
| **debug_log-only IDs** | *(appear only when `-debug_log` is used)* | |
| `[Opt 31-55]` | Sweep skip detail — names specific cell skipped due to DONT_TOUCH | Yes |
| `[Opt 31-431]` | Constant propagation starting point count | Yes |
| `[Opt 31-684]` | Inverter push blocked — names inverter cell and constrained load | Yes |
| `[Opt 31-1019]` | Per-object constraint attribution — percentage of blocked optimizations per DONT_TOUCH cell/net | Yes |
| `[Opt 31-1020]` | Per-phase constrained object count with debug detail (replaces generic `[Opt 31-1021]` message) | Yes |
| `[Opt 31-1555]` | control_set_opt unsupported device notification | Yes |
| `[Opt 31-1565]` | Clock buffer count | Yes |

**"Self-scoping: Yes"** means the ID appears only during opt_design — safe to grep across the full log.
**"Self-scoping: No"** means the ID also appears in other phases — **must** use `sed -n` scoping.

---

### Step 1e — CRITICAL WARNINGs and new message IDs (only if the above steps reveal issues):
```bash
sed -n '/Command: opt_design/,/opt_design: Time/p' <logfile> | grep -E "CRITICAL WARNING.*Opt 31|\[Opt 31-81\]|\[Opt 31-83\]|\[Opt 31-1005\]|\[Opt 31-1064\]|\[Opt 31-1384\]|\[Opt 31-2042\]|\[Opt 31-2117\]|\[Opt 31-2244\]"
```

Key patterns:
- `[Opt 31-81]` CRITICAL WARNING = `set_logic_one`/`set_logic_zero` on an already-driven pin. The constraint has no effect. **Recommendation:** Remove the constraint or fix the netlist — leaving it masks a design intent problem.
- `[Opt 31-83]` = Series input buffers detected (e.g., IBUF → IBUF). **Recommendation:** Fix RTL to avoid chained I/O buffers.
- `[Opt 31-1384]`–`[Opt 31-1389]` = MUXF7/F8/F9 optimization stats — if mostly removals, the synthesis MUXF inference was aggressive and opt_design is correcting it.
- `[Opt 31-2042]` = BRAM memory optimization (port mapping, power opt actions).
- `[Opt 31-2117]`–`[Opt 31-2118]` = Resynth/remap optimization counts.
- `[Opt 31-2244]` = LUT decomposition results.

---

### Step 1f — debug_log Constraint Detail (ONLY when `-debug_log` was used)

When `opt_design` is run with `-debug_log`, additional message IDs appear that identify **exactly** which cells/nets are constrained and how much optimization they block. This is the most actionable data in the entire log.

**Extract per-phase constraint attribution:**
```bash
sed -n '/Command: opt_design/,/opt_design: Time/p' <logfile> | grep "\[Opt 31-1020\]\|\[Opt 31-1019\]" | sort -u
```

- `[Opt 31-1020]` — Per-phase summary: "In phase X, N netlist objects are constrained preventing optimization" (replaces the generic `[Opt 31-1021]` message which only says "run with -debug_log to get more detail")
- `[Opt 31-1019]` — Per-object attribution: "X% of prevented optimizations are due to the following constraint: DONT_TOUCH on netlist object (Cell/Net) : \<name\>" — tells you exactly which constraint and object is responsible

**Extract inverter push blocks:**
```bash
sed -n '/Command: opt_design/,/opt_design: Time/p' <logfile> | grep "\[Opt 31-684\]" | sort -u
```

- `[Opt 31-684]` — "Cannot push inverter X to load Y because of don't touch constraints" — names the specific inverter cell and the constrained load cell

**Extract sweep skips:**
```bash
sed -n '/Command: opt_design/,/opt_design: Time/p' <logfile> | grep "\[Opt 31-55\]" | sort -u
```

- `[Opt 31-55]` — "Skipping sweep on cell due to DONT_TOUCH property, cell: X" — names the cell that sweep would have removed

**Extract constant propagation starting points:**
```bash
sed -n '/Command: opt_design/,/opt_design: Time/p' <logfile> | grep "\[Opt 31-431\]"
```

- `[Opt 31-431]` — "constant propagation found N starting points" — indicates how many constant sources were available for propagation

**All debug_log messages at once:**
```bash
sed -n '/Command: opt_design/,/opt_design: Time/p' <logfile> | grep "\[Opt 31-55\]\|\[Opt 31-431\]\|\[Opt 31-684\]\|\[Opt 31-1019\]\|\[Opt 31-1020\]\|\[Opt 31-1565\]" | sort -u
```

**How to interpret the debug_log constraint data:**

1. **Group `[Opt 31-1019]` by constraint type** (DONT_TOUCH Cell vs. DONT_TOUCH Net) and by object name root (e.g., `keep_me_reg_reg[*]` → 8 cells from a single RTL signal `keep_me_reg`)
2. **High percentage on a few objects** (>10% each) → small number of constraints blocking significant optimization → easy wins by reviewing those specific attributes
3. **Low percentage spread across many objects** (<2% each) → widespread DONT_TOUCH/MARK_DEBUG, likely from IP or debug infrastructure → harder to address, may be intentional
4. **`[Opt 31-684]` messages** identify specific inverter push optimizations blocked → in timing-critical paths, removing DONT_TOUCH from these loads can improve WNS
5. **`[Opt 31-55]` messages** identify cells that sweep would have removed → if these cells are truly dead logic, removing DONT_TOUCH enables cleanup

**Recommendation trigger:** If `[Opt 31-1019]` shows the same DONT_TOUCH Cell/Net across multiple phases (Retarget, Constant propagation, Sweep, Remap), recommend the user review whether that DONT_TOUCH is still needed — it is blocking optimization in 4+ phases simultaneously.

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

Based on analysis, recommend:
1. Large `#Constrained Objects` counts → heavy DONT_TOUCH/MARK_DEBUG; if `-debug_log` was used, reference the specific `[Opt 31-1019]` attribution data showing which cells/nets are responsible; if not, suggest re-running with `-debug_log`
2. Sweep removed < 1% of cells → design already clean, no re-run needed
3. High control set count → suggest `opt_design -control_set_merge`
4. Replicated logic detected → suggest `opt_design -merge_equivalent_drivers`
5. BRAM power opt not run and power matters → suggest `opt_design -bram_power_opt`
6. First pass removed significant logic → suggest a second pass (diminishing returns after 2-3)
7. `-remap` not run → could further pack LUTs

---

### Step 5: Generate report_data.json

Create a `report_data.json` file in the output directory (`vivado_agentic_ai_reports/opt-design-analysis/`) containing all extracted data in the structured format below. This file drives the interactive dashboard.

**Required JSON structure:**
```json
{
  "metadata": {
    "device": "<actual device part>",
    "device_family": "<family name>",
    "command": "<full opt_design command with flags>",
    "runtime_seconds": <N>,
    "analysis_date": "<ISO 8601 timestamp>",
    "project": "<project name>",
    "log_file": "<path to log file>"
  },
  "design_stats": {
    "total_cells": <N>, "total_nets": <N>,
    "luts": <N>, "ffs": <N>, "srl": <N>, "bram": <N>,
    "carry": <N>, "dsp": <N>, "bufg": <N>
  },
  "constraint_census": {
    "dont_touch_cells": <N>, "dont_touch_nets": <N>, "mark_debug_nets": <N>,
    "total_constrained": <N>,
    "pct_cells_constrained": <float>, "pct_nets_constrained": <float>
  },
  "phases": [
    {
      "name": "<phase name>", "phase_num": <N>,
      "cells_created": <N>, "cells_removed": <N>, "constrained_objects": <N>,
      "key_actions": ["<action description>"],
      "inverters_pushed": <N>, "inverter_loads": <N>
    }
  ],
  "dont_touch_impact": [
    {
      "object": "<cell/net name or range>",
      "type": "DONT_TOUCH Cell|DONT_TOUCH Net|DONT_TOUCH Net (MARK_DEBUG)",
      "source": "RTL attribute|XDC constraint|IP default",
      "rtl_signal": "<signal name>", "rtl_file": "<file path>", "rtl_line": <N>,
      "count": <N>,
      "phases_blocked": ["<phase names>"],
      "max_pct": <float>, "total_pct": <float>,
      "severity": "critical|warning|info",
      "recommendation": "<action to take>"
    }
  ],
  "recommendations": [
    {
      "priority": <N>, "severity": "critical|warning|info",
      "title": "<short title>",
      "detail": "<explanation with actual names>",
      "action": "<concrete RTL/XDC change>",
      "file": "<file path>", "line": <N>,
      "phases_unblocked": <N>, "estimated_cells_freed": <N>
    }
  ]
}
```

**Data population rules:**
- `design_stats` — populate from Step 2 Vivado queries (`llength [get_cells]`, cell type counts). If no Vivado design is open, set all to 0 and add a note in metadata.
- `constraint_census` — populate from Step 2 DONT_TOUCH/MARK_DEBUG queries. If no Vivado design is open, estimate from debug_log `[Opt 31-1019]` counts.
- `phases` — one entry per phase from the Change Summary table (Step 1a). Add `inverters_pushed`/`inverter_loads` from `[Opt 31-138]`/`[Opt 31-1566]` messages.
- `dont_touch_impact` — populate from `[Opt 31-1019]` debug_log data (Step 1f). Group by object root name (e.g., `keep_me_reg_reg[0:7]` not 8 separate entries). If `-debug_log` was not used, leave as empty array `[]`.
- `recommendations` — populate from Step 4 analysis. Every recommendation MUST use actual design names (see Design-Specific Fix Rules below).

---

### Step 6: Generate Dashboard HTML

Copy the dashboard template to the output directory alongside `report_data.json`:

```bash
cp <skill_directory>/DASHBOARD_TEMPLATE.html vivado_agentic_ai_reports/opt-design-analysis/dashboard.html
```

The template path is: `<this skill's directory>/DASHBOARD_TEMPLATE.html` — it is bundled with this skill. The dashboard loads `report_data.json` via `fetch()` and renders Charts.js visualizations with 4 tabs:
1. **Optimization Summary** — KPI cards, constrained-objects-by-phase bar chart, constraint census donut, change summary table
2. **DONT_TOUCH Impact** — Impact bars and detail table showing which constraints block which phases
3. **Phase Details** — Blocked/clean phase bars and per-phase action table
4. **Recommendations** — Priority-ranked action cards with severity, file references, and suggested fixes

**Output directory structure after completion:**
```
vivado_agentic_ai_reports/opt-design-analysis/
├── REPORT.md           ← Markdown report (Step 4)
├── report_data.json    ← Structured data (Step 5)
└── dashboard.html      ← Interactive dashboard (Step 6)
```

---


## ⚠️ MANDATORY: Design-Specific Fix Rules

**All fixes MUST use ACTUAL names from the design. NO generic placeholders.**

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

## Report Template

Output a markdown report (REPORT.md), a structured JSON file (report_data.json), and an interactive HTML dashboard (dashboard.html):

**REPORT.md** contents:
- **Command** run and runtime
- **Summary table** (per-phase cells created/removed/constrained)
- **Key actions** per phase (inverter push/pull counts, carry transforms, BUFG insertions with load counts)
- **DONT_TOUCH/MARK_DEBUG inventory** (if design is open)
- **BRAM power opt status** (if applicable)
- **Recommendations** (prioritized)

**report_data.json** — see Step 5 for the required JSON schema. All fields must use actual design names.

**dashboard.html** — copy from DASHBOARD_TEMPLATE.html bundled with this skill (see Step 6).

---

## Optimization Phase Reference

The following opt_design phases and sub-commands should be recognized during log analysis. Each has been validated across hundreds of designs in production:

| Phase/Sub-Command | Description | Key Message IDs |
|---|---|---|
| MBUFG sweep | Sweep/optimize MBUFGCE/MBUFG_GT buffers — remove unused, merge equivalent | `[Opt 31-389]` |
| MUXF optimization | Optimize MUX primitives (MUXF7/F8/F9) — create/remove based on timing | `[Opt 31-1005]`, `[Opt 31-1384]`–`[Opt 31-1389]` |
| Multi-level optimization (MLO) | Tieoff optimization, buffer removal, OBUF/IBUF insertion, BUFG_GT_SYNC | `[Opt 31-288]`, `[Opt 31-289]` |
| Push inverter | Push inverters through LUTs, IOB primitives (IDDR/ODDR), carry chains | `[Opt 31-1566]`, `[Opt 31-1561]`, `[Opt 31-138]` |
| BRAM memory opt | BRAM port optimization, power mode conversion, cascade detection | `[Opt 31-2042]` |
| SRL remap | Remap shift registers between SRL16/SRLC32 and flip-flops | `[Opt 31-389]` |
| BUFG GT sweep | Sweep/remove unused BUFG_GT instances | `[Opt 31-441]`, `[Opt 31-662]` |
| HFN BUFG insertion | Insert BUFGs for high-fanout nets at hierarchy boundaries | `[Opt 31-194]`, `[Opt 31-1077]` |
| HFN split load | Split high-fanout net loads across replicated buffers | `[Opt 31-389]` |
| LUT decomposition | Decompose wide LUTs (LUT6→LUT5+LUT5) for timing | `[Opt 31-2244]` |
| Lookahead8 remap | Remap carry-lookahead logic | `[Opt 31-1834]`, `[Opt 31-519]` |
| Split load | Replicate high-fanout drivers without BUFG insertion | `[Opt 31-389]` |
| Time-driven BUFG | Insert BUFGs based on timing analysis | `[Opt 31-194]` |
| SRL retarget | Retarget SRLs between fixed/variable-length modes | `[Opt 31-49]` |
| Resynth/remap | Re-synthesize and remap logic for QoR | `[Opt 31-2117]`–`[Opt 31-2118]` |
| LUT remap | Remap LUT equations for better packing | `[Opt 31-389]` |
| Aggressive LUT remap | More aggressive LUT remapping with area tradeoff | `[Opt 31-389]` |
| Property optimization | Optimize based on INIT values, constant propagation through properties | `[Opt 31-389]` |
| SLR optimization | SSI/SLR-aware optimizations for multi-die devices | `[Opt 31-422]` |
| Constant propagation | Propagate constant values through logic | `[Opt 31-389]` |
| BUFG insertion (Versal) | Versal-specific BUFG insertion (MMCM/DPLL/XPLL output buffering) | `[Opt 31-194]` |
| Set logic | Apply set_logic_one/set_logic_zero constraints | `[Opt 31-81]` |

### Common Issues After opt_design

| Symptom | Root Cause | Recommendation |
|---|---|---|
| VCC↔GND tieoff cell changes after sweep | Sweep or MLO merged/replaced constant sources differently | Verify tieoff connectivity; if functionally incorrect, constrain the tieoff net with DONT_TOUCH |
| IOB BEL assignment changed (e.g., HDIOLOGIC↔XPIOLOGIC) | Push-inverter through IOB changed BEL assignment due to architecture mapping | Expected on 7-series — verify functional correctness; no action usually needed |
| DRC REQP-2090 after MBUFG_GT sweep (CLR/CLRB_LEAF) | MBUFG_GT sweep left CLR/CLRB_LEAF pin in invalid state | Check AR73639 for CLR pin sequencing requirements; may need to constrain MBUFG_GT with DONT_TOUCH |
| `[Opt 31-81]` CRITICAL WARNING on set_logic | `set_logic_one`/`set_logic_zero` applied to an already-driven pin — constraint ignored | Remove the redundant constraint or fix the netlist so the pin is not driven |
| `[Opt 31-83]` series input buffers | Chained IBUF→IBUF or OBUF→OBUF in the RTL/netlist | Fix RTL to eliminate cascaded I/O buffers |
| Unexpected cell count after high-fanout-net (HFN) split | Driver replication created more cells than expected | Review `-hier_fanout_limit` threshold; lower value = more replication |
| `[Netlist 29-356]` non-native primitives remain | MUXCY/XORCY not fully remapped to CARRY8 during optimization | Run `opt_design -retarget` or re-synthesize the affected hierarchy |

---

## opt_design Directives Reference

| Directive | Purpose |
|---|---|
| `Explore` | Run all optimizations, pick best |
| `ExploreArea` | Optimize for area reduction |
| `ExploreWithRemap` | Include LUT remap pass |
| `NoBramPowerOpt` | Skip BRAM power optimization |
| `-merge_equivalent_drivers` | Merge replicated logic |
| `-control_set_merge` | Combine compatible control sets |
| `-hier_fanout_limit <N>` | Replicate high fanout drivers (min 512) |
| `-debug_log` | Log which constrained objects block optimization |
| `-resynth_seq_area` | Re-synthesize sequential logic for area |
| `-propconst` | Run only constant propagation |
| `-sweep` | Run only sweep (remove unconnected) |
| `-retarget` | Run only retarget (carry chain, inverter push) |
| `-muxf_remap` | Run only MUXF optimization |
| `-shift_register_opt` | Run only SRL optimization |
| `-aggressive_remap` | Aggressive LUT remapping |
