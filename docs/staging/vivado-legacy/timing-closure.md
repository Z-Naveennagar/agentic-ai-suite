<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Timing Closure Prototype

**Category:** Design Closure
Iterative timing analysis, constraint generation, and re-implementation — fully AI-driven.

## Overview

Timing closure is the most challenging and time-consuming phase of FPGA design. This example includes **two complementary agent skills** that work together as a complete methodology:

1. **`post-route-dcp-analysis`** — Opens a routed DCP, classifies all failing timing paths by root cause (CDC, SLR crossing, high fanout, long logic), and walks you through each category interactively — highlighting one representative critical path per category in the Vivado GUI with distinct colors.

2. **`timing-closure-prototype`** — Takes the classified violations and generates a `timing_fixes.xdc` constraint file with real design names, reruns implementation, and validates — iterating up to 3 times until timing closes or escalation is needed.

The recommended workflow is: **analyze first** (skill 1), then **fix** (skill 2).

The included design — `top_design` — is intentionally constructed with multiple categories of timing violations on an SSI (multi-SLR) device.

> This skill requires a **running Vivado MCP server** to open DCPs, run reports, apply constraints, and rerun implementation interactively.

## What's Included

```
timing-closure-prototype/
├── src/
│   └── top_design.sv                                       # Multi-clock datapath
├── constraints/
│   └── top_design.xdc                                      # Placement & clock constraints
├── recreate_project.tcl                                     # Build script
├── timing_fixes.xdc                                         # Reference: generated fixes
├── prompts.md                                               # Prompt library
└── .claude/skills/
    ├── post-route-dcp-analysis/                             # Skill 1: Analyze & visualize
    │   ├── SKILL.md
    │   └── reference/
    │       ├── classification.md
    │       └── highlighting.md
    └── timing-closure-prototype/                            # Skill 2: Fix & iterate
        ├── SKILL.md
        └── reference/
            ├── classification.md
            ├── cdc-fixes.md
            ├── slr-fixes.md
            ├── fanout-fixes.md
            ├── logic-fixes.md
            ├── rerun-strategy.md
            └── validate.md
```

## Two-Skill Workflow

```
  SKILL 1: post-route-dcp-analysis
  ─────────────────────────────────
  Phase 1: ANALYZE
  • Open routed DCP
  • Capture baseline (WNS, TNS, failing path count)
  • Classify paths: CDC / SLR / Fanout / Logic
  • DONT_TOUCH census
  ── USER GATE 1: Review classification ──

  Phase 2: HIGHLIGHT (Interactive)
  • Walk through each category one at a time
  • Highlight representative critical path in Vivado GUI
  • Color-coded: Red=CDC, Blue=SLR, Orange=Fanout, Green=Long Logic
  ── USER GATE per category ──

  SKILL 2: timing-closure-prototype
  ──────────────────────────────────
  Phase 1: GENERATE CONSTRAINTS
  • Generate timing_fixes.xdc with real names
  • Verify constraints parse without errors
  ── USER GATE: Review constraints ──

  Phase 2: RERUN & VALIDATE
  • Rerun implementation
  • Compare against baseline
  • Iterate (max 3) or escalate
```

## Step-by-Step Instructions

### Step 1 — Build the design

```bash
cd timing-closure-prototype/
vivado -mode batch -source recreate_project.tcl
```

This produces a routed DCP at `top_design/top_design.runs/impl_1/top_design_routed.dcp`.

### Step 2 — Analyze and visualize (Skill 1)

```
Open the routed DCP top_design/top_design.runs/impl_1/top_design_routed.dcp
and run the post-route-dcp-analysis skill to classify and highlight the
failing paths.
```

### Step 3 — Fix timing violations (Skill 2)

```
Now run the timing-closure-prototype skill to generate constraints and
close timing.
```

The agent will generate `timing_fixes.xdc`, present it for review, rerun implementation, and iterate.

## Path Classification

| Priority | Category | Color | Condition | Fix Approach |
|----------|----------|-------|-----------|-------------|
| 1 | **CDC** | Red | Different source/destination clocks | `set_false_path` or `set_max_delay -datapath_only` |
| 2 | **SLR Crossing** | Blue | Different SLRs, same clock domain | Register slicing, Pblock, or Laguna flops |
| 3 | **High Fanout** | Orange | Fanout > 1000, route delay > 80% | `MAX_FANOUT` constraint, driver replication |
| 4 | **Long Logic** | Green | Logic levels exceed frequency threshold | `LUT_REMAP`, pipeline insertion |

## Reference Output

The included `timing_fixes.xdc` shows constraints from a successful run that closed all timing (WNS improved from **-0.753 ns** to **+0.824 ns**, eliminating all 2,348 failing endpoints).

## What You'll Learn

- How to **visually identify** timing violations in the Vivado GUI with color-coded path highlighting
- How a **two-skill workflow** (analyze & visualize → fix & iterate) provides full visibility before taking action
- How to classify failing paths by root cause — CDC crossings, SLR boundaries, high fanout nets, and deep logic levels
- How the skill generates **real XDC constraints** using actual cell/net/clock names
- How **user gates** keep you in control — the agent presents analysis and constraints for review before applying changes

## Prompt Library

**Recommended Flow (Two Skills):**

Step 1 — Analyze & visualize:
```
Open the routed DCP top_design/top_design.runs/impl_1/top_design_routed.dcp
and run the post-route-dcp-analysis skill to classify and highlight the
failing paths.
```

Step 2 — Fix & iterate:
```
Now run the timing-closure-prototype skill to generate constraints and
close timing.
```

**Baseline capture:**
```
Open top_design/top_design.runs/impl_1/top_design.dcp and tell me: what's the WNS, TNS, and how many paths are failing?
```

**Classification breakdown:**
```
Classify all failing timing paths into categories: CDC, SLR crossing, high fanout, and long logic. Show me a summary table.
```

**Generate constraints:**
```
Generate timing_fixes.xdc with constraints for all classified violations. Show me the file before applying.
```

**Rerun implementation:**
```
Apply the timing_fixes.xdc and rerun implementation. Compare results against the baseline.
```

**Continue iterating:**
```
The first iteration improved WNS but timing still isn't met. Continue to iteration 2.
```

**Constraint best practices:**
```
What are the guardrails for timing constraints? What mistakes should I avoid with DONT_TOUCH and set_clock_groups?
```

<p class="sphinxhide" align="center"><sub>Copyright &copy; 2026 Advanced Micro Devices, Inc</sub></p>
<p class="sphinxhide" align="center"><sup><a href="https://www.amd.com/en/corporate/copyright">Terms and Conditions</a></sup></p>
