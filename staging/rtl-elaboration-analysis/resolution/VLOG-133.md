<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# VLOG-133: Net on LHS of Procedural Assignment

**Message:** [Synth 8-133] | **Severity:** ERROR | **Standard:** IEEE 1364-2005 §6.1, IEEE 1800-2017 §10.4

## Vivado Message

```
ERROR: [Synth 8-133] net 'result' can not be used in left-hand side of procedural assignment [/path/to/file.v:50]
```

## Root Cause

A `wire` (net type) is assigned inside an `always`, `initial`, `task`, or `function` block.
In Verilog, only `reg` types can appear on the LHS of procedural assignments (`=` or `<=`).

### Common Scenarios

| Scenario | Typical Cause |
|----------|--------------|
| ANSI port declared as `output wire` | Default port type is `wire`; needs `reg` for procedural |
| Internal signal declared as `wire` | Copy-paste from continuous context |
| SystemVerilog `logic` expected | Using `.v` extension (Verilog-2001 mode) instead of `.sv` |

## Fix Options

### Option 1: Change Declaration to `reg` (Verilog-2001)

```verilog
// ANSI port style
```
```diff
- output wire [7:0] result,
+ output reg  [7:0] result,
```

```verilog
// Internal signal
```
```diff
- wire [7:0] result;
+ reg  [7:0] result;
```

### Option 2: Use `logic` (SystemVerilog)

If the file is `.sv` or can be changed to SystemVerilog:
```diff
- output wire [7:0] result,
+ output logic [7:0] result,
```

`logic` works for both continuous and procedural assignments (single-driver only).

### Option 3: Move Assignment to Continuous Context

If the signal should remain a `wire`, move the assignment out of the `always` block:
```diff
- always @(*) begin
-   result = a + b;
- end
+ assign result = a + b;
```

## Decision Guide

| Keep as `wire`? | Use when... |
|-----------------|-------------|
| Yes | Signal has multiple drivers, or only needs `assign` |
| No → `reg` | Signal is assigned in `always`/`initial`/`task`/`function` |
| No → `logic` | SystemVerilog file; single driver; want flexibility |

## Validation

```tcl
synth_design -top $top -part $part -rtl -name rtl_1
```

## References

- IEEE 1364-2005 §6.1 (Net vs variable types)
- IEEE 1800-2017 §6.7 (`logic` type)
- UG901 Ch.4 (Vivado HDL coding)
