<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# D5: Mixed Inferred + Instantiated DSP Cascade

**Check:** D5 | **Severity:** HIGH | **Category:** DSP Inference

## Root Cause

When a DSP cascade chain contains both behaviorally-inferred DSPs and explicitly
instantiated DSP58 primitives, the synthesis tool cannot merge them into a single
cascade chain. The inferred DSP's output (`P`) connects to the instantiated DSP's
input via general routing instead of the dedicated `PCOUT → PCIN` cascade path.

This results in:
- Loss of the dedicated cascade interconnect (adds routing delay)
- Potential timing violations on the cascade path
- Incorrect functionality if the cascade was timing-critical

## Detection

**RTL grep:**
```
grep -rn "DSP58\b\|DSP48E2\b\|DSPCPLX\b" *.sv *.v *.vhd
```

If instantiated DSP primitives are found, check whether the same datapath also has
behaviorally-described multiply-accumulate logic that would infer additional DSPs.

**Post-synthesis check:**
```tcl
# Look for DSPs with P output routed to another DSP's C input (not PCIN)
foreach dsp [get_cells -hierarchical -filter {PRIMITIVE_TYPE =~ DSP.*}] {
    set p_net [get_nets -of [get_pins $dsp/P[*]] -quiet]
    foreach pin [get_pins -of $p_net -filter {DIRECTION == IN} -quiet] {
        set pin_name [get_property REF_PIN_NAME $pin]
        if {[string match "C*" $pin_name]} {
            puts "WARNING: $dsp P output routes to C port (not PCIN cascade): $pin"
        }
    }
}
```

## Fix

### Before (Broken — mixed inferred + instantiated)

```verilog
// Stage 1: Behaviorally inferred DSP
reg [47:0] stage1_p;
always @(posedge clk)
    stage1_p <= a * b;

// Stage 2: Instantiated DSP58 — tool CANNOT cascade from inferred stage1
DSP58 #(
    .USE_MULT("MULTIPLY"),
    .PREG(1)
) dsp_stage2 (
    .CLK(clk),
    .A(c),
    .B(d),
    .PCIN(stage1_p),    // This connection FAILS — stage1 is inferred, not instantiated
    .P(result)
);
```

### After — Option 1: All Behavioral (Recommended)

```verilog
// Both stages inferred — tool creates cascade automatically
reg [47:0] stage1_p, stage2_p;

always @(posedge clk)
    stage1_p <= a * b;

always @(posedge clk)
    stage2_p <= (c * d) + stage1_p;  // Tool infers PCOUT→PCIN cascade
```

### After — Option 2: All Instantiated

```verilog
wire [47:0] pcout_stage1;

DSP58 #(.USE_MULT("MULTIPLY"), .PREG(1))
dsp_stage1 (
    .CLK(clk), .A(a), .B(b),
    .PCOUT(pcout_stage1),
    .P()
);

DSP58 #(.USE_MULT("MULTIPLY"), .PREG(1))
dsp_stage2 (
    .CLK(clk), .A(c), .B(d),
    .PCIN(pcout_stage1),    // Both instantiated — cascade works
    .P(result)
);
```

## Validation

```tcl
# Verify PCOUT→PCIN connections exist
foreach dsp [get_cells -hierarchical -filter {PRIMITIVE_TYPE =~ DSP.*}] {
    set pcout [get_nets -of [get_pins $dsp/PCOUT[*]] -quiet]
    if {$pcout ne ""} {
        set load_pins [get_pins -of $pcout -filter {DIRECTION == IN && REF_PIN_NAME =~ "PCIN*"}]
        if {$load_pins ne ""} {
            puts "OK: $dsp cascades via PCOUT→PCIN"
        }
    }
}
```

## Reference

- [CR-1199907](https://jira.xilinx.com/browse/CR-1199907) — DSP58 P→PCIN connection using inference and instantiation
- AM004 — Versal DSP58 Architecture Manual, Cascade section
