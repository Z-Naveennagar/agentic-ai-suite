<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# S8: VHDL Depth-1 Memory Address Width

**Check:** S8 | **Severity:** LOW | **Category:** Coding Style

## Root Cause

When a VHDL memory is declared with `depth = 1` and the address width is computed
using `clogb2(depth - 1)` or equivalent, the result is `clogb2(0) = 0`. This creates
a **null range** for the address port (e.g., `std_logic_vector(-1 downto 0)`), which
causes synthesis to trim off the address entirely and use only the write-enable as
the clock-enable for the BRAM register.

This means both address `0` and address `1` map to the same storage location, producing
incorrect logic. The same template works correctly in Verilog because Verilog handles
zero-width vectors differently.

## Detection

**VHDL grep:**
```
grep -n "clog2\|clogb2\|log2\|depth.*-.*1\|DEPTH.*1" *.vhd
```

Look for:
- Memory declarations where depth is parameterizable and can be 1
- Address width computed as `integer(ceil(log2(real(depth))))` with depth=1
- Vivado language templates used with depth=1

## Fix

### Before (Broken — null address range)

```vhdl
constant DEPTH : integer := 1;
constant ADDR_W : integer := integer(ceil(log2(real(DEPTH))));
-- ADDR_W = 0, creates null range

signal addr : std_logic_vector(ADDR_W - 1 downto 0);  -- (-1 downto 0) = null!

type mem_type is array (0 to DEPTH - 1) of std_logic_vector(DATA_W - 1 downto 0);
signal mem : mem_type;

process(clk)
begin
    if rising_edge(clk) then
        if (we = '1') then
            mem(to_integer(unsigned(addr))) <= din;  -- addr is null, trimmed
        end if;
        dout <= mem(to_integer(unsigned(addr)));
    end if;
end process;
```

### After (Fixed — explicit minimum address width)

```vhdl
constant DEPTH : integer := 1;
-- Ensure minimum address width of 1 bit
constant ADDR_W : integer := maximum(1, integer(ceil(log2(real(DEPTH)))));
-- ADDR_W = 1

signal addr : std_logic_vector(ADDR_W - 1 downto 0);  -- (0 downto 0) = 1 bit

type mem_type is array (0 to DEPTH - 1) of std_logic_vector(DATA_W - 1 downto 0);
signal mem : mem_type;

process(clk)
begin
    if rising_edge(clk) then
        if (we = '1') then
            mem(to_integer(unsigned(addr))) <= din;
        end if;
        dout <= mem(to_integer(unsigned(addr)));
    end if;
end process;
```

### Alternative: Guard Against Depth=1

```vhdl
function addr_width(depth : integer) return integer is
begin
    if depth <= 1 then
        return 1;
    else
        return integer(ceil(log2(real(depth))));
    end if;
end function;

constant ADDR_W : integer := addr_width(DEPTH);
```

## Key Point

This is a **VHDL-specific** issue. The same Vivado RAM template in Verilog handles
depth=1 correctly because `$clog2(1) = 1` in Verilog (ceiling of log2), whereas
VHDL `ceil(log2(1.0)) = ceil(0.0) = 0`.

## Validation

Check synthesis schematic for the memory — address input should have a wire
connected, not be trimmed:

```tcl
# After synthesis, check if address pins are connected
set bram_cells [get_cells -hierarchical -filter {PRIMITIVE_TYPE =~ BLOCKRAM.*}]
foreach cell $bram_cells {
    set addr_pins [get_pins $cell/ADDR*]
    foreach pin $addr_pins {
        set net [get_nets -of $pin -quiet]
        if {$net eq ""} {
            puts "WARNING: $pin has no driver — possible null address"
        }
    }
}
```

## Reference

- [CR-1223300](https://jira.xilinx.com/browse/CR-1223300) — Incorrect RAM register optimized for depth 1 (VHDL)
- UG901 — Vivado Synthesis Guide, RAM templates
