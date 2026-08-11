<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Software Platform

## Scope

Load this file when the user is assembling the Versal software platform: boot artifacts, common image, DTB generation, AIE domain setup, and the `platform_creation.py` invocation.

## Goal of Step 2

Produce the Vitis platform package (`.xpfm`) that the application build and hw_emu flow consume.

Core outcomes:
- Vitis platform with Linux domain (`xrt`) and AIE domain (`aie_runtime`)
- DTB generated automatically from XSA System Device Tree + `system-user.dtsi`
- Boot directory populated with Versal common image artifacts
- `custom_platform.xpfm` exported and validated by `platforminfo`

```bash
cd step2_pfm
make all COMMON_IMAGE_VERSAL=<path/to/xilinx-versal-common-v2025.2/>
```

## Versal Common Image

The common image provides pre-built Linux software for Versal. It is NOT built from PetaLinux — use the AMD-provided image.

### Path Pattern

```
COMMON_IMAGE_VERSAL = /proj/rdi/xbuilds/released/{ver}/{ver}_released/internal_platforms/sw/versal/xilinx-versal-common-v{ver}/
```

Example for 2025.2:
```
/proj/rdi/xbuilds/released/2025.2/2025.2_released/internal_platforms/sw/versal/xilinx-versal-common-v2025.2/
```

**Important**: `COMMON_IMAGE_VERSAL` is NOT set automatically by sourcing Vitis settings64.sh. It must be passed explicitly to every make command or exported before building.

### Required Contents

Verify these files exist in `COMMON_IMAGE_VERSAL` before starting Step 2:

| File | Purpose |
|------|---------|
| `Image` | Linux kernel image |
| `rootfs.ext4` | Root filesystem |
| `boot.scr` | U-Boot script |
| `bl31.elf` | ARM Trusted Firmware (BL31) |
| `u-boot.elf` | U-Boot bootloader |
| `sysroots/cortexa72-cortexa53-amd-linux/` | Cross-compilation sysroot |
| `environment-setup-cortexa72-cortexa53-amd-linux` | SDK environment setup script |

Note: Versal does NOT use FSBL or PMUFW — those are ZynqMP-specific. Versal uses PLM (Platform Loader and Manager), which is embedded in the device and does not appear as a user-provided artifact.

### Sysroot for Cross-Compilation

Sysroot triplet (same as ZynqMP): `cortexa72-cortexa53-amd-linux`

```
SYSROOT = {COMMON_IMAGE_VERSAL}/sysroots/cortexa72-cortexa53-amd-linux
```

Cross-compiler environment setup script (sets CC, CXX, LD, CFLAGS, LDFLAGS):
```
{COMMON_IMAGE_VERSAL}/environment-setup-cortexa72-cortexa53-amd-linux
```

`cortexa72-cortexa53-xilinx-linux` is a symlink to `cortexa72-cortexa53-amd-linux` — both names resolve to the same sysroot.

## Platform Creation: platform_creation.py

Step 2 runs Vitis via a Python API script:

```bash
vitis -s platform_creation.py \
  --platform_name custom_platform \
  --xsa_path ../step1_vivado/build/vivado/custom_hardware_platform_hw.xsa \
  --xsa-emu_path ../step1_vivado/build/vivado/custom_hardware_platform_hwemu.xsa \
  --boot <COMMON_IMAGE_VERSAL> \
  --user_dtsi ./system-user.dtsi
```

### What platform_creation.py Does (2025.2)

1. Creates Vitis client and sets workspace to current directory
2. Creates platform component with:
   - Linux domain on `psv_cortexa72` processor
   - `enable_zocl_dt_overlay=True` — generates ZOCL device tree overlay node
   - `user_dtsi=system-user.dtsi` — applies board-level device tree customizations
3. Gets the platform component and retrieves the Linux domain
4. Adds **AIE domain** with `aie_runtime` OS — this is the key Versal-specific step absent from ZCU104
5. Renames the Linux domain from its default name to `xrt`
6. Calls `domain.generate_bif()` — creates Boot Image Format file for Versal boot
7. Sets boot directory to `COMMON_IMAGE_VERSAL` (contains bl31.elf, u-boot.elf, boot.scr)
8. Calls `platform.build()` — triggers full platform build including DTB auto-generation

