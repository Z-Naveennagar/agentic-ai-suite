<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# TEMPLATE.md — Annotated SKILL.md Template for Vivado MCP Skills

Use this template when creating a new Vivado skill. Copy the structure, replace bracketed placeholders with your content, and delete sections marked `(optional)` if they don't apply.

---

## The Template

````markdown
---
name: your-skill-name
description: >
  One-sentence summary of what the skill does. Include the Vivado design stage
  (post-synthesis, post-place, etc.) and the primary Vivado command(s). Use when
  user asks to "[trigger phrase 1]", "[trigger phrase 2]", "[trigger phrase 3]",
  or when [contextual trigger]. Also trigger for [related scenario].
---

# Your Skill Title

## Overview (optional — use for complex skills)

**Purpose:** One-sentence description of what the skill analyzes or produces.

**Output:** `vivado_agentic_ai_reports/<skill-name>/`
- `<raw_report>.rpt` — raw Vivado report
- `REPORT.md` — markdown report with **copy-pasteable fixes** (ACTUAL design names, no placeholders)

**Prerequisites:** [Design stage] complete, [constraints type] loaded.

**Output format:** The REPORT.md **must** include copy-pasteable Tcl/XDC fixes for each violation type found. Optionally, create an [output-template.md](output-template.md) to define the exact report structure.

---

## Prerequisites

| Requirement | Details |
|---|---|
| Vivado version | [version] or later ([recommended version]+ recommended) |
| Target family | [families] (e.g., Ultrascale+ xczu*, xcku*, xcvu*) |
| Design state | [e.g., Synthesis 100% complete, timing constraints applied] |
| Open project | [e.g., A Vivado project (.xpr) or checkpoint (.dcp) must be available] |
| Vivado session | Connected via the MCP Vivado bridge (`mcp_vivado_connect`) or interactive Tcl console |

---

## Efficiency Guidelines

- **Pass `session_id`** to every `vivado_execute` call when a Vivado session is active.
- **Write reports to file** — do not output full report content in chat; give a short summary only.
- **Read reports efficiently** — use `grep`, `sed`, or `awk` via terminal to extract specific sections instead of reading entire files into context. Use `wc -l` + `head` to check size first. Full `read_file` is fine only for small reports (<200 lines).
- **Do NOT** use `shell ls`, `shell find`, or `shell glob` to locate files.
- **Do NOT** use Vivado Tcl (`exec cat`, `open`, `read`) to read files. Use `grep`/`sed` via terminal or `read_file` with line ranges.
- **Do NOT** retry a failed Tcl command with different syntax. Report the error and stop or proceed.

---

## Workflow (Autonomous)

**⚠️ CRITICAL: Execute steps SEQUENTIALLY. Wait for each command to complete.**

**⚠️ The workflow is incomplete until REPORT.md exists.** Do not end your turn before calling the write tool to create the file. Do not narrate ("Now generating...") or summarize before writing — invoke the write tool first. Only after the file is written, give a short summary.

```
[Skill Name] Progress:
- [ ] Step 1: [Open design, create dir, run report_X -file]
- [ ] Step 2: [Parse report, extract ACTUAL names]
- [ ] Step 3: [Generate REPORT.md (call write tool), then short summary in chat]
```

### Step 1: Open Design, Create Dir, Run Report (single call)

**DCP workspace:** If workspace has `.dcp` and no `.xpr`, use `open_checkpoint`. Otherwise use `open_run synth_1`.

```tcl
set dcp [lindex [glob -nocomplain *.dcp] 0]; if {$dcp != ""} { open_checkpoint $dcp } elseif {[catch {current_design}]} { open_run synth_1 }; file mkdir vivado_agentic_ai_reports/<skill-name>; <your_report_command> -file vivado_agentic_ai_reports/<skill-name>/<report>.rpt; puts "Design: [current_design]"
```

Use `timeout_seconds: [value]` for commands that may run long. Guidelines:
- `report_*` commands: 120 seconds is usually sufficient
- `synth_design`: 18000 seconds (5 hours) — synthesis can run very long on large designs
- `opt_design`: 18000 seconds (5 hours)
- `place_design` / `route_design`: 18000 seconds (5 hours) each

### Step 2: Parse Report

Parse `vivado_agentic_ai_reports/<skill-name>/<report>.rpt`. Do NOT use Vivado Tcl to read it.

