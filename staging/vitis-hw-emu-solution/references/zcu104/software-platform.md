<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Software Platform

## Scope

Load this file when the user has an XSA and is now assembling the software side of the ZCU104 platform.

## Goal Of Step 2

Turn the exported hardware into a usable Vitis embedded platform package.

Typical software-side inputs include:
- boot components
- device tree content
- Linux kernel image
- root filesystem image
- sysroot or other application-build support content

The tutorial flow expects the platform to be built around these inputs, not just around the XSA alone.

The tutorial’s software-component table maps the required artifacts like this:
- `fsbl.elf`: generated during platform creation
- `pmufw.elf`: generated during platform creation
- `bl31.elf`: extracted from the common image
- `u-boot.elf`: extracted from the common image
- `system.dtb`: generated along with platform creation
- `boot.scr`: extracted from the common image
- `Image`: extracted from the common image
- `rootfs.ext4`: extracted from the common image
- `sysroot`: installed from `sdk.sh`

## Artifacts To Ask For

- XSA from Step 1
- DTB or device-tree generation inputs
- boot files such as FSBL, PMUFW, BL31, U-Boot, and boot script content when applicable
- Linux image inputs such as `Image` and `rootfs.ext4`
- sysroot path
- generated platform package and `.xpfm`

The tutorial-specific directory layout to expect is:

```text
WorkSpace/
├── xilinx-zynqmp-common-v2025.2.tar.gz
├── xilinx-zynqmp-common-v2025.2/
│   ├── bl31.elf
│   ├── boot.scr
│   ├── Image
│   ├── rootfs.ext4
│   ├── sdk.sh
│   └── u-boot.elf
├── zcu104_hardware_platform/
│   ├── zcu104_custom_platform_hw.xsa
│   └── zcu104_custom_platform_hwemu.xsa
└── workspace/
    └── zcu104_custom/
        ├── hw/sdt/system.dtb
        └── export/zcu104_custom/zcu104_custom.xpfm
```

## Packaging Mindset

Separate the questions:

1. do we have the software inputs?
2. were they generated from the current XSA and intended Linux stack?
3. did the platform package embed or reference the right files?

If the platform is malformed, avoid jumping straight to application debug. First identify which input is missing, stale, or mismatched.

## Exact Commands

### Prepare The Common Image

```bash
cd WorkSpace
tar xvf xilinx-zynqmp-common-v2025.2.tar.gz -C .
```

### Device Tree Handling

The 2025.2 tutorial removes the separate `createdts` step from the default path.

Instead, the Platform Wizard is expected to generate the DTB:
- set `Board DTSI` to `zcu104-revc`
- select the user DTSI from `ref_files/step2_pfm/system-user.dtsi`
- enable `DT ZOCL`
- enable `Generate Device Tree Blob (DTB)`

The resulting DTB is expected under:
- `<platform component>/hw/sdt/system.dtb`

### Install The Sysroot

From the extracted common-image directory, run:

```bash
./sdk.sh -d <Install Target Dir>
```

The tutorial notes that `LD_LIBRARY_PATH` must not be set when running `sdk.sh`.

### Create The Platform In Vitis

The GUI path is:
- `File > New Component > Platform`
- component name: `zcu104_custom`
- XSA: `zcu104_custom_platform_hw.xsa`
- optional emulation XSA: `zcu104_custom_platform_hwemu.xsa`
- expand `Advanced Options`
- set `Board DTSI` to `zcu104-revc`
- browse to the user DTSI file in `ref_files/step2_pfm/system-user.dtsi`
- enable `DT ZOCL`
- OS: `linux`
- processor: `psu_cortexa53`
- enable `Generate boot artifacts`
- enable `Generate Device Tree Blob (DTB)`

Then configure:
- display name: `xrt`
- pre-built image directory: `xilinx-zynqmp-common-v2025.2`
- DTB file: auto-populated from the generated platform outputs

The platform output path is:
- `workspace/zcu104_custom/export/zcu104_custom/`

For the scripted flow, the operational path used by Step 3 is:
- `step2_pfm/ws/zcu104_custom/export/zcu104_custom/zcu104_custom.xpfm`

The tutorial also provides a Python automation pattern:

```bash
vitis -s platform_creation.py --platform_name <> --xsa_path <> --xsa-emu_path <> --boot <> --user_dtsi <>
```

## Common Failure Modes

### Missing Boot Or Linux Inputs

If the user has hardware but not the Linux-facing inputs, the platform package is incomplete. Stay in Step 2.

Most often missing in this tutorial:
- common-image extraction was skipped
- `Board DTSI` or user DTSI was not configured in the Platform Wizard
- `DT ZOCL` was left disabled, so the platform lacks the expected ZOCL device-tree content
- `Generate Device Tree Blob (DTB)` was left disabled, so `system.dtb` was never generated with the platform
- `sdk.sh` was not run, so the application sysroot path is unavailable

### Device-Tree Mismatch

If the XSA changed but the DTB path or generated device-tree content did not, expect boot or runtime mismatches later.

The 2025.2 tutorial assumes the DTB was regenerated from the current `zcu104_custom_platform_hw.xsa` as part of platform creation, not reused from an older export.

### Platform Package Exists But Is Wrong

A generated `.xpfm` does not guarantee a correct platform. Ask what it references and whether those references were refreshed after the latest hardware change.

Also verify whether the Vitis domain auto-populated `Qemu Args File` and `Pmu Args File`, because the tutorial expects those to be generated automatically.

## Fast Track

The scripted Step 2 path is:

```bash
cd step2_pfm
make all COMMON_IMAGE_ZYNQMP=<path/to/common_image/>
make clean
```

The Step 2 Makefile’s key actions are:
- verify `COMMON_IMAGE_ZYNQMP/Image` exists
- create `tmp` and set `XILINX_VITIS_DATA_DIR=./tmp`
- run:

```bash
vitis -s platform_creation.py \
  --platform_name zcu104_custom \
  --xsa_path ../step1_vivado/build/vivado/zcu104_custom_platform_hw.xsa \
  --xsa-emu_path ../step1_vivado/build/vivado/zcu104_custom_platform_hwemu.xsa \
  --boot <COMMON_IMAGE_ZYNQMP> \
  --user_dtsi <step2_pfm>/system-user.dtsi
```

- report generated `.xpfm` files with `find . -name "*.xpfm"`

Important scripted-flow details:
- the Makefile implements the new `user_dtsi`-based platform-creation flow rather than an explicit `createdts` command
- the Makefile still contains legacy residue such as an unused `DTB=.../mydevice/.../system.dtb` variable
- `clean` still removes `mydevice`, even though that path is no longer part of the default 2025.2 flow

When scripted Step 2 succeeds but downstream consumers cannot find the platform, check whether the actual output is under `ws/` rather than under a direct `zcu104_custom/` folder.

## Good Outputs

When answering software-platform questions:
- identify the missing or stale software input
- say whether Step 2 is complete
- state whether the user can move on to validation or must regenerate the package

The key output to name explicitly is:
- `zcu104_custom/export/zcu104_custom/zcu104_custom.xpfm`
