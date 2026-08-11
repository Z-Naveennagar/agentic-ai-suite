<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# RTL Lint

**Category:** Design Analysis
Run `synth_design -lint` to catch RTL issues before full synthesis.

## Overview

RTL linting identifies design issues early — before you spend time on full synthesis. This example runs the Vivado RTL linter through an AI agent that categorizes findings, prioritizes them by severity, and recommends specific fixes.

The included design — a packet processor with header parsing, CRC checking, and an output FSM — contains realistic coding patterns that trigger multiple lint rule categories.

## What's Included

```
rtl-lint/
├── packet_processor.xpr                  # Vivado 2025.2 project (xcvu9p)
├── packet_processor.srcs/
│   ├── sources_1/.../packet_processor.sv  # SystemVerilog source
│   └── constrs_1/.../packet_processor.xdc # Timing constraints
├── prompts.md                             # Prompt library
└── .claude/skills/rtl-lint/               # Bundled agent skill
    ├── SKILL.md
    ├── parse_lint_report.py
    └── resolution/                        # 20 rule-specific fix guides
```

## Step-by-Step Instructions

### Step 1 — Download and open the example

Download `vivado-ai-assistant-examples-0.6.8.zip`, unzip it, and open the `rtl-lint/` folder as your workspace in VS Code.

### Step 2 — Verify MCP server is configured

Make sure your MCP configuration points to the Vivado MCP server. See the Getting Started section of this guide.

### Step 3 — Start Vivado

You can either let the AI agent start Vivado for you (just ask *"Start a Vivado session"*), or launch it manually:

```bash
vivado -mode tcl
```

> **Why recreate the project from TCL?** The example includes a `recreate_project.tcl` script rather than the full `.xpr` project directory. This keeps the download small. If you encounter errors when sourcing the script, simply ask the agent: *"Build the Vivado project by sourcing the recreate_project.tcl script"* — it will handle any Vivado version-specific parameter differences automatically.

### Step 4 — Run the RTL lint skill

Open your AI agent chat and use one of these prompts:

**Basic:**
```
Run RTL lint on this design using the rtl-lint skill.
```

**With fixes:**
```
Run RTL lint on the packet_processor design, then fix all violations in the source file.
```

**Fix and re-verify:**
```
Run RTL lint, apply fixes to packet_processor.sv, then re-run lint to confirm all issues are resolved.
```

### Step 5 — What to expect

The agent will:

1. Open the `packet_processor.xpr` project
2. Run `synth_design -top packet_processor -part xcvu9p-flga2104-2L-e -lint`
3. Parse the lint report using the bundled `parse_lint_report.py`
4. Look up each violation in the `resolution/` guides
5. Generate a structured report with severity, source location, and fix recommendations
6. Optionally apply fixes directly to `packet_processor.sv`

### Step 6 — Review the report

The agent produces a markdown report under `vivado_agentic_ai_reports/rtl-lint/` with:

- **Summary table** — violation counts by rule ID and severity
- **Per-violation details** — source code context, root cause, and recommended fix
- **Hotspot analysis** — which files/modules have the most issues

## Expected Violations

This design triggers **8 violations across 4 rule types**:

| Rule | Severity | Count | What It Catches |
|------|----------|-------|-----------------|
| **ASSIGN-3** | CRITICAL WARNING | 1 | Shift amount exceeds operand width |
| **ASSIGN-6** | WARNING | 1 | Signal assigned but never read |
| **INFER-1** | CRITICAL WARNING | 4 | Unintended latch inference |
| **INFER-2** | CRITICAL WARNING | 2 | Case statement missing default branch |

## What You'll Learn

- How **natural language prompts** drive complete Vivado workflows — you describe what you want in plain English, the agent skill translates it into the right sequence of Tcl commands
- How a single prompt like *"Run RTL lint and fix all issues"* triggers a multi-step workflow: project discovery → linter execution → report parsing → resolution guide lookup → code fixes
- How **skills** bridge the gap between your intent and Vivado expertise
- The iterative fix → re-lint loop, driven entirely by conversational prompts

## Prompt Library

**First-time run:**
```
Run RTL lint on this design using the rtl-lint skill.
```

**Full analysis with report:**
```
Run RTL lint on the packet_processor design. Generate a full report with violation counts, severity breakdown, and fix recommendations.
```

**Focus on critical warnings only:**
```
Run RTL lint and show me only the critical warnings. What are the most urgent issues to fix?
```

**Latch inference deep-dive:**
```
Run RTL lint and explain any inferred latch violations. Show me the exact code causing them and how to fix it.
```

**Analyze and fix all issues:**
```
Run RTL lint, then fix all the violations in the source code. Apply the fixes directly to packet_processor.sv.
```

**Fix and re-verify:**
```
Run RTL lint, apply fixes to the source file, then re-run lint to confirm all violations are resolved.
```

**Fix only specific rule:**
```
Run RTL lint. Fix only the INFER-2 (incomplete case statement) violations and leave everything else as-is.
```

**Best practices review:**
```
Run RTL lint and provide coding best-practice recommendations based on the results. Reference UG901 where applicable.
```

<p class="sphinxhide" align="center"><sub>Copyright &copy; 2026 Advanced Micro Devices, Inc</sub></p>
<p class="sphinxhide" align="center"><sup><a href="https://www.amd.com/en/corporate/copyright">Terms and Conditions</a></sup></p>
