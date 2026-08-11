---
name: rtl-elaboration-analysis
description: >
  Analyze Vivado synthesis elaboration errors, critical warnings, and warnings from
  synthesis logs and provide actionable RTL code fixes. Covers 117 actionable Verific
  front-end messages across Verilog/SystemVerilog and VHDL. Works from log files
  (no active Vivado session required) or via Vivado MCP. Use when user asks to
  "analyze synthesis errors", "fix synth errors", "check elaboration log",
  "why did synthesis fail", "fix RTL warnings", "analyze synth log",
  "elaboration errors", "synth failed", "synthesis warnings", "parser error",
  "undeclared variable", "port mismatch", "type mismatch", "infer latch",
  "sensitivity list", or "width mismatch".
argument-hint: "[log-file-path or project-path]"
allowed-tools:
  - tool_search_tool_regex
  - vivadoExecute
  - vivado_doc_search
  - read_file
  - create_file
  - replace_string_in_file
  - run_in_terminal
  - runSubagent
  - file_search
  - grep_search
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
# RTL Elaboration Analysis

## Purpose

Analyzes Vivado synthesis elaboration messages (errors, critical warnings, warnings)
from the Verific/Oasys front-end and provides actionable RTL code fixes with real
source context and diff-formatted patches.

This skill covers the **parser, type-checker, and elaboration phases** of `synth_design` —
the stage where Vivado reads and interprets RTL before synthesis mapping. These are
the `[Synth 8-XXX]` messages that appear when Vivado encounters issues in your HDL code.

**Two operating modes:**
- **Log Analysis Mode** (primary): Parse an existing Vivado synthesis log file.
  No active Vivado session needed. Ideal when synthesis already ran.
- **MCP Mode** (secondary): Use an active Vivado session to run elaboration and
  analyze results in real-time.

**Coverage:** 117 actionable messages across Verilog/SystemVerilog and VHDL:
- **41 Tier 1** — Directly fixable with deterministic code changes
- **76 Tier 2** — Fixable after inspecting RTL source context in workspace

**Expected outcomes:**
- **Errors:** Concrete code fixes with diff blocks showing exactly what to change
- **Critical warnings:** Fixes + explanation of synthesis/simulation impact
- **Warnings:** Fixes + severity assessment (fix vs waive decision)
- **Summary report** with hotspot analysis, prioritized recommendations, and
  cross-file dependency tracking

**Prerequisites:**
- Vivado synthesis log file (`vivado.log`, `runme.log`, or `synth_1/runme.log`)
  OR active Vivado session via MCP
- User RTL source files accessible in workspace (for reading context and generating fixes)
- Write access to workspace for report generation

---

## When to Use

- After `synth_design` fails with elaboration errors
- When synthesis produces many warnings the user wants to address
- User asks "why did synthesis fail" or "fix synth errors"
- After modifying RTL and wanting to check for elaboration issues
- When reviewing synthesis log for code quality

## When NOT to Use

- For lint-only checks → use `rtl-lint` skill (`synth_design -lint`)
- For post-synthesis timing issues → use `timing-methodology-checks`
- For synthesis optimization analysis → use `opt-design-analysis`
- For physical optimization → use `phys-opt-design-analysis`
- When user has no log file and no Vivado session available

---

## DOs

- **Always parse the log first** — extract structured data before analyzing
- **Always read real RTL source** at the referenced file:line before suggesting fixes
- **Always use diff syntax** for code fix blocks (never `verilog`/`vhdl` code fences)
- **Match message IDs to handlers** in [message-handlers.md](message-handlers.md)
- **Fix errors before warnings** — errors block synthesis; warnings are quality issues
- **Search workspace for related code** — typo fixes need the correct name from the design
- **Use vivado_doc_search** for UG901 coding guidance when handler is insufficient
- **Track file hotspots** — files with many messages need structural review

## DON'Ts

- **Never fabricate code** — all code in fixes must come from `read_file` on actual RTL
- **Never create .tcl script files** — use `vivadoExecute` tool directly (MCP mode)
- **Never guess signal types/widths** — read the declaration from source
- **Never skip Tier 3 (advisory) messages** — report them but mark as "requires design decision"
- **Never assume VLOG vs VHDL** — detect from file extension in the message
- **Never parse partial logs** — ensure the log covers the complete elaboration phase
- **Never report wrong counts** — message count must match the log exactly
- **Never suggest fixes that change design behavior** without explicit warning

---

## Efficiency Guidelines

- **Read reports efficiently** — use `grep_search` to extract specific message patterns
  from large logs instead of reading entire files. Use `read_file` with line ranges for
  targeted source inspection.
- **Batch file reads** — when multiple messages reference the same file, read it once
  and extract all relevant sections.
