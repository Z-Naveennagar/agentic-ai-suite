---
name: congestion-analysis
description: >
  Analyze placement and routing congestion from existing Vivado reports (report_design_analysis,
  report_utilization, report_route_status, report_timing_summary) without re-generating them
  from a DCP. Produces structured report_data.json and an interactive HTML dashboard with
  congestion heatmaps, utilization histograms, Rent exponent gauges, routing degradation
  charts, directive recommendations, and optional device floorplan overlays via the
  device-floorplan skill. Use when user asks to "analyze congestion",
  "check congestion", "congestion analysis", "routing congestion", "placement congestion",
  "congestion hotspots", "Rent exponent", "clock region utilization", "over-utilized",
  "congestion heatmap", "congestion dashboard", or "why is routing failing". Covers both
  post-placement (pre-route) and post-route congestion phases. For all device families.
version: 1.3.0
vivado_version: 2025.1+
categories: [design-analysis, congestion, placement, routing, implementation]
device_families: [all]
estimated_duration: 2-5 minutes
complexity: intermediate-to-advanced
author: Vivado AI Skills Team
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
# Congestion Analysis (Placement + Routing)

## Introduction **[MANDATORY]**

**Purpose:** Analyzes congestion across both placement and routing phases by consuming **existing** Vivado report files, or generating new ones from a DCP when the user requests it. Produces a structured `report_data.json` and an interactive `dashboard.html` for visualization. By default, check for existing reports first before opening a DCP.

**Problem Solved:** Routing congestion is a leading cause of timing closure failure and unroutability. This skill provides a unified view across placer and router phases:
- **Placer phase:** Localized high utilization (>80% LUT in a clock region), high Rent exponent (>0.65), MUXF/carry-chain routing pressure, utilization imbalance across clock regions
- **Router phase:** Unrouted/partially routed nets, post-route timing degradation vs pre-route estimates, directional congestion hotspots, routing channel saturation
- **Cross-phase:** Correlating placement congestion predictions with actual routing outcomes

**Expected Outcome:**
- `report_data.json` — structured JSON with all congestion metrics
- `dashboard.html` — interactive Chart.js dashboard (5 tabs: Congestion Hotspots, Overview, Placement, Routing, Recommendations)
- `REPORT.md` — markdown summary with key findings and actions

**Prerequisites:**
- [x] At least ONE of these Vivado reports must exist (the skill checks and asks for missing ones):
  - `report_design_analysis -congestion` output (`.rpt`)
  - `report_design_analysis -complexity` output (`.rpt`)
  - `report_utilization` output (`.rpt`)
  - `report_route_status` output (`.rpt`)
  - `report_timing_summary` output (`.rpt`)

**Key Principle — Report-First, Not DCP-First:**

> **⚠️ DO NOT open a DCP or run report generation commands by default.** These can take many minutes on large designs. Instead:
> 1. Search for existing report files (user may point to them, or they may be in standard Vivado project locations)
> 2. If reports are found → parse them and produce output
> 3. If reports are NOT found → **STOP and ask the user** to either provide report file paths or confirm that you should generate them via Vivado MCP
> 4. Only generate reports via Vivado MCP if the user explicitly confirms

**Reference:**
- **UG906**: Design Analysis and Closure Techniques — `report_design_analysis`
- **UG904**: Vivado Implementation Guide — `place_design`, `route_design` directives
- **UG949**: UltraFast Design Methodology Guide — congestion avoidance

---

## DO's **[MANDATORY]**

### Use This Skill When:

1. **Post-placement congestion**
   - Trigger: "congestion after placement", "placement congestion", "congestion hotspots", "congestion analysis"
2. **Post-route congestion**
   - Trigger: "routing congestion", "unroutable nets", "route_design congestion", "routing failed"
3. **Pre-route congestion prediction**
   - Trigger: "predict congestion", "will routing succeed", "before routing"
4. **Rent exponent / complexity**
   - Trigger: "Rent exponent", "design complexity", "complexity analysis"
5. **Utilization analysis**
   - Trigger: "clock region utilization", "over-utilized", "utilization balance"
6. **Congestion dashboard**
   - Trigger: "congestion dashboard", "congestion heatmap", "visualize congestion"
7. **Placement directive guidance**
   - Trigger: "placement directives", "AltSpreadLogic", "SSI_SpreadLogic", "spread placement"
8. **Post-route timing degradation from congestion**
   - Trigger: "timing worse after routing", "route delay too high", "routing detour"

### Best Practices:

- Always check for BOTH congestion and complexity reports — they provide complementary data
- Keep LUT utilization below 80% per clock region for routability
- A Rent exponent > 0.65 indicates likely routing challenges
- Congestion levels 4+ (on the 0-8 UG1788 scale; level 4 = 16×16 tiles) indicate problems; level 6+ is severe
- Compare post-place and post-route timing to quantify routing degradation
- Correlate unrouted nets with congested clock regions

---

## DON'Ts **[MANDATORY]**

### Do NOT Use This Skill When:

1. **Design not yet placed** → User needs to run `place_design` first
2. **Clock placer failures** → Use clock-placer-failure-debug
3. **Synthesis-level issues** → Use synth-design-analysis
4. **E&P multi-FPGA partition congestion** → This skill handles general congestion; for E&P-specific partition boundary / TDM / mux-ratio analysis, a separate E&P flow is needed

### Common Mistakes to Avoid:

