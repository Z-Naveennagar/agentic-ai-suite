<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Emulation and Run

## Scope

Load this file for the post-package EDF stages: assembling the QEMU image set (`qemu_combined`), the VEK280 BOOT.bin swap (`copy_bin`), injecting artifacts into the rootfs WIC (`insert_image` / `wic cp`), launching emulation (`launch_hw_emu.sh`), the in-guest run script (`run_app_hw_emu.sh`), and the physical-board run.

## Stage 6 — `qemu_combined` (assemble the image set)

Merge the pre-built EDF **disk image** and the pre-built **QEMU bundle** into one `edf_qemu_images/combined/` directory that holds the WIC, the QEMU boot config (`combined.qemuboot.conf`), and the bootloader binaries.

```make
qemu_combined:
	rm -rf edf_qemu_images && mkdir -p edf_qemu_images/combined
	# Prefer YOCTO_ARTIFACTS; fall back to YOCTO_QEMU_ARTIFACTS
	cp -prf ${YOCTO_ARTIFACTS}/${DISK_IMAGES}/* edf_qemu_images/combined/
	cp -prf ${YOCTO_ARTIFACTS}/${QEMU_IMAGES}/*  edf_qemu_images/combined/
```

- VEK385 keys off `*.bin` presence; VEK280 keys off `*.wic*` presence — but the intent is identical: get disk image + QEMU prebuilt into `combined/`.
- If `YOCTO_ARTIFACTS` does not contain them, the makefile falls back to `YOCTO_QEMU_ARTIFACTS` (intended for users who downloaded only the QEMU bundle).

## Stage 6b — `copy_bin`: swap BOOT.bin (all boards in 2026.1)

Each board ships a prebuilt `BOOT-versal-<board>-multidomain.bin` containing only the generic bootloader chain. To make the PLM boot the **design's** PDI, replace it with the `BOOT.bin` emitted by `v++ --package`:

```make
copy_bin:
	if [ -f package.hw_emu/BOOT.bin ]; then \
	  cp package.hw_emu/BOOT.bin edf_qemu_images/combined/BOOT-versal-<board>-multidomain.bin; \
	  ln -sf BOOT-versal-<board>-multidomain.bin edf_qemu_images/combined/boot.bin; \
	else \
	  echo "WARNING: BOOT.bin not found; keeping prebuilt (design PDI not boot-loaded)"; \
	fi
```

(The VEK385 board name token is `2ve-2vm-vek385`, i.e. `BOOT-versal-2ve-2vm-vek385-multidomain.bin`.)

**OSPI boards `dd` into the flash image — VEK385 and VRK160.** Both boot in **OSPI mode** (`mode=8` in `combined.qemuboot.conf`); the loader reads BOOT.bin from MTD offset 0 of `qemu-ospi.bin`, not from the loose `BOOT-...-multidomain.bin`. So they *both* swap the loose file *and* patch the OSPI flash image:

```make
cp $(VPP_BOOT_BIN) $(BOOT_BIN_BOARD)
dd if=$(BOOT_BIN_BOARD) of=$(QEMU_COMBINED)/$(COMBINED)/qemu-ospi.bin conv=notrunc
ln -sf BOOT-versal-<board>-multidomain.bin $(QEMU_COMBINED)/$(COMBINED)/boot.bin
```

VCK190 and VEK280 boot from SD, so they skip the `dd` and instead `wic cp` `boot.bin` into the rootfs WIC boot partition `:1` (see insert_image).

> If `BOOT.bin` is missing, this is the known **2026.1 lopper / `aie_*.dtb` regression** — `v++ --package` fails to emit `BOOT.bin`, so the design PDI is not loaded at boot. The build still completes with the prebuilt; see troubleshooting in `references/edf/validation-and-iteration.md`. The 2025.2 VEK385 `makefile_aie2ps` had no BOOT.bin swap at all — this step is new in the 2026.1 migration.

## Stage 7 — `insert_image` (`wic cp` into the rootfs WIC)

This is the EDF-defining step: rather than re-packaging a boot image, the design artifacts are copied **into a partition of the pre-built rootfs WIC** using the Yocto `wic` tool. `wic` must run with its own sourced environment.

