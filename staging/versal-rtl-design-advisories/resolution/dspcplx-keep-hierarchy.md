<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# C3: `keep_hierarchy` Blocks DSPCPLX Cascade

**Check:** C3 | **Severity:** HIGH | **Category:** DSPCPLX Cascade

## Root Cause

The `keep_hierarchy` attribute prevents synthesis from crossing module boundaries.
When applied to modules containing DSPCPLX primitives, it blocks the tool from
forming `PCOUT → PCIN` cascade chains between DSPCPLXs in different hierarchy levels.

Instead of the dedicated cascade path, the tool routes through the C port or general
fabric, degrading timing and increasing resource usage.

## Detection

**RTL grep:**
```
grep -rn "keep_hierarchy" *.sv *.v *.vhd | grep -i "dsp\|mult\|fir\|filter\|cmult"
```

Look for:
- `(* keep_hierarchy = "yes" *)` on modules that contain complex multipliers
- `KEEP_HIERARCHY` constraint in XDC on DSPCPLX-containing hierarchies

**Post-synthesis check:**
```tcl
# Find DSPCPLX cells not using PCOUT→PCIN cascade
foreach dsp [get_cells -hierarchical -filter {REF_NAME =~ DSPCPLX*}] {
    set pcout_net [get_nets -of [get_pins $dsp/PCOUT[*]] -quiet]
    if {$pcout_net eq ""} {continue}
    set pcin_pins [get_pins -of $pcout_net -filter {REF_PIN_NAME =~ "PCIN*"} -quiet]
    if {$pcin_pins eq ""} {
        puts "WARNING: $dsp PCOUT not connected to PCIN — cascade broken"
    }
}
```

## Fix

### Before (Broken — keep_hierarchy prevents cascade)

```verilog
(* keep_hierarchy = "yes" *)   // <-- REMOVE THIS
module cmult_tap (
    input  wire        clk,
    input  wire [17:0] ar, ai, br, bi,
    input  wire [47:0] acc_in,
    output reg  [47:0] pr, pi
);
    always @(posedge clk) begin
        pr <= ar * br - ai * bi + acc_in;
        pi <= ar * bi + ai * br + acc_in;
    end
endmodule
```

### After (Fixed — hierarchy removed, cascade enabled)

```verilog
// No keep_hierarchy — tool can form cascade chain
module cmult_tap (
    input  wire        clk,
    input  wire [17:0] ar, ai, br, bi,
    input  wire [47:0] acc_in,
    output reg  [47:0] pr, pi
);
    always @(posedge clk) begin
        pr <= ar * br - ai * bi + acc_in;
        pi <= ar * bi + ai * br + acc_in;
    end
endmodule
```

**Also check XDC:**
```tcl
# Remove any XDC constraint that preserves hierarchy on DSP modules
# WRONG:
# set_property KEEP_HIERARCHY true [get_cells -hierarchical *cmult*]
```

## Validation

```tcl
# After re-synthesis, verify cascade formed
foreach dsp [get_cells -hierarchical -filter {REF_NAME =~ DSPCPLX*}] {
    set pcout [get_nets -of [get_pins $dsp/PCOUT[*]] -quiet]
    if {$pcout ne ""} {
        set load [get_pins -of $pcout -filter {DIRECTION==IN && REF_PIN_NAME=~"PCIN*"} -quiet]
        if {$load ne ""} {
            puts "OK: $dsp cascades via PCOUT→PCIN"
        }
    }
}
```

## Reference

- [CR-1247719](https://jira.xilinx.com/browse/CR-1247719) — Cascaded DSPCPLX uses C port instead of PCOUT
- UG901 — Vivado Synthesis Guide, keep_hierarchy attribute