**Reading strategy** (choose based on file size):
- **Small report (<200 lines):** Read with `read_file` tool directly.
- **Medium report (200–2000 lines):** Use `grep -n "<pattern>"` to find line numbers of interest, then `read_file` with specific line ranges, or `sed -n 'start,endp'`.
- **Large report (>2000 lines):** Use `wc -l` + `head -50` to see structure, then targeted `grep`/`sed`/`awk` to extract only the sections needed.

Provide the **grep patterns** the agent should use for this skill's report format:
```bash
# [Example: find all violations]
grep -n "<VIOLATION_PATTERN>" vivado_agentic_ai_reports/<skill-name>/<report>.rpt
# [Example: extract a specific section]
sed -n '/^Section Header/,/^$/p' vivado_agentic_ai_reports/<skill-name>/<report>.rpt
```

Extract:
- [Describe what to extract — violation IDs, clock names, cell paths, etc.]
- [Describe how to identify actual design names from the report]

### Step 3: Generate Report with Copy-Pasteable Fixes

**Action:** Call the write tool to create `vivado_agentic_ai_reports/<skill-name>/REPORT.md`.

**MANDATORY:** For each [violation/finding] type found, include a **📋 Copy-Paste Fix** block with ACTUAL design names substituted. No generic placeholders — the user must be able to copy-paste directly into [XDC/RTL/Tcl].

**Order:** (1) Invoke the write tool with the full report content. (2) Only after the write succeeds, give a short summary. Do NOT output the report as response text. Do NOT say "Now generating..." without immediately invoking the write tool.

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

---

## Fix Templates (include one per violation type the skill detects)

### [VIOLATION-ID]: [Short Description]
```tcl
[Copy-pasteable Tcl/XDC with bracketed placeholder markers like [actual_clock_name]]
# Verify: [verification command]
```

---

## Decision Tree (optional — for skills with multiple modes)

```
[Describe the branching logic]
  ├─ [Condition A] → [Action A]
  └─ [Condition B]
      ├─ [Sub-condition] → [Action]
      └─ [Sub-condition] → [Action]
```

---

## Troubleshooting: REPORT.md Not Created (include in every skill that generates reports)

**Symptom:** Steps 1–2 complete (raw report parsed) but REPORT.md never appears.

**Root cause:** The agent outputs text ("Now I'll generate REPORT.md...") instead of invoking the write tool. A text-only response may end the turn before the file is written.

**Prevention:** Follow Step 3 order strictly — invoke the write tool first, then summarize. Do not narrate before acting.

---

## Error Handling

| Error | Symptom | Action |
|-------|---------|--------|
| No design open | `ERROR: No current design` | `open_run synth_1` or `open_checkpoint` |
| [Prerequisite missing] | [Error message] | [Recovery action] |
| [Report command fails] | [Error message] | Log error, exit or continue |
| [Timeout] | Command exceeds timeout | Increase `timeout_seconds`, suggest smaller design |

---

## Validation

```tcl
if {[file exists "vivado_agentic_ai_reports/<skill-name>/<report>.rpt"]} {
    puts "✓ [Report name] generated"
}
```
Success: raw report exists, REPORT.md exists with copy-pasteable fixes using ACTUAL design names.

---

## References

- **UG[XXX]**: [Title] ([relevant section])
- **UG949**: UltraFast Design Methodology
- **AR [XXXXXXX]**: [Answer Record title] (if applicable)

````

---

## Template Usage Notes

### When to add optional sections

| Section | Add when... |
|---|---|
| Overview block | Skill has multiple outputs or modes |
| Decision tree | Skill has branching logic (Mode A/B, device-specific paths) |
| Resource estimation | Skill adds hardware to the design (ILA, debug cores) |
| Quick-reference command table | Skill uses 10+ distinct Tcl commands |
| Multi-clock / multi-domain | Skill behavior changes based on clock topology |
| Scripted helper procedure | The same Tcl proc is needed across multiple steps |
| Bundled Tcl/shell scripts | Complex log parsing, visualization, or data extraction |

### Sizing guidance

| Skill complexity | SKILL.md lines | Additional files |
|---|---|---|
| Simple (single report, one workflow) | 150–250 | None |
| Medium (report + fixes, one mode) | 250–400 | Optional REFERENCE.md |
| Complex (multiple modes, scripts, decision tree) | 400–500 | REFERENCE.md + TEMPLATES.md |
| Very complex (exceeds 500 lines) | 500 max | Must split into multiple files |

### Description writing formula

```
[Action verb] [what it analyzes] using [Vivado command] to [outcome].
Use when user asks to "[phrase 1]", "[phrase 2]", "[phrase 3]",
or when [contextual condition]. Also trigger for [related scenarios].
```
