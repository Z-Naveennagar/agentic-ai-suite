<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Vitis Cosim EDF hw_emu

## Overview

Use this skill for the **Embedded Development Framework (EDF)** hardware-emulation flow — the `Getting_Started/Vitis/Versal_w_EDF` tutorials. EDF is distinct from the platform-creation skills in two fundamental ways:

1. **Pre-built base platform** — the user does *not* build a Vivado design or a custom `.xpfm`. The flow links kernels onto an AMD-provided extensible base platform pulled from `PLATFORM_REPO_PATHS` (`vck190_base`, `vek280_base`, `vrk160_base`, `vek385_base_reva`).
2. **Pre-built Yocto EDF images** — instead of a PetaLinux `COMMON_IMAGE_*`, EDF uses downloaded Yocto artifacts in `YOCTO_ARTIFACTS`: an app SDK (sysroot), a disk-image WIC, and a QEMU prebuilt bundle. There is no PetaLinux build.

The end-to-end pipeline is a single `make all` (= `TARGET=hw_emu`):

```
aiecompiler (AIE graph) + v++ -c (PL kernel)
  → v++ -l  (fixed XSA on the base platform)
  → v++ -p  (xclbin + PDI + DTBO, --package.defer_aie_run)
  → cross-compile host app (aarch64)
  → qemu_combined (merge EDF disk image + QEMU prebuilt)
  → insert_image (wic cp app/xclbin/PDI/DTBO/run-script into the rootfs WIC)
  → launch_hw_emu.sh (QEMU + XSIM, login amd-edf, run_app_hw_emu.sh)
```

`make sd_card` (= `TARGET=hw`) produces the same artifacts in `hw_run/` for a physical board (OSPI boot + SD WIC) instead of injecting them into the emulation WIC.

Keep this skill focused on the EDF build/package/emulation pipeline. When the failure is *inside* `launch_hw_emu.sh`, QEMU (PMC/APU), remote-port, or AIE SystemC runtime, hand off to `the cosim runtime references (`references/cosim/`)`. When the user wants a **custom** Vivado design + custom platform (not the pre-built base), route to the relevant platform sub-agent (`the VEK280 references (`references/vek280/`)` is the closest analogue for Versal AI Edge).

In the agent hierarchy:
- `the cosim runtime references (`references/cosim/`)` is the top-level orchestrator (runtime / QEMU / cosim)
- `the EDF references (`references/edf/`)` owns the EDF turnkey hw_emu build-and-package flow
- `the per-platform references` own custom platform creation

## Workflow

1. Confirm the request is EDF, not PetaLinux/custom-platform. Tells:
   - `YOCTO_ARTIFACTS` set, `wic cp`, `.wic.ufs`/`.wic.qemu-sd`, login `amd-edf`
   - base platform from `PLATFORM_REPO_PATHS` (`vek385_base_reva`, `vek280_base`), not a `ws/*.xpfm`
   - tutorial path under `Getting_Started/Vitis/Versal_w_EDF/<BOARD>`
   - If it's a custom platform build → route to `the per-platform references`.
2. Identify the board and its EDF variant (see `references/edf/tutorial-overview.md`):
   (2026.1 is canonical; all four use the `qemu_edf` wic env, a BOOT.bin swap, and `-aie-sim-options`)
   - VEK385 → Versal AI Edge **Gen2**, cortexa78 SDK, **aie2ps**, 1 PL kernel, WIC `*.wic.ufs` partition `sda2`, sector 4096, **OSPI boot** → BOOT.bin swap **+ `dd` into `qemu-ospi.bin`**
   - VEK280 → Versal AI Edge (AIE-ML), cortexa72, **aieml**, 3 PL kernels, `*.wic.qemu-sd` partition `mmcblk0p2`, sector 512, SD boot → `boot.bin` into WIC partition `:1`
   - VCK190 → Versal **Gen1** AI Core, cortexa72, **aie** (matmul) + 2 HLS PL kernels, `mmcblk0p2`, sector 512, SD boot, run script applies overlay only (`fpgautil -o`)
   - VRK160 → Versal **RF Series**, cortexa72, **aie** (pure GMIO, **no PL kernel**), `mmcblk0p2`, sector 512, **OSPI boot** → BOOT.bin swap **+ `dd` into `qemu-ospi.bin`**
   - other EDF boards → use the generic adapt pattern
   (2025.2 VEK385 differed: `qemu` petalinux wic env, no BOOT swap, no emconfig/aiesim)
3. Verify prerequisites before building:
   - Vitis sourced; `PLATFORM_REPO_PATHS` points at the install `base_platforms`
   - `YOCTO_ARTIFACTS` populated (SDK, disk image, QEMU prebuilt); sysroot sourced via `sdk.sh`
   - `make check-EDF-common-image` passes (the `.wic.ufs`/`.wic.qemu-sd` exists)