**VEK385** (2026.1) — sector size **4096**, rootfs partition `:2`, `qemu_edf` env; no boot-partition copy (boot is via the OSPI `dd` in `copy_bin`):
```make
insert_image:
	bash -c '\
	unset LD_LIBRARY_PATH; \
	source $(XILINX_VITIS)/data/emulation/qemu/comp/qemu_edf/environment-setup-x86_64-amdedfsdk-linux; \
	wic cp --sector-size=4096 ./run_app_hw_emu.sh        ./edf_qemu_images/combined/$(WIC_PARTITION); \
	wic cp --sector-size=4096 ./application              ./edf_qemu_images/combined/$(WIC_PARTITION); \
	wic cp --sector-size=4096 ./gm2aie.xclbin            ./edf_qemu_images/combined/$(WIC_PARTITION); \
	wic cp --sector-size=4096 ./package.hw_emu/gm2aie.dtbo ./edf_qemu_images/combined/$(WIC_PARTITION); \
	wic cp --sector-size=4096 ./package.hw_emu/gm2aie.pdi  ./edf_qemu_images/combined/$(WIC_PARTITION); \
	wic cp --sector-size=4096 ./emconfig.json            ./edf_qemu_images/combined/$(WIC_PARTITION)'
# WIC_PARTITION = edf-platform-disk-image-amd-cortexa78-mali-common.rootfs.wic.ufs:2
# (2025.2 sourced the qemu/.../petalinux env, used …_edf-linux-disk-image…, and did not copy emconfig.json)
```

**VEK280** — sector size **512**, boot partition `:1` + rootfs partition `:2`, plus emconfig/zocl:
```make
insert_image:
	bash -c '\
	unset LD_LIBRARY_PATH; \
	source $(XILINX_VITIS)/data/emulation/qemu/comp/qemu_edf/environment-setup-x86_64-amdedfsdk-linux; \
	wic cp --sector-size=512 ./edf_qemu_images/combined/boot.bin ./.../$(WIC_BOOT_PARTITION); \
	wic cp --sector-size=512 ./run_app_hw_emu.sh ./.../$(WIC_PARTITION); \
	wic cp --sector-size=512 ./aieml_system      ./.../$(WIC_PARTITION); \
	wic cp --sector-size=512 ./krnl_aieml.xclbin ./.../$(WIC_PARTITION); \
	wic cp --sector-size=512 ./emconfig.json     ./.../$(WIC_PARTITION); \
	wic cp --sector-size=512 ./vek280.dtbo       ./.../$(WIC_PARTITION)'
# WIC_FILE = edf-platform-disk-image-amd-cortexa72-common.rootfs.wic.qemu-sd
# WIC_BOOT_PARTITION = $(WIC_FILE):1 ; WIC_PARTITION = $(WIC_FILE):2
```

**VCK190 and VRK160** follow the **same Cortex-A72 pattern as VEK280** (sector 512, `qemu_edf` env, boot partition `:1` + rootfs `:2`), with two differences in *what* is copied into the rootfs:
- **VCK190** copies `application`, `vck190.xclbin`, `emconfig.json`, and `vck190.dtbo` — **no PDI** (the design PDI is boot-loaded via the swapped BOOT.bin; `run_app_hw_emu.sh` only applies the overlay with `fpgautil -o`).
- **VRK160** copies `host.exe`, `gmio_async_xrt.xclbin`, `emconfig.json`, **and both `gmio_async_xrt.dtbo` + `gmio_async_xrt.pdi`** (emitted directly by `v++ -p`), because its `run_app_hw_emu.sh` runs `fpgautil -b …pdi -o …dtbo`.

Differences that matter (2026.1):
- **`wic` environment**: all four boards source `qemu/comp/qemu_edf` (`amdedfsdk`). (Only the 2025.2 VEK385 used the `qemu/comp/qemu` petalinux env.) Sourcing the wrong one ⇒ `wic: command not found` or sector-size errors.
- **sector size**: 4096 (VEK385) vs 512 (the Cortex-A72 boards) — must match the WIC's geometry.
- **boot delivery**: SD boards (VCK190, VEK280) `wic cp` `boot.bin` into partition `:1`; OSPI boards (VEK385, VRK160) instead `dd` the BOOT.bin into `qemu-ospi.bin` in `copy_bin` and do not write partition `:1`.
- **what else is copied**: all inject `emconfig.json`. VRK160 also injects its PDI (run script does `fpgautil -b`); VCK190 injects no PDI (boot-loaded) and applies overlay only.

## Stage 8 — `start_emu` (launch QEMU + XSIM)

`launch_hw_emu.sh` (generated by `v++ --package` into `package.hw_emu/`) starts QEMU (PMC + APU) and the RTL/AIE simulators, auto-logs in as `amd-edf`, and runs the in-guest script.

