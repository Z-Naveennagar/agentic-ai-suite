<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# C1: DSPCPLX Output Not Registered

**Check:** C1 | **Severity:** HIGH | **Category:** DSPCPLX Cascade

## Root Cause

The DSPCPLX primitive in Versal has a longer internal pipeline than a standard DSP58.
When the DSPCPLX output is used without a register (speedup register), the combinational
output delay is too long for typical clock periods.

For FFT butterfly operations specifically, the total latency through DSPCPLX should be
budgeted at **7 clock cycles** (not 5 as with a standard DSP58 complex multiply).
Under-budgeting latency causes the output path to fail timing.

## Detection

**RTL pattern:**
```
grep -rn "DSPCPLX\|dsp_cplx\|complex_mult" *.sv *.v *.vhd
```

Look for:
- DSPCPLX instantiations without output registers
- Complex multiplier modules where the output is used combinationally
- FFT butterfly modules with latency budget of 5 or fewer cycles

**Post-synthesis check:**
```tcl
# Find DSPCPLX cells and check PREG
foreach dsp [get_cells -hierarchical -filter {REF_NAME =~ DSPCPLX*}] {
    set preg [get_property PREG $dsp]
    if {$preg == 0} {
        puts "WARNING: $dsp — DSPCPLX without PREG (output not registered)"
    }
}
```

## Fix

### Before (Broken — unregistered DSPCPLX output)

```verilog
module cmult (
    input  wire        clk,
    input  wire [17:0] ar, ai,   // Complex input A
    input  wire [17:0] br, bi,   // Complex input B
    output wire [35:0] pr, pi    // Complex output (combinational)
);
    // Complex multiply: (ar + j*ai) * (br + j*bi)
    // Result is unregistered — timing will fail
    assign pr = ar * br - ai * bi;
    assign pi = ar * bi + ai * br;
endmodule
```

### After (Fixed — registered output, latency 7 for FFT)

```verilog
module cmult (
    input  wire        clk,
    input  wire [17:0] ar, ai,
    input  wire [17:0] br, bi,
    output reg  [35:0] pr, pi
);
    // Pipeline registers for DSPCPLX inference
    reg [17:0] ar_r1, ai_r1, br_r1, bi_r1;
    reg [17:0] ar_r2, ai_r2, br_r2, bi_r2;
    reg [35:0] pr_int, pi_int;
    reg [35:0] pr_r1,  pi_r1;

    // Input registers (AREG, BREG — 2 deep)
    always @(posedge clk) begin
        ar_r1 <= ar;  ai_r1 <= ai;  br_r1 <= br;  bi_r1 <= bi;
        ar_r2 <= ar_r1; ai_r2 <= ai_r1; br_r2 <= br_r1; bi_r2 <= bi_r1;
    end

    // Multiply + accumulate (internal pipeline)
    always @(posedge clk) begin
        pr_int <= ar_r2 * br_r2 - ai_r2 * bi_r2;
        pi_int <= ar_r2 * bi_r2 + ai_r2 * br_r2;
    end

    // Output registers (PREG + speedup register)
    always @(posedge clk) begin
        pr_r1 <= pr_int;
        pr    <= pr_r1;
        pi_r1 <= pi_int;
        pi    <= pi_r1;
    end

    // Total latency: 2 (AREG) + 1 (MREG) + 1 (PREG) + 2 (speedup) + 1 = 7
endmodule
```

**Latency budget for DSPCPLX:**

| Stage | Cycles | Register |
|-------|:------:|----------|
| Input A/B registers | 2 | AREG, BREG |
| Multiply | 1 | MREG |
| Post-add | 1 | PREG |
| Speedup registers | 2 | Fabric FF |
| Output register | 1 | Fabric FF |
| **Total** | **7** | |

## Validation

```tcl
# Verify DSPCPLX has all pipeline registers enabled
foreach dsp [get_cells -hierarchical -filter {REF_NAME =~ DSPCPLX*}] {
    puts "$dsp: AREG=[get_property AREG $dsp] BREG=[get_property BREG $dsp] MREG=[get_property MREG $dsp] PREG=[get_property PREG $dsp]"
}
```

## Reference

- [CR-1076270](https://jira.xilinx.com/browse/CR-1076270) — IFFT design timing failure with Versal, passes on US+
- AM004 — Versal DSP58 / DSPCPLX Architecture Manual
