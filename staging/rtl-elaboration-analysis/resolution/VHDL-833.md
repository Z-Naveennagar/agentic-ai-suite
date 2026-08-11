<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# VHDL-833: Unknown Identifier

**Message:** [Synth 8-833] | **Severity:** ERROR
**Also covers:** VLOG-546 (unresolved identifier), VHDL-768 (design unit not found),
VHDL-771 (unit not found in library), VLOG-617 (no signal for port connection)

## Vivado Message

```
ERROR: [Synth 8-833] Unknown identifier my_func [/path/to/file.vhd:60]
ERROR: [Synth 8-768] design unit 'my_pkg' not found [/path/to/file.vhd:3]
```

## Root Cause

An identifier (signal, type, function, procedure, component, entity) is used but
cannot be resolved in the current scope. This is the VHDL equivalent of VLOG-128.

### Pattern Recognition

| Pattern | Symptom | Root Cause |
|---------|---------|------------|
| P1: Missing `use` clause | Name exists in a package | `use work.pkg.all` not declared |
| P2: Missing `library` clause | Package in another library | `library lib` not declared |
| P3: Typo | Name close to existing declaration | Misspelled identifier |
| P4: Missing declaration | Name not found anywhere | Declaration was never added |
| P5: Wrong architecture | Component exists but in a different architecture | Architecture binding issue |

## Fix Options

### P1: Add Missing `use` Clause

```diff
  library ieee;
  use ieee.std_logic_1164.all;
+ use work.my_pkg.all;          -- add package containing my_func
```

### P2: Add Library and Use Clause

```diff
+ library my_lib;
+ use my_lib.my_pkg.all;
+
  entity my_design is
```

### P3: Fix Typo

```diff
- signal_valud <= '1';           -- ERROR: Unknown identifier 'signal_valud'
+ signal_valid <= '1';           -- fix typo
```

### P4: Add Missing Declaration

```diff
  architecture rtl of my_design is
+   signal my_signal : std_logic_vector(7 downto 0);  -- add declaration
  begin
```

### P5: VHDL-768 / 771 — Design Unit Not Found

Usually a project setup issue. Verify:
1. The source file containing the package/entity is added to the project
2. The library assignment is correct
3. Compile order puts the dependency first

```diff
+ library work;                         -- usually implicit
+ use work.missing_pkg.all;             -- ensure file is in project
```

## Cascading Effects

VHDL-833 is a common **root cause** error:
- VHDL-768 (design unit not found) → multiple VHDL-833 for all names from that unit
- VHDL-773 (missing body) → VHDL-833 for identifiers declared in the body

**Fix VHDL-768 first** — the downstream VHDL-833 messages will resolve.

## VLOG-546 / VLOG-617

SystemVerilog equivalents:
```
ERROR: [Synth 8-546] unresolved reference to 'my_type' [/path/to/file.sv:20]
ERROR: [Synth 8-617] no signal named 'clk' for port connection [/path/to/file.sv:30]
```

Fix with `import`:
```diff
+ import my_pkg::*;
```

Or fix signal name:
```diff
- .clk  (clck),    // ERROR: no signal named 'clck'
+ .clk  (clk),     // fix typo
```

## Validation

```tcl
synth_design -top $top -part $part -rtl -name rtl_1
```

## References

- IEEE 1076-2008 §12.4 (Use clauses)
- IEEE 1076-2008 §13.2 (Design libraries)
- UG901 Ch.4