- **Do NOT** retry a failed Tcl command with different syntax. Report the error and stop.
- **Do NOT** use Vivado Tcl (`exec cat`, `open`, `read`) to read files. Use your file
  reader tool.

---

## Workflow

Execute steps **sequentially** in this exact order.

### Step 1: Locate and Identify Log File

Determine operating mode and find the synthesis log.

**Log Analysis Mode** (default when user provides a log file path or log exists in workspace):
1. If `$ARGUMENTS` is a `.log` file path, use it directly
2. Otherwise search workspace:
   ```
   file_search("**/runme.log")
   file_search("**/vivado.log")
   file_search("**/*.log")
   ```
3. If multiple logs found, prefer `synth_1/runme.log` > `vivado.log` > others
4. If no log found, switch to MCP Mode

**MCP Mode** (when no log exists or user requests live analysis):
1. Load Vivado tools: `tool_search_tool_regex` with pattern `"vivado"`
2. Follow TCL in [tcl-reference.md § Step 1](tcl-reference.md) to detect project/non-project
3. Run `synth_design` — TCL in [tcl-reference.md § Step 2](tcl-reference.md)
4. Locate the resulting log file

**Verify:** Log file path is known and file exists.

### Step 2: Create Report Directory

Create output directory for reports:

```
vivado_agentic_ai_reports/rtl-elaboration-analysis/
```

Use `run_in_terminal` to create: `mkdir -p vivado_agentic_ai_reports/rtl-elaboration-analysis`

Or if in MCP mode: `file mkdir vivado_agentic_ai_reports/rtl-elaboration-analysis`

### Step 3: Parse Elaboration Messages

Extract all elaboration messages from the log. Execute the parser:

```bash
python3 <skill_dir>/parse_elab_messages.py <log_file> vivado_agentic_ai_reports/rtl-elaboration-analysis/messages.csv
```

Where `<skill_dir>` is the path to this skill's directory.

**If Python is unavailable**, parse manually using `grep_search` on the log file:
- Pattern: `^(ERROR|CRITICAL WARNING|WARNING):\s*\[Synth\s+8-\d+\]`
- Extract: severity, message ID, text, file path, line number

**CSV column schema** (headerless, 6 columns):

| Col | Field | Description |
|-----|-------|-------------|
| 0 | severity | `ERROR`, `CRITICAL WARNING`, `WARNING`, or `INFO` |
| 1 | msg_id | Integer message ID from `[Synth 8-XXX]` |
| 2 | text | Full message text |
| 3 | file | Source file path (may be empty) |
| 4 | line | Source line number (0 if not available) |
| 5 | language | `VLOG` or `VHDL` (detected from file extension) |

**Verify:** CSV exists. Line count matches message count from log. No parse errors.

### Step 4: Classify and Prioritize

Read the CSV with `read_file` and organize messages:

**4a. Severity grouping:**
1. **Errors** — Must fix. Block synthesis completion.
2. **Critical warnings** — Should fix. May cause incorrect synthesis results.
3. **Warnings** — Review and fix or waive. Quality/simulation-mismatch risk.

**4b. Actionability classification:**

For each message, look up `msg_id` in the dispatch table in
[message-handlers.md § Dispatch Table](message-handlers.md):

- **Tier 1 (Directly Fixable):** Deterministic fix — apply without user input
- **Tier 2 (Fixable with Context):** Fix requires reading surrounding RTL
- **Tier 3 (Advisory):** Report but flag as "requires design decision"

**4c. File hotspot analysis:**
- Group messages by source file
- Rank files by total message count (descending)
- Files with >10 messages are "hotspots" — recommend structural review

**4d. Dependency detection:**
- Some errors cause cascading messages (e.g., undeclared type → multiple "undeclared" errors)
- Identify root cause messages vs cascading effects
- Prioritize root cause fixes

### Step 5: Generate Fixes

For each actionable message (Tier 1 and Tier 2), in priority order (errors first):

1. **Read RTL source context:**
   - Resolve file path from CSV field[3]
   - If path is relative or filename-only: `file_search("**/<filename>")`
   - Read source with `read_file(resolved_path, line-10, line+10)` for ±10 lines context

2. **Look up message handler:**
   - Find handler by `msg_id` in [message-handlers.md](message-handlers.md)
   - If handler references a `→ resolution/<file>.md`, load the resolution guide
     with `read_file` for detailed fix templates and code patterns
   - Follow the handler's fix instructions (or the resolution guide if available)

3. **For Tier 2 messages — inspect surrounding code:**
   - Read module/entity header for port declarations
   - Read signal declarations for type/width information
   - Search workspace for matching names (fuzzy match for typos)
   - Read instantiated module definition for port list comparison

