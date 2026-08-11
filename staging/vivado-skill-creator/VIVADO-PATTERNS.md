<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# VIVADO-PATTERNS.md — Vivado MCP Patterns Catalog

This document catalogs every pattern that emerged from testing production Vivado skills against the MCP server. Each pattern includes the rationale (why it matters), the correct implementation, the common mistake, and which skills demonstrated the pattern.

---

## Pattern 1: Session ID Propagation

**Rationale:** The Vivado MCP server maintains persistent Tcl sessions. When `vivado_start` or `vivado_connect` returns a `session_id`, every subsequent `vivado_execute` call must include it. Without it, commands may target the wrong session or fail entirely in multi-session environments.

**Correct:**
```
vivado_execute(session_id="abc123", tcl_command="report_timing_summary ...")
```

**Wrong:**
```
vivado_execute(tcl_command="report_timing_summary ...")  # missing session_id
```

**Where to enforce:** In the Efficiency Guidelines block of every skill. Also mention it in each workflow step's Tcl block by noting "Pass `session_id` to all `vivado_execute` calls."

---

## Pattern 2: Single-Line Semicolon-Chained Tcl

**Rationale:** The MCP `vivado_execute` tool sends each call as one atomic Tcl command to the Vivado process. Multi-line Tcl blocks that depend on shared variable state will fail if split across separate `vivado_execute` calls — each call starts with a fresh evaluation context for local variables. Semicolon-chaining ensures the entire logical unit executes atomically.

**Correct:**
```tcl
set dcp [lindex [glob -nocomplain *.dcp] 0]; if {$dcp != ""} { open_checkpoint $dcp } elseif {[catch {current_design}]} { open_run synth_1 }; file mkdir vivado_agentic_ai_reports/cdc; report_cdc -file vivado_agentic_ai_reports/cdc/cdc.rpt -details; puts "Clocks: [llength [get_clocks]]"
```

**Wrong:**
```tcl
# These would be 4 separate vivado_execute calls — variables lost between calls
set dcp [lindex [glob -nocomplain *.dcp] 0]
if {$dcp != ""} { open_checkpoint $dcp }
file mkdir vivado_agentic_ai_reports/cdc
report_cdc -file vivado_agentic_ai_reports/cdc/cdc.rpt
```

**When multi-call is OK:** When commands are truly independent (no shared variables) or when you need to check intermediate results before proceeding (e.g., check synthesis status before running reports).

**Demonstrated in:** Every production skill (RTL lint, CDC, timing methodology, clock interaction, baselining).

---

## Pattern 3: Workspace Type Auto-Detection

**Rationale:** Skills must work in both DCP-only workspaces (user provides a `.dcp` file directly) and project workspaces (user has a `.xpr` project). The auto-detection pattern handles both without requiring user input.

**Implementation:**
```tcl
set dcp [lindex [glob -nocomplain *.dcp] 0]; if {$dcp != ""} { open_checkpoint $dcp } elseif {[catch {current_design}]} { open_run synth_1 }
```

**Logic:**
1. Look for `.dcp` files in the working directory
2. If found, use `open_checkpoint`
3. If not found, check if a design is already open (`current_design`)
4. If no design open, use `open_run synth_1` (assumes project workspace)

**Extension for post-implementation skills:**
```tcl
set dcp [lindex [glob -nocomplain *.dcp] 0]; if {$dcp != ""} { open_checkpoint $dcp } elseif {[catch {current_design}]} { open_run impl_1 }
```

**Demonstrated in:** CDC, clock-interaction, timing-methodology-checks.

---

## Pattern 4: Report-to-File with Targeted Reading

**Rationale:** Vivado reports can be enormous (thousands of lines). Dumping them into chat wastes context tokens and may truncate. Instead, write reports to files using Vivado's `-file` flag, then extract only what you need — not Vivado Tcl.

**The key principle: full file reads are expensive.** Every line read into context competes with conversation history, other skill content, and the agent's working memory. Prefer targeted extraction when you know what to look for.

**Decision guide — how to read report files:**

