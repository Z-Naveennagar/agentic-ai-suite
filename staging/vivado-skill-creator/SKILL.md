---
name: vivado-skill-creator
description: >
  Create, review, and improve agent skills for Vivado FPGA workflows using the Vivado MCP server.
  Use when a developer asks to "create a Vivado skill", "write a new skill for Vivado",
  "make an MCP skill", "improve my Vivado skill", "review my SKILL.md", "check my skill
  against best practices", or "help me write a skill for synthesis/implementation/timing/debug".
  Also use when someone says "new skill", "skill template", or "skill best practices" in the
  context of Vivado, FPGA, or hardware design automation.
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
# Vivado Skill Creator

Create and iteratively improve agent skills for Vivado FPGA design workflows that interact with the Vivado MCP server. This skill encodes tested patterns from production Vivado skills (RTL lint, CDC analysis, timing methodology, clock interaction, ILA insertion, clock-region placer debug, custom DRC) and Anthropic's official skill-authoring best practices.

At a high level, the process goes:

1. Understand the Vivado workflow the skill will automate
2. Draft the SKILL.md following the Vivado skill template
3. Test the skill against a real design using the Vivado MCP server
4. Review outputs with the developer, iterate until solid
5. Validate against the checklist

Your job is to figure out where the developer is in this process and help them progress. Maybe they have an existing skill that needs review — jump straight to the checklist. Maybe they want to start from scratch — begin with the interview.

---

## Understanding the developer

Vivado skill developers range from FPGA design experts with minimal prompting experience to AI engineers with limited FPGA knowledge. Pay attention to context cues:

- If they reference UG numbers (UG906, UG949), Tcl commands, or design stages — they know Vivado well; focus your help on skill structure and prompting patterns
- If they describe the workflow in general terms ("I want to check timing") — they know what they want but may need help with Vivado Tcl specifics; use `vivado_doc_search` to fill gaps
- Always explain *why* a pattern matters for the MCP context (e.g., "single-line Tcl because MCP executes each `vivado_execute` call as one atomic command")

---

## Creating a Vivado Skill

### Step 1: Capture Intent

Understand what Vivado workflow the skill automates. Extract answers from the conversation if the developer has already described their workflow, then confirm. Gather:

1. **What Vivado stage does this target?** — Pre-synthesis, post-synthesis, post-place, post-route, hardware debug, etc.
2. **What Vivado reports or commands does it use?** — e.g., `report_methodology`, `report_cdc`, `report_timing_summary`, `report_clock_utilization`, `synth_design -lint`
3. **What is the expected output?** — Raw Vivado report + agent-generated markdown REPORT.md? Tcl remediation script? Modified design? Dashboard?
4. **Does it need a loaded design?** — DCP workspace (`.dcp` files), project workspace (`.xpr`), or either?
5. **Does it produce copy-pasteable fixes?** — If yes, fixes must use actual design names, never placeholders
6. **What device families?** — UltraScale+, Versal, both, or family-independent?
7. **Are there bundled Tcl/shell scripts?** — Helper procs, log extractors, etc.

### Step 2: Interview and Research

Proactively ask about:

- **Supporting files**: "Do you have any supporting files to bundle with this skill? For example: Tcl helper procs (`.tcl`), reference guides (`.md`), constraint templates (`.xdc`), or shell scripts (`.sh`)?" If yes, ask the developer to share the content so you can incorporate it into the appropriate subdirectory (`tcl/`, `scripts/`, `references/`) per the skill directory structure in Step 3.
- **Edge cases**: What happens with single-clock designs? Designs with no violations? Enormous designs (200K+ line logs)?
- **Multi-mode workflows**: Does the skill need to handle both DCP and project workspaces? Interactive vs batch?
- **Dependencies on other skills**: Is this a leaf skill or an orchestrator?
- **Timeout-sensitive commands**: Which Vivado commands might run long? (`synth_design`, `place_design`, `route_design` can take minutes to hours)

