<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# VLOG-134: Variable on LHS of Continuous Assignment

**Message:** [Synth 8-134] | **Severity:** ERROR | **Standard:** IEEE 1364-2005 §6.1

## Vivado Message

```
ERROR: [Synth 8-134] variable 'data_out' can not be used in left-hand side of continuous assignment [/path/to/file.v:30]
```

## Root Cause

A `reg` (variable type) is used on the LHS of an `assign` statement. In Verilog,
`assign` (continuous assignment) requires a `wire` (net type) on the LHS.

## Fix Options

### Option 1: Change Declaration to `wire` (Recommended if purely combinational)

```diff
- output reg [7:0] data_out,
+ output wire [7:0] data_out,
```

or for internal signals:
```diff
- reg [7:0] data_out;
+ wire [7:0] data_out;
```

### Option 2: Move to Procedural Block (If sequential logic intended)

```diff
- assign data_out = data_in & mask;
+ always @(*) begin
+   data_out = data_in & mask;
+ end
```

### Option 3: Use `logic` (SystemVerilog)

In SystemVerilog, `logic` works with both `assign` and `always` blocks (single driver):
```diff
- output reg [7:0] data_out,
+ output logic [7:0] data_out,
```

## Decision Guide

| Approach | When to use |
|----------|-------------|
| Change to `wire` | Signal is purely combinational, driven by `assign` only |
| Move to `always` | Signal needs to be registered or part of procedural logic |
| Use `logic` (SV) | SystemVerilog file; want single declaration for either style |

## Paired with VLOG-133

VLOG-134 is the mirror of VLOG-133:
- **133**: `wire` on LHS of procedural → change to `reg`
- **134**: `reg` on LHS of continuous → change to `wire`

If both appear for the same signal, the declarations and assignments are inconsistent.
Decide the intent (combinational vs sequential) and fix both together.

## Validation

```tcl
synth_design -top $top -part $part -rtl -name rtl_1
```

## References

- IEEE 1364-2005 §6.1 (Net vs variable types)
- IEEE 1800-2017 §10.3 (Continuous assignments)
- UG901 Ch.4
