<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Tutorial Overview

## Scope

Load this file for the high-level EDF flow, the per-board matrix, the two build targets, the artifact chain, and the boundaries between this skill, `the cosim runtime references (`references/cosim/`)`, and the platform sub-agents.

## What is EDF

The **Embedded Development Framework (EDF)** is the AMD methodology for Versal Gen2 bring-up using **pre-built Yocto images** and **pre-built extensible base platforms**. The Getting Started EDF tutorials (`Getting_Started/Vitis/Versal_w_EDF/`) show the turnkey flow that:

1. links the user's AIE graph + PL kernel onto an AMD-provided **extensible base platform** (the "base part" provides PS + PS-to-NoC-DDR; the "extensible part" exposes PL + AIE regions),
2. produces a **fixed XSA**, then an **xclbin + PDI + DTBO**,
3. **injects** those artifacts into a pre-built EDF Linux rootfs **WIC image** with `wic cp`, and
4. boots the WIC under **QEMU + XSIM** via `launch_hw_emu.sh` (for `hw_emu`) — or copies them to an SD card for a physical board (for `hw`).

Reference: AMD EDF wiki — *AMD Embedded Development Framework (EDF)* and *AMD EDF Getting started — Discovery and Evaluation*.

### EDF vs the platform-creation skills

| | EDF (`the EDF references (`references/edf/`)`) | Platform sub-agents (`the per-platform references`) |
|--|------------------------------|------------------------------------------------------|
| Platform | **Pre-built** base `.xpfm` from `PLATFORM_REPO_PATHS` | Built from a Vivado design via `platform_creation.py` |
| Vivado design | none (uses base part) | user-authored `run.tcl` |
| Linux stack | **pre-built Yocto EDF images** in `YOCTO_ARTIFACTS` | PetaLinux `COMMON_IMAGE_*` |
| Image delivery | `wic cp` into a rootfs WIC | `v++ --package` sd_card / `--package.image_format` |
| Login | `amd-edf` / `amd-edf` | `root` / `petalinux` (or board default) |

> If the user wants to own the hardware design or build a custom `.xpfm`, that is **not** the EDF flow — route to the relevant platform sub-agent. `the VEK280 references (`references/vek280/`)` is the closest analogue for Versal AI Edge.

## Two Build Targets

| Target | Make command | Output | Purpose |
|--------|--------------|--------|---------|
| `hw_emu` | `make all` | injects artifacts into the EDF WIC and launches QEMU+XSIM | hardware emulation |
| `hw` | `make sd_card` | `hw_run/` with PDI + xclbin + DTBO + app + `embedded_exec.sh` | physical board (OSPI boot + SD WIC) |

Both first run `check-EDF-common-image` to confirm the pre-built EDF WIC is present.

## Board Matrix

EDF spans Versal **Gen1** (VCK190 AI Core, VEK280 AI Edge, VRK160 RF Series) and **Gen2** (VEK385 AI Edge). This skill documents the **2026.1** EDF flow as canonical. In 2026.1 all four boards share the same shape — `qemu_edf` (`amdedfsdk`) wic environment, a BOOT.bin swap, `emconfig.json` + `aiesim_options.txt` generation, and `launch_hw_emu.sh -aie-sim-options`. The Gen1 boards additionally share the Cortex-A72 EDF SDK, the `*.wic.qemu-sd` rootfs, `/dev/mmcblk0p2`, and sector size 512.

> The 2025.2 VEK385 `makefile_aie2ps` was simpler — it used the `qemu/comp/qemu` (petalinux) wic env, had no BOOT.bin swap, and no emconfig/aiesim steps. If you are on 2025.2, expect those to be absent; everything below reflects 2026.1.

### Quick comparison (2026.1)

