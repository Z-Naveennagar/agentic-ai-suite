<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# CHECKLIST.md — Vivado Skill Validation Checklist

Use this checklist to validate any Vivado MCP skill before distribution. Each item includes what to check, why it matters, and the severity if missing.

Rate each item: ✅ Pass | ⚠️ Warning | ❌ Fail

---

## 1. YAML Frontmatter

| # | Check | Severity | Details |
|---|---|---|---|
| 1.1 | `name` field present and valid | ❌ Fail | Lowercase, hyphens, numbers only. Max 64 chars. No "anthropic" or "claude". |
| 1.2 | `description` field present and non-empty | ❌ Fail | Max 1024 chars. No XML tags. |
| 1.3 | Description includes what the skill does | ⚠️ Warning | First sentence should state the purpose. |
| 1.4 | Description includes trigger phrases | ❌ Fail | Without trigger phrases, the skill won't activate. Include 3+ user phrases. |
| 1.5 | Description mentions Vivado design stage | ⚠️ Warning | e.g., "post-synthesis", "post-place". Helps disambiguation between skills. |
| 1.6 | Description written in third person | ⚠️ Warning | "Runs CDC analysis..." not "I run CDC analysis..." or "You can run...". |

---

## 2. Prerequisites

| # | Check | Severity | Details |
|---|---|---|---|
| 2.1 | Prerequisites table present | ❌ Fail | Must list: Vivado version, target family, design state, open project requirement. |
| 2.2 | Vivado version specified | ⚠️ Warning | Include minimum and recommended versions. |
| 2.3 | Design state requirement clear | ❌ Fail | "Synthesis complete" vs "Placement complete" — agent needs to know what to check. |
| 2.4 | MCP connection mentioned | ⚠️ Warning | Note `mcp_vivado_connect` or interactive Tcl console. |

---

## 3. Efficiency Guidelines

| # | Check | Severity | Details |
|---|---|---|---|
| 3.1 | Efficiency Guidelines section present | ❌ Fail | This block prevents the most common MCP failures. |
| 3.2 | "Pass `session_id`" rule included | ❌ Fail | Missing this causes commands to target wrong session. |
| 3.3 | "Write reports to file" rule included | ❌ Fail | Without this, agent dumps huge reports into chat. |
| 3.4 | "Do NOT use shell ls/find" rule included | ⚠️ Warning | Prevents unreliable file discovery patterns. |
| 3.5 | "Do NOT use Vivado Tcl to read files" rule included | ❌ Fail | Prevents `exec cat` and `open/read/close` anti-patterns. |
| 3.6 | "Do NOT retry failed Tcl" rule included | ❌ Fail | Prevents cascading error spirals. |

---

## 4. Workflow Structure

| # | Check | Severity | Details |
|---|---|---|---|
| 4.1 | Progress tracker (inline checklist) present | ❌ Fail | Agent uses this to track state; skip-proof. |
| 4.2 | Sequential execution warning present | ❌ Fail | "Execute steps SEQUENTIALLY. Wait for each command to complete." |
| 4.3 | Steps are numbered and sequential | ⚠️ Warning | Don't use parallel step numbering for MCP commands. |
| 4.4 | Each step has a clear Tcl command block | ⚠️ Warning | Agent needs copy-pasteable Tcl, not vague instructions. |
| 4.5 | Step 1 includes workspace type auto-detection | ❌ Fail | Must handle both `.dcp` and `.xpr` workspaces. |
| 4.6 | Step 1 creates report output directory | ⚠️ Warning | `file mkdir vivado_agentic_ai_reports/<skill>/` in the same Tcl chain. |
| 4.7 | Report-generating step uses `-file` flag | ❌ Fail | Without `-file`, report goes to stdout and may truncate. |

---

## 5. Tcl Commands

| # | Check | Severity | Details |
|---|---|---|---|
| 5.1 | All Tcl blocks are single-line semicolon-chained | ❌ Fail | Multi-line Tcl breaks across `vivado_execute` calls. |
| 5.2 | No multi-line Tcl that depends on shared variables | ❌ Fail | Variables are lost between separate `vivado_execute` calls. |
| 5.3 | Timeout guidance provided for long-running commands | ⚠️ Warning | `synth_design`, `place_design`, `route_design` need explicit timeouts. |
| 5.4 | No `exec cat`, `open/read/close` for file reading | ❌ Fail | Use agent's native file reader tool instead. |
| 5.5 | No `shell ls`, `shell find`, `shell glob` | ⚠️ Warning | Use Tcl `glob` within `vivado_execute` or agent's file search. |
| 5.6 | Tcl commands use correct syntax (verified) | ❌ Fail | If unsure, recommend `vivado_doc_search` in the skill. |