4. Work the stage that is failing — load only the matching reference:
   - kernel compile / link / package → `references/edf/build-flow.md`
   - WIC injection / QEMU images / launch → `references/edf/emulation-and-run.md`
   - env, downloads, troubleshooting, iteration → `references/edf/validation-and-iteration.md`
5. Hand off to `the cosim runtime references (`references/cosim/`)` once the package is correct and the problem is in the emulator (QEMU boot, remote-port, AIE SystemC, `No such device`, hang).

When invoked as a sub-agent by `the cosim runtime references (`references/cosim/`)`:
- keep the answer scoped to the EDF build/package stage
- report the exact artifact (xclbin / PDI / DTBO / WIC) that unblocks emulation
- state explicitly when ownership should return to `the cosim runtime references (`references/cosim/`)`

## Fast Triage

- `make check-EDF-common-image` fails → the EDF WIC is missing from `YOCTO_ARTIFACTS`; re-download / re-point `YOCTO_ARTIFACTS` or `YOCTO_QEMU_ARTIFACTS`.
- `PLATFORM not found` → `PLATFORM_REPO_PATHS` must point at the Vitis install `base_platforms`; confirm `vek385_base_reva/` or `vek280_base/` exists there.
- host app link errors / missing XRT headers → sysroot not sourced; run the EDF `sdk.sh`, confirm `SYSROOT` resolves under `YOCTO_ARTIFACTS/.../sysroots/cortexa72-cortexa53-amd-linux/`.
- `wic cp` fails / "command not found" → the `wic` environment was not sourced (VEK385 uses the `qemu/comp/qemu` petalinux env; VEK280 uses `qemu_edf/...amdedfsdk` env). See `references/edf/emulation-and-run.md`.
- emulation boots but XRT sees no device / "No such device with index 0" → missing zocl DTBO and/or `emconfig.json` in the WIC (VEK280 path); regenerate `dtbo` + `emconfig`.
- `BOOT.bin not found` warning (VEK280) → known 2026.1 lopper/`aie_*.dtb` regression; design PDI not boot-loaded. See troubleshooting in `references/edf/validation-and-iteration.md`.
- emulation launches but hangs / QEMU or AIE SystemC misbehaves → hand off to `the cosim runtime references (`references/cosim/`)`.
- user wants a custom Vivado design or custom `.xpfm` → route to `the per-platform references`.

## Reference Selection

### `references/edf/tutorial-overview.md`
Load for what EDF is, the pre-built-platform + pre-built-image model, the per-board matrix (VCK190, VEK280, VRK160, VEK385, plus a generic adapt pattern for other boards), the two targets (`hw_emu` vs `hw`), the artifact chain, and boundaries with `the cosim runtime references (`references/cosim/`)` and the platform sub-agents.

### `references/edf/build-flow.md`
Load for the Makefile build stages: `aiecompiler` (AIE graph → `libsdf.a`/`libadf.a`), `v++ -c` (PL kernels), `v++ -l` (fixed XSA), `v++ -p` (xclbin/PDI/DTBO), and the aarch64 host cross-compile. Includes the VEK385 vs VEK280 per-stage differences.

### `references/edf/emulation-and-run.md`
Load for `qemu_combined`, `copy_bin` (VEK280 BOOT.bin swap), `insert_image` (`wic cp` targets + sector sizes + partitions), `launch_hw_emu.sh` arguments, `run_app_hw_emu.sh`, and the physical-board OSPI/SD run.

### `references/edf/validation-and-iteration.md`
Load for environment setup, EDF artifact downloads, `check-EDF-common-image`, the expected `TEST PASSED` output, troubleshooting (sysroot, wic env, zocl/emconfig, BOOT.bin regression), and how to iterate after a kernel or host change.

## Output Style

- Always name the board and its EDF variant the answer applies to (e.g. VEK385 cortexa78/aie2ps vs the cortexa72 boards VCK190/VEK280/VRK160, and aie2ps vs aieml vs aie/GMIO).
- Distinguish the **pre-built base platform** (EDF) from **custom platform creation** (platform sub-agents) — never tell an EDF user to run Vivado/`platform_creation.py` unless they explicitly want the custom path.
- Name the concrete artifact that should exist next (`gm2aie.xclbin`, `aieml.xsa`, `*.wic.ufs`, `package.hw_emu/launch_hw_emu.sh`, …).
- Distinguish `YOCTO_ARTIFACTS` (EDF Yocto images) from `COMMON_IMAGE_*` (PetaLinux) — they are not interchangeable.
- Explicitly say when the task has crossed into `the cosim runtime references (`references/cosim/`)` (emulator runtime) or a platform sub-agent (custom platform) territory.