| | VCK190 | VEK280 | VRK160 | VEK385 |
|--|--------|--------|--------|--------|
| SoC | Versal Gen1 AI Core | Versal AI Edge (AIE-ML) | Versal RF Series | Versal AI Edge **Gen2** |
| Base platform | `vck190_base` | `vek280_base` | `vrk160_base` | `vek385_base_reva` |
| EDF SDK | `amd-cortexa72-common` | `amd-cortexa72-common` | `amd-cortexa72-common` | `amd-cortexa78(-mali)-common` |
| AIE | `aie` (matmul) | `aieml` (matmul) | `aie` (**pure GMIO**) | `aie2ps` |
| PL kernels | 2 (mm2s, s2mm) | 3 (mm2s, s2mm×2) | **0** | 1 (s2mm) |
| AIE archive | `libadf.a` | `libadf.a` | `libadf.a` | `libsdf.a` |
| xclbin / host | `vck190.xclbin` / `application` | `krnl_aieml.xclbin` / `aieml_system` | `gmio_async_xrt.xclbin` / `host.exe` | `gm2aie.xclbin` / `application` |
| WIC / mount | `*.wic.qemu-sd` / `mmcblk0p2` | `*.wic.qemu-sd` / `mmcblk0p2` | `*.wic.qemu-sd` / `mmcblk0p2` | `*.wic.ufs` / `sda2` |
| sector size | 512 | 512 | 512 | 4096 |
| wic env | `qemu_edf` | `qemu_edf` | `qemu_edf` | `qemu_edf` (2025.2: `qemu`) |
| BOOT.bin into rootfs | boot part `:1` (wic cp) | boot part `:1` (wic cp) | `:1` **+ `dd` into `qemu-ospi.bin`** | **`dd` into `qemu-ospi.bin`** (OSPI) |
| Boot mode | SD | SD | **OSPI** (`mode=8`) | **OSPI** (`mode=8`) |
| Work dir | `vck190_work/` | `aieml_work/` | `vrk160_work/` | `aie2ps_work/` |
| Branch | `2026.1_next` | `2026.1_next` | `2026.1_VRK160_tutorial` | `2026.1_VEK385_migration` |

### VEK385 — Versal AI Edge Gen2 (verified; 2026.1 on branch `2026.1_VEK385_migration`)

| Property | Value |
|----------|-------|
| Tutorial | `Getting_Started/Vitis/Versal_w_EDF/VEK385` |
| Base platform | `${PLATFORM_REPO_PATHS}/vek385_base_reva/vek385_base_reva.xpfm` |
| Linux CPU | Cortex-A78 (`linux_cortexa78`) |
| AI Engine | **AIE2-PS** (`aie2ps`), compiled with `aiecompiler` → `libsdf.a` |
| App sample | GMIO → AIE → S2MM (`gm2aie`); 1 PL kernel `s2mm` |
| xclbin / artifacts | `gm2aie.xclbin`, `gm2aie.pdi`, `gm2aie.dtbo` (+ `emconfig.json`, `aiesim_options.txt`) |
| Host exe | `application` (host.cpp + `aie_control_xrt.cpp`) |
| EDF disk image | `amd-cortexa78-mali-common_edf-platform-disk-image` (2025.2: `…_edf-linux-disk-image`) |
| EDF WIC | `edf-platform-disk-image-amd-cortexa78-mali-common.rootfs.wic.ufs` |
| WIC rootfs partition | `:2` → mounted from `/dev/sda2` |
| `wic cp` sector size | `4096` |
| QEMU prebuilt | `amd-cortexa78-mali-common_vek385_qemu_prebuilt` |
| `wic` env to source | `$XILINX_VITIS/data/emulation/qemu/comp/qemu_edf/environment-setup-x86_64-amdedfsdk-linux` (2025.2 used the `qemu/.../petalinux` env) |
| BOOT.bin | swapped (`BOOT-versal-2ve-2vm-vek385-multidomain.bin`) **and `dd`-ed into `qemu-ospi.bin`** — VEK385 boots in **OSPI mode** (`mode=8`) |
| `-aie-sim-options` | yes (points the AIE simulator at the `_aie` workdir) |
| Board boot | OSPI/QSPI (SW1 = ON,ON,ON,OFF), then SD WIC |
| SDK source dir | makefile uses `amd-cortexa78-common_meta-edf-app-sdk`; README download is `amd-cortexa78-mali-common_meta-edf-app-sdk` — confirm the dir that exists |

Work directory: the top `Makefile` copies `makefile_aie2ps` into `aie2ps_work/` and drives the build there.

### VEK280 — Versal AI Edge / AIE-ML (verified from `VEK280/aieml_work`)