---

## 6. Report Generation

| # | Check | Severity | Details |
|---|---|---|---|
| 6.1 | Output goes to `vivado_agentic_ai_reports/<skill>/` | ⚠️ Warning | Standardized location for orchestrator compatibility. |
| 6.2 | Action-before-narration enforcement present | ❌ Fail | "Invoke the write tool first, then summarize." |
| 6.3 | REPORT.md troubleshooting section present | ⚠️ Warning | Explains the "narrate without acting" failure mode. |
| 6.4 | Report file is read with agent's file reader or grep/sed | ❌ Fail | Not Vivado Tcl. |
| 6.5 | Targeted reading guidance provided for large reports | ⚠️ Warning | Skill should specify grep patterns or line ranges for reports >200 lines. Blind full reads bloat context. |
| 6.6 | Raw report path matches what Step 1 creates | ⚠️ Warning | Mismatched paths cause "file not found" in Step 2. |

---

## 7. Design-Specific Fixes

| # | Check | Severity | Details |
|---|---|---|---|
| 7.1 | "ACTUAL names" mandate present | ❌ Fail (if skill has fixes) | Skip only if skill produces no fix recommendations. |
| 7.2 | WRONG/CORRECT example table present | ⚠️ Warning | Concrete examples help the agent understand the constraint. |
| 7.3 | Fix templates use bracket markers | ⚠️ Warning | `[actual_clock_name]` style markers that the agent replaces. |
| 7.4 | Workflow includes "extract ACTUAL names" step | ❌ Fail (if skill has fixes) | Must happen between parsing the report and generating REPORT.md. |
| 7.5 | Fixes are copy-pasteable into XDC/RTL/Tcl | ❌ Fail (if skill has fixes) | Include `# Verify:` comment with validation command. |

---

## 8. Error Handling

| # | Check | Severity | Details |
|---|---|---|---|
| 8.1 | Error handling table present | ❌ Fail | At minimum: no design open, report command fails, prerequisite missing. |
| 8.2 | "No design open" error covered | ❌ Fail | Most common failure — recovery is `open_run` or `open_checkpoint`. |
| 8.3 | Missing prerequisites covered | ⚠️ Warning | What happens if synthesis isn't done? Constraints missing? |
| 8.4 | Command timeout scenario covered | ⚠️ Warning | Especially for `synth_design`, `place_design`, `route_design`. |

---

## 9. Validation

| # | Check | Severity | Details |
|---|---|---|---|
| 9.1 | Validation Tcl snippet present | ⚠️ Warning | `file exists` check for generated reports. |
| 9.2 | Success criteria stated | ⚠️ Warning | "Raw report exists AND REPORT.md exists with actual design names." |

---

## 10. References

| # | Check | Severity | Details |
|---|---|---|---|
| 10.1 | UG numbers cited | ⚠️ Warning | Grounds the skill in official documentation. |
| 10.2 | References are accurate | ⚠️ Warning | UG906 for timing, UG974 for XPM, UG949 for methodology, etc. |

---

## 11. Size and Structure

| # | Check | Severity | Details |
|---|---|---|---|
| 11.1 | SKILL.md body under 500 lines | ⚠️ Warning | If over 500, must split into REFERENCE.md, TEMPLATES.md, etc. |
| 11.2 | File references are one level deep | ⚠️ Warning | SKILL.md → REFERENCE.md (OK). SKILL.md → A.md → B.md (bad). |
| 11.3 | Long reference files have table of contents | ⚠️ Warning | Files >100 lines need a TOC so agent can navigate. |
| 11.4 | Consistent terminology throughout | ⚠️ Warning | Pick one term and stick with it (e.g., always "probe", not mix of "probe/monitor/debug port"). |

---

## 12. Composition (for skills in a shared library)