- **Opening a DCP to generate reports without asking:** Report generation can take 5-30 minutes on large designs. Always check for existing reports first.
- **Assuming design_analysis.rpt has congestion data:** The report may have been generated with `-timing -complexity` but NOT `-congestion`. Always check for the "Placer Final Level Congestion" section before assuming congestion data is present.
- **Looking only at global utilization:** A design at 50% global LUT usage can have 95%+ in individual clock regions
- **Ignoring carry chain density:** Carry chains are not counted in LUT utilization but consume routing
- **Applying spreading directives without understanding cause:** Spreading fixes over-utilization but may hurt timing on short paths
- **Not accounting for HLUTNM on LUT pairs:** Packed LUT pairs may reduce routability even at moderate utilization
- **Re-running route_design without fixing placement:** Most routing failures originate from poor placement
- **Using `-return_string` and `-file` together:** Vivado does not allow both flags simultaneously. Use `-file` to write reports, then read the file.
- **Expecting Rent exponent to always be available:** Even with `-complexity`, Vivado may report "No complexity report generated as cells satisfying given conditions are not present in the design." Set Rent to null and note the reason.

---

## Efficiency Guidelines

- **Pass `session_id`** to every `vivado_execute` call when a Vivado session is active.
- **Write reports to file** using Vivado's `-file` flag — do not dump full report content in chat. Give a short summary only.
- **Read reports efficiently** — use `grep`, `sed`, or `awk` via terminal to extract specific sections from report files instead of reading entire files into context. Use `wc -l` + `head` to check size/structure first. Full `read_file` is fine only for small reports (<200 lines).
- **Do NOT** use `shell ls`, `shell find`, or `shell glob` to locate files.
- **Do NOT** use Vivado Tcl (`exec cat`, `open`, `read`) to read files. Use your file reader tool or `grep`/`sed` via terminal.
- **Do NOT** retry a failed Tcl command with different syntax. Report the error and stop or proceed to the next step.

---

## Mandatory Workflow **[MANDATORY]**

**⚠️ CRITICAL: Execute steps SEQUENTIALLY.** Wait for each step to complete before proceeding.

**⚠️ The workflow is incomplete until ALL THREE output files exist (REPORT.md, report_data.json, dashboard.html).** Do not end your turn before writing all output files. Do not narrate ("Now generating...") — invoke the write tool first. Only after files are written, give a short summary.

### Execution Mode

**Type:** Report-based analysis (no DCP required by default)
**Duration:** 2-5 minutes
**User Intervention Required:** Only if no reports are found

---

### Step 1: Locate Existing Reports
**Objective:** Find congestion-relevant report files without generating them

**Action:** Search for report files in the user's workspace. Check these common locations:
1. User-specified path (if they provided one)
2. Current working directory
3. Standard Vivado project structure: `<project>.runs/impl_*/`
4. `vivado_agentic_ai_reports/` directory
5. Any `.rpt` files the user mentioned

**Reports to locate (priority order):**

| Report | Generated By | Key Data |
|--------|-------------|----------|
| Congestion report | `report_design_analysis -congestion` | Per-direction congestion levels, clock region hotspots |
| Complexity report | `report_design_analysis -complexity` | Rent exponent, average fanout, logic levels |
| Utilization report | `report_utilization` | Per-clock-region LUT/FF/BRAM/DSP/URAM % |
| SLR utilization | `report_utilization -slr` | Per-SLR breakdown (multi-die devices) |
| Route status | `report_route_status` | Routed/unrouted/partial net counts |
| Timing summary | `report_timing_summary` | WNS/WHS/TNS/THS post-route |
| Design analysis | `report_design_analysis` | Combined output with multiple sections |
| Clock utilization | `report_clock_utilization` | Per-CR FF/LUTRAM/BRAM/DSP counts + clock routing resource util |
| QoS suggestions | `report_qor_suggestions` | Vivado-recommended optimizations |

**Search approach:**
```bash
# Search for report files in likely locations
find . -name "*.rpt" -newer /dev/null 2>/dev/null | head -30
# Or check specific project paths
ls -la *.rpt 2>/dev/null
```

**Decision Point:**
- **Reports found** → Proceed to Step 2
- **No reports found** → **STOP.** Tell the user:
  > "I could not find existing congestion/utilization/routing report files. Please either:
  > 1. Point me to the report file paths, or
  > 2. Confirm you want me to generate them via Vivado (this may take several minutes on large designs)"
  
  If user confirms generation, use Vivado MCP to generate reports.
  **⚠️ IMPORTANT: `-return_string` and `-file` cannot be used together.** Use `-file` only:
  ```tcl
  file mkdir vivado_agentic_ai_reports/congestion-analysis
  ```
  ```tcl
  report_design_analysis -congestion -complexity -file vivado_agentic_ai_reports/congestion-analysis/design_analysis.rpt
  ```
  ```tcl
  report_clock_utilization -file vivado_agentic_ai_reports/congestion-analysis/clock_util.rpt
  ```
  ```tcl
  report_utilization -file vivado_agentic_ai_reports/congestion-analysis/utilization.rpt
  ```
  ```tcl
  report_route_status -file vivado_agentic_ai_reports/congestion-analysis/route_status.rpt
  ```
  ```tcl
  report_timing_summary -file vivado_agentic_ai_reports/congestion-analysis/timing_summary.rpt
  ```
  Also query HLUTNM count directly (not available in standard reports):
  ```tcl
  puts "HLUTNM:[llength [get_cells -hier -filter {SOFT_HLUTNM != \"\" || HLUTNM != \"\"}]]"
  ```

**Success Criteria:**
- [x] At least congestion OR utilization report located
- [x] File paths recorded for parsing

---

### Step 2: Parse Placement Congestion Data
**Objective:** Extract placement-phase congestion metrics from reports

**Parse from congestion report (`report_design_analysis -congestion`):**

Use `grep`/`sed`/`awk` to extract:

**⚠️ IMPORTANT: First check if the report actually contains congestion data.**
A `design_analysis.rpt` may exist but only contain `-timing` or `-complexity` sections.
```bash
# Check if congestion section exists
grep -c "Placer Final Level Congestion" <report.rpt>
# If 0, the report lacks -congestion flag → need to regenerate with -congestion
```

```bash
# Extract the placer congestion table (the key data)
grep -A 20 "Placer Final Level Congestion" <report.rpt>

# Look for "No effective congestion windows" message
grep "No effective congestion" <report.rpt>
```

