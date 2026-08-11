<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Tutorial Overview

## Scope

Load this file when the user needs the high-level flow for the VEK280 platform tutorial, when deciding which platform path to take, or when deciding whether a problem belongs here or in `the cosim runtime references (`references/cosim/`)`.

## Purpose

This skill covers the VEK280 (Versal AI Edge) platform flow that precedes hardware emulation. Unlike the ZCU104 and VCK190 tutorials, the VEK280 tutorial explicitly supports two platform paths:

**Path A — Pre-built platform (fast bring-up):**
- Skip Vivado and Vitis platform creation entirely
- Use the AMD-provided `xilinx_vek280_base` xpfm from the installation
- Go directly to application build and hw_emu
- Best for: first-time users, quick validation, CI/CD

**Path B — Custom platform (full control):**
- Build a Vivado hardware design from `run.tcl`
- Create a custom Vitis platform via `platform_creation.py`
- Full ownership of clocks, interrupts, memory maps, and AXI topology
- Best for: production designs, custom IP, non-standard boot configuration

**Always inform users that Path B exists even if they ask only about Path A.** The pre-built platform is a convenience, not a ceiling.

## Target Platform

| Property | Value |
|----------|-------|
| Board | VEK280 Evaluation Board |
| SoC | Versal AI Edge |
| Part | xcve2802-vsvh1760-2MP-e-S |
| Linux CPU | Cortex-A72 (`psv_cortexa72`) |
| AI Engine | AIE-ML (next-gen, distinct from AIE1 on VCK190) |
| QEMU instances in hw_emu | 2 (PMC + APU) |
| Memory | DDR4 |

## AIE-ML vs AIE1

VEK280 uses **AIE-ML** — the next-generation AI Engine introduced in the Versal AI Edge series. Key differences from AIE1 (VCK190):

| Aspect | VEK280 (AIE-ML) | VCK190 (AIE1) |
|--------|----------------|--------------|
| Compiler | `aiecompiler` (AIE-ML mode) | `aiecompiler` (AIE mode) |
| Sample used | `aie-ml_sys_design` | `aie_sys_design` |
| Application | matrix multiplication | simple adder |
| Makefile | `makefile_aieml` | `makefile_aie` |
| Run script | `run_aieml.sh` | `run_aie.sh` |
| xclbin name | `krnl_aieml.xclbin` | `krnl_adder.xclbin` |

Do not use AIE1 sample sources or AIE1 compilation flags for VEK280.

## Tutorial-Specific Names (Custom Path)

The 2025.2 tutorial ref_files consistently use these names:

- Tutorial root: `Getting_Started/Vitis_Platform/ref_files/vek280/`
- Vivado batch script: `run.tcl`
- Vivado project name: `project_1`
- XSA name: `vek280_custom.xsa`
- Platform name: `vek280_custom`
- Platform output (custom): `ws/vek280_custom/export/vek280_custom/vek280_custom.xpfm`
- Versal common image variable: `COMMON_IMAGE_VERSAL`
- Sysroot: `{COMMON_IMAGE_VERSAL}/sysroots/cortexa72-cortexa53-amd-linux/`
- vadd work directory: `vadd_work/`
- aieml work directory: `aieml_work/`

## Pre-built Platform Path

The AMD-provided base platform is available at:

```
/proj/rdi/xbuilds/released/2025.2/2025.2_released/internal_platforms/xilinx_vek280_base_202520_1/xilinx_vek280_base_202520_1.xpfm
```

When using this platform, pass it explicitly to Step 3 make commands:
```bash
PLATFORM=/proj/rdi/xbuilds/released/2025.2/2025.2_released/internal_platforms/xilinx_vek280_base_202520_1/xilinx_vek280_base_202520_1.xpfm
```

The Makefile default PLATFORM points to the custom path (`ws/vek280_custom/...`). If using the pre-built platform, always override PLATFORM explicitly.

## Artifact Chain

### Path A — Pre-built

```
Pre-built xpfm (from installation)
  └── Step 3: vadd + aieml application build + hw_emu run
```

### Path B — Custom

```
Step 1 — run.tcl → build/vivado/vek280_custom.xsa
Step 2 — platform_creation.py → ws/vek280_custom/export/vek280_custom/vek280_custom.xpfm
Step 3 — vadd + aieml application build + hw_emu run
```

## Boundaries

Stay in this skill when the user is:
- deciding between pre-built and custom platform paths
- building or reviewing the Vivado hardware design (custom path)
- creating or inspecting the Vitis platform (custom path)
- assembling boot components, common image, or sysroot
- validating with `platforminfo`, vadd, or aieml
- iterating after a hardware or software change

Switch to `the cosim runtime references (`references/cosim/`)` when the user is:
- debugging `launch_hw_emu.sh` startup
- investigating QEMU PMC or APU failures
- diagnosing remote-port connections or AIE-ML SystemC bridge issues
- analyzing runtime PS/PL/AIE-ML behavior

## Fast Path Commands

### Path A — Pre-built xpfm

```bash
VER=2025.2
PLATFORM=/proj/rdi/xbuilds/released/${VER}/${VER}_released/internal_platforms/xilinx_vek280_base_202520_1/xilinx_vek280_base_202520_1.xpfm
COMMON_IMAGE_VERSAL=/proj/rdi/xbuilds/released/${VER}/${VER}_released/internal_platforms/sw/versal/xilinx-versal-common-v${VER}/

# vadd hw_emu
make vadd_emu PLATFORM=$PLATFORM COMMON_IMAGE_VERSAL=$COMMON_IMAGE_VERSAL

# aieml hw_emu
make aieml_emu PLATFORM=$PLATFORM COMMON_IMAGE_VERSAL=$COMMON_IMAGE_VERSAL
```

### Path B — Custom platform (full flow)

```bash
make all COMMON_IMAGE_VERSAL=$COMMON_IMAGE_VERSAL
# runs: hw → pfm → vadd_emu → aieml_emu
```
