<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# D9: DSP INT8 Constant Inputs Optimized Away

**Check:** D9 | **Severity:** MEDIUM | **Category:** DSP Inference

## Root Cause

When using DSP58 in INT8 mode with constant-value inputs (e.g., fixed coefficients),
synthesis optimization may remove the constant drivers and simplify the logic. This
breaks the DSP INT8 inference because the tool no longer sees the expected input
structure — the DSP is either not inferred or inferred incorrectly, pushing logic
to fabric.

## Detection

**RTL pattern:**
```
grep -n "assign.*coeff.*=.*'d\|parameter.*COEFF\|localparam.*COEFF" *.sv *.v
```

Look for:
- Constants or parameters assigned to DSP input ports
- `assign coeff = 9'd85;` or similar fixed-value drivers
- Constants feeding A, B, or D inputs of INT8 multiply chains

**Synthesis log check:**
```
grep -i "optimiz.*constant\|trimm.*constant\|remov.*unused" synth.log
```

## Fix

### Before (Broken — constants optimized away)

```systemverilog
module dsp_int8_filter (
    input  wire        clk,
    input  wire        rst,
    input  wire        ce,
    input  wire signed [8:0] data_in [0:2],
    output reg  signed [47:0] result
);
    // Fixed coefficients
    logic signed [8:0] coeff;
    assign coeff = 9'sd85;

    reg signed [8:0] a0_reg, a1_reg, a2_reg;

    always_ff @(posedge clk) begin
        if (rst) begin
            a0_reg <= '0;
            a1_reg <= '0;
            a2_reg <= '0;
        end else if (ce) begin
            a0_reg <= coeff;    // Constant — optimizer may remove
            a1_reg <= coeff;    // Constant — optimizer may remove
            a2_reg <= coeff;    // Constant — optimizer may remove
        end
    end

    always_ff @(posedge clk)
        result <= a0_reg * data_in[0] + a1_reg * data_in[1] + a2_reg * data_in[2];
endmodule
```

### After (Fixed — keep attribute preserves constants)

```systemverilog
module dsp_int8_filter (
    input  wire        clk,
    input  wire        rst,
    input  wire        ce,
    input  wire signed [8:0] data_in [0:2],
    output reg  signed [47:0] result
);
    // Fixed coefficients — keep prevents optimization
    logic signed [8:0] coeff;
    assign coeff = 9'sd85;

    (* keep = "true" *) reg signed [8:0] a0_reg;
    (* keep = "true" *) reg signed [8:0] a1_reg;
    (* keep = "true" *) reg signed [8:0] a2_reg;

    always_ff @(posedge clk) begin
        if (rst) begin
            a0_reg <= '0;
            a1_reg <= '0;
            a2_reg <= '0;
        end else if (ce) begin
            a0_reg <= coeff;
            a1_reg <= coeff;
            a2_reg <= coeff;
        end
    end

    always_ff @(posedge clk)
        result <= a0_reg * data_in[0] + a1_reg * data_in[1] + a2_reg * data_in[2];
endmodule
```

**VHDL equivalent:**
```vhdl
attribute keep : string;
attribute keep of a0_reg : signal is "true";
attribute keep of a1_reg : signal is "true";
attribute keep of a2_reg : signal is "true";
```

## Validation

```tcl
# Verify DSP is inferred with AREG used (not bypassed)
foreach dsp [get_cells -hierarchical -filter {PRIMITIVE_TYPE =~ DSP.*}] {
    set areg [get_property AREG $dsp]
    puts "$dsp: AREG=$areg"
}

# Check no fabric multipliers remain
set fab_mult [get_cells -hierarchical -filter {PRIMITIVE_TYPE =~ CLB.LUT.* && NAME =~ "*mult*"} -quiet]
if {[llength $fab_mult] > 0} {
    puts "WARNING: [llength $fab_mult] fabric multiplier cells found — DSP inference may have failed"
}
```

## Reference

- [CR-1186324](https://jira.xilinx.com/browse/CR-1186324) — DSP INT8: incorrect inference using constant input signal
- AM004 — Versal DSP58 Architecture Manual, INT8 mode
