<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Validation and Iteration

## Scope

Load this file for EDF environment setup, artifact downloads, the `check-EDF-common-image` gate, the expected `TEST PASSED` output, troubleshooting, and how to iterate after a change.

## Toolchain

Source Vivado and Vitis (match the tutorial version, e.g. 2025.2):

```bash
source /proj/xbuilds/2025.2_released/installs/lin64/2025.2/Vivado/settings64.sh
source /proj/xbuilds/2025.2_released/installs/lin64/2025.2/Vitis/settings64.sh
```

## Environment Variables

EDF uses a **different** variable set than the PetaLinux platform skills. These are **not** set by `settings64.sh`:

| Variable | Value | Notes |
|----------|-------|-------|
| `PLATFORM_REPO_PATHS` | `<Vitis_tools>/base_platforms` | Where the pre-built base `.xpfm` lives (VEK385 README sets it here, **not** `internal_platforms`). |
| `YOCTO_ARTIFACTS` | `<path-to-design>/yocto_artifacts` | Holds the EDF SDK, disk image, and QEMU prebuilt. Create the dir and download into it. |
| `YOCTO_QEMU_ARTIFACTS` | (optional) | Fallback source for QEMU/disk images if not under `YOCTO_ARTIFACTS`. |
| `SYSROOT` | `${YOCTO_ARTIFACTS}/<edf-app-sdk>/sdk/sysroots/cortexa72-cortexa53-amd-linux/` | Set by sourcing the SDK `sdk.sh`; the makefile also derives it. |

> `COMMON_IMAGE_VERSAL` may be passed through by the top Makefile for compatibility, but the EDF flow's Linux stack comes from `YOCTO_ARTIFACTS`, not from a PetaLinux `COMMON_IMAGE_*`. Do not substitute one for the other.

## EDF Artifact Downloads

From the AMD **Embedded Design Tools / EDF downloads** page, for the board's package (VEK385 = package **25.11**), download into `${YOCTO_ARTIFACTS}/`:

1. **App SDK** — e.g. `amd-cortexa78-mali-common_meta-edf-app-sdk`. Run its self-extracting script and point the output at `${YOCTO_ARTIFACTS}/<sdk>/`, then source it:
   ```bash
   source ${YOCTO_ARTIFACTS}/amd-cortexa78-mali-common_meta-edf-app-sdk/sdk.sh -d ./yocto_artifacts/ -y
   ```
2. **OSPI image** — the board's QSPI/OSPI boot image (for physical-board boot).
3. **EDF disk image (WIC)** — `amd-cortexa78-mali-common_edf-platform-disk-image` (2025.2: `…_edf-linux-disk-image`); unzip — provides the `*.wic.ufs` for emulation and `*.wic.xz` for SD.
4. **QEMU prebuilt** — `amd-cortexa78-mali-common_vek385_qemu_prebuilt` (the QEMU boot config + bootloaders for emulation).

> The exact SDK name varies across the tutorial files (`amd-cortexa78-mali-common_meta-edf-app-sdk` in the README vs `amd-cortexa78-common_meta-edf-app-sdk` in `makefile_aie2ps`). Confirm the directory name that actually exists under `YOCTO_ARTIFACTS` and make `SYSROOT` / the SDK source path match it.

### Per-board artifact names

VEK385 (Gen2) uses the **Cortex-A78** EDF set; VCK190, VEK280, and VRK160 (Gen1) use the **Cortex-A72** EDF set. Only the SDK family and the per-board QEMU prebuilt change:

| Board | App SDK | Disk image / WIC | QEMU prebuilt |
|-------|---------|------------------|---------------|
| VEK385 | `amd-cortexa78(-mali)-common_meta-edf-app-sdk` | `amd-cortexa78-mali-common_edf-platform-disk-image` / `*.wic.ufs` | `amd-cortexa78-mali-common_vek385_qemu_prebuilt` |
| VCK190 | `amd-cortexa72-common_meta-edf-app-sdk` | `amd-cortexa72-common_edf-platform-disk-image` / `*.wic.qemu-sd` | `amd-cortexa72-common_vck190_qemu_prebuilt` |
| VEK280 | `amd-cortexa72-common_meta-edf-app-sdk` | `amd-cortexa72-common_edf-platform-disk-image` / `*.wic.qemu-sd` | `amd-cortexa72-common_vek280_qemu_prebuilt` |
| VRK160 | `amd-cortexa72-common_meta-edf-app-sdk` | `amd-cortexa72-common_edf-platform-disk-image` / `*.wic.qemu-sd` | `amd-cortexa72-common_vrk160_qemu_prebuilt` |

The Gen1 SDK can be sourced either via its `sdk.sh` installer or via the `environment-setup-cortexa72-cortexa53-amd-linux` script it installs. Match the EDF package to the Vitis version (VCK190/VRK160 tutorials target 2026.1; VEK385/VEK280 shipped at 2025.2 and refresh at 2026.1).

## `check-EDF-common-image` gate

Both `make all` and `make sd_card` first verify the EDF WIC exists:

```make
check-EDF-common-image:
	IMAGE1="$(YOCTO_ARTIFACTS)/$(QEMU_IMAGES)/edf-platform-disk-image-...rootfs.wic.ufs"   # 2026.1 (2025.2: edf-linux-disk-image-...)
	IMAGE2="$(YOCTO_QEMU_ARTIFACTS)/edf-platform-disk-image-...rootfs.wic.ufs"
	[ -f "$IMAGE1" ] || [ -f "$IMAGE2" ] || { echo "Error: EDF image not found"; exit 1; }
```

If this fails, the WIC was not downloaded or `YOCTO_ARTIFACTS` / `YOCTO_QEMU_ARTIFACTS` is wrong. (VEK385 checks `*.wic.ufs`; VEK280 checks `*.wic*`.)

## Run

```bash
# VEK385 (from Getting_Started/Vitis/Versal_w_EDF/VEK385)
export PLATFORM_REPO_PATHS=<Vitis_tools>/base_platforms
export YOCTO_ARTIFACTS=<path-to-design>/yocto_artifacts
source ${YOCTO_ARTIFACTS}/amd-cortexa78-mali-common_meta-edf-app-sdk/sdk.sh -d ./yocto_artifacts/ -y

make all        # TARGET=hw_emu : build → package → inject → QEMU+XSIM
# or
make sd_card    # TARGET=hw     : stage hw_run/ for the physical board
```

Useful sub-targets (inside the work dir, e.g. `aie2ps_work/`): `make build`, `make package TARGET=hw_emu`, `make host`, `make qemu_combined`, `make insert_image`, `make start_emu`. `make clean` / `make ultraclean` reset intermediate / all outputs.

## Expected Output

```
...
run s2mm
graph end
s2mm completed with status(4)
TEST PASSED
INFO: Embedded host run completed.
```

`TEST PASSED` is the success marker (`RESULT_STRING = TEST PASSED` for VEK280's matmul; the VEK385 GMIO sample prints the same).

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `check-EDF-common-image` fails | WIC not present | Download the EDF disk image; verify `YOCTO_ARTIFACTS`/`YOCTO_QEMU_ARTIFACTS`. |
| `PLATFORM ... not found` | `PLATFORM_REPO_PATHS` wrong | Point it at the Vitis install `base_platforms`; confirm `vek385_base_reva/` or `vek280_base/`. |
| host link fails / missing `xrt.h`, `adf_api` | sysroot not sourced or wrong path | Source the EDF `sdk.sh`; confirm `SYSROOT` dir exists; match the SDK directory name actually present. |
| `wic: command not found` / sector errors | wrong/absent wic env | VEK385: source `qemu/comp/qemu/...petalinux`; VEK280: source `qemu/comp/qemu_edf/...amdedfsdk`; use sector 4096 (VEK385) / 512 (VEK280). |
| XRT: `No such device with index '0'` | zocl overlay / emconfig not in WIC, or overlay not applied at runtime | Ensure `emconfig.json` + the `*.dtbo` are `wic cp`-d into partition `:2`, and that `run_app_hw_emu.sh` applies the overlay (`fpgautil -o` / `-b -o`). VEK385 designs load PDI+DTBO; VCK190 applies overlay-only. |
| `WARNING: BOOT.bin not found` (any board, 2026.1) | 2026.1 lopper / `aie_*.dtb` regression — `v++ --package` didn't emit BOOT.bin | Build completes with the prebuilt boot.bin but the design PDI is **not** boot-loaded; track the tool regression. Where the run script does `fpgautil -b` (VEK385, VEK280, VRK160), functional PDI load may still happen at runtime. |
| OSPI board boots but design PDI not active (VEK385, VRK160) | OSPI image not patched | `copy_bin` must `dd` the v++ `BOOT.bin` into `qemu-ospi.bin` (OSPI `mode=8`); a loose-file swap alone is not read by the OSPI loader. |
| emulation launches then hangs / disconnect | runtime / QEMU / remote-port / AIE SystemC | Out of EDF scope — hand off to `the cosim runtime references (`references/cosim/`)`. |
| user wants custom Vivado design / `.xpfm` | not the EDF flow | Route to `the per-platform references`. |

## Iteration

Regenerate only the layers a change touches:

- **AIE graph / kernel source changed** → rebuild the AIE archive + affected `.xo`, re-link XSA, re-package, re-inject (`make build && make package && make insert_image && make start_emu`).
- **Host source only** → `make host` then `make insert_image` + `make start_emu` (no kernel rebuild).
- **Matrix sizes (VEK280)** → pass `sizeM/sizeK/sizeN`, `subM/subK/subN`, `NIterations` on the make line; these flow to both AIE preproc (`--aie.Xpreproc`) and host (`-D…`), so the kernels and host must be rebuilt together.
- **Switching emulation ↔ board** → change `TARGET` (`make all` vs `make sd_card`); the package and delivery steps differ, so do a clean rebuild of the package stage.
- Use `make clean` between target switches to avoid stale `_x.*` / `package.*` artifacts.

## Validation Record (template)

Record what was actually tested so later runs can trust it:

```
Board / variant : VEK385 (cortexa78 / aie2ps)
Version         : 2025.2
Base platform   : vek385_base_reva.xpfm        : PASS/FAIL
check-EDF-image : PASS/FAIL
build+package   : gm2aie.xclbin/.pdi/.dtbo     : PASS/FAIL
hw_emu run      : TEST PASSED (QEMU + XSIM)     : PASS/FAIL
```