If the developer describes a Vivado command you're unfamiliar with, use `vivado_doc_search` to look up correct syntax, properties, and options before writing the skill.

### Step 3: Write the SKILL.md

Read [TEMPLATE.md](TEMPLATE.md) for the full annotated template. The key sections every Vivado skill must have:

```
vivado-skill/
├── SKILL.md              # Main instructions (<500 lines)
├── REFERENCE.md          # Detailed tables, API docs (optional)
├── TEMPLATES.md          # Code templates (optional)
├── tcl/                  # Bundled Tcl procs (optional)
│   └── helper.tcl
└── scripts/              # Shell scripts (optional)
    └── extract_log.sh
```

**Mandatory SKILL.md components for Vivado skills:**

1. **YAML frontmatter** with `name` and `description` (include Vivado trigger phrases)
2. **Prerequisites table** — Vivado version, device family, design state, open project/DCP
3. **Efficiency Guidelines** — The MCP-specific DO/DON'T block (see [VIVADO-PATTERNS.md](VIVADO-PATTERNS.md))
4. **Workflow with progress tracker** — Sequential steps with inline checklist
5. **Tcl command blocks** — Single-line semicolon-chained for MCP execution
6. **Design-specific fix rules** — ACTUAL names mandate with WRONG/CORRECT table
7. **Error handling table** — Common errors → symptoms → actions
8. **Validation snippet** — Tcl to confirm the skill's work succeeded
9. **References** — UG numbers

**Sections to add when applicable:**

- **Report output template** — If the skill generates REPORT.md
- **Fix templates** — Copy-pasteable Tcl/XDC/Verilog with placeholder markers
- **Decision tree** — For skills with multiple modes or branching logic
- **Resource estimation** — For skills that add hardware (ILA, debug cores)
- **Quick-reference command table** — For complex skills with many Tcl commands
- **Troubleshooting checklist** — Common failure modes

### Step 4: Apply Vivado-Specific Patterns

Read [VIVADO-PATTERNS.md](VIVADO-PATTERNS.md) for the complete pattern catalog. The critical ones that every Vivado skill must follow:

**Pattern 1: MCP Efficiency Guidelines block** — Include this verbatim in every skill:

```markdown
## Efficiency Guidelines

- **Pass `session_id`** to every `vivado_execute` call when a Vivado session is active.
- **Write reports to file** — do not output full report content in chat; give a short summary only.
- **Read reports efficiently** — use `grep`, `sed`, or `awk` to extract specific sections from report files instead of reading entire files into context. Use `wc -l` + `head` to check size/structure first. Full `read_file` is fine only for small reports (<200 lines).
- **Do NOT** use `shell ls`, `shell find`, or `shell glob` to locate files.
- **Do NOT** use Vivado Tcl (`exec cat`, `open`, `read`) to read files. Use your file reader tool or `grep`/`sed` via terminal.
- **Do NOT** retry a failed Tcl command with different syntax. Report the error and stop or proceed.
```

**Pattern 2: Single-line Tcl for MCP execution** — All Tcl blocks must be semicolon-chained:

```tcl
# ✅ CORRECT
set dcp [lindex [glob -nocomplain *.dcp] 0]; if {$dcp != ""} { open_checkpoint $dcp } elseif {[catch {current_design}]} { open_run synth_1 }; file mkdir vivado_agentic_ai_reports/my-skill; puts "Design: [current_design]"

# ❌ WRONG — multi-line (MCP treats each vivado_execute as one atomic call)
set dcp [lindex [glob -nocomplain *.dcp] 0]
if {$dcp != ""} {
    open_checkpoint $dcp
}
```

**Pattern 3: Action-before-narration enforcement** — Include this in any skill that generates report files:

```markdown
**⚠️ The workflow is incomplete until REPORT.md exists.** Do not end your turn before
calling the write tool to create the file. Do not narrate ("Now generating...") or
summarize before writing — invoke the write tool first. Only after the file is written,
give a short summary.
```