**Placer congestion table format (Vivado 2025.x):**
```
| Direction | Type  | Level | Congestion | Window | Combined LUTs | Avg LUT Inputs | LUT | LUTRAM | Flop | MUXF | RAMB | URAM | DSP | CARRY | SRL | Cell Names |
| East      | Short |     5 |        89% | (CLEL_R_X10Y164,CLE_M_X26Y195) | 4% | 3.753 | 72% | 11% | 59% | 0% | 100% | NA | 91% | 6% | 25% | cell1(21%),cell2(20%) |
```

Parse each row to extract:
- `direction`: East/West/North/South
- `type`: Short/Long/Global
- `level`: 0-8 integer (UG1788 congestion level)
- `congestion_pct`: percentage (e.g., 89)
- `window`: site coordinate pair
- `resource_breakdown`: LUT/LUTRAM/Flop/BRAM/DSP/Carry/SRL percentages within the window
- `top_cells`: cell name(s) with contribution percentages

**Also check Router Initial Congestion section:**
```bash
grep -A 10 "Router Initial Congestion" <report.rpt>
```

**Parse from complexity report (`report_design_analysis -complexity`):**

**⚠️ Rent exponent may not be available.** Vivado may output:
> "No complexity report generated as cells satisfying given conditions are not present in the design."

Check for this condition before trying to parse Rent:
```bash
# Check if Rent data exists
grep -c "No complexity report generated" <report.rpt>
# If found, Rent is unavailable → set rent_exponent = null, add rent_note

# If Rent IS available:
grep -i "rent" <report.rpt>
grep -i "fanout\|fan-out" <report.rpt>
grep -i "logic level" <report.rpt>
```

**Parse from utilization report (`report_utilization`):**
```bash
# Extract global utilization summary
grep -E "CLB LUT|CLB Reg|Block RAM|DSP|URAM|CLB " <utilization_report.rpt> | head -20

# Extract SLR utilization (if -slr report exists)
grep -A 100 "SLR" <slr_utilization_report.rpt> | head -120
```

**Parse from clock utilization report (`report_clock_utilization`):**

This report provides per-clock-region resource counts that are not in the standard utilization report:
```bash
# Extract "Load Primitives" section — has per-CR FF, LUTRAM, BRAM, DSP counts
grep -n "Clock Regions : Load Primitives" <clock_util.rpt>
# Then read the table starting at that line number + ~8 lines for the header
# Each row: | Region | GClk Used/Avail | FF Used/Avail | LUTRAM Used/Avail | BRAM Used/Avail | DSP Used/Avail | GT | HARD IP |

# Extract Routing Resource Utilization — has per-CR HROUTE/HDISTR/VROUTE/VDISTR
grep -n "Routing Resource Utilization" <clock_util.rpt>
# Each row: | Region | HROUTES Used/Avail/% | HDISTRS Used/Avail/% | VROUTES Used/Avail/% | VDISTRS Used/Avail/% |
```

**⚠️ NOTE: Per-CR LUT count is NOT available from `report_clock_utilization`.** 
Only FF, LUTRAM, BRAM, DSP are available per CR. For per-CR total LUT counts, you would need
`report_utilization` with specific options or Tcl queries.

**Data to collect (populate into JSON):**

```
placement_congestion:
  global_congestion:
    north: <int or null>    # congestion level 0-8 (UG1788), null if no window reported
    south: <int or null>
    east: <int or null>
    west: <int or null>
    max_direction: <string>
    max_value: <int>
  congestion_windows: [  # from Placer Final Level Congestion Reporting
    {
      direction: "East",
      type: "Short",
      level: 5,
      congestion_pct: 89,
      window: "(CLEL_R_X10Y164,CLE_M_X26Y195)",
      combined_luts_pct: 4,
      avg_lut_inputs: 3.753,
      resource_breakdown: {
        lut_pct: 72, lutram_pct: 11, flop_pct: 59, muxf_pct: 0,
        bram_pct: 100, uram_pct: null, dsp_pct: 91, carry_pct: 6, srl_pct: 25
      },
      affected_clock_regions: ["X0Y2", "X0Y3", "X1Y2", "X1Y3"],  # from get_clock_regions -of_objects [get_tiles ...]
      top_cells: [
        { name: "inst_a/inst_b", short_name: "inst_b", module: "mod_A", parent_module: "mod_top", pct: 21,
          resources: { lut: 6234, ff: 8304, bram_tiles: 17, dsp: 116, srl: 1137 },
          placed_in_crs: ["X0Y2", "X1Y2"] },
        { name: "inst_a/inst_c", short_name: "inst_c", module: "mod_B", parent_module: "mod_top", pct: 20,
          resources: { lut: 6190, ff: 8350, bram_tiles: 17, dsp: 116, srl: 1137 },
          placed_in_crs: ["X0Y2", "X0Y3"] }
      ],
      congestion_type_summary:  # added at same level as congestion_windows
        short: { count: 2, max_level: 5, max_pct: 89, directions: ["East", "West"] }
        long: { count: 0, max_level: null, max_pct: null, directions: [] }
        note: "Only Short congestion detected..."
    }
  ]
  router_initial_congestion: <string>  # "No effective congestion windows..." or window details
  rent_exponent: <float or null>
  rent_note: <string or null>  # explanation if Rent unavailable
  avg_fanout: <float or null>
  logic_levels:
    avg: <float or null>
    max: <int>
  per_clock_region: [  # from report_clock_utilization "Load Primitives" section
    { region: "X0Y0", ff_used: 13358, ff_avail: 23040, ff_pct: 57.97,
      lutram_used: 1185, lutram_avail: 5760, lutram_pct: 20.57,
      bram_used: 72, bram_avail: 72, bram_pct: 100.0,
      dsp_used: 66, dsp_avail: 96, dsp_pct: 68.75 }
  ]
  per_clock_region_routing: [  # from report_clock_utilization "Routing Resource Utilization"
    { region: "X0Y0", hroute_pct: 0.0, hdistr_pct: 25.0, vroute_pct: 0.0, vdistr_pct: 0.0 }
  ]
  per_slr: [  # only for multi-SLR devices
    { slr: "SLR0", lut_pct: 65.3, ff_pct: 40.2, congestion_max: 2 }
  ]
  global_utilization:
    lut_used: <int>
    lut_available: <int>
    lut_pct: <float>
    ff_used: <int>
    ff_available: <int>
    ff_pct: <float>
    bram_used: <float>
    bram_available: <int>
    bram_pct: <float>
    dsp_used: <int>
    dsp_available: <int>
    dsp_pct: <float>
    clb_used: <int>
    clb_available: <int>
    clb_pct: <float>
    uram_used: <int>
    uram_available: <int>
    uram_pct: <float>
```

