<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# VLOG-637: Dual Driver (Continuous + Procedural)

**Message:** [Synth 8-637] | **Severity:** CRITICAL WARNING
**Also covers:** VHDL-823 (signal driven twice in process)

## Vivado Message

```
CRITICAL WARNING: [Synth 8-637] variable 'data' cannot be written by both
  continuous and procedural assignments [/path/to/file.v:55]
ERROR: [Synth 8-823] signal 'data' is driven twice in process [/path/to/file.vhd:60]
```

## Root Cause

A signal has two conflicting driver types:
- An `assign` statement (continuous)
- An `always` block assignment (procedural)

Or in VHDL, a signal is assigned in two separate processes or in both a concurrent
and sequential context.

## Fix Steps

### Step 1: Find All Drivers

Search the file for all assignments to the signal:
```
grep_search for: "data\s*<=" and "assign\s+data" and "data\s*="
```

### Step 2: Determine Intent

| If... | Then... |
|-------|---------|
| `assign` is the intended driver | Remove the `always` block assignment |
| `always` block is the intended driver | Remove the `assign` statement |
| Both are needed for different conditions | Merge into a single driver style |

### Step 3: Apply Fix

**Remove the continuous assignment:**
```diff
- assign data = default_value;          // remove continuous driver
-
  always @(posedge clk) begin
    if (enable)
      data <= new_value;
+   else
+     data <= default_value;            // move default here
  end
```

**Or remove the procedural assignment:**
```diff
- always @(*) begin
-   data = a & b;                       // remove procedural driver
- end

+ assign data = a & b;                  // keep only continuous
```

**Or merge into a single always block:**
```diff
- assign data = sel ? a : b;
- always @(posedge clk)
-   if (load) data <= ext_data;

+ always @(posedge clk) begin
+   if (load)
+     data <= ext_data;
+   else
+     data <= sel ? a : b;              // merged into one driver
+ end
```

## VHDL: Driven Twice in Process (823)

Two assignments to the same signal in the same process where both are always executed:

```diff
  process(clk)
  begin
    if rising_edge(clk) then
-     data <= a;          -- first assignment
-     data <= b;          -- second assignment overwrites — remove one
+     data <= b;          -- keep only the intended assignment
    end if;
  end process;
```

Or signal driven by two separate processes — merge into one:
```diff
- -- Process 1
- process(clk) begin
-   if rising_edge(clk) then data <= a; end if;
- end process;
- -- Process 2
- process(clk) begin
-   if rising_edge(clk) then data <= b; end if;
- end process;

+ -- Single process
+ process(clk) begin
+   if rising_edge(clk) then
+     if sel = '1' then data <= a;
+     else              data <= b;
+     end if;
+   end if;
+ end process;
```

## Validation

```tcl
synth_design -top $top -part $part -rtl -name rtl_1
```

## References

- IEEE 1364-2005 §6.1 (Net vs variable resolution)
- IEEE 1800-2017 §10.3.1 (Continuous assignment restrictions)
- UG901 Ch.4