### DTB Auto-Generation (2025.2)

In 2025.2, the Platform Wizard auto-generates the DTB from the XSA's embedded System Device Tree (SDT) combined with `system-user.dtsi`. There is no separate `createdts` invocation.

Generated DTB location after platform build:
```
step2_pfm/ws/custom_platform/hw/sdt/system.dtb
```

Do not attempt to generate the DTB separately with `xsct -eval "createdts ..."` for 2025.2 — that is the legacy flow used in 2024.1 and earlier.

### system-user.dtsi

The `system-user.dtsi` file customizes the device tree for VCK190 hardware:

```c
compatible = "xlnx,versal";
model = "Xilinx custom-vck190";
chosen {
    bootargs = "console=ttyAMA0 earlycon=pl011,mmio32,0xFF000000,115200n8 \
                clk_ignore_unused root=/dev/mmcblk0p2 rw rootwait cma=512M";
}
```

Key settings:
- Serial console: `ttyAMA0` at `0xFF000000` (pl011 UART)
- Root device: `/dev/mmcblk0p2` (SD card second partition)
- CMA: 512 MB for contiguous memory (required for DMA-capable PL kernels and AIE)
- Ethernet PHY: GEM0 in `rgmii-id` mode
- SD controller: sdhci1, 8-bit bus, eMMC capable
- I2C: 400 kHz clock

If boot fails with "VFS: Unable to mount root fs", check the `root=` argument and SD partition layout.

## AIE Domain

The AIE domain is a Versal-specific addition not present in ZCU104 platforms.

In `platform_creation.py`:
```python
platform.add_domain(name="aie_runtime", os="aie_runtime")
```

This domain enables:
- AIE graph compilation and linking against the platform
- AIE kernel execution at runtime via XRT
- AIE SystemC model inclusion in hw_emu

If the AIE domain is missing from the platform, `aiecompiler` will fail to find the platform's AIE architecture description, and `v++ --link` will not be able to include AIE kernels.

## Platform Output Structure

After a successful Step 2 build:

```
step2_pfm/ws/
└── custom_platform/
    ├── export/
    │   └── custom_platform/
    │       ├── custom_platform.xpfm     ← main platform file
    │       ├── hw/
    │       │   └── custom_hardware_platform_hw.xsa
    │       ├── hw_emu/
    │       │   └── custom_hardware_platform_hwemu.xsa
    │       └── sw/
    │           └── custom_platform/
    │               └── xrt/             ← Linux domain artifacts
    └── hw/
        └── sdt/
            └── system.dtb               ← auto-generated DTB
```

## Common Failure Modes

### COMMON_IMAGE_VERSAL Not Found

Error: `'COMMON_IMAGE_VERSAL' is not accessible`

Fix: ensure the path exists and contains `Image`:
```bash
ls $COMMON_IMAGE_VERSAL/Image
```
Pass it explicitly: `make all COMMON_IMAGE_VERSAL=/proj/rdi/xbuilds/released/2025.2/2025.2_released/internal_platforms/sw/versal/xilinx-versal-common-v2025.2/`

### AIE Domain Missing from platforminfo

If `platforminfo` shows no AIE domain:
- Check that `platform_creation.py` called `platform.add_domain(name="aie_runtime", os="aie_runtime")`
- Verify the hw XSA includes the AIE topology (Step 1 must have enabled AIE in the block design)

### DTB Generation Fails

If platform build errors with DTB or SDT related messages:
- Verify the XSA was exported correctly from Vivado (not corrupted)
- Verify `system-user.dtsi` is present in step2_pfm/ and has correct Versal compatible string
- Check that `enable_zocl_dt_overlay=True` is set in platform_creation.py

### xpfm in Wrong Location

Step 3 Makefiles may default to a PLATFORM path that does not include the `ws/` subdirectory. Always pass PLATFORM explicitly:
```
PLATFORM=step2_pfm/ws/custom_platform/export/custom_platform/custom_platform.xpfm
```

### Platform Build Succeeds but hw_emu Fails to Start

This is a `the cosim runtime references (`references/cosim/`)` concern, not a platform concern — hand off.
Check that `custom_hardware_platform_hwemu.xsa` was correctly passed as `--xsa-emu_path` during Step 2.