**Success Criteria:**
- [x] Congestion levels per direction extracted
- [x] Rent exponent captured (if available)
- [x] Per-clock-region utilization parsed

---

### Step 3: Parse Routing Congestion Data
**Objective:** Extract routing-phase congestion metrics from reports

**Parse from route status report (`report_route_status`):**
```bash
# Extract route status summary
grep -E "routed|unrouted|partial|conflict|antenna" <route_status.rpt>

# Extract net counts
grep -E "^[[:space:]]*[0-9]" <route_status.rpt> | head -20
```

**Parse from timing summary (`report_timing_summary`):**
```bash
# Extract WNS/WHS
grep -E "WNS|WHS|TNS|THS" <timing_summary.rpt>

# Extract worst setup paths
grep -A 5 "Worst.*Setup" <timing_summary.rpt>

# Extract worst hold paths
grep -A 5 "Worst.*Hold" <timing_summary.rpt>
```

**Data to collect:**

```
routing_congestion:
  route_status:
    nets_routed: <int>
    nets_unrouted: <int>
    nets_partial: <int>
    nets_conflicts: <int>
    nets_antennas: <int>
    route_completion_pct: <float>
  timing:
    wns: <float>
    whs: <float>
    tns: <float>
    ths: <float>
    failing_endpoints_setup: <int>
    failing_endpoints_hold: <int>
  timing_degradation:  # if both pre-route and post-route timing available
    wns_pre_route: <float>
    wns_post_route: <float>
    degradation_ns: <float>
    degradation_pct: <float>
```

**Note:** If routing reports don't exist (design is only placed, not yet routed), set `routing_congestion` to `null` in the JSON. This is valid — the skill works for placement-only analysis too.

**Success Criteria:**
- [x] Route status parsed (or noted as not available)
- [x] Post-route timing captured (if available)

---

### Step 4: Assess MUXF / Carry Chain / HLUTNM Impact
**Objective:** Quantify routing pressure from special structures

**If a Vivado session is active**, query directly:
```tcl
set muxf7 [llength [get_cells -hier -filter {PRIMITIVE_TYPE =~ CLB.MUXF.MUXF7}]]; set muxf8 [llength [get_cells -hier -filter {PRIMITIVE_TYPE =~ CLB.MUXF.MUXF8}]]; set carries [llength [get_cells -hier -filter {PRIMITIVE_TYPE =~ CLB.CARRY.*}]]; set hlutnm [llength [get_cells -hier -filter {HLUTNM != ""}]]; puts "MUXF7:$muxf7 MUXF8:$muxf8 CARRY:$carries HLUTNM:$hlutnm"
```

**If no Vivado session**, try parsing from utilization report:
```bash
# MUXF counts from utilization report
grep -E "MUXF7|MUXF8|F7 Mux|F8 Mux" <utilization_report.rpt>

# Carry chain counts
grep -i "carry" <utilization_report.rpt>
```

**Data to collect:**
```
routing_pressure:
  muxf7_count: <int>
  muxf8_count: <int>
  carry_count: <int>
  hlutnm_count: <int>  # may be null if not available from reports; query via Tcl
  primary_clock: <string>  # e.g. "clk300m (3.333 ns / 300 MHz)"
  primary_clock_loads: <int>  # from report_clock_utilization
```

**If these counts are unavailable from reports and no Vivado session exists**, set them to `null`. Do NOT open a DCP just to get these counts.

**Success Criteria:**
- [x] MUXF / carry / HLUTNM counts captured or noted as unavailable

---

### Step 5: Generate Recommendations
**Objective:** Produce prioritized actionable recommendations based on data

**Recommendation Engine (apply ALL that match):**

