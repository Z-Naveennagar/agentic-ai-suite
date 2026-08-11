<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Declaration Errors

**Covers IDs:** 126, 129, 131, 599, 615, 624, 636, 841, 856

Grouped fixes for declaration-related elaboration errors — duplicate declarations,
missing directions, type declarations, and ordering issues.

---

## VLOG-126 / VLOG-599: Duplicate Declaration

```
ERROR: [Synth 8-126] identifier 'data' is being redeclared [/path/to/file.v:20]
ERROR: [Synth 8-599] duplicate declaration of 'data' [/path/to/file.v:25]
```

**Fix:** Remove the duplicate. Search for all declarations of the name and keep one.

```diff
  wire [7:0] data;
- wire [7:0] data;   // duplicate — remove
```

Common cause: ANSI port with separate body declaration:
```diff
  module top (
    input wire [7:0] data    // ANSI declaration
  );
- wire [7:0] data;           // redundant — remove (already declared in port list)
```

**VHDL equivalent — signal declared in both entity and architecture:**
```diff
  entity top is
    port (
      data : in std_logic_vector(7 downto 0)
    );
  end entity;
  architecture rtl of top is
-   signal data : std_logic_vector(7 downto 0);  -- conflicts with port 'data'
  begin

---

## VLOG-129: Port Direction Not Declared

```
ERROR: [Synth 8-129] port direction for 'data' is not declared [/path/to/file.v:5]
```

**Fix:** Add `input`, `output`, or `inout` to the port:
```diff
- module top (clk, data);
-   wire [7:0] data;
+ module top (input clk, input wire [7:0] data);
```

**VHDL equivalent — port mode missing:**
```diff
  entity top is
    port (
-     data : std_logic_vector(7 downto 0)    -- missing mode (in/out/inout)
+     data : in std_logic_vector(7 downto 0) -- add direction
    );
  end entity;
```

---

## VLOG-131: Port Not in Port List

```
ERROR: [Synth 8-131] port 'extra_out' is not in the port list [/path/to/file.v:8]
```

**Fix:** Add the port to the module header:
```diff
- module top (clk, rst, data);
+ module top (clk, rst, data, extra_out);
```

Or remove the erroneous port declaration from the body.

**VHDL equivalent — signal declared but not in entity port list:**
```diff
  entity top is
    port (
      clk  : in  std_logic;
      rst  : in  std_logic;
-     data : in  std_logic_vector(7 downto 0)
+     data : in  std_logic_vector(7 downto 0);
+     extra_out : out std_logic    -- add missing port
    );
  end entity;
```

---

## VLOG-615: Duplicate Enum Value

```
ERROR: [Synth 8-615] duplicate enum value 'RED' [/path/to/file.sv:10]
```

**Fix:** Assign unique values:
```diff
  typedef enum logic [1:0] {
    RED   = 2'b00,
-   GREEN = 2'b00,     // duplicate of RED
+   GREEN = 2'b01,     // unique value
    BLUE  = 2'b10
  } color_t;
```

---

## VLOG-624: Undeclared Type

```
ERROR: [Synth 8-624] type 'state_t' is not declared [/path/to/file.sv:15]
```

**Fix:** Add `import` or `typedef`:
```diff
+ import my_pkg::state_t;   // if defined in a package
```
Or add the typedef locally:
```diff
+ typedef enum logic [1:0] {IDLE, RUN, DONE} state_t;
```

**Cascading:** VLOG-624 often triggers VLOG-128 for all variables of that type.
Fix the type declaration first.

---

## VLOG-636: Type Used Before Declaration

```
ERROR: [Synth 8-636] type 'my_type' is used before its declaration [/path/to/file.sv:20]
```

**Fix:** Move the `typedef` above its first use:
```diff
+ typedef struct packed { logic [7:0] data; logic valid; } my_type;
+
  my_type my_signal;  // now my_type is declared before use
- typedef struct packed { logic [7:0] data; logic valid; } my_type;
```

---

## VHDL-841: Protected Type Variable Initialized

```
ERROR: [Synth 8-841] protected type variable 'v' has initializer [/path/to/file.vhd:30]
```

**Fix:** Remove the initializer — protected types cannot have default values:
```diff
- variable v : my_protected_type := init_val;
+ variable v : my_protected_type;
```

---

## VHDL-856: Constant Must Have Value

```
ERROR: [Synth 8-856] constant 'C_WIDTH' must have a value [/path/to/file.vhd:10]
```

**Fix:** Add the value:
```diff
- constant C_WIDTH : integer;
+ constant C_WIDTH : integer := 8;
```

---

## Validation

```tcl
synth_design -top $top -part $part -rtl -name rtl_1
```
