<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# M7: Write-First URAM Mismatched Structure

**Check:** M7 | **Severity:** MEDIUM | **Category:** Memory Inference

## Root Cause

Write-first mode for URAM inference requires the read and write paths to have
**identical enable and reset structure**. If the enable signal on the read path
differs from the write path (e.g., different CE conditions, missing reset on one
side), synthesis cannot infer URAM and falls back to LUTRAM.

## Vivado Warning

```
WARNING: [Synth 8-6849] Infeasible attribute ram_style = "ultra" set for RAM
"rams_sp_wf/RAM_reg", trying to implement using LUTRAM
```

## Detection

**RTL grep:**
```
grep -rn "ram_style.*ultra" *.sv *.v *.vhd
```

Then inspect the `always` block for asymmetric enable/reset:
- Write path has enable `we` but read path has different enable `re`
- Write path has reset but read path does not (or vice versa)
- Different conditional structure around the read vs write

## Fix

### Before (Broken — mismatched enable structure)

```verilog
(* ram_style = "ultra" *)
reg [71:0] mem [0:4095];
reg [71:0] dout;

always @(posedge clk) begin
    if (we) begin                    // Write path: guarded by 'we'
        mem[addr] <= din;
    end
end

always @(posedge clk) begin
    if (re) begin                    // Read path: guarded by 're' — MISMATCH
        dout <= mem[addr];
    end
end
```

### After (Fixed — matching enable structure)

```verilog
(* ram_style = "ultra" *)
reg [71:0] mem [0:4095];
reg [71:0] dout;

always @(posedge clk) begin
    if (en) begin                    // Same enable for both
        if (we) begin
            mem[addr] <= din;
            dout <= din;             // Write-first: output = new data
        end else begin
            dout <= mem[addr];       // Read when not writing
        end
    end
end
```

### Alternative: Split with matching structure

```verilog
(* ram_style = "ultra" *)
reg [71:0] mem [0:4095];
reg [71:0] dout;

// Both paths use the same enable 'en'
always @(posedge clk) begin
    if (en) begin
        if (we)
            mem[wr_addr] <= din;
    end
end

always @(posedge clk) begin
    if (en) begin                    // MUST match write-side enable
        if (we && rd_addr == wr_addr)
            dout <= din;
        else
            dout <= mem[rd_addr];
    end
end
```

## Key Rules for Write-First URAM Inference

1. **Same enable** — read and write paths must be gated by the same enable signal
2. **Same reset** — if either path has reset, both must have identical reset logic
3. **Consistent structure** — the `if/else` nesting must be symmetrical
4. **No extra logic** — avoid additional conditions on only one path

## Validation

```tcl
# Check synthesis log for infeasible ram_style warnings
# If URAM was inferred successfully, no 8-6849 warning appears
grep "8-6849\|Infeasible.*ram_style" vivado.log
```

## Reference

- [CR-1263465](https://jira.xilinx.com/browse/CR-1263465) — Fail to infer URAM for write-first RAM
- UG901 — Vivado Synthesis Guide, RAM inference templates
