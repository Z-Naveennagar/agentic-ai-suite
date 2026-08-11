<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# S1: VHDL Counter Increment Placement

**Check:** S1 | **Severity:** MEDIUM | **Category:** Coding Style

## Root Cause

In VHDL, signal assignment ordering within a process matters for synthesis inference.
When a counter increment is placed **outside** the `if` block (after the reset/wrap
check), synthesis generates suboptimal logic with significantly more LUTs on Versal
compared to UltraScale+. This is because the tool cannot efficiently merge the
counter increment with the range check.

Placing the increment in the `else` branch produces clean, minimal logic.

## Detection

**VHDL grep:**
```
grep -n "<=.*+.*1\|<=.*-.*1" *.vhd | grep -v "else"
```

Look for counter increment/decrement patterns that appear **after** an `if` block
rather than inside an `else` branch.

## Fix

### Before (Suboptimal — increment outside if)

```vhdl
process(clk)
begin
    if rising_edge(clk) then
        if (i = 50) then
            i <= 0;
        end if;
        i <= i + 1;           -- WRONG: Outside if, overwrites wrap
    end if;
end process;
```

This generates 39 LUTs + 4 LOOKAHEAD8 on Versal (vs 8 LUTs + 4 CARRY8 on US+).

### After (Optimal — increment in else branch)

```vhdl
process(clk)
begin
    if rising_edge(clk) then
        if (i = 50) then
            i <= 0;
        else
            i <= i + 1;       -- CORRECT: In else branch
        end if;
    end if;
end process;
```

This generates 5 LUTs + 4 LOOKAHEAD8 on Versal — nearly optimal.

### Verilog Equivalent

The same principle applies in Verilog, though it's less common:

```verilog
// WRONG
always @(posedge clk) begin
    if (i == 50) i <= 0;
    i <= i + 1;    // Overwrites the wrap — creates mux
end

// CORRECT
always @(posedge clk) begin
    if (i == 50)
        i <= 0;
    else
        i <= i + 1;
end
```

## Why It Matters More on Versal

On UltraScale+, the CARRY8 primitive masks some of the suboptimal logic because
carry chains are faster. On Versal, the LOOKAHEAD8 carry is slower, and the extra
MUX logic from the incorrect coding style pushes the design over timing budgets
that were met on US+.

## Validation

After re-synthesis, compare LUT counts:

```tcl
# Check utilization of the counter module
report_utilization -hierarchical -hierarchical_depth 2 -cells [get_cells *counter*]
```

Expected: LUT count should decrease significantly (e.g., 39 → 5 for a 50-count counter).

## Reference

- [CR-1063518](https://jira.xilinx.com/browse/CR-1063518) — QoR issue with Versal for free-running counter
- UG901 — Vivado Synthesis Guide, Counter inference patterns
