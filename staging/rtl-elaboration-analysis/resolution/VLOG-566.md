<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# VLOG-566: Inferring Latch

**Message:** [Synth 8-566] | **Severity:** WARNING | **Standard:** UG901 Ch.4.3.1

## Vivado Message

```
WARNING: [Synth 8-566] inferring latch for variable 'state_reg' [/path/to/file.v:100]
```

## Root Cause

A combinational `always` block has incomplete assignment coverage — some execution
paths don't assign a value to the signal, so a latch is inferred to hold the
previous value. Latches are almost always unintentional in FPGA designs.

### Pattern Recognition

| ID | Pattern | Root Cause |
|----|---------|------------|
| P1 | `if (en) out <= val;` (no else) | Missing `else` branch |
| P2 | `case (sel) ... endcase` (no default) | Missing `default` case |
| P3 | Multiple outputs, not all assigned in every branch | Partial assignment |
| P4 | `if/else` chain without final `else` | Missing terminal else |

## Fix Options

### P1: Add Missing `else` Branch

```diff
  always @(*) begin
    if (enable)
      data_out = data_in;
+   else
+     data_out = '0;          // prevent latch — assign known value
  end
```

### P2: Add `default` to Case Statement

```diff
  always @(*) begin
    case (state)
      IDLE:  next_state = RUN;
      RUN:   next_state = DONE;
      DONE:  next_state = IDLE;
+     default: next_state = IDLE;  // prevent latch
    endcase
  end
```

### P3: Initialize All Outputs at Block Start (Best Practice)

For blocks with multiple outputs, assign default values at the top:

```diff
  always @(*) begin
+   // Default values — prevents latches for all outputs
+   next_state = state;
+   data_out   = '0;
+   valid      = 1'b0;
+
    case (state)
      IDLE: begin
        if (start) begin
          next_state = RUN;
          valid = 1'b1;
        end
-       // data_out not assigned here → latch!
      end
      RUN: begin
        next_state = DONE;
        data_out = result;
      end
    endcase
  end
```

### P4: Add Terminal `else`

```diff
  always @(*) begin
    if (sel == 2'b00)
      out = a;
    else if (sel == 2'b01)
      out = b;
    else if (sel == 2'b10)
      out = c;
+   else
+     out = '0;               // cover sel == 2'b11
  end
```

### Convert to Sequential (If Latch Was Intentional)

In rare cases where holding the previous value is desired, use a register:
```diff
- always @(*)                    // combinational latch — bad
-   if (en) data_out = data_in;
+ always @(posedge clk)          // registered — explicit hold
+   if (en) data_out <= data_in; // holds when en=0 (register behavior)
```

## VHDL Equivalent

VHDL uses `process` blocks with the same patterns:
```diff
  process(sel, a, b)
  begin
    case sel is
      when "00" => out <= a;
      when "01" => out <= b;
+     when others => out <= (others => '0');  -- prevent latch
    end case;
  end process;
```

## Decision Guide

| Approach | When to use |
|----------|-------------|
| Add default values at block top | Multiple outputs — safest, most maintainable |
| Add `else`/`default` | Single output, simple logic |
| Convert to sequential | Value should genuinely hold across clock cycles |

## Validation

After fixing, verify the latch warning is gone:
```tcl
synth_design -top $top -part $part -rtl -name rtl_1
```

Also check `report_utilization` for LDCE/LDPE count — should be 0 unless intentional.

## References

- UG901 Ch.4.3.1 (Latch inference)
- IEEE 1364-2005 §9.4.2 (Level-sensitive sequential logic)
- STARC RTL Coding Rules §2.2.1
