<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Block RAM and UltraRAM Guidelines

Sources: UG901 memory coding techniques, UG1387 RAM inference methodology, and AM007 Versal
memory resources. Confirm behavior on the actual Vivado release and target part.

## MEM-1 — Code a supported synchronous memory template

Use a clocked read for BRAM/UltraRAM inference. An asynchronous array read normally maps to
distributed resources instead of these synchronous hard memories.

```systemverilog
(* ram_style = "block" *) logic [DATA_W-1:0] mem [0:DEPTH-1];
logic [DATA_W-1:0] rd_data;

always_ff @(posedge clk) begin
  if (wr_en)
    mem[addr] <= wr_data;
  if (rd_en)
    rd_data <= mem[addr];
end
```

Choose and test read-during-write semantics deliberately. Do not change bypass logic or write
mode merely to obtain a desired primitive.

## MEM-2 — Pipeline according to the memory configuration and timing target

BRAM and UltraRAM provide configurable internal/output registers. Extra output or cascade
registers often improve Fmax, especially for long UltraRAM cascades, but the required number
and placement depend on depth, cascade length, latency, and target clock. They are not a
universal one-register requirement.

Verify the inferred primitive properties and the end-to-end read latency. For UltraRAM
cascades, follow AM007's `REG_CAS_A/B` guidance for the configured cascade.

```tcl
set memories [get_cells -hier -filter {PRIMITIVE_GROUP == BLOCKRAM}]
foreach m $memories {
  list $m [get_property -quiet PRIMITIVE_SUBGROUP $m] [get_property -quiet DOA_REG $m] [get_property -quiet DOB_REG $m]
}
```

## MEM-3 — Keep array reset separate; make register resets inference-compatible

Do not reset the memory array. Resetting every array element prevents normal BRAM/UltraRAM
inference.

Do not apply a blanket prohibition to address or read-data registers. UG1387 documents that
register absorption depends on the particular RAM template and compatible reset behavior.
When a RAM output and an optional external output register both use asynchronous reset, their
reset behavior must match for the optional register to be absorbed. Address, output, and
pipeline resets can remain in fabric when their behavior cannot map to the memory resource.

Use reset only where the architectural contract needs defined data. For datapaths, a valid
bit or initialization/flush protocol can often avoid resetting wide data registers.

Verify both behavior and mapping:

- Simulate assertion/deassertion and the first valid read.
- Inspect whether intended address/output registers were absorbed.
- Check for unexpected fabric registers around the memory.

## MEM-4 — Respect UltraRAM behavior

UltraRAM uses synchronous access and has specific port, collision, cascade, ECC, and reset
rules. Select inference versus XPM/primitive instantiation based on whether the required
configuration is supported by an HDL template. Verify the actual primitive subgroup and
configured latency rather than assuming `ram_style="ultra"` guarantees the result.

## MEM-5 — Treat fanout as a post-placement problem

Register memory outputs where required by timing and allow the tools to optimize or replicate
when legal. `max_fanout` is an optimization hint, not a universal threshold. Measure with
`report_high_fanout_nets` after placement and avoid `DONT_TOUCH`/`KEEP` on a register that
must be absorbed into RAM.

## Checklist

- [ ] Read behavior uses a supported synchronous template.
- [ ] Read-during-write behavior is explicit and tested.
- [ ] The memory array is not reset.
- [ ] Address/output reset behavior matches the selected inference template and contract.
- [ ] Output/cascade registers and read latency match the timing requirement.
- [ ] The inferred BRAM/URAM subtype and properties match intent.
- [ ] High fanout is measured after implementation rather than assumed from RTL width.
