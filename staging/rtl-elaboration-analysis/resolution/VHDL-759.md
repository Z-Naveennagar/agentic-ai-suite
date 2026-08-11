<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# VHDL-759: Width Mismatch in Assignment

**Message:** [Synth 8-759] | **Severity:** ERROR
**Also covers:** VLOG-514 (port width mismatch), VHDL-781 (port width mismatch),
760 (logical operator length), 761 (array aggregate width), 857 (generic width), 867 (function arg size)

## Vivado Message

```
ERROR: [Synth 8-759] width mismatch in assignment; target has 8 bits, source has 16 bits [/path/to/file.vhd:45]
WARNING: [Synth 8-514] port width mismatch; port 'data_in' has 8 bits, signal 'bus' has 16 bits [/path/to/file.v:30]
```

## Root Cause

Source and target of an assignment, port connection, or operator have different bit widths.
The message always tells you the expected and actual widths.

## Fix Steps

### Step 1: Read Both Declarations

Read the declaration of both source and target to understand intent:
```
read_file for target signal declaration
read_file for source signal/expression
```

### Step 2: Determine Which Side to Fix

| Scenario | Fix |
|----------|-----|
| Target should be wider | Change target declaration |
| Source should be narrower | Slice or resize the source |
| Both are correct but need conversion | Add explicit conversion |
| Port width changed upstream | Update instantiation to match |

### Step 3: Apply Fix

**VHDL — Resize with `resize()` (numeric types):**
```diff
- data_out <= data_in;                              -- 8-bit target, 16-bit source
+ data_out <= resize(data_in, data_out'length);     -- truncate to 8 bits
```

**VHDL — Slice (std_logic_vector):**
```diff
- data_out <= data_in;                -- 8-bit target, 16-bit source
+ data_out <= data_in(7 downto 0);   -- take lower 8 bits
```

**VHDL — Zero-extend (target wider):**
```diff
- data_out <= data_in;                                    -- 16-bit target, 8-bit source
+ data_out <= (others => '0');                             -- clear first
+ data_out(data_in'range) <= data_in;                     -- assign lower bits
```
Or:
```diff
+ data_out <= std_logic_vector(resize(unsigned(data_in), 16));
```

**Verilog — Fix port width:**
```diff
- .data_in  (bus),          // port is 8 bits, bus is 16 bits
+ .data_in  (bus[7:0]),     // slice to match port width
```

**Verilog — Change declaration:**
```diff
- wire [15:0] bus;
+ wire [7:0]  bus;          // match port width
```

**Generic width mismatch (VHDL-857):**
```diff
- generic map (WIDTH => X"FF")    -- 8 bits, but generic expects 16
+ generic map (WIDTH => X"00FF")  -- pad to 16 bits
```

## Common Patterns

| ID | Pattern | Typical Fix |
|----|---------|-------------|
| 759 | Signal assignment | `resize()` or slice |
| 514 | Port connection | Slice signal or fix port |
| 781 | Port map (VHDL) | Same as 514 |
| 760 | `and`/`or`/`xor` operands | Resize one operand |
| 761 | Array aggregate | Fix element widths |
| 857 | Generic map | Fix actual value width |
| 867 | Function argument | Fix argument width |

## Validation

```tcl
synth_design -top $top -part $part -rtl -name rtl_1
```

## References

- IEEE 1076-2008 §9.2.6 (Type conversion)
- IEEE 1800-2017 §11.6 (Expression bit-length)
- UG901 Ch.4