| # | Check | Severity | Details |
|---|---|---|---|
| 12.1 | Report directory follows convention | ⚠️ Warning | `vivado_agentic_ai_reports/<skill-name>/` |
| 12.2 | Workspace detection pattern is standard | ⚠️ Warning | Same DCP-vs-project Tcl in Step 1. |
| 12.3 | No conflicts with other skills' report dirs | ⚠️ Warning | Unique `<skill-name>` subdirectory. |
| 12.4 | Orchestrator compatibility | ⚠️ Warning | If part of a suite (like baselining), can it be called by an orchestrator skill? |

---

## 13. Bundled Tcl Efficiency (UG835/UG894)

Applies when the skill includes bundled `.tcl` files (`tcl/`, `scripts/*.tcl`). Does not apply to inline MCP Tcl snippets in SKILL.md.

| # | Check | Severity | Details |
|---|---|---|---|
| 13.1 | `get_*` results cached in variables | ⚠️ Warning | If same `get_clocks`, `get_cells`, `get_nets` etc. is called more than once in a proc, cache in a variable and reuse. |
| 13.2 | `get_property` called on whole list, not per-object | ⚠️ Warning | Replace `foreach x $list { get_property P $x }` with `get_property P $list` and multi-var foreach. |
| 13.3 | Filters pushed into `get_*` not applied in Tcl loop | ⚠️ Warning | Use `-filter {PROP == val}` inside `get_cells`/`get_nets` rather than checking inside foreach. |
| 13.4 | Single-use query results nested, not stored | ⚠️ Warning | `get_pins -of_objects [get_nets ...]` is faster than storing intermediate `set nets [get_nets]` when result used once. |
| 13.5 | `report_*` with both `-file` and `-return_string` combined | ❌ Fail | Never call the same `report_*` command twice — once to file, once to string. Combine: `set r [report_X -file f.rpt -return_string]`. |
| 13.6 | No `in`/`ni` operator on Vivado collections | ⚠️ Warning | Collections truncate at 500 in string representation. Use `lsearch -exact` instead. |
| 13.7 | Missing `$rpt_dir` or other variables used before definition | ❌ Fail | If a proc uses `$rpt_dir` to write reports, define it at the top of that proc. |

---

## Scoring

Count the results:

| Result | Meaning |
|---|---|
| All ✅ | Skill is ready for distribution |
| Any ⚠️, no ❌ | Skill works but has room for improvement |
| Any ❌ | Skill has critical issues — fix before distribution |

### Minimum viable skill (must pass all ❌ items):

- Valid YAML frontmatter with trigger phrases (1.1, 1.2, 1.4)
- Prerequisites table (2.1, 2.3)
- Full Efficiency Guidelines block (3.1–3.3, 3.5, 3.6)
- Workflow with progress tracker and sequential execution (4.1, 4.2, 4.5, 4.7)
- Single-line Tcl (5.1, 5.2, 5.4)
- Action-before-narration (6.2, 6.4)
- Actual-names mandate (7.1, 7.4, 7.5 — if skill has fixes)
- Error handling table with "no design open" (8.1, 8.2)

---

## Quick Audit Command

To quickly audit a SKILL.md file, search for these critical markers:

```bash
# Check for required sections (any missing = ❌)
grep -c "session_id" SKILL.md              # Pattern 1: session_id propagation
grep -c "semicolon\|single.line\|single-line" SKILL.md  # Pattern 2: single-line Tcl note
grep -c "open_checkpoint\|glob.*\.dcp" SKILL.md  # Pattern 3: workspace auto-detect
grep -c "\-file" SKILL.md                  # Pattern 4: report-to-file
grep -c "vivado_agentic_ai_reports" SKILL.md  # Pattern 5: standard report dir
grep -c "write tool\|invoke.*write\|REPORT.md.*exists" SKILL.md  # Pattern 6: action-before-narration
grep -c "ACTUAL\|actual.*names\|NO.*placeholder" SKILL.md  # Pattern 7: real names mandate
grep -c "\- \[ \]" SKILL.md               # Pattern 8: progress tracker
grep -c "SEQUENTIALLY\|sequential" SKILL.md  # Pattern 10: sequential execution
grep -c "Do NOT.*retry\|do not.*retry" SKILL.md  # Pattern 11: no-retry rule
```

Any count of 0 on a critical marker suggests the corresponding pattern is missing.
