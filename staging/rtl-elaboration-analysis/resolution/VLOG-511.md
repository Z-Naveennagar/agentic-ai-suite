<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# VLOG-511: Named Port Does Not Exist

**Message:** [Synth 8-511] | **Severity:** ERROR
**Also covers:** 519 (no field in class), 577 (no field in struct), 731 (VHDL: no such port), 777 (VHDL: record element not found), 730 (VHDL: no such generic), 767 (VHDL: no such attribute)

## Vivado Message

```
ERROR: [Synth 8-511] named port 'clk_in' does not exist in module 'sub_module' [/path/to/file.v:25]
ERROR: [Synth 8-731] no port named 'clk_in' on entity 'sub_module' [/path/to/file.vhd:30]
```

## Root Cause

A named port/field/generic connection references a name that doesn't exist in the
target module, struct, class, entity, or record type. Common causes:

| Pattern | Root Cause |
|---------|------------|
| P1: Typo | Port name misspelled — close match exists |
| P2: Renamed port | Module port was renamed but instantiation not updated |
| P3: Wrong module | Instantiating the wrong module version |
| P4: Missing port | Port genuinely needs to be added to the module |

## Fix Steps

### Step 1: Read the Target Definition

```
read_file on the module/entity definition to get the actual port list
```

### Step 2: Fuzzy Match

Compare the unresolved name against actual ports. Common typo patterns:
- Swapped characters: `clk_in` vs `clk_ni`
- Missing underscore: `datain` vs `data_in`
- Case mismatch (VHDL is case-insensitive, Verilog is not): `CLK` vs `clk`
- Prefix/suffix: `data` vs `data_i`, `i_data` vs `data`

### Step 3: Apply Fix

**If typo (edit distance ≤ 2):**
```diff
  .clk_ni  (sys_clk),     // ERROR: no port 'clk_ni'
+ .clk_in  (sys_clk),     // fix typo: clk_ni → clk_in
```

**If port was removed/renamed — update instantiation:**
```diff
  .old_port_name (signal),  // port no longer exists
+ .new_port_name (signal),  // use current port name
```

**If port needs to be added to the module:**
```diff
  module sub_module (
    input wire clk,
    input wire rst,
+   input wire clk_in,      // add missing port
    output wire [7:0] data
  );
```

## VHDL-Specific Notes

For VHDL record elements (VHDL-777):
```diff
  my_rec.feild <= '1';      -- ERROR: no element 'feild'
+ my_rec.field <= '1';      -- fix typo
```

For VHDL generics (VHDL-730):
```diff
  generic map (WIDHT => 8)   -- ERROR: no generic 'WIDHT'
+ generic map (WIDTH => 8)   -- fix typo
```

## Validation

```tcl
synth_design -top $top -part $part -rtl -name rtl_1
```

## References

- IEEE 1364-2005 §12.3.3 (Named port connections)
- IEEE 1076-2008 §6.5.7 (VHDL port map)
