<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Versal RTL Design Advisories Report

| Field | Value |
|-------|-------|
| Project | fir_filter_project |
| Top Module | fir_top |
| Part | xcvm1802-vsva2197-2MP-e-S |
| Date | 2026-05-11 |
| Checks Run | 38 of 42 applicable |

## Summary

| Severity | Count |
|----------|:-----:|
| HIGH     | 3     |
| MEDIUM   | 2     |
| LOW      | 1     |
| PASS     | 32    |
| SKIPPED  | 4     |

**Total: 6 issues found across 4 categories**

## Findings

### D1: Pattern Detect Uses Conditional If/Else

- **Severity:** HIGH
- **File:** [src/dsp_chain.sv:87](src/dsp_chain.sv#L87)
- **Category:** DSP Inference
- **Current Code:**
```verilog
always @(posedge clk) begin
    if (product == 48'h0000_DEAD_BEEF)
        overflow_det <= 1'b1;
    else
        overflow_det <= 1'b0;
end
```
- **Recommended Fix:**
```verilog
always @(posedge clk)
    overflow_det <= (product == 48'h0000_DEAD_BEEF);
```
- **Explanation:** Conditional `if/else` generates a MUX in fabric instead of using the DSP58's built-in PATTERNDETECT hardware. The direct equality operator maps to the DSP's internal comparator.
- **Reference:** [CR-1034185](https://jira.xilinx.com/browse/CR-1034185) | [Resolution Guide](../resolution/D1.md)

---

### D6: DSP58 P→C Feedback Without PREG

- **Severity:** HIGH
- **File:** [src/mac_unit.sv:42](src/mac_unit.sv#L42)
- **Category:** DSP Inference
- **Current Code:**
```verilog
wire [47:0] product = a * b;
always @(posedge clk) begin
    if (load)
        accum <= product;
    else
        accum <= accum + product;  // P→C feedback, no PREG
end
```
- **Recommended Fix:**
```verilog
reg [47:0] product_reg;
always @(posedge clk)
    product_reg <= a * b;          // MREG

always @(posedge clk) begin
    if (load)
        accum <= product_reg;
    else
        accum <= accum + product_reg;  // PREG on output
end
```
- **Explanation:** The DSP58 output P feeds back to input C without an output register (PREG). PREG is architecturally required for any P→C feedback loop to meet timing.
- **Reference:** [CR-1150378](https://jira.xilinx.com/browse/CR-1150378) | [Resolution Guide](../resolution/D6.md)

---

### M3: URAM Wrong Write Mode

- **Severity:** HIGH
- **File:** [src/data_buffer.sv:23](src/data_buffer.sv#L23)
- **Category:** Memory Inference
- **Current Code:**
```verilog
(* ram_style = "ultra" *)
reg [71:0] mem [0:4095];

always @(posedge clk) begin
    if (we) mem[wr_addr] <= din;
end

always @(posedge clk) begin
    if (we && rd_addr == wr_addr)
        dout <= din;           // Write-first — NOT supported on 2P URAM
    else
        dout <= mem[rd_addr];
end
```
- **Recommended Fix:**
```verilog
(* ram_style = "ultra" *)
reg [71:0] mem [0:4095];

always @(posedge clk) begin
    if (we) mem[wr_addr] <= din;
end

always @(posedge clk) begin
    dout <= mem[rd_addr];      // Read-first — supported on 2P URAM
end
```
- **Explanation:** Simple dual-port URAM only supports read-first write mode. Write-first causes the tool to fall back to LUTRAM or BRAM with a `[Synth 8-6849]` warning.
- **Reference:** [CR-1058874](https://jira.xilinx.com/browse/CR-1058874) | [Resolution Guide](../resolution/M3.md)

---

### M6: URAM Without `ram_decomp` Attribute

- **Severity:** MEDIUM
- **File:** [src/data_buffer.sv:20](src/data_buffer.sv#L20)
- **Category:** Memory Inference
- **Current Code:**
```verilog
(* ram_style = "ultra" *)
reg [71:0] mem [0:4095];
```
- **Recommended Fix:**
```verilog
(* ram_style = "ultra", ram_decomp = "area" *)
reg [71:0] mem [0:4095];
```
- **Explanation:** Without `ram_decomp = "area"`, Versal may use 25% more URAMs than necessary by choosing a wider matrix shape. The area attribute forces taller cascades to minimize URAM count.
- **Reference:** [CR-1161721](https://jira.xilinx.com/browse/CR-1161721) | [Resolution Guide](../resolution/M6.md)

---

### S1: VHDL Counter Increment Placement

- **Severity:** MEDIUM
- **File:** [src/ctrl_fsm.vhd:156](src/ctrl_fsm.vhd#L156)
- **Category:** Coding Style
- **Current Code:**
```vhdl
process(clk)
begin
    if rising_edge(clk) then
        if (count_i = MAX_COUNT) then
            count_i <= 0;
        end if;
        count_i <= count_i + 1;
    end if;
end process;
```
- **Recommended Fix:**
```vhdl
process(clk)
begin
    if rising_edge(clk) then
        if (count_i = MAX_COUNT) then
            count_i <= 0;
        else
            count_i <= count_i + 1;
        end if;
    end if;
end process;
```
- **Explanation:** Counter increment outside the `else` branch generates ~39 LUTs on Versal vs ~5 LUTs with the correct coding. The `else` branch lets synthesis cleanly merge the counter and wrap logic.
- **Reference:** [CR-1063518](https://jira.xilinx.com/browse/CR-1063518) | [Resolution Guide](../resolution/S1.md)

---

### S8: VHDL Depth-1 Memory Address Width

- **Severity:** LOW
- **File:** [src/coeff_rom.vhd:30](src/coeff_rom.vhd#L30)
- **Category:** Coding Style
- **Current Code:**
```vhdl
constant DEPTH  : integer := 1;
constant ADDR_W : integer := integer(ceil(log2(real(DEPTH))));
-- ADDR_W = 0 → null range address
```
- **Recommended Fix:**
```vhdl
constant DEPTH  : integer := 1;
constant ADDR_W : integer := maximum(1, integer(ceil(log2(real(DEPTH)))));
-- ADDR_W = 1 → valid 1-bit address
```
- **Explanation:** `ceil(log2(1.0))` returns 0 in VHDL, creating a null address range. This causes the address to be trimmed, making all addresses map to the same location.
- **Reference:** [CR-1223300](https://jira.xilinx.com/browse/CR-1223300) | [Resolution Guide](../resolution/S8.md)

---

## Categories Not Applicable

- **Steps 2–3 partially (DSPCPLX):** No DSPCPLX primitives in design — C1–C5 skipped
- **Step 9 (Migration):** Not migrating from US+ — G1, G2 skipped

## Recommendations

1. **[HIGH PRIORITY]** Fix D1 pattern detect to use direct equality — avoids fabric MUX and uses DSP58 hardware comparator
2. **[HIGH PRIORITY]** Fix D6 accumulator to add PREG pipeline stage — required for P→C feedback timing
3. **[HIGH PRIORITY]** Fix M3 URAM write mode to read-first — write-first not supported on 2P URAM
4. **[MEDIUM]** Add `ram_decomp = "area"` on URAM arrays to save ~25% URAM resources
5. **[MEDIUM]** Move VHDL counter increment to `else` branch for 8× LUT reduction
6. **[LOW]** Guard depth-1 memory address width with `maximum(1, ...)` function
