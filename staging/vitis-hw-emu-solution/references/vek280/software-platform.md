<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Software Platform

## Scope

Load this file when the user is on the custom platform path (Path B): creating the Vitis platform from the VEK280 XSA, setting up the AIE-ML domain, or troubleshooting the platform build.

For the pre-built path (Path A), skip to `references/vek280/validation-and-iteration.md`.

## Goal of the Platform Step

Produce `ws/vek280_custom/export/vek280_custom/vek280_custom.xpfm` that the application build and hw_emu flow consume.

```bash
make pfm COMMON_IMAGE_VERSAL=$COMMON_IMAGE_VERSAL
# or as part of full flow:
make all COMMON_IMAGE_VERSAL=$COMMON_IMAGE_VERSAL
```

## Versal Common Image

Same image directory used by VCK190. Variable name: `COMMON_IMAGE_VERSAL`.

```
COMMON_IMAGE_VERSAL = /proj/rdi/xbuilds/released/{ver}/{ver}_released/internal_platforms/sw/versal/xilinx-versal-common-v{ver}/
```

Example (2025.2):
```
/proj/rdi/xbuilds/released/2025.2/2025.2_released/internal_platforms/sw/versal/xilinx-versal-common-v2025.2/
```

**Not set by settings64.sh — export manually.**

Required contents: `Image`, `rootfs.ext4`, `boot.scr`, `bl31.elf`, `u-boot.elf`, `sysroots/cortexa72-cortexa53-amd-linux/`

Sysroot path:
```
SYSROOT = {COMMON_IMAGE_VERSAL}/sysroots/cortexa72-cortexa53-amd-linux/
```

## platform_creation.py — VEK280 Specifics

The VEK280 `platform_creation.py` differs from VCK190 in several ways:

### Command Invocation

```bash
vitis -s platform_creation.py \
  --platform_name vek280_custom \
  --xsa_path build/vivado/vek280_custom.xsa \
  --boot $COMMON_IMAGE_VERSAL \
  --user_dtsi system-user.dtsi
```

**No `--xsa-emu_path` argument** — VEK280 uses a single XSA for both hw and hw_emu (unlike VCK190 which required separate hw + hwemu XSA files).

### Key API Differences vs VCK190

| Aspect | VEK280 | VCK190 |
|--------|--------|--------|
| XSA inputs | Single XSA | hw XSA + hwemu XSA |
| DTB generation | `generate_dtb=True` via advanced options | Platform Wizard auto-gen |
| ZOCL overlay | `dt_zocl="1"`, `dt_overlay="0"` | `enable_zocl_dt_overlay=True` |
| user_dtsi | Advanced options dict | Direct argument |
| Workspace path | `ws/` subdirectory | Current directory |
| AIE domain name | `ai_eingine` (note: typo in script) | `ai_eingine` (same typo) |

### What platform_creation.py Does (2025.2)

1. Creates Vitis client and sets workspace to `<cwd>/ws/`
2. Creates platform component with:
   - Linux domain on `psv_cortexa72`
   - Advanced options: `dt_zocl="1"`, `dt_overlay="0"`, `user_dtsi=<path>`
   - `generate_dtb=True` — DTB auto-generated from XSA SDT + user_dtsi
3. Adds **AIE-ML domain** (`ai_eingine` name, `aie_runtime` OS)
4. Renames Linux domain from `linux_psv_cortexa72` to `xrt`
5. Calls `domain.generate_bif()` — creates BIF for Versal boot
6. Sets boot directory to `COMMON_IMAGE_VERSAL`
7. Calls `platform.build()`

### system-user.dtsi (VEK280)

```
console=ttyAMA0 earlycon=pl011,mmio32,0xFF000000,115200n8
cma=512M
root=/dev/mmcblk0p2
```

Same structure as VCK190 — Versal UART console, 512MB CMA, SD card root. Compatible with Versal AI Edge.

## Platform Output Structure

After successful `make pfm`:

```
ws/
└── vek280_custom/
    ├── export/
    │   └── vek280_custom/
    │       ├── vek280_custom.xpfm     ← main platform file
    │       ├── hw/
    │       │   └── vek280_custom.xsa
    │       └── sw/
    │           └── vek280_custom/
    │               └── xrt/           ← Linux domain artifacts
    └── hw/
        └── sdt/
            └── system.dtb             ← auto-generated DTB
```

## Common Failure Modes

### COMMON_IMAGE_VERSAL Not Found

Same as VCK190. Verify:
```bash
ls $COMMON_IMAGE_VERSAL/Image
```

### Single XSA Only — No hwemu XSA

If you try to pass `--xsa-emu_path` to the VEK280 `platform_creation.py`, it will fail — the argument does not exist in this version. The single XSA handles both hw and hw_emu.

### Platform in ws/ Subdirectory

The VEK280 workspace is at `ws/` (not the current directory like VCK190). Confirm:
```bash
ls ws/vek280_custom/export/vek280_custom/vek280_custom.xpfm
```

If using the tutorial Makefile's PLATFORM default — it already points to `$(ROOT_DIR)/ws/$(PLATFORM_NAME)/...` so no override is needed for the custom path. Override only when using the pre-built platform.

### AIE-ML Domain Not Appearing in platforminfo

If `platforminfo` does not list the AIE domain:
- Verify the XSA includes the AIE-ML array (check run.tcl output for AIE inclusion)
- Check that `platform_creation.py` called `platform.add_domain(cpu="ai_engine", os="aie_runtime")`
- Re-run `make pfm` with a clean `ws/` directory