| Situation | Approach | Why |
|---|---|---|
| You know the exact section headers or violation IDs | `grep` / `sed` / `awk` via terminal | Pulls only relevant lines; minimal context cost |
| Report is small (<200 lines) | `read_file` (full or ranged) | Overhead is negligible |
| Report is medium (200–2000 lines) and you need specific sections | `grep -n` to find line numbers, then `read_file` with line range | Read only the sections you need |
| Report is large (>2000 lines) and you need the overall structure | `head -50` to see the TOC/summary, then targeted `grep`/`sed` | Never read the full file |
| First time seeing a report format (exploration) | `wc -l` + `head -80` to understand structure, then targeted reads | Get the lay of the land before committing context |

**Correct flow (targeted):**
1. Vivado command writes report: `report_methodology -file vivado_agentic_ai_reports/methodology.rpt`
2. Agent checks size and structure:
   ```bash
   wc -l vivado_agentic_ai_reports/methodology.rpt
   head -40 vivado_agentic_ai_reports/methodology.rpt   # summary section
   ```
3. Agent extracts specific violations:
   ```bash
   grep -n "TIMING-" vivado_agentic_ai_reports/methodology.rpt   # find violation lines
   sed -n '45,80p' vivado_agentic_ai_reports/methodology.rpt     # read a specific section
   ```
4. Agent summarizes findings in chat (short) and writes REPORT.md (detailed)

**Correct flow (small reports):**
1. Vivado command writes report
2. Agent reads file with `read_file` tool (report is small, full read is fine)
3. Agent summarizes and writes REPORT.md

**Wrong flow:**
```tcl
# ❌ Using Vivado Tcl to read files — wastes Vivado process time, unreliable for large files
set fp [open "report.rpt" r]; set data [read $fp]; close $fp; puts $data
```

```tcl
# ❌ Also wrong — shell commands via Vivado
exec cat report.rpt
```

```
# ❌ Also wrong — reading a 5000-line report entirely into context when you only need 20 lines
read_file("methodology.rpt", startLine=1, endLine=5000)
```

**Why not Vivado Tcl for reading?** The MCP `vivado_execute` tool has output size limits and timeout constraints. Large file reads through Vivado Tcl risk truncation and consume Vivado session time unnecessarily.

**Why not blind full reads?** A `report_timing_summary` can be 3000+ lines, a `report_clock_utilization` 500+ lines, and `vivado.log` 200K+ lines. Reading these fully into context is wasteful when the skill only needs specific violation IDs, clock names, or cell paths. Use `grep`/`sed` to extract exactly what you need.

**Demonstrated in:** All analysis skills. clock-region-placer-failure-ep provides the most mature example with its log pattern table and `crp_extract_log.sh` script.

---

## Pattern 5: Standardized Report Directory

**Rationale:** Consistent output locations allow orchestrator skills (like `baselining`) to find sub-skill outputs reliably. They also give users a predictable place to look.

**Convention:**
```
vivado_agentic_ai_reports/<skill-name>/
├── <vivado_report>.rpt    # Raw Vivado output (via -file flag)
└── REPORT.md              # Agent-generated markdown summary with fixes
```

**Directory creation** — always in Step 1, alongside the report command:
```tcl
file mkdir vivado_agentic_ai_reports/<skill-name>; report_X -file vivado_agentic_ai_reports/<skill-name>/X.rpt
```

**Demonstrated in:** CDC (`baselining/cdc/`), clock-interaction (`baselining/clock-interaction/`), timing-methodology-checks (`baselining/timing-methodology-checks/`).

---

## Pattern 6: Action-Before-Narration

**Rationale:** The most common failure mode in agent skills is the agent narrating its intent ("Now I'll generate the report...") instead of actually writing the file. In an agentic loop, a text-only response can end the agent's turn before the file is created, leaving the workflow incomplete.

**Enforcement language (include in every skill that generates files):**

```markdown
**⚠️ The workflow is incomplete until REPORT.md exists.** Do not end your turn before
calling the write tool to create the file. Do not narrate ("Now generating...") or
summarize before writing — invoke the write tool first. Only after the file is
written, give a short summary.
```

**Also include the Troubleshooting section:**

```markdown
## Troubleshooting: REPORT.md Not Created

**Symptom:** Earlier steps complete but REPORT.md never appears.

**Root cause:** The agent outputs text instead of invoking the write tool. A text-only
response may end the turn before the file is written.

**Prevention:** Follow the step order strictly — invoke the write tool first, then summarize.
```