**Pattern 4: Design-specific fix rules** — Include this table in any skill that recommends fixes:

```markdown
## ⚠️ MANDATORY: Design-Specific Fix Rules

**All fixes MUST use ACTUAL names from the design. NO generic placeholders.**

| Rule | ❌ WRONG | ✅ CORRECT |
|------|----------|------------|
| Clock names | `clk_a`, `clk_b` | `HOSTCLK`, `GTX_CLK` |
| Cell paths | `*_sync_reg*` | `core_0/host_*_sync_reg*` |
| MMCM pins | `mmcm/CLKOUT0` | `ios_0/mmcm_0/CLKOUT2` |
| Periods | `<period>` | `12.800` |
```

**Pattern 5: Standardized report output** — All skills write to the same directory tree:

```
vivado_agentic_ai_reports/<skill-name>/
├── <raw_report>.rpt    # Vivado's native output (-file flag)
└── REPORT.md           # Agent-generated markdown with fixes
```

**Pattern 6: Auto-detect workspace type** — Every workflow Step 1 must handle both DCP and project:

```tcl
set dcp [lindex [glob -nocomplain *.dcp] 0]; if {$dcp != ""} { open_checkpoint $dcp } elseif {[catch {current_design}]} { open_run synth_1 }
```

**Pattern 7: Compile-time optimized Tcl (UG835/UG894)** — All bundled Tcl scripts must follow these efficiency rules. Each violation adds unnecessary Tcl↔C++ round-trips that slow skill execution:

| Rule | ❌ Wrong | ✅ Correct |
|---|---|---|
| Cache object queries | `[get_clocks]` called 3× in a proc | `set clks [get_clocks]; reuse $clks` |
| Vectorize `get_property` | `get_property LOC $cell` inside foreach | `get_property LOC $cells` on whole list |
| Push filter to C++ layer | foreach loop with Tcl `if` check | `-filter {PROP == val}` in `get_*` |
| Nest for single-use results | `set nets [...]; get_pins -of $nets` | `get_pins -of_objects [get_nets ...]` |
| Combine `-file -return_string` | `report_X -return_string` then `report_X -file` | `set r [report_X -file f.rpt -return_string]` |
| Membership test | `if {$name in [get_cells *]}` | `if {[lsearch -exact [get_cells *] $name] != -1}` |

See [VIVADO-PATTERNS.md Pattern 17](VIVADO-PATTERNS.md) for full rationale, examples, and the source UG tables.

### Step 5: Write the Description

The `description` field is the primary triggering mechanism. For Vivado skills, include:

1. What the skill does (one sentence)
2. What Vivado stage it targets
3. Specific trigger phrases users might say (be generous — undertriggering is worse than overtriggering)
4. Vivado command names that are central to the skill

Write in third person. Example:

```yaml
description: >
  Runs 55+ timing methodology checks (UG906) on synthesized FPGA designs to identify
  timing violations and generate actionable RTL/XDC fixes. Use when user asks to "check
  timing methodology", "validate timing", "run methodology checks", or reports
  timing-related issues after synthesis.
```

---

## Reviewing an Existing Vivado Skill

When a developer brings an existing skill for review, read [CHECKLIST.md](CHECKLIST.md) and evaluate it against each item. For each issue found, explain:

1. **What's wrong** — the specific checklist item that failed
2. **Why it matters** — what will go wrong when the agent uses this skill via MCP
3. **How to fix it** — concrete edit with before/after

Present findings as a prioritized list: critical issues (will cause failures) first, then improvements (will improve quality), then nice-to-haves.

---

## Testing a Vivado Skill

### Create Test Scenarios

For each Vivado skill, create 2-3 test scenarios that cover:

1. **Happy path** — A design where the workflow runs cleanly and produces expected results
2. **Edge case** — A design that exercises unusual conditions (single clock domain for CDC skill, zero violations for lint skill, DCP workspace instead of project)
3. **Error path** — A design that's missing prerequisites (no synthesis run, no constraints file)