**VEK385** (2026.1 — now also passes `-aie-sim-options`; mounts `/dev/sda2`):
```make
start_emu:
	package.hw_emu/launch_hw_emu.sh \
	  -qemu-config edf_qemu_images/combined/combined.qemuboot.conf \
	  -login "amd-edf" -password "amd-edf" \
	  -aie-sim-options $(ROOT_DIR)/aiesim_options.txt \
	  -run-app "mount /dev/sda2 /media; cd /media; ./run_app_hw_emu.sh" | tee embedded_run.log
```

**VEK280** (adds AIE-ML sim options and a different mount device):
```make
start_emu:
	package.hw_emu/launch_hw_emu.sh \
	  -qemu-config edf_qemu_images/combined/combined.qemuboot.conf \
	  -login "amd-edf" -password "amd-edf" \
	  -aie-sim-options $(ROOT_DIR)/aiesim_options.txt \
	  -run-app "mount /dev/mmcblk0p2 /media; cd /media; ./run_app_hw_emu.sh" | tee embedded_run.log
```

VCK190 and VRK160 launch like VEK280 (mount `/dev/mmcblk0p2`, pass `-aie-sim-options`); VEK385 mounts `/dev/sda2`.

- Login is always `amd-edf` / `amd-edf` for EDF images.
- The rootfs WIC partition mounts from `/dev/sda2` (VEK385) or `/dev/mmcblk0p2` (Cortex-A72 boards: VEK280, VCK190, VRK160) — this matches the `wic cp` partition `:2`.
- `-aie-sim-options` hands the AIE SystemC simulator the absolute AIE workdir path. In **2026.1 all four boards pass it** (the 2025.2 VEK385 makefile omitted it).
- `| tee embedded_run.log; exit ${PIPESTATUS[0]}` preserves the emulation exit code.

## In-guest run script (`run_app_hw_emu.sh`)

Runs inside the emulated Linux after login. It applies the device-tree overlay (so zocl/the PL region binds), sets emulation mode, and runs the host app:

```bash
fpgautil -b gm2aie.pdi -o gm2aie.dtbo          # VEK385: load PDI + DTBO
export XCL_EMULATION_MODE=hw_emu
./application ./gm2aie.xclbin                    # VEK280: ./aieml_system ./krnl_aieml.xclbin
```

The `fpgautil` invocation differs per board — match the artifacts that were injected:

| Board | `run_app_hw_emu.sh` device-tree / PDI step | App launch |
|-------|--------------------------------------------|-----------|
| VEK385 | `fpgautil -b gm2aie.pdi -o gm2aie.dtbo` | `./application ./gm2aie.xclbin` |
| VEK280 | `fpgautil -b krnl_aieml.pdi -o vek280.dtbo` | `./aieml_system ./krnl_aieml.xclbin` |
| VCK190 | `fpgautil -o vck190.dtbo` (**overlay only** — PDI boot-loaded via BOOT.bin) | `./application ./vck190.xclbin` |
| VRK160 | `fpgautil -b gmio_async_xrt.pdi -o gmio_async_xrt.dtbo` | `./host.exe gmio_async_xrt.xclbin` |

All set `export XCL_EMULATION_MODE=hw_emu` before launching. Applying the zocl overlay is what registers the `zyxclmm_drm` device node; skipping it ⇒ XRT `No such device with index '0'`.

Expected success markers (from the tutorial):
```
... run s2mm ... graph end ... s2mm completed with status(4)
TEST PASSED
INFO: Embedded host run completed.
```

## Physical board run (`make sd_card`, TARGET=hw)

`make sd_card` builds the same kernels for `hw` and stages a `hw_run/` directory instead of injecting into the emulation WIC:

```make
run_hw:                       # VEK385
	make build && make package TARGET=hw && make host
	mkdir -p hw_run/
	cp package.hw/gm2aie.dtbo package.hw/gm2aie.pdi gm2aie.xclbin application embedded_exec.sh hw_run/
```

On the board:
1. Boot from **OSPI/QSPI** using the downloaded OSPI image (VEK385 SW1 = ON,ON,ON,OFF), with the EDF Linux disk image (`*.wic.xz`) written to an SD card as the secondary boot media.
2. Log in as `amd-edf` (first login forces a password change; that becomes the sudo password).
3. Copy `hw_run/` to the board (scp or SD), then run `embedded_exec.sh`, which does `fpgautil -b *.pdi -o *.dtbo` and `./application *.xclbin`.

When emulation **launches** but then hangs, disconnects, or the simulator misbehaves, the problem is no longer in this skill — hand off to `the cosim runtime references (`references/cosim/`)` (QEMU / remote-port / AIE SystemC).
