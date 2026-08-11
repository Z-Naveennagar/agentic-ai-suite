<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Opt Design Log Analysis

**Category:** Design Analysis
Parse and analyze `opt_design` logs for actionable insights — including `-debug_log` constraint attribution.

## Overview

The `opt_design` step produces detailed logs about what optimizations were applied (retarget, constant propagation, sweep, BUFG insertion, SRL, remap) and their impact. When `DONT_TOUCH` or `MARK_DEBUG` attributes are present, they block optimizations — but the standard log only tells you *how many* objects are constrained, not *which ones*.

This example uses Vivado's `-debug_log` flag to reveal **exactly** which cells and nets are blocked, and in which phases. The AI agent parses the log, surfaces the constraint attribution data, and recommends which `DONT_TOUCH` attributes to review.

## What's Included

```
opt-design-analysis/
├── recreate_project.tcl                        # Tcl script to build project & run opt_design -debug_log
├── src/
│   ├── opt_design_demo.v                       # Demo design with 10 optimization patterns
│   └── bram_block.v                            # BRAM instantiation module
├── constraints/
│   └── constraints.xdc                         # 200 MHz clock constraint
├── prompts.md                                  # Prompt library
└── .claude/skills/opt-design-analysis/         # Bundled agent skill
    ├── SKILL.md
    └── DASHBOARD_TEMPLATE.html                 # Interactive dashboard template
```

## Design Patterns

The demo design (`opt_design_demo.v`) contains 10 intentional patterns that exercise different `opt_design` phases:

| Pattern | RTL Construct | Phase Targeted |
|---------|---------------|----------------|
| High-fanout enable | 1-bit `enable` driving 256 registers | BUFG insertion |
| SRL chain | 16-stage shift register | Shift Register Optimization |
| Constant propagation | Registers with constant `8'hAA` input | Constant Propagation |
| Carry chain | 32-bit accumulator | Retarget / Carry remap |
| Dead logic | Disconnected registers | Sweep |
| Control set fragmentation | Same data, different enables per bit | Control set merge |
| DONT_TOUCH registers | `(* DONT_TOUCH = "TRUE" *)` on `keep_me_reg` | Blocks Retarget, PropConst, Sweep, Remap |
| MARK_DEBUG signals | `(* MARK_DEBUG = "TRUE" *)` on `debug_reg` nets | Blocks Sweep (via implicit DONT_TOUCH) |
| BRAM instantiation | Dual-port BRAM in READ_FIRST mode | BRAM Power Opt |
| MUX tree | 4-input priority MUX → 16-bit output | MUXF optimization |

## Step-by-Step Instructions

### Step 1 — Recreate the project and run opt_design

```bash
cd opt-design-analysis/
vivado -mode batch -source recreate_project.tcl
```

> This takes approximately 1–2 minutes. The script targets `xcu200-fsgd2104-2-e` (Alveo U200) at 200 MHz.

### Step 2 — Run the opt-design-analysis skill

Open the project folder in your IDE and start the AI agent:

**Full analysis:**
```
Analyze the opt_design log for this project and generate a full report.
```

> No live Vivado session is needed. The analysis skill parses the implementation log file.

### Step 3 — What to expect

The agent will:

1. Find the `vivado.log` in the project directory
2. Scope its grep to the `opt_design` section
3. Extract the command, summary table, and completion status
4. Parse `-debug_log` constraint attribution messages (`[Opt 31-1019]`, `[Opt 31-1020]`)
5. Identify which cells/nets are blocked and in which phases
6. Group constraints by type (DONT_TOUCH Cell vs. DONT_TOUCH Net)
7. Generate three output files:
    - `REPORT.md` — Markdown report with per-phase breakdown and prioritized recommendations
    - `report_data.json` — Structured JSON with all extracted metrics
    - `dashboard.html` — Interactive Chart.js dashboard

## Expected Results

### Summary Table

With the intentional `DONT_TOUCH` and `MARK_DEBUG` attributes, all phases show blocked optimizations:

| Phase | #Cells Created | #Cells Removed | #Constrained Objects |
|-------|---------------|----------------|---------------------|
| Retarget | 0 | 0 | **8** |
| Constant propagation | 0 | 0 | **8** |
| Sweep | 0 | 0 | **24** |
| BUFG optimization | 0 | 0 | 0 |
| Shift Register Optimization | 0 | 0 | 0 |
| Remap | 0 | 0 | **16** |
| Post Processing Netlist | 0 | 0 | **8** |

## What You'll Learn

- How **`-debug_log`** transforms opaque "constrained objects" counts into specific cell/net names with percentage attribution
- How `DONT_TOUCH` and `MARK_DEBUG` propagate through opt_design phases — a single attribute blocks 5+ phases
- How to read `[Opt 31-1019]` messages to identify the highest-impact constraints to review
- How a single prompt like *"Analyze the opt_design log"* triggers a multi-step workflow

## Prompt Library

**Quick summary:**
```
Show me the opt_design summary table — how many cells were created, removed, and constrained in each phase?
```

**Full analysis with recommendations:**
```
Run the opt-design-analysis skill on this project. Give me the full report with per-phase breakdown and recommendations.
```

**debug_log deep-dive:**
```
The log was run with -debug_log. Show me exactly which cells and nets have DONT_TOUCH and how much optimization they are blocking per phase.
```

**Constraint attribution:**
```
Group the [Opt 31-1019] messages by constraint type. Which DONT_TOUCH cells are blocking the most optimization across all phases?
```

**Actionable cleanup:**
```
Which DONT_TOUCH attributes can be safely removed to improve optimization? Are any of them blocking optimization in 4+ phases?
```

**Directive comparison:**
```
I used ExploreWithRemap. Would a different directive have been better for this design?
```

**Re-run with debug_log:**
```
The log shows constrained objects but no detail. Re-run opt_design with -debug_log and analyze the results.
```

<p class="sphinxhide" align="center"><sub>Copyright &copy; 2026 Advanced Micro Devices, Inc</sub></p>
<p class="sphinxhide" align="center"><sup><a href="https://www.amd.com/en/corporate/copyright">Terms and Conditions</a></sup></p>