### Run Tests via MCP

For each test scenario:

1. Start a Vivado session: use `vivado_start` or `vivado_connect`
2. Follow the skill's workflow step by step, using `vivado_execute` for each Tcl block
3. Verify the skill's output: does REPORT.md exist? Are fix recommendations using actual design names? Does the validation snippet pass?

### Evaluate Results

Check each test run against these criteria:

- Did the agent follow the workflow sequentially without skipping steps?
- Were all `vivado_execute` calls single-line semicolon-chained?
- Was `session_id` passed to every call?
- Did the agent write REPORT.md before narrating?
- Do recommended fixes use actual design names (not placeholders)?
- Did error handling work for the error-path test?

---

## Improving a Vivado Skill

### How to Think About Improvements

1. **Generalize, don't overfit.** If the skill works only for the test design, it's useless. Avoid fiddly changes tied to specific cell names or hierarchies. Instead, explain the *reasoning* behind patterns so the agent can adapt.

2. **Explain the why.** Today's LLMs are smart. Instead of writing "ALWAYS use single-line Tcl", write "Use single-line semicolon-chained Tcl because the MCP server executes each `vivado_execute` call as one atomic command — multi-line blocks fragment into separate calls that lose variable state." The agent will internalize the principle and apply it even in situations you didn't anticipate.

3. **Keep it lean.** Remove instructions that aren't pulling their weight. If the agent consistently does something correctly without being told, the instruction is wasted tokens. Read the MCP execution transcripts, not just the final outputs — if the skill is making the agent waste time on unproductive steps, cut those parts.

4. **Look for repeated work across test cases.** If every test run has the agent writing the same Tcl helper proc on the fly, bundle it as a script in `tcl/`. This saves every future invocation from reinventing the wheel.

5. **Watch for MCP-specific failure patterns:**
   - Agent using Vivado Tcl (`exec cat`) to read files instead of the file reader tool
   - Agent dumping full report content in chat instead of writing to file
   - Agent retrying failed Tcl with different syntax (leads to cascading errors)
   - Agent narrating "Now I'll generate..." without actually invoking the write tool
   - Agent using multi-line Tcl blocks that break across `vivado_execute` calls

### The Iteration Loop

1. Apply improvements to the skill
2. Rerun all test scenarios
3. Compare outputs: did the improvements fix the issues without introducing regressions?
4. Repeat until the developer is satisfied

---

## Skill Composition Guidelines

### Leaf Skills vs Orchestrator Skills

- **Leaf skills** do one thing well (CDC analysis, timing methodology, RTL lint). Keep them focused and under 500 lines.
- **Orchestrator skills** sequence leaf skills. They are lightweight pointers, not full workflows. Example: the `baselining` skill just lists which leaf skills to run in order.

### When to Split

If your SKILL.md is approaching 500 lines, split into:

| File | Content | When Loaded |
|---|---|---|
| SKILL.md | Overview, workflow, key patterns | When skill triggers |
| REFERENCE.md | Detailed tables, check IDs, API docs | When agent needs lookup data |
| TEMPLATES.md | Code templates, fix patterns | When agent generates fixes |

### Cross-Skill Conventions

All Vivado skills in the organization should follow these conventions so they compose cleanly:

- **Report directory**: `vivado_agentic_ai_reports/<skill-name>/`
- **Progress tracker format**: Inline markdown checklist in the workflow section
- **Workspace detection**: The same DCP-vs-project Tcl pattern in every Step 1
- **Fix format**: Copy-pasteable with actual design names

---

## Reference Files

- [TEMPLATE.md](TEMPLATE.md) — Full annotated SKILL.md template for Vivado skills
- [VIVADO-PATTERNS.md](VIVADO-PATTERNS.md) — Complete catalog of Vivado MCP patterns with rationale
- [CHECKLIST.md](CHECKLIST.md) — Validation checklist for reviewing Vivado skills
