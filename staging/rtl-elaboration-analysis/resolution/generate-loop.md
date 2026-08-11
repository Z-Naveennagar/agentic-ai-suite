<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Generate and Genvar Errors

**Covers IDs:** 581, 630

Grouped fixes for generate block and genvar usage errors.

---

## VLOG-581: Illegal Genvar Use

```
ERROR: [Synth 8-581] illegal use of genvar outside generate block [/path/to/file.v:25]
```

**Fix:** Move genvar usage inside a `generate` block:

```diff
- genvar i;
- for (i = 0; i < WIDTH; i = i+1) begin
-   assign data[i] = src[i] & mask[i];   // genvar outside generate
- end

+ genvar i;
+ generate
+   for (i = 0; i < WIDTH; i = i+1) begin : gen_loop
+     assign data[i] = src[i] & mask[i];
+   end
+ endgenerate
```

> **Note:** In SystemVerilog, the explicit `generate`/`endgenerate` keywords are
> optional — but the `for` loop with `genvar` must still be at module scope
> (not inside an `always` block).

Common mistake — using genvar inside procedural code:
```diff
  always @(*) begin
-   genvar i;                             // can't use genvar here
-   for (i = 0; i < 4; i = i+1)
-     out[i] = in[i] & en;
+   integer i;                            // use integer for procedural loops
+   for (i = 0; i < 4; i = i+1)
+     out[i] = in[i] & en;
  end
```

---

## VLOG-630: Same Genvar in Nested Loop

```
ERROR: [Synth 8-630] same genvar 'i' used in nested generate loop [/path/to/file.v:35]
```

**Fix:** Use a different genvar name for the inner loop:

```diff
  genvar i;
+ genvar j;
  generate
    for (i = 0; i < ROWS; i = i+1) begin : gen_row
-     for (i = 0; i < COLS; i = i+1) begin : gen_col    // reusing 'i'
+     for (j = 0; j < COLS; j = j+1) begin : gen_col    // use 'j'
        assign matrix[i][j] = src[i] & mask[j];
      end
    end
  endgenerate
```

### Best Practice

Use descriptive genvar names for nested loops to prevent confusion:
```verilog
genvar gi, gj, gk;   // row, column, depth
```

---

## Validation

```tcl
synth_design -top $top -part $part -rtl -name rtl_1
```