| Condition | Severity | Recommendation | Directive/Action |
|-----------|----------|---------------|-----------------|
| Rent > 0.65 | HIGH | Design has inherent routing complexity | `place_design -directive AltSpreadLogic_high` or device upgrade |
| Rent > 0.75 | CRITICAL | Severe routing complexity | Device upgrade or major design restructure |
| Any clock region LUT > 80% | HIGH | Over-utilized clock region(s) | `place_design -directive AltSpreadLogic_medium` |
| Any clock region LUT > 90% | CRITICAL | Severely over-utilized | `place_design -directive SpreadLogic_high` + floorplan review |
| Any CR BRAM >= 95% | HIGH | BRAM saturation in clock region | Convert to LUTRAM (RAM_STYLE distributed), re-architect storage |
| Multiple CRs BRAM == 100% | CRITICAL | BRAM saturation is likely primary congestion driver | Major BRAM reduction needed: LUTRAM, SRL chains, or device upgrade |
| Congestion window BRAM == 100% | CRITICAL | BRAM full inside congestion window | Spread BRAM-heavy modules with pblock constraints |
| Congestion level 4-5 | HIGH | Sub-optimal placement / QoR variation (UG1788) | `place_design -directive SpreadLogic_high` or AltSpreadLogic_high |
| Congestion level >= 6 | CRITICAL | Difficult P&R to unroutable (level 7+); severe QoR loss | Identify top cells from window (Cell Names column), spread with pblocks; reduce utilization/SLR load |
| Clock routing HDISTR >= 90% | CRITICAL | Clock distribution saturated | Reduce clock loads; BUFGCE_DIV; move modules to other CRs |
| Clock routing HROUTE > 100% | CRITICAL | Clock routing oversubscribed | Mandatory clock load reduction in that CR |
| Utilization imbalance > 30% | MEDIUM | Uneven placement | `place_design -directive AltSpreadLogic_medium` |
| MUXF count > 5000 | MEDIUM | MUXF routing overhead | Consider `synth_design -no_muxf` (trade LUTs for routability) |
| Unrouted nets > 0 | CRITICAL | Routing failed | Fix placement congestion first, then re-route |
| Route degradation > 0.5 ns | HIGH | Significant routing detour | `phys_opt_design -directive AggressiveExplore` post-route |
| Route degradation > 1.0 ns | CRITICAL | Severe routing detour | Re-place with spreading + re-route |
| Hold violations > 0 | MEDIUM | Hold violations from routing | `phys_opt_design -hold_fix -directive AggressiveExplore` |
| Multi-SLR, SLR imbalance > 15% | MEDIUM | SLR utilization imbalance | `place_design -directive SSI_SpreadLogic_high` |
| Multi-SLR, SLR imbalance > 25% | HIGH | Severe SLR imbalance | Floorplan with Pblocks to balance SLRs |

**Data to collect:**
```
recommendations: [
  {
    priority: 1,
    severity: "CRITICAL",
    category: "placement",
    finding: "Clock region X2Y3 at 92% LUT utilization",
    action: "Re-place with: place_design -directive SpreadLogic_high",
    expected_impact: "Distribute logic to neighboring regions, reducing peak utilization below 80%"
  }
]
```

**Success Criteria:**
- [x] Recommendations prioritized by severity
- [x] Each recommendation has specific directive/action
- [x] All matching conditions evaluated

---

### Step 6: Generate Assessment and Overall Scores
**Objective:** Compute overall congestion health scores

**Scoring:**

> **Congestion level scale (UG1788 / `report_design_analysis -congestion`):** levels
> run **0–8**, where a level `y` window spans `2^y × 2^y` INT tiles. Level 4 (16×16)
> = minor QoR variability; level 5 (32×32) = sub-optimal placement; level 6 (64×64)
> = difficult P&R and severe QoR loss; **level 7+ (128×128+) = effectively
> unroutable**. Score against this full 0–8 scale, not a 0–5 scale.

```
Placement Score (1-5):
  5 = Rent < 0.55 (or N/A), all regions < 65% LUT/BRAM, congestion ≤ 1
  4 = Rent < 0.60, all regions < 75% LUT/BRAM, congestion ≤ 3
  3 = Rent < 0.65, most regions < 80% LUT, congestion ≤ 4 (level 4: minor)
  2 = Rent < 0.70, some regions > 80% LUT or BRAM > 90%, congestion == 5
  1 = Rent ≥ 0.70, regions > 90% LUT, BRAM saturated in multiple CRs, or congestion ≥ 6 (level 6+: difficult→unroutable)
  
  NOTE: If Rent is unavailable (null), score based on congestion level, 
  utilization, and BRAM saturation only. Do not penalize for missing Rent.
  NOTE: BRAM saturation in congestion windows is a strong indicator — 
  if BRAM == 100% inside a congestion window, cap placement score at 1-2.

Routing Score (1-5):
  5 = All nets routed, WNS ≥ 0, no degradation
  4 = All nets routed, WNS ≥ 0, degradation < 0.2 ns
  3 = All nets routed, WNS < 0 but > -0.5 ns
  2 = All nets routed, WNS < -0.5 ns or partial unrouted
  1 = Unrouted nets or WNS < -1.0 ns

Overall Score: min(placement_score, routing_score) if both available,
              else whichever is available
```

**Data:**
```
assessment:
  placement_score: <int 1-5>
  routing_score: <int 1-5>  # null if routing not done
  overall_score: <int 1-5>
  overall_status: "GREEN" | "YELLOW" | "RED"
    GREEN = score >= 4
    YELLOW = score == 3
    RED = score <= 2
```

---

### Step 7: Write Output Files
**Objective:** Create all three output files

**⚠️ CRITICAL: Write ALL files before giving any summary.**

Create output directory:
```bash
mkdir -p vivado_agentic_ai_reports/congestion-analysis
```

#### 7a: Write `report_data.json`

Write the structured JSON file following the schema in [TEMPLATES.md](TEMPLATES.md). This file powers the dashboard.

**Location:** `vivado_agentic_ai_reports/congestion-analysis/report_data.json`

#### 7b: Write `REPORT.md`

Write the markdown report with executive summary, findings, and recommendations.

**Location:** `vivado_agentic_ai_reports/congestion-analysis/REPORT.md`

