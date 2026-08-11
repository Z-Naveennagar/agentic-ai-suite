<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# RTL Elaboration Analysis Report — Example (Errors Found)

```markdown
# RTL Elaboration Analysis Report

## Summary
| Severity | Count | Actionable | Advisory |
|----------|-------|------------|----------|
| Error | 3 | 3 | 0 |
| Critical Warning | 1 | 1 | 0 |
| Warning | 2 | 2 | 0 |

- **Log File:** [synth_1/runme.log](../../project_1.runs/synth_1/runme.log)
- **Analysis Status:** ⚠️ **ERRORS FOUND — synthesis incomplete**
- **Total Messages:** 6 (3 errors, 1 critical warning, 2 warnings)

## File Hotspots
| File | Errors | Crit. Warnings | Warnings | Total |
|------|--------|----------------|----------|-------|
| [fsm.sv](../../rtl/fsm.sv) | 1 | 1 | 1 | 3 |
| [top.v](../../rtl/top.v) | 1 | 0 | 1 | 2 |
| [alu.vhd](../../rtl/alu.vhd) | 1 | 0 | 0 | 1 |

## Message Type Distribution
| ID | Severity | Count | Description | Actionable? |
|----|----------|-------|-------------|-------------|
| 128 | ERROR | 1 | Undeclared variable | Tier 1 ✅ |
| 566 | WARNING | 1 | Latch inference | Tier 2 ✅ |
| 637 | CRITICAL | 1 | Dual driver | Tier 1 ✅ |
| 759 | ERROR | 1 | Width mismatch | Tier 2 ✅ |
| 564 | WARNING | 1 | Incomplete sensitivity list | Tier 1 ✅ |
| 133 | ERROR | 1 | Net on LHS of procedural | Tier 1 ✅ |

## Fixes — Errors (Priority 1)

### [Synth 8-128] Undeclared variable
**File:** [top.v:42](../../rtl/top.v#L42)
**Message:** 'mask' is not declared
**Root Cause:** Signal `mask` is used in an AND expression but never declared.

**Problematic Code:**
` ` `diff
  always @(posedge clk) begin
-   data_out <= data_in & mask;  // <- 'mask' is not declared
  end
` ` `

**Recommended Fix:**
` ` `diff
+ reg [7:0] mask;               // <- add missing declaration (width inferred from data_in)
+
  always @(posedge clk) begin
    data_out <= data_in & mask;
  end
` ` `

**Rationale:** Signal `mask` is used on the RHS of a non-blocking assignment inside
a clocked always block. Width is inferred as `[7:0]` to match `data_in`. Declared
as `reg` since it appears in procedural context.

---

### [Synth 8-133] Net on LHS of procedural assignment
**File:** [fsm.sv:18](../../rtl/fsm.sv#L18)
**Message:** net 'next_state' can not be used in left-hand side of procedural assignment
**Root Cause:** `next_state` is declared as `wire` (or default net type) but assigned
inside an `always` block.

**Problematic Code:**
` ` `diff
- output wire [1:0] next_state,  // <- wire cannot be procedurally assigned
` ` `

**Recommended Fix:**
` ` `diff
+ output reg  [1:0] next_state,  // <- change to reg for always block
` ` `

**Rationale:** Procedural assignments (`=` or `<=`) require `reg` or `logic` type.

---

### [Synth 8-759] Width mismatch in assignment
**File:** [alu.vhd:45](../../rtl/alu.vhd#L45)
**Message:** width mismatch in assignment; target has 8 bits, source has 16 bits
**Root Cause:** Assigning a 16-bit expression to an 8-bit signal without explicit slicing.

**Problematic Code:**
` ` `diff
- result <= a_extended * b;      -- 16-bit product assigned to 8-bit result
` ` `

**Recommended Fix:**
` ` `diff
+ result <= resize(a_extended * b, result'length);  -- truncate to 8 bits
` ` `

**Rationale:** VHDL requires explicit width management. Use `resize()` for numeric types.

## Fixes — Critical Warnings (Priority 2)

### [Synth 8-637] Dual driver
**File:** [fsm.sv:30](../../rtl/fsm.sv#L30)
**Message:** variable 'enable' cannot be written by both continuous and procedural assignments
**Root Cause:** Signal `enable` has both an `assign` statement and an `always` block assignment.

**Problematic Code:**
` ` `diff
- assign enable = default_en;
-
- always @(posedge clk)
-   if (start) enable <= 1'b1;
` ` `

**Recommended Fix:**
` ` `diff
+ always @(posedge clk) begin
+   if (start)
+     enable <= 1'b1;
+   else
+     enable <= default_en;   // merge into single driver
+ end
` ` `

## Fixes — Warnings (Priority 3)

### [Synth 8-566] Latch inference
**File:** [fsm.sv:55](../../rtl/fsm.sv#L55)
**Message:** inferring latch for variable 'data_out'
**Root Cause:** Incomplete `if` statement — missing `else` branch.

**Problematic Code:**
` ` `diff
  always @(*) begin
    if (enable)
      data_out = data_in;
-   // <- missing else branch — latch inferred
  end
` ` `

**Recommended Fix:**
` ` `diff
  always @(*) begin
    if (enable)
      data_out = data_in;
+   else
+     data_out = '0;          // prevent latch
  end
` ` `

---

### [Synth 8-564] Incomplete sensitivity list
**File:** [top.v:80](../../rtl/top.v#L80)
**Message:** referenced signal 'sel' should be on the sensitivity list
**Root Cause:** Combinational always block reads `sel` but it's not in `@(...)`.

**Recommended Fix:**
` ` `diff
- always @(a, b)
+ always @(*)               // automatic sensitivity list
` ` `

## Recommendations

### Immediate (fix now)
1. Fix all 3 errors — synthesis cannot complete until these are resolved
2. Fix the dual-driver critical warning — may cause incorrect synthesis

### High-Impact Quick Wins
3. Replace `always @(signal_list)` with `always @(*)` in all combinational blocks
4. Add default values at the top of combinational always blocks to prevent latches

### Next Steps
- Fix errors and re-run: `synth_design -top top -part <part> -rtl -name rtl_1`
- Many warnings may resolve after fixing root cause errors (cascading effect)
```
