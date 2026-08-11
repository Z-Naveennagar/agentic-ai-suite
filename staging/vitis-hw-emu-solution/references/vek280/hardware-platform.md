<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Hardware Platform

## Scope

Load this file when the user is on the custom platform path (Path B): building a Vivado hardware design for VEK280, exporting the XSA, or deciding when to build custom hardware vs using the pre-built platform.

## When to Build Custom Hardware

Use the custom Vivado path when:
- Adding custom PL IP or accelerators not in the base platform
- Requiring specific clock frequencies, AXI port configurations, or interrupt routing
- Needing to modify CIPS peripherals, DDR settings, or memory maps
- Building a production design that must differ from the AMD reference
- Debugging hardware-level issues that require visibility into the block design

Use the **pre-built xpfm** when:
- Validating the sw/hw_emu flow quickly without hardware changes
- Running the tutorial vadd and aieml examples as-is
- Prototyping application software before hardware is finalized

## Pre-built Platform (Reference)

Path:
```
/proj/rdi/xbuilds/released/2025.2/2025.2_released/internal_platforms/xilinx_vek280_base_202520_1/xilinx_vek280_base_202520_1.xpfm
```

This platform was built from AMD's reference VEK280 block design. It provides:
- Standard CIPS configuration for VEK280 board
- DDR4 memory controller
- AIE-ML array connectivity
- Standard clock and interrupt configuration

It is functionally equivalent to what `run.tcl` + `platform_creation.py` produce when run without modification.

## Custom Vivado Design (run.tcl)

### Device Target

```
Part:  xcve2802-vsvh1760-2MP-e-S   (Versal AI Edge)
Board: xilinx.com:vek280:part0:1.2
```

### What run.tcl Does

```bash
cd <tutorial_root>
make hw
# runs: vivado -mode batch -notrace -source run.tcl -tclargs
# output: build/vivado/vek280_custom.xsa
```

Step by step:
1. Creates Vivado project `project_1` for xcve2802-vsvh1760-2MP-e-S
2. Opens the "Versal Extensible Part Support" example design from the Vivado Store (requires XHUB / network access)
3. Configures:
   - Two clocks: 625 MHz and 100 MHz outputs
   - 63 interrupt configurations
   - AIE-ML inclusion enabled
4. Generates HDL wrapper
5. Exports `vek280_custom.xsa`

> **Note:** Unlike VCK190, the VEK280 tutorial exports only **one XSA** (hardware). There is no separate `*_hwemu.xsa`. The hw_emu simulation models are embedded in the single XSA.

### Key Design Parameters

| Parameter | VEK280 | VCK190 (reference) |
|-----------|--------|-------------------|
| Part | xcve2802-vsvh1760-2MP-e-S | xcvc1902-vsva2197-2MP-e-S |
| AI Engine | AIE-ML | AIE1 |
| Clock outputs | 625 MHz + 100 MHz | Varies |
| Interrupts | 63 | Standard |
| DDR constraints | Not required in tutorial | ddr.xdc required |
| Separate hwemu XSA | No — single XSA | Yes — hw + hwemu |

### Designing Custom Hardware

When creating your own VEK280 hardware design from scratch (not using run.tcl):
- Start from the Versal AI Edge extensible example design in Vivado
- Ensure CIPS is configured for VEK280 board (boot mode, peripherals)
- Keep `preferred_sim_model = tlm` for NoC and memory controllers for hw_emu compatibility
- Export a single XSA — `platform_creation.py` accepts only one XSA path (unlike VCK190 which accepted hw + hwemu separately)
- Reference `the VCK190 references (`references/vck190/`)` `references/vek280/hardware-platform.md` for detailed CIPS/NOC/AIE Vivado design guidance — the concepts are directly applicable to Versal AI Edge

### XHUB Network Requirement (run.tcl)

`run.tcl` downloads the Versal Part Support example from the Vivado Store. If the machine cannot reach the Vivado Store, Step 1 will fail. In that case, either:
- Use the pre-built xpfm (skip Steps 1 and 2 entirely)
- Pre-cache the Versal example design locally and modify run.tcl to source it from disk

## Export Checklist (Custom Path)

Before leaving Step 1:

1. `build/vivado/vek280_custom.xsa` exists and is recent
2. No ERROR lines in `build/vivado/vivado.log`
3. CRITICAL WARNINGs reviewed (BD connectivity warnings are expected for platform designs)

The next artifact after Step 1 is:
```
ws/vek280_custom/export/vek280_custom/vek280_custom.xpfm
```
produced by `make pfm` in Step 2.