**Structure:**
```markdown
# Congestion Analysis Report

**Design:** [design_name]
**Device:** [part_number]
**Date:** [timestamp]
**Reports Analyzed:** [list of report files parsed]

## Executive Summary

| Metric | Value | Status |
|--------|-------|--------|
| Overall Score | X/5 | 🟢/🟡/🔴 |
| Placement Score | X/5 | 🟢/🟡/🔴 |
| Routing Score | X/5 | 🟢/🟡/🔴 |
| Rent Exponent | X.XX | ✅ / ⚠️ / ❌ |
| Max Congestion Level | N (direction) | ✅ / ⚠️ / ❌ |
| Over-Utilized Regions | N | ✅ / ⚠️ / ❌ |
| Unrouted Nets | N | ✅ / ❌ |
| WNS | X.XXX ns | ✅ / ❌ |

## Placement Congestion

### Congestion Levels
| Direction | Level | Assessment |
|-----------|-------|------------|
| North | X.X | ... |
| South | X.X | ... |
| East | X.X | ... |
| West | X.X | ... |

### Per-Clock-Region Utilization (Hot Regions)
| Region | LUT% | FF% | BRAM% | DSP% | Status |
|--------|------|-----|-------|------|--------|

### Routing Pressure
| Factor | Count | Impact |
|--------|-------|--------|
| MUXF7 | N | ... |
| MUXF8 | N | ... |
| Carry Chains | N | ... |

## Routing Congestion
[If routing data available]
### Route Status
| Category | Count |
|----------|-------|
| Routed | N |
| Unrouted | N |
| Partial | N |

### Timing
| Metric | Value |
|--------|-------|
| WNS | X.XXX ns |
| WHS | X.XXX ns |

## Recommendations
[Prioritized list from Step 5]

## Dashboard
Open `dashboard.html` in a browser to view the interactive dashboard:
\```bash
cd vivado_agentic_ai_reports/congestion-analysis && python3 -m http.server 8080
\```
Then navigate to `http://localhost:8080/dashboard.html`
```

#### 7c: Write `dashboard.html`

Copy the dashboard template from the skill folder:
```bash
cp <skill_folder>/DASHBOARD_TEMPLATE.html vivado_agentic_ai_reports/congestion-analysis/dashboard.html
```

Where `<skill_folder>` is the directory containing this SKILL.md. The dashboard loads `report_data.json` via `fetch()` at runtime.

**Dashboard Features:**
- **Congestion Hotspots tab (default):** Short vs Long congestion type breakdown, device floorplan heatmap with congestion window overlays (dashed borders on CR grid), congestion window detail cards with module correlation (module name, parent module, resource footprint, CR placement), contribution bar charts per window, module hierarchy tree with congestion attribution tags
- **Overview tab:** Global utilization bars, directional congestion compass, complexity metrics
- **Placement tab:** Per-CR FF/BRAM/DSP heatmaps (4×5 grid matching device clock regions), BRAM and DSP bar charts, detailed per-CR table with congestion window membership
- **Routing tab:** Clock routing resource heatmaps (HROUTE/HDISTR/VROUTE/VDISTR per CR), route status donut, timing KPIs, timing degradation chart
- **Recommendations tab:** Prioritized action cards with severity color coding, reference thresholds table

**\u26a0\ufe0f Dashboard data requirements:**
- `metadata.clock_region_grid` must be set for heatmaps: `{cols: 4, rows: 5, labels_x: ["X0","X1","X2","X3"], labels_y: ["Y0","Y1","Y2","Y3","Y4"]}`
- Per-CR data arrays must use region names matching grid labels (e.g., "X0Y0", "X2Y3")
- Null values are handled gracefully — displayed as "N/A" or "—"

**Success Criteria:**
- [x] `report_data.json` written with all collected metrics
- [x] `REPORT.md` written with executive summary + findings
- [x] `dashboard.html` copied to output directory
- [x] Dashboard URL printed for user

---

### Step 8: Generate Device Floorplan with Congestion Overlay *(Optional)*
**Objective:** Produce a spatial device floorplan visualization using the `device-floorplan` skill with congestion overlay data

> **Skip this step** if the user only wants the Chart.js dashboard, or if the `device-floorplan` skill is not available. The Step 7 dashboard already includes a CSS-based CR heatmap in the Hotspots tab. This step adds a full interactive device floorplan with site-level rendering, zoom/pan, and congestion overlays.

**Action:** Invoke the `device-floorplan` skill to generate the base viewer, populating its overlay placeholders with congestion-specific data derived from `report_data.json`.

#### 8a: Build Overlay Data from report_data.json

Using the data already collected in Steps 2-6, construct the overlay variables:

**`OVERLAY_TITLE`** — Set to the design name and congestion summary:
```javascript
const OVERLAY_TITLE = "Congestion Hotspot Map — " + (reportData.metadata.design || "Design");
```

**`OVERLAY_CR_FILLS`** — Semi-transparent clock region backgrounds colored by BRAM utilization (the primary congestion driver). Build from `placement_congestion.per_clock_region`:
```javascript
const OVERLAY_CR_FILLS = reportData.placement_congestion.per_clock_region.map(cr => ({
  cr: cr.region,                    // e.g. "X0Y3"
  color: cr.bram_pct >= 95 ? "rgba(248,113,113,0.25)"    // red — critical
       : cr.bram_pct >= 80 ? "rgba(251,191,36,0.20)"     // amber — warning
       : cr.bram_pct >= 50 ? "rgba(74,222,128,0.12)"     // green-dim — moderate
       :                     "rgba(74,222,128,0.06)"      // green-faint — low
}));
```

**`OVERLAY_RECTS`** — Rectangles around congestion window boundaries. Build from `placement_congestion.congestion_windows`:
```javascript
const OVERLAY_RECTS = reportData.placement_congestion.congestion_windows.map(w => {
  // Parse the affected CRs to find bounding box in CR coordinates
  const crs = w.affected_clock_regions || [];
  let minCol = Infinity, maxCol = -1, minRow = Infinity, maxRow = -1;
  crs.forEach(cr => {
    const m = cr.match(/X(\d+)Y(\d+)/);
    if (m) {
      minCol = Math.min(minCol, +m[1]); maxCol = Math.max(maxCol, +m[1]);
      minRow = Math.min(minRow, +m[2]); maxRow = Math.max(maxRow, +m[2]);
    }
  });
  return {
    cr_from: `X${minCol}Y${minRow}`,  // bottom-left CR of the window
    cr_to:   `X${maxCol}Y${maxRow}`,  // top-right CR of the window
    color:   w.direction === "East" ? "rgba(248,113,113,0.8)" : "rgba(251,146,60,0.8)",
    lineWidth: 2,
    dash: [6, 4],                      // dashed border
    label: `${w.direction} ${w.type} L${w.level} (${w.congestion_pct}%)`
  };
});
```

**`OVERLAY_LEGEND`** — Legend entries for the congestion color scale:
```javascript
const OVERLAY_LEGEND = [
  { color: "rgba(248,113,113,0.25)", label: "BRAM ≥95%" },
  { color: "rgba(251,191,36,0.20)",  label: "BRAM 80-95%" },
  { color: "rgba(74,222,128,0.12)",  label: "BRAM 50-80%" },
  { color: "rgba(74,222,128,0.06)",  label: "BRAM <50%" },
  { color: "rgba(248,113,113,0.8)",  label: "East Congestion Window", dash: true },
  { color: "rgba(251,146,60,0.8)",   label: "West Congestion Window", dash: true }
];
```

**`OVERLAY_SITE_HIGHLIGHTS`** — *(Optional)* If DCP-based cell placement data was collected, highlight specific sites where top-contributing cells are placed:
```javascript
const OVERLAY_SITE_HIGHLIGHTS = topContributingCells.map(cell => ({
  site: cell.placed_site,            // e.g. "SLICE_X42Y120"
  color: "rgba(168,139,250,0.9)",    // purple glow
  label: cell.short_name
}));
```

#### 8b: Invoke device-floorplan Skill

Pass the overlay variables when invoking the device-floorplan skill to generate the viewer. The device-floorplan skill accepts these as template substitution placeholders in the HTML template.

The resulting floorplan viewer will be saved alongside the dashboard:
```
vivado_agentic_ai_reports/congestion-analysis/
├── report_data.json          (Step 7a)
├── REPORT.md                 (Step 7b)
├── dashboard.html            (Step 7c — Chart.js analytics)
└── congestion_floorplan.html  (Step 8 — device floorplan with overlays)
```

**Success Criteria:**
- [x] `congestion_floorplan.html` renders the device with congestion CR fills and window boundaries
- [x] Zoom/pan works; CR colors match BRAM utilization severity
- [x] Congestion window dashed rectangles visible at zoomed-out view
- [x] Legend shows BRAM color scale and window type markers

---

### Decision Tree

```
START
  ↓
