<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Validation And Iteration

## Scope

Load this file when the user wants to prove the ZCU104 platform works, inspect metadata, or decide which tutorial stage must be rerun after a change.

## Goal Of Step 3

Validate that the generated platform can be consumed by an application flow.

Useful validation categories:
- inspect platform metadata
- build or run a simple application against the platform
- confirm the platform package exposes the expected hardware and software view

## Validation Tactics

### Platform Metadata

Use platform metadata inspection, such as `platforminfo`, to verify that the generated platform looks structurally correct before debugging applications.

The exact tutorial command is:

```bash
platforminfo ./zcu104_custom/export/zcu104_custom/zcu104_custom.xpfm
```

The tutorial’s expected `platforminfo` output confirms, among other things:
- generated version `2025.2`
- default clock index `2`
- clock frequencies `100`, `200`, and `400` MHz
- memory tags `HP0`, `HP1`, `HP2`, `HP3`, `HPC0`, `HPC1`
- default processor group `linux_psu_cortexa53`
- processor-group OS name `xrt`
- QEMU args path `qemu/pmu_args.txt:qemu/qemu_args.txt`

The published 2025.2 Step 3 example currently shows `Generated Version: 2024.2`.
Treat that as a tutorial inconsistency rather than the target version for this flow.

### Application Validation

Use a simple sample application first. The point is not workload realism; the point is proving the platform is consumable.

If a simple application fails, the problem is usually still in platform construction rather than in the application itself.

The tutorial uses the `Simple Vector Addition` example in the Vitis Unified IDE:

- system project name: `vadd`
- platform: `zcu104_custom`
- kernel image: `xilinx-zynqmp-common-v2025.2/Image`
- rootfs: `xilinx-zynqmp-common-v2025.2/rootfs.ext4`
- sysroot: `zcu104_software_platform/xilinx-zynqmp-common-v2025.2/sysroots/cortexa72-cortexa53-amd-linux`

After build, the tutorial expects:
- `sd_card.img` under `WorkSpace/vadd/build/<TARGET>/package/package/`
- for `hw_emu`, the emulator is started from the IDE with `Start Emulator`
- for board validation, the SD image comes from `vadd/build/hw/package/package/sd_card.img`

On-board, the tutorial’s command-line validation is:

```bash
cd /run/media/mmcblk0p1/
./simple_vadd krnl_vadd.xclbin
```

The expected success marker is:
- `TEST PASSED`

## Iteration Rules

After a change, rerun only the necessary stage:

- hardware design changed: regenerate the XSA, then rebuild the downstream platform layers
- software inputs changed: rebuild the software platform and validate again
- only the application changed: keep the platform fixed and rerun validation

This stage discipline prevents unnecessary rebuilds and keeps failures attributable.

Use the tutorial’s exact rebuild guidance:

- hardware updates:
  - re-export the XSA in Step 1
  - in Step 2, right-click the platform and choose `Update Hardware Specification`
  - select the updated XSA and rebuild the platform
  - clean and rebuild the application in Step 3
- software component updates:
  - copy the updated software component into the boot or SD directory
  - clean and rebuild the platform
  - clean and rebuild the application
- application updates:
  - host-only change: clean and rebuild the host, then copy the host ELF to the FAT partition
  - kernel-only change: clean kernel and hardware-link outputs, rebuild them, then copy the XCLBIN to the FAT partition

## Fast Track

The scripted Step 3 path is:

```bash
cd step3_validate
make all
make sd_card
make clean
```

The Step 3 Makefile’s key defaults are:
- `PLATFORM ?= ../step2_pfm/ws/zcu104_custom/export/zcu104_custom/zcu104_custom.xpfm`
- `TARGET ?= hw_emu`
- `SYSROOT := $(COMMON_IMAGE_ZYNQMP)/sysroots/cortexa72-cortexa53-amd-linux`

The Step 3 Makefile’s key build steps are:
- compile the kernel with `v++ -c` into `$(TEMP_DIR)/vadd.xo`
- link the kernel with `v++ -l` into `build_dir.<TARGET>/krnl_vadd.link.xclbin`
- build the host executable `simple_vadd`
  - native host compile for `sw_emu`
  - cross-compile with `aarch64-linux-gnu-g++` for `hw_emu` and `hw`
- generate emulation config with `emconfigutil`
- package the SD image contents with `v++ -p`
  - `rootfs.ext4`
  - `Image`
  - `run_app.sh`
  - `simple_vadd`
  - `emconfig.json`

The scripted run behavior is:
- `make run TARGET=hw_emu` launches `package.hw_emu/launch_hw_emu.sh -run-app run_app.sh`
- `make sd_card TARGET=hw` prepares the board-run package rather than executing it locally

When debugging scripted Step 3 failures, first classify which layer failed:
- host compile
- kernel compile or link
- packaging
- emulator launch via `launch_hw_emu.sh`

The tutorial notes a naming difference:
- IDE flow: `vadd` and `binary_container_1.xclbin`
- command-line flow: `simple_vadd` and `krnl_vadd.xclbin`

## Validation Record (2025.2)

**Tested:** 2026-04-13

```
Step 1 — XSA build       : PASS  (~2 min)
Step 2 — Platform build  : PASS  (~8 min, DTB auto-generated)
Step 3 — hw_emu run      : PASS  (TEST PASSED, QEMU + XSIM)
```

## Handoff To `the cosim runtime references (`references/cosim/`)`

Move to `the cosim runtime references (`references/cosim/`)` when:
- the platform validates but `hw_emu` fails
- QEMU launch or DTB behavior is the current issue
- the user is now debugging runtime interaction between PS software and PL logic

State this handoff explicitly so the user understands the platform is no longer the bottleneck.
