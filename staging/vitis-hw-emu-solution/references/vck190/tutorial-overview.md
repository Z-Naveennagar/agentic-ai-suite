<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Tutorial Overview

## Scope

Load this file when the user needs the high-level flow for the VCK190 Edge platform-creation tutorial or when deciding whether a problem belongs here or in `the cosim runtime references (`references/cosim/`)`.

## Purpose

This skill covers the custom embedded platform creation flow for VCK190 (Versal Gen1 ACAP) that precedes hardware emulation and co-simulation. The tutorial's structure is stage-oriented:

1. create the Versal hardware platform in Vivado (CIPS + NOC + DDR + AIE)
2. assemble the software platform with Versal Linux common image and AIE domain
3. validate the resulting platform with vadd (PL kernel) and aie_adder (AIE+PL) applications
4. iterate efficiently when hardware or software content changes

Treat the platform as a prerequisite for later `hw_emu` and cosim work.

## Target Platform

| Property | Value |
|----------|-------|
| Board | VCK190 Evaluation Board |
| SoC | Versal Gen1 ACAP |
| Part | xcvc1902-vsva2197-2MP-e-S |
| Linux CPU | Cortex-A72 (`psv_cortexa72`) |
| QEMU instances in hw_emu | **2 (PMC + APU)** |
| AI Engine | **Yes — AIE1, explicit domain required** |
| Memory | DDR4 + LPDDR4 (dual NOC) |
| Boot firmware | PLM (embedded in silicon — no FSBL/PMUFW) |

## Tutorial-Specific Names

The 2025.2 tutorial consistently uses these names and paths:

- tutorial root: `Vitis_Platform_Creation/Design_Tutorials/03_Edge_VCK190/`
- ref_files root: `03_Edge_VCK190/ref_files/`
- step-1 hardware folder: `ref_files/step1_vivado/`
- Vivado batch script: `step1_vivado/run.tcl`
- DDR pin constraints: `step1_vivado/ddr.xdc`
- exported hardware XSA: `step1_vivado/build/vivado/custom_hardware_platform_hw.xsa`
- exported hardware-emulation XSA: `step1_vivado/build/vivado/custom_hardware_platform_hwemu.xsa`
- Versal common image variable: `COMMON_IMAGE_VERSAL`
- Versal common image path (2025.2): `/proj/rdi/xbuilds/released/2025.2/2025.2_released/internal_platforms/sw/versal/xilinx-versal-common-v2025.2/`
- platform component name in Vitis: `custom_platform`
- platform output path: `step2_pfm/ws/custom_platform/export/custom_platform/`
- platform xpfm: `custom_platform.xpfm`
- step-3 directory name: `step3_application` (NOT step3_validate — differs from ZCU104)
- AIE adder run script: `step3_application/run_aie.sh`
- vadd run script: `step3_application/run_vadd.sh`

The stage ordering in 2025.2:
- create the Versal hardware design and export both hw.xsa and hwemu.xsa
- build the Vitis platform — DTB is auto-generated from DTSI + XSA (no standalone createdts)
- validate with `platforminfo`, vadd application, and AIE adder application

Key 2025.2 change vs earlier versions:
- DTB is generated automatically by the Vitis Platform Wizard during platform creation
- `platform_creation.py` uses `enable_zocl_dt_overlay=True` and explicit `user_dtsi` argument
- AIE domain (`aie_runtime`) is added explicitly as a separate platform domain
- standalone `createdts` workflow is legacy — do not apply to 2025.2

Use these exact names when mapping a user's state against the tutorial. If their names differ, translate explicitly rather than assuming their layout is wrong.

## Architecture: Versal Gen1 vs ZCU104

| Aspect | VCK190 (Versal Gen1) | ZCU104 (Zynq UltraScale+) |
|--------|---------------------|--------------------------|
| SoC part | xcvc1902-vsva2197-2MP-e-S | xczu7ev-ffvc1156-2-e |
| Linux CPU | psv_cortexa72 (A72) | psu_cortexa53 (A53) |
| QEMU instances | 2: PMC + APU | 1: APU only |
| AI Engine | Yes — explicit domain required | No |
| Memory | DDR4 + LPDDR4 (dual NOC) | DDR4 (single) |
| DDR constraints | ddr.xdc required | Not required |
| Boot firmware | PLM (no FSBL/PMUFW) | FSBL + PMUFW generated |
| Vivado script | run.tcl (XHUB example download) | system_step1.tcl + export_xsa.tcl |
| Common image var | COMMON_IMAGE_VERSAL | COMMON_IMAGE_ZYNQMP |
| Sysroot triplet | cortexa72-cortexa53-amd-linux | cortexa72-cortexa53-amd-linux |
| Test applications | vadd (PL) + aie_adder (AIE+PL) | vadd only |