[Search for existing report files]
  ↓
[Reports found?]
  ├─ NO → STOP: Ask user for report paths or confirm generation
  └─ YES ↓
[Parse placement congestion data (Step 2)]
  ↓
[Routing reports available?]
  ├─ YES → Parse routing data (Step 3)
  └─ NO → Set routing_congestion = null
  ↓
[MUXF/carry data available?]
  ├─ YES → Capture counts (Step 4)
  └─ NO → Set routing_pressure = null
  ↓
[Generate recommendations (Step 5)]
  ↓
[Compute scores (Step 6)]
  ↓
[Write report_data.json + REPORT.md + dashboard.html (Step 7)]
  ↓
[User wants device floorplan overlay?]
  ├─ YES → Generate congestion floorplan via device-floorplan skill (Step 8)
  └─ NO → Skip
  ↓
EXIT with summary
```

---

## ⚠️ MANDATORY: Design-Specific Fix Rules

**All fixes MUST use ACTUAL names from the design. NO generic placeholders.**

| Rule | ❌ WRONG | ✅ CORRECT |
|------|----------|------------|
| Clock names | `clk_a`, `clk_b` | `HOSTCLK`, `GTX_CLK` |
| Cell paths | `*_sync_reg*` | `core_0/host_*_sync_reg*` |
| Clock regions | `X0Y0` generic | `X2Y3` (actual hot region) |
| Directives | "try a spreading directive" | `place_design -directive AltSpreadLogic_high` |
| Net names | `<net>` | `core_0/data_valid` |

Extract actual names from the parsed reports **before** generating output files.

---

## Mandatory Inputs **[MANDATORY]**

### Required Inputs

| Input Parameter | Type | Description | Validation | Example |
|----------------|------|-------------|------------|---------|
| report_files | file paths | At least 1 congestion-relevant report | Must exist | `congestion.rpt`, `utilization.rpt` |

### Optional Inputs

| Input Parameter | Type | Default | Description |
|----------------|------|---------|-------------|
| output_dir | string | `vivado_agentic_ai_reports/congestion-analysis` | Report output directory |
| utilization_threshold | float | 0.80 | LUT utilization threshold per clock region |
| rent_threshold | float | 0.65 | Rent exponent warning threshold |
| congestion_threshold | int | 3 | Congestion level triggering detailed analysis |

---

## Mandatory Output **[MANDATORY]**

### Output Files

| File | Format | Description |
|------|--------|-------------|
| `report_data.json` | JSON | Structured metrics (see [TEMPLATES.md](TEMPLATES.md)) |
| `REPORT.md` | Markdown | Human-readable summary with findings |
| `dashboard.html` | HTML | Interactive Chart.js dashboard |

All files are written to the output directory (default: `vivado_agentic_ai_reports/congestion-analysis/`).

---

## Error Handling **[MANDATORY]**

### Error 1: No Reports Found
**Symptom:** No `.rpt` files in expected locations
**Action:** Ask user for report paths or confirm report generation
**User Guidance:** "I could not find congestion/utilization report files. Please provide paths or confirm I should generate them."

### Error 2: Report Format Unrecognized
**Symptom:** grep/sed cannot parse expected fields
**Action:** Try reading full file for manual parsing; if still fails, skip that report and note in output
**User Guidance:** "Report format differs from expected Vivado output. Skipping [report_name]."

### Error 3: Vivado Session Required But Not Available
**Symptom:** User confirmed generation but no Vivado MCP session exists
**Action:** Guide user to start a Vivado session or open a DCP
**User Guidance:** "No active Vivado session. Start one with the DCP, then re-run this skill."

---

## Examples **[MANDATORY]**

### Example 1: Placement-Only Analysis (No Routing Yet)

**User Request:** "Analyze congestion on my placed design"

**Workflow:**
1. Find `congestion.rpt` and `utilization.rpt` in project directory
2. Parse: Congestion level 3 (East), Rent 0.62, clock region X2Y1 at 85% LUT
3. No routing reports → `routing_congestion = null`
4. Recommendation: `place_design -directive AltSpreadLogic_medium` before routing
5. Output: JSON + REPORT.md + dashboard with Placement tab active, Routing tab shows "Not yet routed"

### Example 2: Full Placement + Routing Analysis

**User Request:** "Check congestion, routing just failed with unrouted nets"

**Workflow:**
1. Find congestion, utilization, route_status, and timing reports
2. Parse placement: Congestion level 4 (East/West), Rent 0.68, two regions > 85% LUT
3. Parse routing: 47 unrouted nets, WNS = -0.342 ns
4. Correlate: Unrouted nets concentrated in X2Y2-X2Y3 (same high-utilization regions)
5. Recommendation: Priority 1 — `place_design -directive SpreadLogic_high`, re-route
6. Output: Full JSON + REPORT + dashboard with all 4 tabs populated

### Example 3: User Points to Custom Report Paths

**User Request:** "Analyze congestion — reports are in /data/project/reports/"

**Workflow:**
1. Check `/data/project/reports/` for `.rpt` files
2. Match files to report types by content inspection (grep headers)
3. Parse and produce output normally

---

## Integration

### Related Skills

**Upstream (Run Before):**
- **opt-design-analysis**: Verify optimization quality before checking congestion
- **synth-design-analysis**: Check synthesis quality

**Downstream (Run After):**
- **phys-opt-design-analysis**: Physical optimization after addressing congestion
- **route-design-analysis**: Detailed routing failure analysis (complements this skill's routing section)
- **versal-timing-closure-methodology**: Full timing closure flow including congestion

**Complementary Skills:**
- **device-floorplan**: Spatial device visualization with congestion overlays (Step 8) — reuse its generic overlay primitives for CR fills, congestion window boundaries, and site highlights
- **fanout-opt**: If congestion is driven by high fanout nets
- **clock-tree-topology-review**: If clock congestion is significant

---

## Key Congestion Thresholds

| Metric | Green (✅) | Yellow (⚠️) | Red (❌) |
|--------|-----------|-------------|---------|
| LUT per clock region | < 70% | 70-80% | > 80% |
| Rent exponent | < 0.55 | 0.55-0.65 | > 0.65 |
| Congestion level | 0-3 | 4-5 | 6+ |
| Unrouted nets | 0 | — | > 0 |
| Route WNS degradation | < 0.1 ns | 0.1-0.5 ns | > 0.5 ns |
| SLR util imbalance | < 10% | 10-20% | > 20% |

---

## References

### Vivado Documentation
- **UG906**: Design Analysis and Closure Techniques — `report_design_analysis`, congestion methodology
- **UG904**: Vivado Implementation Guide — `place_design` and `route_design` directives
- **UG949**: UltraFast Design Methodology Guide — congestion avoidance, utilization guidelines
- **UG835**: Vivado TCL Commands Reference

---

## Metadata

**Trigger Phrases:**
- "congestion analysis"
- "routing congestion"
- "placement congestion"
- "Rent exponent"
- "clock region utilization"
- "over-utilized"
- "congestion hotspot"
- "congestion dashboard"
- "congestion heatmap"
- "unroutable nets"
- "why is routing failing"

**Keywords:** congestion, placement, routing, Rent, utilization, clock-region, MUXF, carry-chain, AltSpreadLogic, SSI_SpreadLogic, routing-pressure, heatmap, dashboard

**Confidence Threshold:** 0.80

---

## Changelog

### Version 1.3.0
- **Device floorplan integration** — New optional Step 8 invokes the `device-floorplan` skill to generate an interactive spatial visualization with congestion overlays:
  - CR fills colored by BRAM utilization (primary congestion driver)
  - Dashed rectangle overlays for congestion window boundaries
  - Optional site-level highlights for top contributing cells
  - Full zoom/pan/hover on the actual device floorplan (not just a CSS grid)
- Added `device-floorplan` as complementary skill in Integration section
- Ported from internal repo to team repo (`skills/vivado/` format)

### Version 1.2.0 (2026-03-28)
- **Congestion Hotspots tab** — new default tab with:
  - Short vs Long congestion type breakdown cards
  - Device floorplan heatmap with congestion window overlays (dashed borders showing affected CRs)
  - Module hierarchy tree with congestion attribution tags
  - Per-window contribution bar charts (Chart.js horizontal bars)
  - Enhanced cell data: module name, parent module, resource footprint, CR placement
- New data model fields: `affected_clock_regions`, `congestion_type_summary`, `module_hierarchy`, `top_cells[].short_name`, `top_cells[].module`, `top_cells[].parent_module`, `top_cells[].resources`, `top_cells[].placed_in_crs`
- When DCP is available, queries Vivado for: `get_clock_regions -of_objects [get_tiles ...]` to map window tiles to CRs; `get_property REF_NAME` for module names; `report_utilization -cells` for per-module resources; `get_cells -filter IS_PRIMITIVE` placed sites for CR attribution
- CR detail table now shows which congestion window(s) affect each CR

### Version 1.1.0 (2026-03-28)
- Added lessons learned: checking for -congestion flag, Rent unavailability, -return_string/-file exclusion, clock_util.rpt as data source, BRAM/clock routing rules in recommendation engine

### Version 1.0.0 (2026-03-28)
- Initial release
- Unified placement + routing congestion analysis
- Report-first approach (no DCP required by default)
- Structured JSON output (report_data.json)
- Interactive HTML dashboard (dashboard.html)
- Replaces `place-design-congestion-analysis` (placement only) and `congestion-analysis-ep` (E&P specific)
