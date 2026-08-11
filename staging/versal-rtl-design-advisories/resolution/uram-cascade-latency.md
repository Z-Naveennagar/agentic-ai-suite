<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# M1: Cascaded URAM With Low Read Latency

**Check:** M1 | **Severity:** HIGH | **Category:** Memory Inference

## Root Cause

When URAMs are cascaded (cascade_height > 1), the enable signal propagates through
each URAM in the cascade chain via `CAS_OUT_EN → CAS_IN_EN`. Each URAM adds one
clock cycle of latency to this cascade path.

If `read_latency` is set too low for the cascade depth, the timing path through
the cascade chain violates setup requirements. A cascade_height of 8 (the maximum
for a single URAM column) produces a path with ~8 logic levels through the URAM
cascade, requiring `read_latency` of 4–5 to meet timing.

## Vivado Message

```
Slack (VIOLATED) : -X.XXXns
Path Type: Setup
Logic Levels: 10 (LUT2=1 LUT5=1 LUT6=1 URAM288E5=7)
```

When you see URAM288E5 appearing multiple times in a timing path's logic levels,
the cascade chain is on the critical path.

## Detection

**RTL grep:**
```
grep -rn "read_latency\|READ_LATENCY\|cascade_height\|CASCADE_HEIGHT" *.sv *.v *.vhd *.xci
```

**XPM parameter check:**
```tcl
# If using xpm_memory_tdpram or xpm_memory_sdpram
grep -rn "READ_LATENCY_A\|READ_LATENCY_B\|CASCADE_HEIGHT" *.sv *.v *.vhd
```

Rules of thumb:
- cascade_height=4 → read_latency ≥ 3
- cascade_height=8 → read_latency ≥ 4 (preferably 5)

## Fix

### Before (Broken — read_latency too low for cascade depth)

```verilog
xpm_memory_sdpram #(
    .ADDR_WIDTH_A(15),
    .ADDR_WIDTH_B(15),
    .MEMORY_SIZE(768 * 1024),     // Large memory → deep cascade
    .READ_DATA_WIDTH_B(768),
    .READ_LATENCY_B(2),           // TOO LOW for cascade_height=8
    .MEMORY_PRIMITIVE("ultra"),
    .CASCADE_HEIGHT(0)            // 0 = tool decides (may choose 8)
) mem_inst (
    // ...
);
```

### After (Fixed — read_latency increased to match cascade depth)

```verilog
xpm_memory_sdpram #(
    .ADDR_WIDTH_A(15),
    .ADDR_WIDTH_B(15),
    .MEMORY_SIZE(768 * 1024),
    .READ_DATA_WIDTH_B(768),
    .READ_LATENCY_B(5),           // FIXED: latency 5 for deep cascade
    .MEMORY_PRIMITIVE("ultra"),
    .CASCADE_HEIGHT(0)
) mem_inst (
    // ...
);
```

### Alternative: Limit Cascade Height

If latency cannot be increased, limit the cascade height and accept more URAM usage:

```verilog
xpm_memory_sdpram #(
    .ADDR_WIDTH_A(15),
    .ADDR_WIDTH_B(15),
    .MEMORY_SIZE(768 * 1024),
    .READ_DATA_WIDTH_B(768),
    .READ_LATENCY_B(2),
    .MEMORY_PRIMITIVE("ultra"),
    .CASCADE_HEIGHT(2)            // Limit cascade to 2 — less latency needed
) mem_inst (
    // ...
);
```

**Trade-off:** Lower cascade height uses more URAMs (wider matrix instead of
taller column) but requires fewer pipeline stages.

## Validation

```tcl
# Check cascade height and pipeline registers on URAMs
foreach uram [get_cells -hierarchical -filter {PRIMITIVE_TYPE =~ BLOCKRAM.URAM.*}] {
    set cas [get_property CASCADE_ORDER $uram]
    set oreg [get_property OREG_A $uram]
    puts "$uram: CASCADE_ORDER=$cas OREG_A=$oreg"
}

# Check for URAM-dominated timing paths
report_timing -through [get_pins -hierarchical -filter {REF_PIN_NAME =~ CAS_OUT_EN_*}] -max_paths 5
```

## Reference

- [CR-1028747](https://jira.xilinx.com/browse/CR-1028747) — Poor Fmax in IPI design with cascaded URAM
- AM007 — Versal Memory Resources Architecture Manual, URAM cascade timing
