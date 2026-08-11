<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# D1: Pattern Detect Uses Conditional If/Else

**Check:** D1 | **Severity:** HIGH | **Category:** DSP Inference

## Root Cause

When pattern detect logic is coded using a conditional `if/else` statement, the synthesis
tool generates a MUX in fabric instead of using the DSP58's built-in pattern detect
hardware. The DSP58 `PATTERNDETECT` output compares the `P` output against a `PATTERN`
value internally — but only when the RTL uses a direct equality operator.

Using `if (p == pattern) patdet <= 1; else patdet <= 0;` generates fabric logic because
synthesis interprets this as a conditional assignment, not a pattern comparison.

## Detection

**RTL grep:**
```
grep -n "if.*==.*pattern\|if.*patterndetect\|if.*pat_det" *.sv *.v
```

Look for:
- `if (product == PATTERN)` or similar conditional checks on DSP outputs
- Separate `if/else` branches assigning 1 or 0 to a detect signal
- Pattern detect signal driven by combinational logic outside the DSP

## Fix

### Before (Broken — fabric MUX)

```verilog
module dsp_patdet (
    input  wire        clk,
    input  wire [17:0] a,
    input  wire [17:0] b,
    output reg         pattern_match
);
    reg [47:0] product;

    always @(posedge clk)
        product <= a * b;

    // WRONG: Conditional generates MUX in fabric
    always @(posedge clk) begin
        if (product == 48'h0000_0000_FFFF)
            pattern_match <= 1'b1;
        else
            pattern_match <= 1'b0;
    end
endmodule
```

### After (Fixed — DSP58 pattern detect hardware)

```verilog
module dsp_patdet (
    input  wire        clk,
    input  wire [17:0] a,
    input  wire [17:0] b,
    output reg         pattern_match
);
    reg [47:0] product;

    always @(posedge clk)
        product <= a * b;

    // CORRECT: Direct equality — synthesis maps to DSP PATTERNDETECT
    always @(posedge clk)
        pattern_match <= (product == 48'h0000_0000_FFFF);
endmodule
```

**Key difference:** The direct equality `(product == PATTERN)` is a single expression
that synthesis recognizes as a pattern-detect candidate. The `if/else` form is not.

## Validation

After synthesis, verify DSP58 pattern detect is used:

```tcl
# Check that PATTERNDETECT output is connected
foreach dsp [get_cells -hierarchical -filter {PRIMITIVE_TYPE =~ DSP.*}] {
    set pd [get_pins $dsp/PATTERNDETECT]
    if {[get_nets -of $pd -quiet] ne ""} {
        puts "OK: $dsp uses PATTERNDETECT output"
    }
}
```

## Reference

- [CR-1034185](https://jira.xilinx.com/browse/CR-1034185) — DSP PatternDetect logic incorrectly inferred
- UG901 — Vivado Synthesis Guide, Pattern Detect coding example