| Property | Value |
|----------|-------|
| Tutorial | `Getting_Started/Vitis/Versal_w_EDF/VEK280` |
| Base platform | `${PLATFORM_REPO_PATHS}/vek280_base/vek280_base.xpfm` |
| Linux CPU | Cortex-A72 (`cortexa72-cortexa53`) |
| AI Engine | **AIE-ML** (`aieml`), `v++ --compile --mode aie` → `libadf.a`; matrix-multiply sample |
| PL kernels | `mm2s_8_128.xo`, `s2mm_16_128.xo`, `s2mm_32_128.xo` |
| Link output | `aieml.xsa`; xclbin `krnl_aieml.xclbin` |
| Extra artifacts | `emconfig.json`, zocl overlay `vek280.dtbo`, `aiesim_options.txt` |
| EDF disk image | `amd-cortexa72-common_edf-platform-disk-image` |
| EDF WIC | `edf-platform-disk-image-amd-cortexa72-common.rootfs.wic.qemu-sd` |
| WIC partitions | boot `:1`, rootfs `:2` → mounted from `/dev/mmcblk0p2` |
| `wic cp` sector size | `512` |
| QEMU prebuilt | `amd-cortexa72-common_vek280_qemu_prebuilt` |
| `wic` env to source | `$XILINX_VITIS/data/emulation/qemu/comp/qemu_edf/environment-setup-x86_64-amdedfsdk-linux` |
| BOOT.bin | swapped: prebuilt `BOOT-versal-vek280-multidomain.bin` replaced by v++ `BOOT.bin` (`copy_bin`) |

The VEK280 EDF makefile additionally generates `emconfig.json` and a zocl device-tree overlay — both are required for XRT to find the device in emulation (see `references/edf/emulation-and-run.md`).

### VCK190 — Versal Gen1 AI Core (verified, 2026.1 / branch `2026.1_next`)

| Property | Value |
|----------|-------|
| Tutorial | `Getting_Started/Vitis/Versal_w_EDF/VCK190` |
| Base platform | `${PLATFORM_REPO_PATHS}/vck190_base/vck190_base.xpfm` |
| Linux CPU | Cortex-A72 (`amd-cortexa72-common` SDK) |
| AI Engine | **AIE** (`aiecompiler` → `libadf.a`); matrix-multiply graph |
| PL kernels | 2 HLS data movers — `mm2s.xo`, `s2mm.xo` (`v++ -c`) |
| Link output / xclbin | `vck190_<target>.xsa` / `vck190.xclbin` |
| Host exe | `application` (host.cpp + `aie_control_xrt.cpp`) |
| Extra artifacts | `emconfig.json`, zocl overlay `vck190.dtbo`, `aiesim_options.txt` |
| Connectivity | `vitis_dir/system.cfg` wires `mm2s_1/mm2s_2 → ai_engine_0.DataIn{1,2}`, `ai_engine_0.DataOut1 → s2mm` |
| EDF disk image / WIC | `amd-cortexa72-common_edf-platform-disk-image` / `*.wic.qemu-sd` (`mmcblk0p2`, sector 512) |
| QEMU prebuilt | `amd-cortexa72-common_vck190_qemu_prebuilt` |
| BOOT.bin | swapped (`BOOT-versal-vck190-multidomain.bin`) |
| Runtime DT | `run_app_hw_emu.sh` applies the overlay with `fpgautil -o vck190.dtbo` (PDI is boot-loaded via the swapped BOOT.bin — no `-b` PDI at runtime) |

> Note: VCK190 **DFX is not supported in the EDF flow** (2026.1). For DFX use the legacy `Versal_w_PetaLinux/VCK190_dfx` tutorial.

### VRK160 — Versal RF Series (verified, 2026.1 / branch `2026.1_VRK160_tutorial`)

