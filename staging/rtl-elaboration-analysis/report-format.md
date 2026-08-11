<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Report Format — RTL Elaboration Analysis

## Output Files

The skill produces these files in the report directory:

| File | Purpose |
|------|---------|
| `elab_messages.csv` | Parsed messages: severity, msg_id, text, file, line, language |
| `report_data.json` | Structured analysis results for machine consumption |
| `REPORT.md` | Human-readable report with fixes |

---

## REPORT.md Structure

```markdown
# RTL Elaboration Analysis Report

**Design**: <top_module>
**Log file**: <path_to_log>
**Messages found**: <total> (E:<errors> CW:<crit_warnings> W:<warnings>)
**Actionable**: <count> | **Advisory**: <count>

## Summary

| Severity | Count | Actionable |
|----------|-------|------------|
| ERROR | N | N |
| CRITICAL WARNING | N | N |
| WARNING | N | N |

## Errors (Tier 1 — Immediate Fixes)

### [Synth 8-128] 'my_signal' is not declared
**File**: [path/to/file.v](path/to/file.v#L42)
**Cause**: Signal used but never declared.
**Fix**:
\```diff
--- a/path/to/file.v
+++ b/path/to/file.v
@@ -41,2 +41,3 @@
 // existing code context
+wire [7:0] my_signal;
 assign out = my_signal;
\```

### [Synth 8-XXX] ...
...

## Critical Warnings (Tier 1)

...

## Warnings (Tier 2 — Design Improvements)

### [Synth 8-566] inferring latch for variable 'state_reg'
**File**: [path/to/fsm.sv](path/to/fsm.sv#L100)
**Cause**: Incomplete case/if coverage in combinational always block.
**Fix**:
\```diff
--- a/path/to/fsm.sv
+++ b/path/to/fsm.sv
@@ -98,4 +98,5 @@
 always_comb begin
     case (state)
         IDLE: next_state = RUN;
+        default: next_state = IDLE;
     endcase
\```

## Advisory (Tier 3 — No Code Fix Needed)

| ID | Message | File | Line |
|----|---------|------|------|
| 564 | referenced signal 'clk' should be ... | ctrl.v | 200 |

## Cascading Errors

The following errors may be caused by earlier failures:

- [Synth 8-402] `failed synthesizing module 'sub_mod'` — likely caused by errors above in sub_mod
```

---

## Diff Format Rules

1. Use unified diff format with `--- a/` and `+++ b/` headers
2. Use **workspace-relative paths** in diff headers (not absolute)
3. Include 2-3 lines of surrounding context
4. Use `@@` hunk headers with approximate line numbers
5. Mark additions with `+`, deletions with `-`, context with space
6. Wrap diffs in ` ```diff ` fenced code blocks

---

## File Link Format

Use markdown links with workspace-relative paths:

- `[path/to/file.v](path/to/file.v#L42)` — link to specific line
- `[path/to/file.v](path/to/file.v#L40-L45)` — link to line range
- Never use absolute paths in links
- Never wrap file references in backticks

---

## report_data.json Schema

```json
{
  "design": "<top_module>",
  "log_file": "<path>",
  "timestamp": "<ISO-8601>",
  "summary": {
    "total": 15,
    "errors": 3,
    "critical_warnings": 2,
    "warnings": 10,
    "actionable": 12,
    "advisory": 3
  },
  "messages": [
    {
      "severity": "ERROR",
      "msg_id": 128,
      "text": "'my_signal' is not declared",
      "file": "src/top.v",
      "line": 42,
      "language": "VLOG",
      "tier": 1,
      "category": "undeclared_identifier",
      "fix_applied": true,
      "fix_description": "Added wire declaration",
      "cascading": false
    }
  ]
}
```

---

## Grouping and Ordering

1. Group by severity: ERROR → CRITICAL WARNING → WARNING
2. Within each group, sort by tier (1 first, then 2, then 3)
3. Within each tier, sort by file path then line number
4. Tier 3 messages go in a summary table, not individual sections
5. Cascading errors go in a separate section at the end