**Demonstrated in:** CDC, clock-interaction, timing-methodology-checks (all include both the enforcement language and the troubleshooting section).

---

## Pattern 7: Design-Specific Fix Names

**Rationale:** The entire point of agent-generated fixes is that users can copy-paste them directly. Placeholder names (`clk_a`, `<period>`, `*_sync_reg*`) defeat this purpose and create extra work. The agent must extract actual names from Vivado reports and substitute them into fix templates.

**Implementation:** The skill's workflow must include a "Parse report, extract ACTUAL names" step between running the Vivado command and generating the report. The fix template section should use bracketed markers (e.g., `[actual_clock_name]`) that the agent replaces with real values from the parsed report.

**Enforcement table (include in every skill with fixes):**

| Rule | ❌ WRONG | ✅ CORRECT |
|------|----------|------------|
| Clock names | `clk_a`, `clk_b` | `HOSTCLK`, `GTX_CLK` |
| Cell paths | `*_sync_reg*` | `core_0/host_*_sync_reg*` |
| MMCM pins | `mmcm/CLKOUT0` | `ios_0/mmcm_0/CLKOUT2` |
| Periods | `<period>` | `12.800` |
| Signal names | `signal` | `host_enable` |
| Net names | `<net>` | `core_0/data_valid` |

**Demonstrated in:** All analysis skills (CDC, clock-interaction, timing-methodology-checks, custom-drc-ep).

---

## Pattern 8: Progress Tracker

**Rationale:** Inline checklists serve two purposes: (a) the agent uses them to track state across multi-step workflows, preventing step-skipping; (b) the `vivado_todos` MCP tool can mirror them in the VS Code sidebar, giving the user visibility.

**Format:**
```markdown
[Skill Name] Progress:
- [ ] Step 1: Open design, create dir, run report_X -file
- [ ] Step 2: Parse report, extract ACTUAL names
- [ ] Step 3: Generate REPORT.md (call write tool), then short summary in chat
```

**Each step should map to one or two `vivado_execute` calls.** Don't create steps that are too granular (one step per Tcl command) or too coarse (entire workflow in one step).

**Demonstrated in:** CDC, clock-interaction, timing-methodology-checks, baselining.

---

## Pattern 9: Timeout Guidance

**Rationale:** The MCP server has configurable timeouts. Skills must annotate commands that need non-default timeouts to prevent premature termination. The default may be 600 seconds, but synthesis and implementation can take much longer.

**Guidelines:**

| Command Category | Typical Duration | Recommended Timeout |
|---|---|---|
| `report_*` commands | 10–120 seconds | 120 seconds |
| `synth_design -lint` | 30–120 seconds | 120 seconds |
| `synth_design` (full) | 60–18000+ seconds | 18000 seconds (5 hours) |
| `opt_design` | 60–18000+ seconds | 18000 seconds (5 hours) |
| `place_design` | 120–18000+ seconds | 18000 seconds (5 hours) |
| `route_design` | 120–18000+ seconds | 18000 seconds (5 hours) |
| `validate_bd_design` | 10–60 seconds | 120 seconds |

**Implementation:** Add a note after the Tcl block:
```markdown
Use `timeout_seconds: 120` for the report_methodology command.
```

**Demonstrated in:** RTL lint (`synth_design -lint` gets explicit timeout note).

---

## Pattern 10: Sequential Execution Enforcement

**Rationale:** Vivado MCP commands must execute sequentially — the Vivado Tcl process is single-threaded. If the agent tries to parallelize `vivado_execute` calls, they will serialize at the MCP level anyway but may cause confusing interleaved output or race conditions.

**Enforcement language:**
```markdown
**⚠️ CRITICAL: Execute steps SEQUENTIALLY. Wait for each command to complete.**
```

