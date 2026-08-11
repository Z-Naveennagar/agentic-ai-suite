<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# M6: URAM Without `ram_decomp` Attribute

**Check:** M6 | **Severity:** MEDIUM | **Category:** Memory Inference

## Root Cause

On Versal devices, the default URAM decomposition strategy can produce arrays that
use up to **25% more URAM288E5 primitives** than necessary compared to UltraScale+
for the same memory configuration. This is because the tool may choose a wider matrix
shape (e.g., 4×1 instead of 7×1) to optimize for timing at the expense of area.

Adding `(* ram_decomp = "area" *)` forces the tool to minimize URAM count, choosing
taller cascade chains over wider matrices.

## Detection

**RTL grep:**
```
# Check if URAM memories have ram_decomp attribute
grep -rn "ram_style.*ultra\|MEMORY_PRIMITIVE.*ultra" *.sv *.v *.vhd
grep -rn "ram_decomp" *.sv *.v *.vhd
```

If the first grep finds URAM-targeted memories but the second grep finds nothing,
the attribute is missing.

**Post-synthesis utilization check:**
```tcl
# Compare URAM usage vs expected
set uram_count [llength [get_cells -hierarchical -filter {PRIMITIVE_TYPE =~ BLOCKRAM.URAM.*}]]
puts "Total URAMs used: $uram_count"
report_ram_utilization
```

## Fix

### Before (Default — may over-allocate URAMs)

```verilog
(* ram_style = "ultra" *)
reg [767:0] mem [0:28671];    // 28K deep × 768-bit wide
```

### After (Fixed — area-optimal decomposition)

```verilog
(* ram_style = "ultra", ram_decomp = "area" *)
reg [767:0] mem [0:28671];    // Same memory, fewer URAMs
```

**VHDL:**
```vhdl
attribute ram_style  : string;
attribute ram_decomp : string;
attribute ram_style  of mem : signal is "ultra";
attribute ram_decomp of mem : signal is "area";
```

**XPM instantiation:**
```verilog
(* ram_decomp = "area" *)
xpm_memory_tdpram #(
    .MEMORY_SIZE(28672 * 768),
    .MEMORY_PRIMITIVE("ultra"),
    // ...
) mem_inst ( /* ... */ );
```

## Impact Example

For a 28K × 768-bit memory:

| Strategy | Matrix Shape | URAM Count |
|----------|:-----------:|:----------:|
| Default (timing) | 4×1 | 96 |
| `ram_decomp = "area"` | 7×1 | 77 |
| **Savings** | | **20%** |

The area strategy uses taller cascades (7 deep instead of 4), trading some cascade
latency for fewer URAMs. Combine with appropriate `read_latency` (see check M1).

## Validation

```tcl
# Check matrix shape in RAM utilization report
report_ram_utilization -file ram_util.rpt
# Look for "Matrix Shape" column — should be taller (e.g., 7x1 vs 4x1)
```

## Reference

- [CR-1161721](https://jira.xilinx.com/browse/CR-1161721) — Versal URAM memory array 25% larger than US+
- AM007 — Versal Memory Resources Architecture Manual