## Boundaries

Stay in this skill when the user is:
- building or reviewing the Vivado hardware design (CIPS, NOC, DDR, AIE topology)
- exporting or replacing the XSA (hw or hwemu variant)
- assembling boot components, DTB, kernel, rootfs, AIE domain, or sysroot inputs
- building or checking the `.xpfm`
- validating the platform build with `platforminfo` or a sample application (vadd or aie_adder)

Switch to `the cosim runtime references (`references/cosim/`)` when the user is:
- launching `hw_emu` (launch_hw_emu.sh)
- debugging QEMU PMC or APU instance startup
- diagnosing PS/PL/AIE traffic, remote-port connections, AIE SystemC bridge, or DDR-sharing
- investigating runtime mismatches between QEMU and XSIM

## Expected Artifact Chain

Think in this order:

1. Vivado design and exported XSA:
   - `step1_vivado/build/vivado/custom_hardware_platform_hw.xsa`
   - `step1_vivado/build/vivado/custom_hardware_platform_hwemu.xsa`
2. Versal boot and Linux software inputs (from COMMON_IMAGE_VERSAL):
   - `bl31.elf`
   - `u-boot.elf`
   - `boot.scr`
   - `Image`
   - `rootfs.ext4`
   - sysroot at `sysroots/cortexa72-cortexa53-amd-linux/`
3. Generated platform package and metadata:
   - `step2_pfm/ws/custom_platform/export/custom_platform/custom_platform.xpfm`
   - `vitis-comp.json`
   - boot folder contents (BIF-referenced artifacts)
4. Application build and validation output:
   - `platforminfo` report from `step2_pfm/platforminfo/`
   - vadd: `simple_vadd` (AArch64), `krnl_vadd.xclbin`, `launch_hw_emu.sh`
   - aie_adder: `aie_adder` (AArch64), `krnl_adder.xclbin`, AIE graph artifacts

If any earlier stage is incomplete, later failures are usually downstream symptoms.

## Common Questions This Skill Should Answer

- What should exist after Step 1 for VCK190?
- Which software artifacts are needed before creating the Versal platform package?
- Why does the AIE domain fail to build or appear in platforminfo?
- Which tutorial stage needs to be rerun after a hardware or software change?
- How does PLM firmware fit into the Versal platform (vs FSBL/PMUFW in ZCU104)?

## Fast Path Commands (ref_files scripted flow)

```bash
# Step 1 — Vivado hardware build
cd step1_vivado
make all

# Step 2 — Vitis platform (DTB auto-generated, no createdts)
cd step2_pfm
make all COMMON_IMAGE_VERSAL=<path/to/xilinx-versal-common-v2025.2/>

# Step 3 — hw_emu validation (vadd + aie_adder)
cd step3_application
make vadd_emu   PLATFORM=<path/to/custom_platform.xpfm> COMMON_IMAGE_VERSAL=<path>
make aie_adder_emu PLATFORM=<path/to/custom_platform.xpfm> COMMON_IMAGE_VERSAL=<path>
```

Top-level orchestration from ref_files/:
```bash
make all COMMON_IMAGE_VERSAL=<path>      # hw_emu flow
make sd_card COMMON_IMAGE_VERSAL=<path>  # hardware flow
```

## Scripted Makefile Flow

The `ref_files/Makefile` orchestrates all three steps.

Key dependency chain:
- XSA target: `step1_vivado/build/vivado/custom_hardware_platform_hw.xsa`
- platform target: `step2_pfm/ws/custom_platform/export/custom_platform/custom_platform.xpfm`
- step3 dispatch: `make vadd_emu` and `make aie_adder_emu` in `step3_application/`

The step2_pfm Makefile skips `getplatforminfo` by default — run separately with `make getplatforminfo`.

The step3_application Makefile copies vadd and AIE adder sources from `$XILINX_VITIS/samples/` before building. Verify XILINX_VITIS is set by sourcing Vitis settings64.sh.

Known 2025.2 path notes:
- PLATFORM default in step3 may not match actual ws/ output path from step2 — pass PLATFORM explicitly
- COMMON_IMAGE_VERSAL must be set explicitly; it is not exported by settings64.sh