**When parallel is OK:** Non-MCP operations can be parallelized — e.g., reading multiple report files with the file reader tool, or running shell scripts alongside Vivado commands (if they don't interact with the same Vivado session).

**Demonstrated in:** All production skills include this warning.

---

## Pattern 11: No Tcl Syntax Retry

**Rationale:** When a Vivado Tcl command fails, the agent's natural instinct is to try a slightly different syntax. This almost always makes things worse — it can change design state (e.g., partially executed commands), create confusing error cascades, and waste time. The correct behavior is to report the error and let the user decide.

**Enforcement language:**
```markdown
- **Do NOT** retry a failed Tcl command with different syntax. Report the error and stop or proceed.
```

**Exception:** If the skill explicitly provides an alternative command for a known error condition (documented in the Error Handling table), the agent should use that alternative.

**Demonstrated in:** All production skills include this in Efficiency Guidelines.

---

## Pattern 12: Large Log Handling

**Rationale:** Vivado logs for complex designs (especially E&P) can exceed 200K lines. Reading them sequentially wastes context tokens and time. Skills should provide extraction scripts or targeted grep patterns.

**Approaches (in order of preference):**

1. **Extraction script** — Bundle a shell script that produces a compact digest:
   ```bash
   bash <skill_dir>/crp_extract_log.sh <run_directory>
   # Produces: crp_digest.txt (~0.2% of original log)
   ```
   Best when the skill always needs the same sections. Write the script once, save every future invocation from re-discovering the right grep patterns.

2. **Targeted grep + sed** — Provide specific patterns and line-range extraction:
   ```bash
   # Find the anchor line, then read a fixed window around it
   LINE=$(grep -n "BUFG info for the design:" vivado.log | tail -1 | cut -d: -f1)
   sed -n "${LINE},$((LINE+15))p" vivado.log

   # Or extract all lines matching a pattern family
   grep -A5 "Place 30-7211" vivado.log

   # Or count occurrences first to decide whether a full read is needed
   grep -c "CRITICAL WARNING" vivado.log
   ```
   Best when the skill needs flexibility — different designs may have different sections of interest.

3. **Report-to-file** — Use Vivado's built-in `-file` flag to write structured reports instead of parsing logs.
   Best for Vivado commands that produce clean, structured output (most `report_*` commands).

4. **Ranged read_file** — When you need a known section but can't easily grep for it:
   ```
   read_file("report.rpt", startLine=45, endLine=80)
   ```
   Use `grep -n` first to find the line numbers, then read only that range.

**Never:** Read the full `vivado.log` sequentially into context. Even for report files, prefer targeted reads over full reads when the file exceeds ~200 lines.

**Demonstrated in:** clock-region-placer-failure-ep (extraction script + targeted grep patterns).

---

## Pattern 13: Decision Tree for Multi-Mode Skills

**Rationale:** Complex skills that support multiple modes (interactive vs batch, UltraScale+ vs Versal, DCP vs log-only) need an explicit decision tree so the agent picks the right path. Without one, the agent may attempt steps that require unavailable inputs.

**Format:**
```
[Starting condition?]
  ├─ [Condition A] → [Action/Mode A]
  └─ [Condition B]
      ├─ [Sub-condition] → [Action]
      └─ [Sub-condition] → [Action]
```

**Demonstrated in:** clock-region-placer-failure-ep (Mode A: log analysis vs Mode B: DCP interactive), custom-drc-ep (Workflow A: run existing vs Workflow B: create new).

---

## Pattern 14: Workflow Gates

**Rationale:** For skills that author code (DRC scripts, constraint files), the agent may prematurely load designs or run commands before prerequisite artifacts exist. Workflow gates explicitly block progression.

**Implementation:**
```markdown
**Workflow gate:** Do NOT open the DCP, start Vivado, or interact with the design
until the script has been written and saved (Step 2 complete).
```

**When to use:** Any skill where the agent writes a file that will be sourced/executed in Vivado. The file must exist before the Vivado step runs.

**Demonstrated in:** custom-drc-ep (Step 2 must complete before Step 3 validation).

---

## Pattern 15: Bundled Script Organization

**Rationale:** Complex skills benefit from bundled Tcl procs, shell scripts, or Python scripts. Consistent organization helps the agent find and reference them correctly.

**Convention:**
```
my-skill/
├── SKILL.md
├── REFERENCE.md
├── tcl/
│   ├── helper_procs.tcl      # Tcl procs sourced in Vivado
│   └── debug_params.tcl      # Parameter settings sourced before commands
├── scripts/
│   ├── extract_log.sh        # Shell scripts for log parsing
│   └── visualize.sh          # Dashboard/report generators
└── reference/
    ├── format-spec.md         # Detailed format documentation
    └── procs-api.md           # Proc documentation
```

**Reference from SKILL.md:**
```tcl
source <skill_dir>/tcl/helper_procs.tcl
```

```bash
bash <skill_dir>/scripts/extract_log.sh <run_dir>
```

**Demonstrated in:** clock-region-placer-failure-ep (crp_debug_params.tcl, crp_extract_log.sh, crp_visualize.sh, clockDebug.tcl), custom-drc-ep (tcl/all.tcl + 15 EP_*.tcl files).

---

## Pattern 16: Vivado Doc Search for Unfamiliar Commands

**Rationale:** When a skill's logic requires Vivado Tcl commands not covered by its templates, the agent should use `vivado_doc_search` to look up correct syntax rather than guessing. This prevents hallucinated command options and incorrect property names.

**Implementation in skills:**
```markdown
**Looking up unfamiliar Vivado commands (optional):**
If the logic requires Vivado Tcl commands or object properties not covered by the
templates, use `vivado_doc_search` to look up correct syntax, property names, and
command options before writing the script.
```

**Demonstrated in:** custom-drc-ep (recommended for niche property queries when authoring new DRC checks).

---

## Pattern 17: Compile-Time Optimized Tcl (UG835/UG894)

**Rationale:** Bundled Tcl scripts in skills run inside Vivado's Tcl interpreter. Each call to a `get_*` command or `report_*` command crosses the Tcl↔C++ interface boundary, which has measurable runtime cost. For skills that iterate over designs with thousands of cells or paths, these patterns can reduce execution time by 2–10×. Source: UG835 (Handling Lists of Objects), UG894 (Tcl Scripting Tips, Writing Efficient Code, Caching Objects, Performance via Nesting, get_property and Sorted Lists).

### Rule 1: Cache object queries — never re-query the same collection

```tcl
# ❌ WRONG — get_clocks called 3 times, 3 round-trips to C++
set count [llength [get_clocks -quiet]]
foreach clk [lrange [get_clocks -quiet] 0 4] { ... }
puts "Total clocks: [llength [get_clocks -quiet]]"

# ✅ CORRECT — query once, reuse variable
set clocks [get_clocks -quiet]
set count [llength $clocks]
foreach clk [lrange $clocks 0 4] { ... }
```

### Rule 2: Vectorize get_property — one call for all objects, not N calls in a loop

```tcl
# ❌ WRONG — N round-trips to C++ (O(N) Tcl↔C++ crossings)
foreach cell $cells {
    set loc [get_property LOC $cell]
    puts "$cell at $loc"
}

# ✅ CORRECT — one get_property call returns ordered list matching $cells
foreach cell $cells loc [get_property LOC $cells] {
    puts "$cell at $loc"
}
```

The list returned by `get_property` has the same number of elements in the same order as the input list — this makes vectorized `foreach` with multiple lists safe.

### Rule 3: Use -filter at the C++ level, not post-processing in Tcl

```tcl
# ❌ SLOW — get_cells returns everything, foreach checks each one in Tcl
foreach bram [get_cells -hier -filter {PRIMITIVE_SUBGROUP == bram}] {
    if {[get_property WRITE_WIDTH_B $bram] > 36} {
        lappend big_brams $bram
    }
}

# ✅ FAST — filter pushed into C++ layer, Tcl never sees the rejected objects
set big_brams [get_cells -hier -filter {PRIMITIVE_SUBGROUP == bram && WRITE_WIDTH_B > 36}]
```

### Rule 4: Nest commands to stay in the C++ layer

```tcl
# ❌ SLOWER — intermediate Tcl variable forces a C++→Tcl→C++ round-trip
set nets [get_nets -hier]
set pins [get_pins -of_objects $nets]

# ✅ FASTER — nested call executes entirely in C++, returns to Tcl once
set pins [get_pins -of_objects [get_nets -hier]]
```

Exception: Create intermediate variables when the same result is reused multiple times (Rule 1). Nesting is only better when the intermediate result is used exactly once.

### Rule 5: Combine -file and -return_string into a single report_* call

Every `report_*` command that supports both `-file` and `-return_string` should use them together in one call. Calling the same command twice — once for file output, once for string parsing — doubles the runtime cost.

```tcl
# ❌ WRONG — same report generated twice
report_timing -setup -max_paths 10 -quiet -return_string  ;# parsed
report_timing -setup -max_paths 10 -file timing.rpt       ;# saved

# ✅ CORRECT — one call, both outputs
set timing_report [report_timing -setup -max_paths 10 -quiet -file timing.rpt -return_string]
```

This rule applies to all `-return_string` capable commands: `report_timing`, `report_timing_summary`, `report_methodology`, `report_design_analysis`, `report_qor_suggestions`, `report_cdc`, `report_clock_interaction`, etc.

### Rule 6: Avoid `in`/`ni` list operators on Vivado collections

Due to Vivado's collection "shimmering" (the `tcl.collectionResultDisplayLimit` parameter truncates string representation at 500 objects by default), the `in` and `ni` operators cannot reliably check membership in large collections.

```tcl
# ❌ UNSAFE — silently wrong if collection has >500 objects
if {$cellName in [get_cells *]} { ... }

# ✅ SAFE — lsearch operates on the actual collection, not the truncated string
if {[lsearch -exact [get_cells *] $cellName] != -1} { ... }
```

### Summary Table

| Pattern | Impact | Example |
|---|---|---|
| Cache `get_*` results | Avoids repeating C++ queries | `set clks [get_clocks]; llength $clks` |
| Vectorize `get_property` | O(N) → O(1) calls | `get_property LOC $cells` on whole list |
| Push filter to C++ | Eliminates Tcl-level loop | `-filter {PROP == val}` in `get_cells` |
| Nest commands | Stays in C++, avoids round-trip | `get_pins -of_objects [get_nets]` |
| Combine `-file -return_string` | Halves report command calls | `report_X -file f.rpt -return_string` |
| Use `lsearch` not `in` | Correct for large collections | `lsearch -exact $collection $name` |

**Where to apply:** In ALL bundled Tcl scripts (`tcl/`, `scripts/*.tcl`) within a skill. These patterns should be written correctly from the start — they're not micro-optimizations, they're correct Vivado Tcl idioms.

**Demonstrated in:** versal-timing-closure-methodology (7 scripts audited and fixed against these patterns, commit 3ed6ae3).

---

## Anti-Patterns to Avoid

These are failure modes observed during skill testing. Include relevant warnings in your skills.

| Anti-Pattern | What Happens | Prevention |
|---|---|---|
| Multi-line Tcl in MCP | Variables lost between `vivado_execute` calls | Use semicolon-chaining |
| Reading files via Vivado Tcl | `exec cat` or `open/read/close` — slow, truncation risk | Use agent's file reader tool |
| Full log reading | 200K+ line log fills context window | Use extraction scripts or targeted grep |
| Blind full file read | Reading a 3000-line report when you need 20 lines | Use `grep`/`sed` or ranged `read_file` |
| Narrating before acting | "Now I'll generate..." ends turn without writing file | Action-before-narration enforcement |
| Placeholder names in fixes | User can't copy-paste `clk_a` | Extract actual names from reports |
| Parallel MCP calls | Vivado is single-threaded; race conditions | Sequential execution enforcement |
| Tcl syntax retry on failure | Cascading errors, design state corruption | No-retry rule + error handling table |
| `shell ls` / `shell find` | Not reliable in MCP context | Use Tcl `glob` or agent's file search |
| Missing session_id | Commands may target wrong session | Propagate session_id on every call |
| Skipping validation step | Errors caught late or not at all | Always include validation Tcl snippet |
| Re-querying same collection | Extra C++ round-trips per call | Cache in variable, reuse (Rule 17.1) |
| Per-object `get_property` loop | O(N) Tcl↔C++ crossings | Vectorize over whole list (Rule 17.2) |
| Double `report_*` call | Same Vivado command run twice | Combine `-file -return_string` (Rule 17.5) |
| `in`/`ni` on large collection | Silent wrong result >500 objects | Use `lsearch -exact` (Rule 17.6) |
