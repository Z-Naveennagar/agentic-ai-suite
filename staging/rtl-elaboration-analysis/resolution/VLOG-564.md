<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# VLOG-564: Incomplete Sensitivity List

**Message:** [Synth 8-564] | **Severity:** WARNING
**Also covers:** VHDL-758 (signal not in sensitivity list), VLOG-585 (always_ff no event control)

## Vivado Message

```
WARNING: [Synth 8-564] referenced signal 'sel' should be on the sensitivity list [/path/to/file.v:80]
WARNING: [Synth 8-758] signal 'sel' is read in the process but is not in the sensitivity list [/path/to/file.vhd:80]
```

## Root Cause

A combinational `always` block or VHDL process reads a signal that is not listed in
its sensitivity list. Synthesis ignores sensitivity lists (infers from usage), but
simulation respects them — creating a **simulation/synthesis mismatch**.

## Fix Options

### Option 1: Use Automatic Sensitivity (Recommended)

**Verilog-2001:**
```diff
- always @(a, b)          // missing 'sel'
+ always @(*)             // automatic — all read signals included
```

**SystemVerilog:**
```diff
- always @(a, b)
+ always_comb             // automatic sensitivity + additional checks
```

**VHDL-2008:**
```diff
- process(a, b)           -- missing 'sel'
+ process(all)            -- automatic sensitivity (VHDL-2008)
```

> **Note:** VHDL `process(all)` requires the project to enable VHDL-2008 mode.

### Option 2: Add Missing Signals Explicitly

When automatic sensitivity is not desired (e.g., intentional clock gating):

**Verilog:**
```diff
- always @(a, b)
+ always @(a, b, sel)
```

**VHDL:**
```diff
- process(a, b)
+ process(a, b, sel)
```

### Option 3: Convert to Sequential (If Intent is Registered)

If the block should be sequential (registered output):
```diff
- always @(a, b)
-   result = a & sel;
+ always @(posedge clk)
+   result <= a & sel;     // now registered — sensitivity is just the clock
```

## Decision Guide

| Approach | When to use |
|----------|-------------|
| `always @(*)` / `always_comb` | Combinational logic — default choice |
| Add signals explicitly | Intentional gating or legacy code you can't restructure |
| Convert to sequential | The output should actually be registered |

## VLOG-585: always_ff Without Event Control

```
WARNING: [Synth 8-585] always_ff block requires an event control
```

**Fix:** Add clock edge:
```diff
- always_ff begin
+ always_ff @(posedge clk) begin
```

## Validation

```tcl
synth_design -top $top -part $part -rtl -name rtl_1
```

## References

- IEEE 1364-2005 §9.7.5 (Implicit sensitivity lists)
- IEEE 1800-2017 §9.2.2.2 (`always_comb`)
- IEEE 1076-2008 §11.3 (`process(all)`)
- UG901 Ch.4
