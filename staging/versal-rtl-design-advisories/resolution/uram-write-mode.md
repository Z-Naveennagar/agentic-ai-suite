<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# M3: URAM Wrong Write Mode

**Check:** M3 | **Severity:** HIGH | **Category:** Memory Inference

## Root Cause

Versal URAM288E5 supports only specific write modes depending on the port configuration:

| Configuration | Supported Write Mode | Unsupported |
|---------------|---------------------|-------------|
| Simple Dual-Port (2P) | **Read-first** only | Write-first, No-change |
| True Dual-Port (T2P) | **No-change** only | Read-first, Write-first |

Using an unsupported write mode causes the tool to either:
- Silently fall back to BRAM (if available)
- Push the memory to LUTRAM
- Generate incorrect behavior in hardware emulation

## Vivado Warning

```
WARNING: [Synth 8-6849] Infeasible attribute ram_style = "ultra" set for RAM "mem_reg",
trying to implement using LUTRAM
```

## Detection

**RTL pattern — write-first (problematic for 2P URAM):**
```verilog
// Write-first: write happens, then read data = written data
always @(posedge clk) begin
    if (we) begin
        mem[addr] <= din;
    end
    dout <= mem[addr];     // Read-first if read uses same addr
end
```

**Grep for URAM with potential write-mode issues:**
```
grep -rn "ram_style.*ultra\|MEMORY_PRIMITIVE.*ultra\|URAM" *.sv *.v *.vhd
```

Then inspect the read/write behavior in the always block.

## Fix

### Before (Broken — write-first on 2P URAM)

```verilog
(* ram_style = "ultra" *)
reg [71:0] mem [0:4095];

// Simple dual-port with write-first behavior
always @(posedge clk) begin
    if (we_a) begin
        mem[addr_a] <= din_a;
    end
end

always @(posedge clk) begin
    // Write-first: new data visible on read port same cycle
    if (we_a && addr_b == addr_a)
        dout_b <= din_a;         // WRONG for URAM — write-first not supported on 2P
    else
        dout_b <= mem[addr_b];
end
```

### After (Fixed — read-first for 2P URAM)

```verilog
(* ram_style = "ultra" *)
reg [71:0] mem [0:4095];

// Simple dual-port with read-first behavior (supported by URAM)
always @(posedge clk) begin
    if (we_a) begin
        mem[addr_a] <= din_a;
    end
end

always @(posedge clk) begin
    dout_b <= mem[addr_b];       // Read-first: old data on read port
end
```

### True Dual-Port — NO_CHANGE mode

```verilog
(* ram_style = "ultra" *)
reg [71:0] mem [0:4095];

// Port A: NO_CHANGE mode (only mode supported for T2P URAM)
always @(posedge clk) begin
    if (en_a) begin
        if (we_a)
            mem[addr_a] <= din_a;
        else
            dout_a <= mem[addr_a];    // Read only when NOT writing
    end
end

// Port B: Same NO_CHANGE pattern
always @(posedge clk) begin
    if (en_b) begin
        if (we_b)
            mem[addr_b] <= din_b;
        else
            dout_b <= mem[addr_b];    // Read only when NOT writing
    end
end
```

## Write Mode Quick Reference

| Code Pattern | Write Mode | 2P URAM | T2P URAM |
|-------------|-----------|:-------:|:--------:|
| `dout <= mem[addr]; if(we) mem[addr] <= din;` | Read-first | **OK** | NO |
| `if(we) mem[addr] <= din; dout <= din;` | Write-first | NO | NO |
| `if(we) mem[addr] <= din; else dout <= mem[addr];` | No-change | NO | **OK** |

## Validation

```tcl
# Verify URAMs were inferred (not pushed to BRAM/LUTRAM)
set uram_count [llength [get_cells -hierarchical -filter {PRIMITIVE_TYPE =~ BLOCKRAM.URAM.*}]]
puts "URAM count: $uram_count"

# Check synthesis log for infeasible warnings
grep "Infeasible.*ram_style.*ultra\|8-6849" synth.log
```

## Reference

- [CR-1058874](https://jira.xilinx.com/browse/CR-1058874) — Invalid output in hw_emu when array implemented by URAM
- [CR-1168604](https://jira.xilinx.com/browse/CR-1168604) — HLS reports URAM usage incorrectly (T2P write mode)
- AM007 — Versal Memory Resources Architecture Manual, URAM write modes
