<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# ILA & VIO Insertion Flow

**Category:** Hardware Debug | **Board:** AMD Versal VCK190 | **Time:** ~15 minutes

Insert AXIS-ILA and AXIS-VIO debug cores into a Versal block design using only natural-language prompts. Capture AXI-Stream waveforms and control/monitor signals live via JTAG — no manual IP configuration required.

## What You'll Build

A PL-only free-running AXI-Stream pipeline on the VCK190 — no PS data paths, no DMA, no DDR. All interaction happens through JTAG debug cores inserted by the AI agent:

```
axis_stream_source ──AXIS──> axis_filter ──AXIS──> AXI4-Stream Data FIFO
        ^                        ^           |
   VIO outputs:             VIO output:     ILA monitors
   - stream_enable          - bypass_enable  this interface
   - pattern_sel[1:0]
                                        VIO input:
                                        - packet_count[31:0]
```

Two bundled skills (`bd-ila-insertion` and `bd-vio-insertion`) teach the agent the correct Vivado parameter sequences, connection patterns, and Versal-specific requirements — like using AXIS-ILA/VIO instead of System ILA/VIO, and routing the JTAG debug path through the AXI Debug Hub and NoC.

## Prerequisites

- VS Code with Vivado MCP Server extension v0.6.8 connected
- Vivado 2025.2 installed and licensed for Versal
- (For hardware test) VCK190 board connected via JTAG

## What's Included

```
ila-insertion-flow/
├── .claude/
│   └── skills/
│       ├── bd-ila-insertion/SKILL.md   # Agent skill for ILA insertion
│       └── bd-vio-insertion/SKILL.md   # Agent skill for VIO insertion
├── spec/
│   └── hardware_spec_vck190.md         # Hardware specification
├── src/
│   ├── axis_stream_source.v            # Free-running AXI-Stream source
│   └── axis_filter.v                   # Passthrough filter with bypass
└── prompts.md
```

## Walk-Through

### Step 1 — Build the Base Design

```
Build the VCK190 project from spec/hardware_spec_vck190.md
with RTL sources from src/. Run through synthesis only.
```

The agent reads the hardware spec, creates a Vivado project targeting the VCK190 (`xcvc1902-vsva2197-2MP-e-S`), adds the two RTL files as module references, and builds a block design with CIPS, AXI NoC, AXI Debug Hub, proc_sys_reset, and the streaming pipeline.

### Step 2 — Insert the VIO

```
Insert an AXIS-VIO to control and monitor the streaming pipeline.
Output probes: stream_enable (1-bit, init 0), pattern_sel (2-bit, init 0),
bypass_enable (1-bit, init 1). Input probe: packet_count (32-bit).
Validate the design.
```

The agent creates an AXIS-VIO with 3 output probes and 1 input probe, connects them to the pipeline, and validates the block design.

### Step 3 — Insert the ILA

```
Insert an AXIS-ILA on the AXI-Stream interface between axis_filter
and the FIFO. Use 1024 sample depth. Validate the design.
```

The agent creates an AXIS-ILA configured for interface monitoring, connects it to the AXI-Stream net, and validates.

### Step 4 — Build the PDI

```
Generate output products, implement, and generate PDI. Report timing.
```

**Expected results:**

| Metric | Value |
|--------|-------|
| Target Device | xcvc1902-vsva2197-2MP-e-S |
| Clock | 100 MHz (`pl0_ref_clk`) |
| WNS (Setup) | +6.132 ns |
| WHS (Hold) | +0.017 ns |
| Timing | All constraints met |

### Step 5 — Hardware Test

Program the VCK190 and verify the debug cores:

| Test | Expected | Result |
|------|----------|--------|
| `stream_enable=0` → `packet_count` is 0 | Count stays at 0 | PASS |
| `stream_enable=1` → packets flowing | Count increments (~0x6A000/sec) | PASS |
| `bypass_enable=0` → data blocked | Count stops | PASS |
| `bypass_enable=1` → data resumes | Count resumes | PASS |
| ILA trigger on TVALID=1 | Captured incrementing TDATA | PASS |

## Single-Prompt Build

If you prefer to run everything in one shot:

```
Build the VCK190 project from spec/hardware_spec_vck190.md with RTL from src/.
Insert AXIS-VIO (stream_enable, pattern_sel, bypass_enable outputs; packet_count input).
Insert AXIS-ILA on the filter->FIFO AXI-Stream interface, 1024 depth.
Build through PDI and report timing.
```

## Debug Core Reference

| Parameter | AXIS-VIO | AXIS-ILA |
|-----------|----------|----------|
| IP | `axis_vio:1.0` | `axis_ila:1.0` |
| Monitor Type | — | `C_MON_TYPE` = `Interface_Monitor` |
| Slot 0 Interface | — | AXI-Stream (`axis_rtl:1.0`) |
| Output Probes | 3 (stream_enable, pattern_sel, bypass_enable) | — |
| Input Probes | 1 (packet_count, 32-bit) | — |
| Sample Depth | — | 1024 |
| Clock | `pl0_ref_clk` (100 MHz) | `pl0_ref_clk` (100 MHz) |

## What You'll Learn

- How to **insert debug cores into Block Designs** using natural-language prompts — no manual IP catalog browsing or connection wiring
- How the bundled skills handle **Vivado parameter sequencing** and Versal-specific constraints
- The difference between **AXIS-VIO** (runtime control/monitor) and **AXIS-ILA** (waveform capture) debug strategies
- How **interface monitoring** captures full AXI-Stream protocol (TDATA, TVALID, TREADY, TKEEP, TLAST) in a single ILA slot
- How debug core insertion affects **timing and resources**

## Prompt Library

**Step 1 — Build PL-Only Streaming Pipeline:**
```
Build the VCK190 project from spec/hardware_spec_vck190.md with RTL sources
from src/. Run through synthesis only.
```

**Step 2 — Insert VIO:**
```
Insert an AXIS-VIO to control and monitor the streaming pipeline.
Output probes: stream_enable (1-bit, init 0), pattern_sel (2-bit, init 0),
bypass_enable (1-bit, init 1). Input probe: packet_count (32-bit).
Validate the design.
```

**Step 3 — Insert ILA:**
```
Insert an AXIS-ILA on the AXI-Stream interface between axis_filter and the
FIFO. Use 1024 sample depth. Validate the design.
```

**Step 4 — Build Through PDI:**
```
Generate output products, implement, and generate PDI. Report timing.
```

**Full End-to-End:**
```
Build the VCK190 project from spec/hardware_spec_vck190.md with RTL from src/.
Insert AXIS-VIO (stream_enable, pattern_sel, bypass_enable outputs; packet_count input).
Insert AXIS-ILA on the filter->FIFO AXI-Stream interface, 1024 depth.
Build through PDI and report timing.
```

<p class="sphinxhide" align="center"><sub>Copyright &copy; 2026 Advanced Micro Devices, Inc</sub></p>
<p class="sphinxhide" align="center"><sup><a href="https://www.amd.com/en/corporate/copyright">Terms and Conditions</a></sup></p>
