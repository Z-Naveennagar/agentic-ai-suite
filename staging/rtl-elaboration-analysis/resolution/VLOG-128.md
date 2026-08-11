<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# VLOG-128: Undeclared Identifier

**Message:** [Synth 8-128] | **Severity:** ERROR | **Standard:** IEEE 1364-2005 §12.3, IEEE 1800-2017 §6.7

## Vivado Message

```
ERROR: [Synth 8-128] 'my_signal' is not declared [/path/to/file.v:42]
```

## Root Cause

A signal, variable, or net name is used but has no visible declaration in the current scope.

### Pattern Recognition

| Pattern | Symptom | Root Cause |
|---------|---------|------------|
| P1: Typo | Name close to existing declaration | Misspelled identifier |
| P2: Missing declaration | Name not found anywhere in module | Declaration was never added |
| P3: Missing import | Name exists in a package | Missing `import pkg::*` |
| P4: Missing include | Name defined in a header file | Missing `` `include "header.vh" `` |

## Fix Options

### P1: Fix Typo (Most Common)

**Detection:** Use fuzzy search — find declarations with edit distance ≤ 2 from the
undeclared name.

```verilog
// Before — typo: 'data_vaild' instead of 'data_valid'
assign out = data_vaild;  // ERROR: [Synth 8-128] 'data_vaild' is not declared
```

```diff
- assign out = data_vaild;
+ assign out = data_valid;   // fix typo
```

### P2: Add Missing Declaration

**Detection:** No similar name found. Infer type from usage context:
- Used on LHS of `<=` inside `always @(posedge ...)` → `reg`
- Used on LHS of `=` inside `always @(*)` → `reg` (or `logic` in SV)
- Used only on RHS or in `assign` RHS → `wire`
- Used on LHS of `assign` → `wire`

```verilog
// Before — signal used but never declared
always @(posedge clk)
  data_out <= data_in & mask;  // ERROR: 'mask' is not declared
```

```diff
  // Signal declarations
  wire [7:0] data_in;
+ reg  [7:0] mask;         // add missing declaration — inferred reg from always block
```

**Width inference:** Extract width from the context expression. If `data_in` is `[7:0]`
and `mask` is ANDed with it, `mask` should also be `[7:0]`.

### P3: Add Missing Import (SystemVerilog)

**Detection:** Search `*.sv` files for `typedef` or `parameter` matching the name.

```verilog
// Before — type defined in package but not imported
module my_mod (input clk);
  state_t current_state;  // ERROR: 'state_t' is not declared
```

```diff
+ import my_pkg::state_t;  // or: import my_pkg::*;
+
  module my_mod (input clk);
    state_t current_state;
```

### P4: Add Missing Include

**Detection:** Search `*.vh` / `*.svh` files for the declaration.

```verilog
// Before — macro/parameter defined in header
module top;
  wire [`DATA_WIDTH-1:0] bus;  // ERROR: 'DATA_WIDTH' is not declared
```

```diff
+ `include "defines.vh"
+
  module top;
    wire [`DATA_WIDTH-1:0] bus;
```

## Cascading Effects

VLOG-128 is a common **root cause** that triggers cascading messages:
- VLOG-546 (unresolved identifier) on same or related names
- VLOG-576 (type mismatch) when undeclared name is used in typed context
- VLOG-402 (failed synthesizing module) when errors accumulate

**Fix the VLOG-128 first** — many downstream messages will resolve automatically.

## Validation

After applying the fix, re-run elaboration and verify:
```tcl
synth_design -top $top -part $part -rtl -name rtl_1
```
The message should no longer appear for the fixed identifier.

## References

- IEEE 1364-2005 §12.3 (Verilog scope rules)
- IEEE 1800-2017 §6.7 (SystemVerilog net/variable declarations)
- UG901 Ch.4 (Vivado Synthesis — HDL coding guidelines)
