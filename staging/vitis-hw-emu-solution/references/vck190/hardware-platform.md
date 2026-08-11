<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Hardware Platform

## Scope

Load this file when the user is in the Vivado phase of the VCK190 tutorial, when the XSA is missing or stale, or when diagnosing hardware design configuration issues specific to Versal Gen1.

## Goal of Step 1

Produce the hardware handoff that the software-platform stage consumes.

Core outcomes:
- a valid VCK190-targeted Vivado hardware design (Versal ACAP xcvc1902)
- an exported XSA for Vitis platform creation (`custom_hardware_platform_hw.xsa`)
- an exported hw_emu XSA with TLM simulation models (`custom_hardware_platform_hwemu.xsa`)
- CIPS, NOC, DDR4, LPDDR4, and AIE topology that matches the intended acceleration use case

The tutorial's canonical Step 1 script is:
```bash
cd step1_vivado
make all
# runs: vivado -mode batch -notrace -source run.tcl
# outputs: build/vivado/custom_hardware_platform_hw.xsa
#          build/vivado/custom_hardware_platform_hwemu.xsa
```

The Vivado project targets part: `xcvc1902-vsva2197-2MP-e-S`

## Key Vivado Design Elements

### CIPS (Control Interface and Processing System) Configuration

The tutorial configures the CIPS IP with these settings:
- Boot mode: SD1/eMMC1 (SD 3.0)
- Active peripherals: GEM0 (Ethernet), CAN1, UART0, I2C0, I2C1, USB3
- IPI channels enabled for A72 processors
- Interrupt routing configured for PL-to-PS signaling

These settings must match the VCK190 board definition. Mismatches between CIPS peripheral settings and the device tree (system-user.dtsi) cause Linux boot failures.

### NOC DDR4 Configuration

- Input clock: 200 MHz (5000 ps period)
- Memory type: DDR4-3200AA (22-22-22)
- Timing parameters: TRCD, TRP, TRC configured for DDR4-3200

### NOC LPDDR4 Configuration

- Flipped pinout enabled for VCK190 board
- Input clock: 200.321 MHz (4992 ps period)
- Dual-channel LPDDR4 support

### DDR Constraints File

The `ddr.xdc` file is required for DDR pin placement. It maps:
- LPDDR4 data/address/control signals (CH0_A, CH0_B, CH1) to FPGA package pins
- DDR4 signals to FPGA package pins
- Timing and electrical properties for high-speed memory interfaces

If ddr.xdc is missing or not imported, synthesis will fail or produce incorrect pin assignments.

### AIE Topology

The "Extensible Part Support Example" design includes the AI Engine array. When exporting XSA:
- AIE must be included in the design topology
- The hwemu.xsa uses SystemC TLM models for AIE simulation
- Do not disable AIE in the block design if the platform will support AIE kernels

### Vivado Script: run.tcl

The Step 1 script (`run.tcl`) performs these key actions:
1. Detects CPU count for parallel build
2. Downloads "ext_platform_part" example design from Vivado Store via XHUB
3. Creates project for xcvc1902-vsva2197-2MP-e-S
4. Configures CIPS (boot mode, peripherals, IPI, interrupts)
5. Configures NOC DDR4 and LPDDR4 with VCK190-specific timing
6. Imports `ddr.xdc` constraints
7. Generates HDL wrapper and block design outputs
8. Exports both XSA files

If XHUB download fails (no network or Vivado Store unavailable), the script cannot proceed. Check network access to the Vivado Store before running in isolated environments.

## What To Inspect

- Vivado project settings: correct part (xcvc1902-vsva2197-2MP-e-S)
- CIPS configuration: boot mode, peripheral enables, IPI channels
- NOC configuration: DDR4 and LPDDR4 timing parameters
- DDR constraints: ddr.xdc imported and matching board pinout
- Both XSA files present and timestamped after latest hardware edit
- hwemu.xsa: verify it was exported with TLM simulation models

Check these platform-facing settings before export:
```tcl
# Verify simulation model is TLM for hw_emu compatibility
get_property preferred_sim_model [current_project]
# For Versal, NOC TLM is set per-IP during design automation
```

## Common Failure Modes

### XHUB Download Failure

If Vivado cannot reach the Vivado Store to download the Part Support example:
- Error: unable to instantiate `ext_platform_part`
- Fix: ensure network access or pre-cache the example design locally

### Missing ddr.xdc

If ddr.xdc is not present in step1_vivado/ when run.tcl executes:
- Error during constraint import step
- Fix: verify ddr.xdc exists alongside run.tcl before `make all`

### Stale XSA

If the user changed CIPS configuration, NOC parameters, or AXI connectivity but reused an older XSA:
- Platform build may succeed but DTB, boot, or application behavior will mismatch
- Common triggers: changed peripheral enables, clock IDs, AXI sptag names
- Fix: re-run `make all` in step1_vivado to regenerate both XSA files

### Wrong hwemu.xsa

If `custom_hardware_platform_hwemu.xsa` is absent or was exported without TLM models:
- hw_emu platform build will proceed but emulation startup will fail
- verify: `file size custom_hardware_platform_hwemu.xsa` should be comparable to hw.xsa

## Export Checklist

Before leaving Step 1, verify:

1. `build/vivado/custom_hardware_platform_hw.xsa` exists
2. `build/vivado/custom_hardware_platform_hwemu.xsa` exists
3. Both files are newer than the last run.tcl modification
4. No ERROR lines in `build/vivado/vivado.log`
5. CRITICAL WARNINGs reviewed (BD connectivity warnings are usually non-blocking for platform design)

The Tcl equivalents for manual export:
```tcl
write_hw_platform -hw     -force -file ./custom_hardware_platform_hw.xsa
write_hw_platform -hw_emu -force -file ./custom_hardware_platform_hwemu.xsa
```

## Good Outputs

When answering hardware-phase questions:
- identify whether both XSA files are present and current
- state whether Step 1 is complete
- name the next software-stage artifact that should be produced

The next concrete artifact after Step 1 is:
- `step2_pfm/ws/custom_platform/export/custom_platform/custom_platform.xpfm`
  produced by `make all COMMON_IMAGE_VERSAL=<path>` in step2_pfm/