| Property | Value |
|----------|-------|
| Tutorial | `Getting_Started/Vitis/Versal_w_EDF/VRK160` |
| Base platform | `${PLATFORM_REPO_PATHS}/vrk160_base/vrk160_base.xpfm` |
| Linux CPU | Cortex-A72 (`amd-cortexa72-common` SDK) |
| AI Engine | **AIE** (`aiecompiler` → `libadf.a`); **pure GMIO async-XRT graph — no PL kernel** |
| PL kernels | **none** — the AIE archive links directly into the fixed XSA |
| Link output / xclbin | `sys_gmio_async_xrt.xsa` / `gmio_async_xrt.xclbin` |
| Host exe | `host.exe` |
| Extra artifacts | `emconfig.json`, `aiesim_options.txt`; `v++ -p` emits `gmio_async_xrt.dtbo` + `gmio_async_xrt.pdi` directly |
| EDF disk image / WIC | `amd-cortexa72-common_edf-platform-disk-image` / `*.wic.qemu-sd` (`mmcblk0p2`, sector 512) |
| QEMU prebuilt | `amd-cortexa72-common_vrk160_qemu_prebuilt` |
| BOOT.bin | swapped (`BOOT-versal-vrk160-multidomain.bin`) **and `dd`-ed into `qemu-ospi.bin`** because VRK160 boots in OSPI mode (`mode=8`); the OSPI loader reads BOOT.bin from MTD offset 0 |
| Runtime DT | `run_app_hw_emu.sh` does `fpgautil -b gmio_async_xrt.pdi -o gmio_async_xrt.dtbo` |

### Other EDF boards — generic adapt pattern

> For an EDF board not listed above, the flow is identical; adapt the per-board values and **confirm the concrete names against that board's tutorial.**

Change only these per-board values (everything else in the flow is identical):

| Variable | What it selects | Confirm from |
|----------|-----------------|--------------|
| `PLATFORM` | `${PLATFORM_REPO_PATHS}/<board>_base*/...xpfm` | the board's base platform under the Vitis install `base_platforms` |
| `SYSROOT` | `${YOCTO_ARTIFACTS}/<sdk-name>/sdk/sysroots/<arch-triple>/` | the EDF app-SDK `sdk.sh` for that board |
| AIE toolchain | `aie2ps` (Gen2) vs `aieml` | the board's AI Engine generation |
| `DISK_IMAGES` / WIC name | `<...>_edf-*-disk-image` + `*.wic.*` | the EDF disk-image download |
| `QEMU_IMAGES` | `<...>_<board>_qemu_prebuilt` | the EDF QEMU prebuilt download |
| `WIC_PARTITION` / mount dev | `sda2` vs `mmcblk0p2`, sector `4096` vs `512` | the board's WIC layout |
| `wic` env | `qemu/comp/qemu` vs `qemu/comp/qemu_edf` | the EDF QEMU env shipped with Vitis |

Do not invent these names — read them from the target board's `Makefile`/`makefile_aie*` and EDF download set.

## Artifact Chain (hw_emu)

```
user AIE graph (graph.cpp)          ─ aiecompiler ─┐
user PL kernel(s) (s2mm.cpp / mm2s) ─ v++ -c ──────┤
                                                   ├─ v++ -l ─→ <name>_hw_emu.xsa  (on base platform)
                                                   └─ v++ -p ─→ xclbin + PDI + DTBO (+ emconfig/zocl for VEK280)
host.cpp ─ aarch64 g++ (sysroot) ─→ application
EDF disk image + QEMU prebuilt ─ qemu_combined ─→ edf_qemu_images/combined/
  └─ insert_image (wic cp app/xclbin/PDI/DTBO/run-script into rootfs WIC)
       └─ launch_hw_emu.sh -login amd-edf -run-app "mount … /media; ./run_app_hw_emu.sh"  → TEST PASSED
```

## Boundaries

Stay in this skill when the user is:
- compiling AIE/PL kernels, linking the fixed XSA, or packaging xclbin/PDI/DTBO on a **pre-built base platform**
- assembling EDF Yocto images (`qemu_combined`) or injecting artifacts (`insert_image` / `wic cp`)
- setting up `YOCTO_ARTIFACTS`, the EDF SDK sysroot, or `PLATFORM_REPO_PATHS`
- running `make all`/`make sd_card` and reading the EDF build log

Switch to `the cosim runtime references (`references/cosim/`)` when the user is:
- debugging `launch_hw_emu.sh` startup, QEMU PMC/APU, remote-port, or AIE SystemC
- analyzing runtime PS/PL/AIE behavior or hangs inside emulation

Route to `the per-platform references` when the user wants a **custom** Vivado design and custom `.xpfm` instead of the pre-built EDF base platform.
