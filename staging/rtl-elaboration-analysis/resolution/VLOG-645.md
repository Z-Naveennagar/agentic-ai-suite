<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# VLOG-645: Blocking/Non-blocking Assignment Mix

**Message:** [Synth 8-645] | **Severity:** WARNING | **Standard:** IEEE 1364-2005 §9.2

## Vivado Message

```
WARNING: [Synth 8-645] variable 'data' is being assigned both blocking and
  non-blocking assignments, non-blocking assignments will be treated as
  blocking assignments [/path/to/file.v:30]
```

## Root Cause

The same variable is assigned with both `=` (blocking) and `<=` (non-blocking) within
the same `always` block or across blocks. This creates simulation/synthesis mismatch.

### Rules

| Block Type | Correct Assignment | Reason |
|------------|-------------------|--------|
| `always @(posedge clk)` | `<=` (non-blocking) | Sequential — avoids race conditions |
| `always @(*)` / `always_comb` | `=` (blocking) | Combinational — ensures correct evaluation order |

## Fix Options

### Sequential Block — Use All Non-blocking

```diff
  always @(posedge clk) begin
-   temp = data_in;        // blocking — wrong in sequential
-   data_out <= temp;      // non-blocking
+   temp <= data_in;       // non-blocking — consistent
+   data_out <= temp;      // non-blocking
  end
```

### Combinational Block — Use All Blocking

```diff
  always @(*) begin
-   result <= a + b;       // non-blocking — wrong in combinational
+   result = a + b;        // blocking — correct for combinational
  end
```

### Mixed Intent — Split Into Two Blocks

If both blocking and non-blocking are intentional (e.g., intermediate combinational
value feeding a register):

```diff
- always @(posedge clk) begin
-   temp = a + b;           // blocking for intermediate
-   result <= temp & mask;  // non-blocking for register
- end

+ // Combinational logic
+ always @(*) begin
+   temp = a + b;
+ end
+
+ // Sequential logic
+ always @(posedge clk) begin
+   result <= temp & mask;
+ end
```

## Decision Guide

| Situation | Fix |
|-----------|-----|
| All in `always @(posedge/negedge)` | Change all to `<=` |
| All in `always @(*)` / `always_comb` | Change all to `=` |
| Mixed intent in one block | Split into separate comb + seq blocks |

## Validation

```tcl
synth_design -top $top -part $part -rtl -name rtl_1
```

## References

- IEEE 1364-2005 §9.2 (Procedural assignments)
- Cummings SNUG-2000 "Nonblocking Assignments in Verilog Synthesis"
- UG901 Ch.4
