<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# VHDL-747: Missing Case Choices

**Message:** [Synth 8-747] | **Severity:** ERROR
**Also covers:** VHDL-790 (missing case alternatives)

## Vivado Message

```
ERROR: [Synth 8-747] missing choice(s) in case statement [/path/to/file.vhd:120]
```

## Root Cause

A `case` statement does not cover all possible values of the case expression type.
VHDL requires full coverage — every possible value must have a matching `when` clause,
or a `when others` clause must be present.

### Common Scenarios

| Scenario | Example |
|----------|---------|
| Enumerated type missing values | `type state_t is (IDLE, RUN, DONE, ERR)` — `ERR` not covered |
| `std_logic_vector` without `others` | 4-bit vector has 16 values, only 3 listed |
| Integer subtype range | `range 0 to 7` — only 0-5 covered |

## Fix Options

### Option 1: Add `when others` (Recommended)

```diff
  case state is
    when IDLE => next_state <= RUN;
    when RUN  => next_state <= DONE;
    when DONE => next_state <= IDLE;
+   when others => next_state <= IDLE;  -- cover ERR and any future values
  end case;
```

For `std_logic_vector`:
```diff
  case sel is
    when "00" => out <= a;
    when "01" => out <= b;
    when "10" => out <= c;
+   when others => out <= (others => '0');
  end case;
```

### Option 2: Add Explicit Missing Choices

When each value needs specific handling:
```diff
  case state is
    when IDLE => next_state <= RUN;
    when RUN  => next_state <= DONE;
    when DONE => next_state <= IDLE;
+   when ERR  => next_state <= IDLE;  -- explicit recovery
  end case;
```

### Option 3: Combine Choices

```diff
  case opcode is
    when "0000" => result <= a + b;
    when "0001" => result <= a - b;
+   when "0010" | "0011" => result <= a;  -- combine related opcodes
+   when others => result <= (others => '0');
  end case;
```

## Important Notes

- **Always prefer `when others`** for `std_logic_vector` cases — they have 9-value logic
  (`U`, `X`, `Z`, etc.) making explicit coverage impractical
- For enumerated types, `when others` prevents breakage when new enum values are added
- Missing choices also cause latch inference (related to VLOG-566 pattern)

## Verilog Equivalent

Verilog does not require full case coverage but will infer latches without `default`:
```verilog
case (state)           // Add: default: next_state = IDLE;
```

## Validation

```tcl
synth_design -top $top -part $part -rtl -name rtl_1
```

## References

- IEEE 1076-2008 §10.9 (Case statement completeness)
- UG901 Ch.4
