<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Hardware Platform

## Scope

Load this file when the user is in the Vivado phase of the ZCU104 tutorial or when the XSA is missing, stale, or suspected to be incomplete.

## Goal Of Step 1

Produce the hardware handoff that the software-platform stage consumes.

Core outcomes:
- a valid ZCU104-targeted Vivado hardware design
- an exported XSA suitable for Vitis platform creation
- clocks, interfaces, and platform-facing hardware choices that match the intended acceleration use case

The tutorial’s canonical setup starts with:

```bash
source <Vivado_Install_Directory>/settings64.sh
mkdir WorkSpace
cd WorkSpace
mkdir zcu104_hardware_platform
cd zcu104_hardware_platform
vivado &
```

The expected Vivado project is:
- project name: `zcu104_custom_platform`
- board: `Zynq UltraScale+ ZCU104 Evaluation Board`
- block design name: `system`
- project option: `Project is an extensible Vitis platform`

## What To Inspect

- block-design Tcl or Vivado project settings
- target board selection and platform assumptions
- exported XSA path and timestamp
- whether the hardware change the user made actually requires a new export

Also inspect these tutorial-specific platform settings:
- clock wizard outputs at `100`, `200`, and `400` MHz
- `clk_out2` marked as the default platform clock
- `PFM.IRQ` exported from `axi_intc_0/intr` with:
  `set_property PFM.IRQ {intr { id 0 range 32 }} [get_bd_cells /axi_intc_0]`
- PS AXI master ports exported for kernel control connectivity
- PS AXI slave ports tagged as `HPC0`, `HPC1`, `HP0`, `HP1`, `HP2`, and `HP3`
- PS simulation model set to TLM for hardware emulation if emulation support is needed

## Hardware-Side Thinking

Before moving forward, confirm:

1. the design is still the intended ZCU104 platform base
2. the XSA was regenerated after the latest hardware edits
3. any platform-facing IP changes are reflected in the exported hardware handoff

Do not debug software packaging against a stale XSA.

## Common Failure Modes

### Missing XSA

If there is no exported XSA, stop and complete the hardware-export stage first.

The tutorial expects:
- `zcu104_custom_platform_hw.xsa`
- optionally `zcu104_custom_platform_hwemu.xsa`

### Stale XSA

If the user changed clocks, interfaces, interrupts, or address mapping but reused an older XSA, expect later platform-package failures or mismatches.

Common stale-XSA triggers in this tutorial:
- changed clock IDs or default clock selection
- changed AXI slave `sptag` names
- changed interrupt-controller wiring
- toggled emulation support but did not re-export `*_hwemu.xsa`

### Wrong Problem Layer

If the user reports application or `hw_emu` failure but the platform hardware is still changing, first stabilize the hardware export. Otherwise later diagnosis is noisy.

## Export Checklist

Before leaving Step 1, the tutorial expects:

1. validate the block design
2. create the HDL wrapper for `system.bd`
3. generate the pre-synthesis block design
4. optionally generate a bitstream
5. export platform hardware and, if needed, hardware emulation

The Tcl alternative shown in the tutorial is:

```tcl
set_property platform.default_output_type "sd_card" [current_project]
set_property platform.design_intent.embedded "true" [current_project]
set_property platform.design_intent.server_managed "false" [current_project]
set_property platform.design_intent.external_host "false" [current_project]
set_property platform.design_intent.datacenter "false" [current_project]
write_hw_platform -hw -force -file ./zcu104_custom_platform_hw.xsa
write_hw_platform -hw_emu -force -file ./zcu104_custom_platform_hwemu.xsa
```

## Fast Track

The scripted reproduction for Step 1 is:

```bash
cd step1_vivado
make all
make clean
```

The Step 1 Makefile’s key actions are:
- create `build/vivado`
- run Vivado in batch mode from that directory
- source `system_step1.tcl`
- source `../../export_xsa.tcl`

The scripted Step 1 outputs land under:
- `step1_vivado/build/vivado/zcu104_custom_platform_hw.xsa`
- `step1_vivado/build/vivado/zcu104_custom_platform_hwemu.xsa`

When debugging scripted Step 1 failures, check:
- whether `vivado` is on `PATH`
- whether the batch Tcl files are present and resolvable from `build/vivado`
- whether the expected XSA files were actually emitted under `build/vivado`

## Good Outputs

When answering hardware-phase questions:
- identify whether the XSA is present and current
- state whether Step 1 is complete
- name the next software-stage artifact that should be produced

The next concrete artifact after Step 1 is usually:
- extracted common-image content under `xilinx-zynqmp-common-v2025.2`
- a Step 2 platform configuration that will generate `system.dtb` during platform creation
