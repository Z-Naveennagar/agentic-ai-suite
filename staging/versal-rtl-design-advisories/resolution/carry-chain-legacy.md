<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# A1: Legacy Carry-Chain Instantiations

**Check:** A1 | **Severity:** HIGH | **Category:** Carry Chain / Arithmetic

## Root Cause

Versal uses `LOOKAHEAD8` primitives for carry chains, which have fundamentally different
architecture and timing from UltraScale+ `CARRY8` and 7-Series `CARRY4`. Directly
instantiating `CARRY4` or `CARRY8` in RTL targeting Versal forces the synthesis tool
to perform primitive remapping (`CARRY4 → CARRY8 → LOOKAHEAD8`), which can insert
pass-through LUTs and create suboptimal timing paths.

The remapped path often includes `LUTCY2` primitives that are effectively pass-throughs,
adding delay without function.

## Detection

**RTL grep:**
```
grep -rn "\bCARRY4\b\|\bCARRY8\b\|\bCARRY4_inst\b\|\bcarry_inst\b" *.sv *.v *.vhd
```

**Post-synthesis timing path signature:**
```
# Look for LOOKAHEAD8 + LUTCY2 pass-through in timing paths
grep "LUTCY2.*Prop.*pass\|LOOKAHEAD8.*LUTCY2" timing_report.rpt
```

## Fix

### Before (Broken — legacy CARRY4 instantiation)

```verilog
// Explicitly instantiated carry chain — will be remapped poorly on Versal
CARRY4 carry_inst (
    .CI    (carry_in),
    .CYINIT(1'b0),
    .DI    (data_in[3:0]),
    .S     (sum_in[3:0]),
    .CO    (carry_out[3:0]),
    .O     (result[3:0])
);
```

### After (Fixed — behavioral RTL, tool infers optimal carry)

```verilog
// Behavioral arithmetic — synthesis infers optimal carry structure per device
reg [4:0] result_ext;

always @(*) begin
    result_ext = {1'b0, data_in} + {1'b0, addend};
end

assign result    = result_ext[3:0];
assign carry_out = result_ext[4];
```

### Before (Broken — CARRY8 chain)

```verilog
// US+ CARRY8 — maps poorly to Versal LOOKAHEAD8
CARRY8 #(.CARRY_TYPE("SINGLE_CY8"))
carry8_inst (
    .CI     (cin),
    .CI_TOP (1'b0),
    .DI     (di[7:0]),
    .S      (s[7:0]),
    .CO     (co[7:0]),
    .O      (o[7:0])
);
```

### After (Fixed — behavioral)

```verilog
// Let synthesis choose the best carry implementation
wire [8:0] sum = {1'b0, a} + {1'b0, b} + cin;
assign o   = sum[7:0];
assign cout = sum[8];
```

## Key Points

- **Always use behavioral arithmetic** on Versal — `+`, `-`, `<`, `>` operators
- The tool will infer LOOKAHEAD8 when beneficial and LUTs when they're faster
- Versal carry chains are **architecturally slower** than US+ (see check A2)
- If migrating from US+, search for all `CARRY4`, `CARRY8` instantiations and replace

## Validation

```tcl
# Verify no legacy carry primitives remain after synthesis
set carry4 [get_cells -hierarchical -filter {REF_NAME == CARRY4} -quiet]
set carry8 [get_cells -hierarchical -filter {REF_NAME == CARRY8} -quiet]
if {[llength $carry4] > 0 || [llength $carry8] > 0} {
    puts "ERROR: [llength $carry4] CARRY4 + [llength $carry8] CARRY8 legacy primitives found"
} else {
    puts "OK: No legacy carry primitives"
}
```

## Reference

- [CR-1034326](https://jira.xilinx.com/browse/CR-1034326) — Suboptimal carry-chain remapping for QoR
- UG901 — Vivado Synthesis Guide, Arithmetic inference
