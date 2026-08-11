<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# D6: DSP58 P→C Feedback Without PREG

**Check:** D6 | **Severity:** HIGH | **Category:** DSP Inference

## Root Cause

When the DSP58 output `P` feeds back to input `C` (common in accumulators and
feedback paths), the `PREG` output register is required for correct timing. Without
PREG, the feedback path is purely combinational through the DSP, creating a long
timing path that often fails.

The DSP58 architecture requires `PREG=1` for any `P→C` feedback loop. This is an
architectural constraint, not a tool limitation.

## Detection

**RTL pattern:**
```
# Look for accumulator patterns without explicit pipeline register
grep -n "<=.*+.*product\|<=.*+.*mult_out\|acc.*<=.*acc.*+" *.sv *.v
```

**Post-synthesis check:**
```tcl
# Find DSPs where P feeds back to C without PREG
foreach dsp [get_cells -hierarchical -filter {PRIMITIVE_TYPE =~ DSP.*}] {
    set preg [get_property PREG $dsp]
    if {$preg == 0} {
        set c_net [get_nets -of [get_pins $dsp/C[*]] -quiet]
        set p_net [get_nets -of [get_pins $dsp/P[*]] -quiet]
        if {$c_net eq $p_net && $c_net ne ""} {
            puts "CRITICAL: $dsp has P→C feedback with PREG=0"
        }
    }
}
```

## Fix

### Before (Broken — no PREG on feedback path)

```verilog
module dsp_accum (
    input  wire        clk,
    input  wire [26:0] a,
    input  wire [17:0] b,
    input  wire        load,
    output reg  [47:0] accum
);
    wire [47:0] product = a * b;

    // Accumulator without output register on DSP
    // P feeds to C combinationally — timing will fail
    always @(posedge clk) begin
        if (load)
            accum <= product;
        else
            accum <= accum + product;
    end
endmodule
```

### After (Fixed — PREG ensures registered feedback)

```verilog
module dsp_accum (
    input  wire        clk,
    input  wire [26:0] a,
    input  wire [17:0] b,
    input  wire        load,
    output reg  [47:0] accum
);
    reg  [47:0] product_reg;

    // Stage 1: Registered multiply (MREG)
    always @(posedge clk)
        product_reg <= a * b;

    // Stage 2: Registered accumulate (PREG)
    // The output register ensures P→C feedback is registered
    always @(posedge clk) begin
        if (load)
            accum <= product_reg;
        else
            accum <= accum + product_reg;
    end
endmodule
```

**Key point:** The accumulator output `accum` must be the direct output of a
registered `always @(posedge clk)` block so synthesis infers `PREG=1`. If any
combinational logic sits between the DSP P output and its feedback to C, the
path will fail timing.

## Validation

```tcl
# Verify PREG is set on DSPs with feedback
foreach dsp [get_cells -hierarchical -filter {PRIMITIVE_TYPE =~ DSP.*}] {
    set preg [get_property PREG $dsp]
    set opmode [get_property OPMODEREG $dsp]
    puts "$dsp: PREG=$preg OPMODEREG=$opmode"
}
```

## Reference

- [CR-1150378](https://jira.xilinx.com/browse/CR-1150378) — Register has been bad located, DSP58 timing failure
- AM004 — Versal DSP58 Architecture Manual, PREG register requirements
