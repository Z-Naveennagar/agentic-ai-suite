<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Port Connection Errors

**Covers IDs:** 142, 143, 144, 145, 510, 512, 513, 596, 597, 598, 602, 631, 646, 649

Grouped fixes for port and interface connection issues during elaboration.

---

## VLOG-142 / VLOG-144: Mixed Named/Ordered Connections

```
ERROR: [Synth 8-142] mixed named and ordered port connections are illegal [/path/to/file.v:25]
ERROR: [Synth 8-144] mixed named and ordered parameter overrides are illegal [/path/to/file.v:25]
```

**Fix:** Convert all to named style (recommended):
```diff
- sub_mod u1 (clk, .data(bus), rst);       // mixed ordered + named
+ sub_mod u1 (.clk(clk), .data(bus), .rst(rst));  // all named
```

For parameters:
```diff
- sub_mod #(8, .DEPTH(16)) u1 (...);
+ sub_mod #(.WIDTH(8), .DEPTH(16)) u1 (...);
```

**VHDL equivalent — named association required for all ports:**
```diff
- u1 : entity work.sub_mod port map (clk, bus, rst);  -- positional
+ u1 : entity work.sub_mod port map (clk => clk, data => bus, rst => rst);  -- named
```

For generics:
```diff
- u1 : entity work.sub_mod generic map (8, 16)
+ u1 : entity work.sub_mod generic map (WIDTH => 8, DEPTH => 16)
```

---

## VLOG-143 / VLOG-145: Duplicate Connections

```
ERROR: [Synth 8-143] duplicate port connection for 'data' [/path/to/file.v:30]
ERROR: [Synth 8-145] duplicate parameter override for 'WIDTH' [/path/to/file.v:30]
```

**Fix:** Remove the duplicate:
```diff
  sub_mod u1 (
    .clk  (clk),
    .data (bus_a),
-   .data (bus_b),    // duplicate — remove
    .out  (result)
  );
```

---

## VLOG-510: Mixed Port Directions

```
ERROR: [Synth 8-510] mixed port directions in expression [/path/to/file.v:20]
```

**Fix:** Split into separate port connections:
```diff
- .bus ({data_out, data_in}),   // mixing input and output in one expression
+ .data_out (data_out),
+ .data_in  (data_in),
```

---

## VLOG-512 / VLOG-513: Wrong Number of Connections

```
ERROR: [Synth 8-512] too many port connections [/path/to/file.v:25]
WARNING: [Synth 8-513] too few port connections [/path/to/file.v:25]
```

**Fix (512 — too many):** Remove excess positional connections. Use named style to
see which are extra.

**Fix (513 — too few):** Add missing connections. Compare against module port list.

```diff
  // Module has 3 ports: clk, data, out
- sub_mod u1 (clk, data, out, extra);  // 512: 4 connections for 3 ports
+ sub_mod u1 (clk, data, out);
```

**VHDL equivalent:**
```diff
  -- Entity has 3 ports: clk, data, q
- u1 : entity work.sub_mod port map (clk, data, q, extra);  -- too many
+ u1 : entity work.sub_mod port map (clk => clk, data => data, q => q);
```

For missing connections in VHDL:
```diff
- u1 : entity work.sub_mod port map (clk => clk);  -- missing data and q
+ u1 : entity work.sub_mod port map (clk => clk, data => data, q => q);
```
Or use `open` for intentionally unconnected outputs:
```diff
+ u1 : entity work.sub_mod port map (clk => clk, data => data, q => open);
```

---

## VLOG-596 / VLOG-602: Interface Port Issues

```
ERROR: [Synth 8-596] unconnected interface port [/path/to/file.sv:40]
ERROR: [Synth 8-602] generic interface not resolved [/path/to/file.sv:40]
```

**Fix (596):** Connect the interface port:
```diff
  sub_mod u1 (
    .clk (clk),
+   .axi_if (my_axi_bus),    // connect interface port
    .data (data)
  );
```

**Fix (602):** Specify concrete interface type:
```diff
- sub_mod u1 (.bus_if(my_bus));  // generic interface can't be resolved
+ sub_mod u1 (.bus_if(my_axi_bus));  // use concrete interface instance
```

---

## VLOG-597: Hierarchical Name Unresolved

```
ERROR: [Synth 8-597] hierarchical name 'u_sub.internal_sig' not resolved [/path/to/file.v:50]
```

**Fix:** Verify the hierarchical path exists. Common issues:
- Instance name changed → update path
- Signal made local/private → expose through port
- Cross-module reference not synthesizable → use port connections instead

---

## VLOG-598: No Signal for `.*` Connection

```
ERROR: [Synth 8-598] no signal found for port connection using .* [/path/to/file.sv:35]
```

**Fix:** Add a matching signal or use explicit named connection:
```diff
+ wire [7:0] missing_port_name;   // add signal matching port name
  sub_mod u1 (.*);
```

Or switch to explicit connection:
```diff
- sub_mod u1 (.*);
+ sub_mod u1 (.clk(clk), .rst(rst), .data(data));
```

---

## VLOG-631 / VLOG-649: Unconnected Ports

```
WARNING: [Synth 8-631] all outputs of instance 'u1' are unconnected [/path/to/file.v:60]
WARNING: [Synth 8-649] port 'debug_out' is unconnected [/path/to/file.v:60]
```

**Fix (631):** If instance is unused, remove it. If outputs are used elsewhere via
hierarchy, connect them or suppress with `(* keep = "true" *)`.

**Fix (649):** Connect the port or explicitly leave open:
```diff
  sub_mod u1 (
    .clk  (clk),
    .data (data),
-   // debug_out not connected — warning
+   .debug_out ()            // explicitly unconnected
  );
```

**VHDL equivalent:**
```diff
  u1 : entity work.sub_mod port map (
    clk  => clk,
    data => data,
-   -- debug_out not connected — warning
+   debug_out => open        -- explicitly unconnected
  );
```

---

## VLOG-646: Input Port Has Internal Driver

```
WARNING: [Synth 8-646] input port 'data_in' has an internal driver [/path/to/file.v:40]
```

**Fix:** Remove the internal driver or change port direction:
```diff
- input wire [7:0] data_in,
+ inout wire [7:0] data_in,    // if bidirectional is intended
```
Or remove the internal assignment to the input port.

---

## Validation

```tcl
synth_design -top $top -part $part -rtl -name rtl_1
```