4. **Generate diff-formatted fix:**
   ```diff
   - old_code  // <- problem description
   + new_code  // <- fix description
   ```

5. **For Tier 3 messages — write advisory:**
   - Explain the issue and why automatic fix is not possible
   - List design options the user should consider
   - Reference UG901/UG906 guidance

**Scaling — Branch Decision:**

Count total actionable messages (= non-empty, non-INFO lines in CSV).

- **≤50 messages → Standard Flow:** Proceed directly to Step 6.
- **>50 messages → Extended Flow:** Execute Steps 5A and 5B first, then proceed to Step 6.

---

### Extended Flow (>50 messages only)

#### Step 5A: Generate Per-File Message Parts

Split the CSV into per-file message reports organized by ascending difficulty
(easiest fixes first), chunked for subagent token budget.

**Execute via `run_in_terminal`:**
```bash
cd vivado_agentic_ai_reports/rtl-elaboration-analysis
python3 <workspace_root>/skills/vivado/rtl-elaboration-analysis/csv_to_per_file_parts.py elab_messages.csv ./
```

**Script behavior:**
- Reads `elab_messages.csv` (6-column CSV from Step 3)
- Groups messages by source filename
- Sorts files by message count ascending (easiest first)
- Splits into part files with max 20 files each
- Number of parts = ceil(total_files / 20)

**Generated files:**
- `messages_by_file.txt` — Summary with error counts + file rankings
- `messages_by_file_part1.txt` — Easiest files ← START HERE
- `messages_by_file_part2.txt` — Medium complexity
- `messages_by_file_partN.txt` — Progressive difficulty

**Verify:** All part files created. Sum of messages across all parts = total in CSV.

#### Step 5B: Per-File Subagent Analysis (MANDATORY)

Launch one subagent per part file. Each subagent processes up to 20 RTL files.

**Subagent prompt template:**

```
You are analyzing RTL elaboration messages for files in Part N.

**Input:** messages_by_file_partN.txt
**Per-message format:** Read <workspace_root>/skills/vivado/rtl-elaboration-analysis/report-format.md
**Output:** Return a dictionary mapping each filename to its analysis markdown.

For each file in the part file:
1. Parse messages (#, Severity, Line, Synth 8-XXX, Language, Message)
2. Locate source file: file_search(query="**/<filename>")
3. For each message:
   a. Read source code at file:line with read_file (±10 lines context)
   b. Look up msg_id in message-handlers.md dispatch table
   c. If handler references → resolution/<file>.md, load and apply fix template
   d. Write Problematic Code with diff block (- lines from real source)
   e. Write Recommended Fix with diff block (+ lines corrected)
   f. Write Rationale explaining why
4. Verify: message count in markdown == count in part file

Use REAL source code (read_file) — never fabricate.
Return: {"file1.sv": "# Analysis...", "file2.sv": "# Analysis...", ...}
```

**Save outputs:** Write each file's analysis to `file_analysis/<filename>_analysis.md`

**Verification before proceeding:**
- `file_analysis/` directory exists
- Number of `*_analysis.md` files = number of files with messages
- Each `.md` file is >1KB (not empty placeholders)

If verification fails → re-execute Step 5B for missing files before proceeding.

---

### Step 6: Write Report

**⚠️ The workflow is incomplete until REPORT.md exists.** Write the file before
narrating or summarizing.

Save to: `vivado_agentic_ai_reports/rtl-elaboration-analysis/REPORT.md`

**Report structure:**

```markdown
# RTL Elaboration Analysis Report

## Summary
| Severity | Count | Actionable | Advisory |
|----------|-------|------------|----------|
| Error | N | N | N |
| Critical Warning | N | N | N |
| Warning | N | N | N |

## File Hotspots
| File | Errors | Crit. Warnings | Warnings | Total |
|------|--------|----------------|----------|-------|
| ... | ... | ... | ... | ... |

## Message Type Distribution
| ID | Severity | Count | Description | Actionable? |
|----|----------|-------|-------------|-------------|
| ... | ... | ... | ... | ... |

## Fixes — Errors (Priority 1)
### [Synth 8-XXX] <description>
**File:** [file.v:42](../../path/to/file.v#L42)
**Message:** <full message text>
**Root Cause:** <explanation>

**Problematic Code:**
\`\`\`diff
  context line
- problematic line  // <- what's wrong
  context line
\`\`\`

**Recommended Fix:**
\`\`\`diff
  context line
+ fixed line  // <- what changed and why
  context line
\`\`\`

**Rationale:** <why this fix is correct>

## Fixes — Critical Warnings (Priority 2)
...

## Fixes — Warnings (Priority 3)
...

## Advisory — Design Decisions Required
...

## Recommendations
### Immediate (fix now)
### High-Impact Quick Wins
### Design Review Items
### Accept/Waive
```

