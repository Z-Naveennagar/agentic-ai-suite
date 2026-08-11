<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Type and Interface Mismatch Errors

**Covers IDs:** 576, 580, 583, 591, 592, 608, 622, 793, 794, 839, 840

Grouped fixes for type mismatch, packed/unpacked conflicts, and interface binding errors.

---

## VLOG-576: Type Mismatch

```
ERROR: [Synth 8-576] type mismatch in assignment [/path/to/file.sv:30]
```

**Fix:** Read both sides and add a type cast or change one declaration:
```diff
- logic [7:0] sig_a;
- my_struct_t sig_b;
- assign sig_a = sig_b;                  // type mismatch
+ assign sig_a = sig_b.data;             // access specific field
```

Or cast:
```diff
+ assign sig_a = 8'(sig_b);             // explicit cast (SV)
```

---

## VLOG-580: Must Be Packed Type

```
ERROR: [Synth 8-580] must be a packed type [/path/to/file.sv:35]
```

**Fix:** Add `packed` keyword to the type definition:
```diff
- typedef struct {
+ typedef struct packed {
    logic [7:0] data;
    logic       valid;
  } my_type;
```

Packed types are required for:
- Bit-selects and part-selects
- Assignments to/from `logic` vectors
- Use in ports without explicit conversion

---

## VLOG-583: Packed Union Size Mismatch

```
ERROR: [Synth 8-583] packed union member size mismatch [/path/to/file.sv:40]
```

**Fix:** All members of a `packed union` must have the same bit width:
```diff
  typedef union packed {
-   logic [7:0]  byte_val;    // 8 bits
-   logic [15:0] word_val;    // 16 bits — mismatch!
+   logic [15:0] byte_val;    // 16 bits — pad to match
+   logic [15:0] word_val;    // 16 bits
  } my_union;
```

Or use `struct packed` instead if fields have different sizes.

---

## VLOG-591 / VLOG-592: Interface / Modport Mismatch

```
ERROR: [Synth 8-591] interface type mismatch [/path/to/file.sv:50]
ERROR: [Synth 8-592] modport name mismatch [/path/to/file.sv:55]
```

**Fix (591):** Use the correct interface type at the instantiation:
```diff
- my_bus_if  bus_inst();     // wrong interface type
+ axi_bus_if bus_inst();     // correct interface type
```

**Fix (592):** Use the correct modport name:
```diff
- sub_mod u1 (.bus(bus_inst.master));    // modport 'master' doesn't exist
+ sub_mod u1 (.bus(bus_inst.m_port));    // use actual modport name
```

---

## VHDL-608: External Name Type Mismatch

```
ERROR: [Synth 8-608] type of external name does not match [/path/to/file.vhd:60]
```

**Fix:** Read both declarations and align types:
```diff
- alias ext_sig is <<signal .top.u1.data : std_logic>>;  -- actual is slv(7:0)
+ alias ext_sig is <<signal .top.u1.data : std_logic_vector(7 downto 0)>>;
```

---

## VLOG-622: Packed Range on Unpacked Type

```
ERROR: [Synth 8-622] packed dimension on unpacked type [/path/to/file.sv:65]
```

**Fix:** Remove packed dimension or change to packed type:
```diff
- integer [7:0] data;           // integer is unpacked — can't add packed range
+ logic [7:0] data;             // use packed type instead
```

---

## VHDL-793 / VHDL-794: Port/Generic Type Mismatch

```
ERROR: [Synth 8-793] type of actual port does not match formal [/path/to/file.vhd:70]
ERROR: [Synth 8-794] type of actual generic does not match formal [/path/to/file.vhd:75]
```

**Fix:** Read the entity declaration and fix the actual to match the formal type:
```diff
  -- Entity expects: port data_in : std_logic_vector(7 downto 0)
  -- Actual signal: signal my_data : unsigned(7 downto 0)
  port map (
-   data_in => my_data,                          -- type mismatch
+   data_in => std_logic_vector(my_data),         -- add conversion
  )
```

---

## VHDL-839: Invalid Assignment Target

```
ERROR: [Synth 8-839] invalid assignment to type [/path/to/file.vhd:80]
```

**Fix:** Ensure LHS and RHS types are compatible. Common fix is type conversion:
```diff
- my_unsigned <= my_slv;                            -- can't assign slv to unsigned
+ my_unsigned <= unsigned(my_slv);                   -- add type conversion
```

---

## VHDL-840: Concatenation Width Mismatch

```
ERROR: [Synth 8-840] concatenation width mismatch [/path/to/file.vhd:85]
```

**Fix:** Ensure total width of concatenated elements matches target:
```diff
  -- target is 16 bits, but a(7:0) & b(3:0) = 12 bits
- result <= a & b;
+ result <= "0000" & a & b;     -- pad to 16 bits
```

---

## Validation

```tcl
synth_design -top $top -part $part -rtl -name rtl_1
```