**Formatting rules:**
- All code blocks use `diff` syntax (never `verilog`/`vhdl`)
- All file references are clickable markdown links with line numbers
- Use workspace-relative paths for links
- See [report-format.md](report-format.md) for detailed formatting rules

### Step 7: Verify Report Accuracy

1. Count messages in report matches count in CSV
2. All errors have fix recommendations (Tier 1/2) or advisory notes (Tier 3)
3. All code in diff blocks is from actual RTL files (verify by re-reading)
4. File links point to correct locations
5. No fabricated violations or fixes

---

## Message Categories

The 117 actionable messages span these categories. See
[message-handlers.md](message-handlers.md) for full handler details.

| Category | VLOG IDs | VHDL IDs | Count | Description |
|----------|----------|----------|-------|-------------|
| Declarations & Scope | 126–134 | 730–731, 833 | ~18 | Undeclared, redeclared, wrong type |
| Port Connections | 142–145, 510–518 | 752–753, 775, 778–781 | ~22 | Named/ordered mix, width mismatch |
| Type & Width | 576–583 | 740–762, 793–794, 840, 857 | ~20 | Type mismatch, width mismatch |
| Assignments | 133–134, 530, 637 | 817–818, 823 | ~10 | LHS errors, dual driver |
| Constants & Ranges | 539–549 | 741–745, 766, 769, 825 | ~14 | Unresolved, out of range |
| Process/Always | 560–567, 585 | 758, 812, 817–818 | ~12 | Sensitivity list, clock, latch |
| Case Statements | 506–508, 150 | 746–747, 790, 814 | ~10 | Overlap, missing, duplicate |
| Loops | 552–555 | 756–757, 816 | ~6 | Limit exceeded, non-converging |
| Parameters/Generics | 148, 408–410, 647–648 | 755, 778, 794, 857 | ~10 | Missing, mismatch, non-constant |
| Interfaces/Components | 591–592, 596, 602 | 773, 783, 830 | ~8 | Mismatch, unconnected |
| Enums & Aggregates | 615–616, 599 | 750–751, 770, 774, 789 | ~8 | Duplicate, missing elements |
| Miscellaneous | 117, 544–545, 624, 630 | 805, 841, 856, 858, 864, 866 | ~12 | Various code issues |

---

## Inputs

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| log_path | path | Auto-detect | Path to Vivado synthesis log file |
| project_path | path | `pwd` | Project directory (MCP mode) |
| severity_filter | enum | `ALL` | Minimum: `ERROR`, `CRITICAL`, `WARNING`, `ALL` |
| report_dir | string | `vivado_agentic_ai_reports/rtl-elaboration-analysis` | Output directory |

---

## Output

**Location:** `vivado_agentic_ai_reports/rtl-elaboration-analysis/`

```
vivado_agentic_ai_reports/
└── rtl-elaboration-analysis/
    ├── messages.csv              ← Parsed messages (6-column CSV)
    ├── REPORT.md                 ← AI-generated analysis with fixes
    ├── report_data.json          ← Structured data (optional, for dashboards)
    ├── messages_by_file.txt      ← (Extended Flow) Per-file summary
    ├── messages_by_file_part*.txt← (Extended Flow) Per-file detail parts
    └── file_analysis/            ← (Extended Flow) Per-file subagent output
        ├── <file1>_analysis.md
        └── <file2>_analysis.md
```


- [ ] Applying the fix resolves the message
- [ ] Fix does not introduce new messages

---

## Supporting Files

| File | Purpose |
|------|---------|
| [message-handlers.md](message-handlers.md) | Per-message-ID fix instructions and dispatch table |
| [resolution-guide.md](resolution-guide.md) | Resolution system index and workflow |
| [resolution/](resolution/) | Per-ID deep-dive fix guides with code templates |
| [parse_elab_messages.py](parse_elab_messages.py) | Python parser: Vivado log → CSV |
| [csv_to_per_file_parts.py](csv_to_per_file_parts.py) | CSV splitter for Extended Flow (>50 messages) |
| [tcl-reference.md](tcl-reference.md) | TCL commands for MCP mode workflow |
| [report-format.md](report-format.md) | Diff syntax rules, file link format, section templates |
| [examples/](examples/) | Example reports: [report-errors.md](examples/report-errors.md), [report-clean.md](examples/report-clean.md) |

---

## References

Access via **vivado_doc_search** tool:
- **UG901**: Vivado Synthesis User Guide (HDL Coding Techniques)
- **UG906**: Vivado Design Analysis and Closure Techniques
- **UG949**: UltraFast Design Methodology Guide
- **UG835**: Vivado Tcl Command Reference

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-06-02 | Initial release — 117 actionable message handlers, log parser, dual-mode workflow |
