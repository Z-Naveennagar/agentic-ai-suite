<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Build Flow

## Scope

Load this file for the EDF kernel-build and packaging stages: AIE compile, PL kernel compile, link to fixed XSA, package to xclbin/PDI/DTBO, and host cross-compile. Primary board examples are VEK385 (`makefile_aie2ps`) and VEK280 (`makefile_aieml`); VCK190 (`makefile_vck190`) and VRK160 (`makefile_vrk160`) are called out where they differ. All four use the same dispatcher pattern: the top `Makefile` copies the inner `makefile_<board>` into `<board>_work/` and runs the build there with design sources referenced as `../<srcdir>/...`.

## Driver Makefile (top level)

The tutorial's top `Makefile` is a thin dispatcher. For VEK385 it:

1. runs `check-EDF-common-image`,
2. creates `aie2ps_work/`, copies `makefile_aie2ps` → `aie2ps_work/Makefile` and the run/exec script in,
3. invokes the inner make with `TARGET`, `PLATFORM`, `SYSROOT`:

```make
all:     check-EDF-common-image aie2ps_emu      # hw_emu
sd_card: check-EDF-common-image aie2ps_hw       # hw

aie2ps_emu:
	rm -rf aie2ps_work && mkdir aie2ps_work
	cp makefile_aie2ps aie2ps_work/Makefile
	cp ./run_app_hw_emu.sh aie2ps_work/
	$(MAKE) -C aie2ps_work all TARGET=hw_emu PLATFORM=$(PLATFORM) SYSROOT=$(SYSROOT)/
```

`PLATFORM` defaults to the **pre-built base platform**:

```make
PLATFORM := ${PLATFORM_REPO_PATHS}/vek385_base_reva/vek385_base_reva.xpfm   # VEK385
PLATFORM ?= ${PLATFORM_REPO_PATHS}/vek280_base/vek280_base.xpfm             # VEK280
```

## Stage 1 — AIE graph compile

The AIE graph is compiled with `aiecompiler` and emitted as an **output archive** (not a `.xo`), which the linker consumes directly.

**VEK385 (AIE2-PS):**
```make
GRAPH_XO := libsdf.a
$(GRAPH_XO): ../aie2ps/graph.cpp
	aiecompiler -include="${XILINX_VITIS_AIETOOLS}/include" -include="./" \
	  -workdir ./_aie --platform $(PLATFORM) \
	  --nodot-graph=true -log-level=5 -v \
	  -include="../aie2ps/" -include="../aie2ps/kernels" -include="./" \
	  --output-archive=$(GRAPH_XO) $<
```

**VEK280 (AIE-ML):**
```make
LIBADF = libadf$(OPT).a
AIE_CMPL_CMD := v++ --compile --mode aie --platform $(PLATFORM) --include "./src" --aie.workdir ./Work0 src/graph.cpp
$(LIBADF): src/*
	$(AIE_CMPL_CMD) --aie.log-level 5 --aie.Xpreproc "$(SIZES_D)" \
	  --aie.Xchess "..." --aie.output-archive $(LIBADF)
```

Key point: VEK385 invokes `aiecompiler` directly; VEK280 invokes the AIE compiler through `v++ --mode aie`. Both produce an archive (`libsdf.a` / `libadf.a`).

## Stage 2 — PL kernel compile (`v++ -c`)

**VEK385** — one kernel `s2mm`:
```make
$(S2MM_XO): ../aie2ps/s2mm.cpp
	v++ -t $(TARGET) --platform $(PLATFORM) -c -o $@ $< -k s2mm --config ../aie2ps/cfg/s2mm.cfg
```

**VEK280** — three kernels (data-mover MM2S + two S2MM):
```make
VPP_XO_FLAGS := -c -t $(TARGET) --platform $(PLATFORM) --save-temps -g
mm2s_8_128.xo:  src/mm2s_8_128.cpp ;  $(VPP) $(VPP_XO_FLAGS) -k mm2s_8_128 $< -o $@
s2mm_16_128.xo: src/s2mm_16_128.cpp ; $(VPP) $(VPP_XO_FLAGS) -k s2mm_16_128 $< -o $@
s2mm_32_128.xo: src/s2mm_32_128.cpp ; $(VPP) $(VPP_XO_FLAGS) -k s2mm_32_128 $< -o $@
```

**VCK190** — two HLS data movers (`mm2s`, `s2mm`):
```make
$(MM2S_XO): ../HLS_Kernels/mm2s.cpp ; v++ -t $(TARGET) --platform $(PLATFORM) -c -o $@ $< -k mm2s $(MM2S_FLAGS)
$(S2MM_XO): ../HLS_Kernels/s2mm.cpp ; v++ -t $(TARGET) --platform $(PLATFORM) -c -o $@ $< -k s2mm $(S2MM_FLAGS)
```

**VRK160** — **no PL kernel**. The design is a pure GMIO async-XRT AIE graph; Stage 2 is skipped and the AIE archive links straight into the XSA.

## Stage 3 — Link to fixed XSA (`v++ -l`)

Linking binds the AIE archive + PL `.xo`(s) onto the **extensible base platform**, producing the fixed XSA.

**VEK385:**
```make
LINK_OUT := $(FIXED_XSA_NAME)_$(TARGET).xsa     # e.g. *_hw_emu.xsa
$(LINK_OUT): $(GRAPH_XO) $(S2MM_XO)
	v++ -t $(TARGET) --platform $(PLATFORM) --temp_dir _x.$(TARGET) -l -o $@ $^ \
	  --config ../aie2ps/cfg/binary_container_1-link.cfg
```

**VEK280:**
```make
LINK_OUTPUT := aieml.xsa
$(LINK_OUTPUT): $(KERNEL_XO) $(LIBADF)
	v++ -l --platform $(PLATFORM) $(KERNEL_XO) $(LIBADF) -t $(TARGET) --save-temps -g \
	  --config system.cfg -o $(LINK_OUTPUT)
```

**VCK190** (`vck190_<target>.xsa`): links the AIE archive + 2 HLS `.xo` with `vitis_dir/system.cfg` connectivity.

**VRK160** (`sys_gmio_async_xrt.xsa`): links the AIE archive alone (no `.xo`) with GMIO configs:
```make
v++ -s --config ../aie/cfg/global.ini -t $(TARGET) -I . --config ../aie/cfg/package_link.ini \
  --platform $(PLATFORM) -l -o sys_gmio_async_xrt.xsa libadf.a \
  --config ../aie/cfg/gmio_async_xrt.xclbin_config.ini --config ../aie/cfg/system.cfg
```

## Stage 4 — Package (`v++ -p`)

Packaging emits the runtime artifacts. `--package.defer_aie_run` is used so the AIE graph is started by the host application (not auto-run at load).

**VEK385:**
```make
XCLBIN := gm2aie.xclbin
$(XCLBIN): $(LINK_OUT)
	v++ --package.defer_aie_run --config ../aie2ps/cfg/package.cfg \
	  --package.out_dir package.$(TARGET) -s -f $< $(GRAPH_XO) -t $(TARGET) -p -o $@
# → package.$(TARGET)/gm2aie.pdi, gm2aie.dtbo, gm2aie.xclbin
```

**VEK280:**
```make
XCLBIN := krnl_aieml.xclbin
$(XCLBIN): $(LIBADF) $(KERNEL_XO) $(EXECUTABLE)
	v++ -p -t $(TARGET) --save-temps --platform $(PLATFORM) \
	  --package.out_dir package.$(TARGET) --package.defer_aie_run \
	  $(LINK_OUTPUT) $(LIBADF) -o $(XCLBIN)
	$(MAKE) emconfig        # emconfig.json — XRT topology for hw_emu
	$(MAKE) dtbo            # vek280.dtbo — zocl overlay (zyxclmm_drm); else "No such device"
	$(MAKE) aiesim_options  # aiesim_options.txt → AIE_PKG_DIR = Work0
	$(MAKE) qemu_combined && $(MAKE) copy_bin && $(MAKE) insert_image && $(MAKE) start_emu
```

Packaging-time extra outputs:
- `emconfig.json` (`emconfigutil`) — XRT reads it in `XCL_EMULATION_MODE=hw_emu`. Generated by **all four boards in 2026.1** (added to VEK385 in the 2026.1 migration).
- `aiesim_options.txt` — points the AIE simulator at the AIE workdir; passed via `launch_hw_emu.sh -aie-sim-options`. Also **all four in 2026.1**.
- `<board>.dtbo` zocl overlay — **VEK280 and VCK190** compile a separate overlay (e.g. `vek280.dtbo` from `_x/package/updated_zocl.dtsi`); without it zocl never binds and XRT reports `No such device with index '0'`. VEK385's DTBO comes straight from `package.hw_emu/gm2aie.dtbo`, and VRK160's from `package.*/gmio_async_xrt.dtbo` (emitted directly by `v++ -p`).

## Stage 5 — Host application (aarch64 cross-compile)

Both boards cross-compile the host with the Vitis aarch64 GCC against the **EDF sysroot**.

```make
CXX := $(XILINX_VITIS)/gnu/aarch64/lin/aarch64-linux/bin/aarch64-linux-gnu-g++
GCC_FLAGS    := -Wall -c -std=c++17 -Wno-int-to-pointer-cast --sysroot=$(SYSROOT)
GCC_INCLUDES := -I$(SYSROOT)/usr/include/xrt -I$(SYSROOT)/usr/include \
                -I${XILINX_VITIS}/aietools/include -I${XILINX_VITIS}/include
GCC_LIB := -L$(SYSROOT)/usr/lib --sysroot=$(SYSROOT) \
           -L${XILINX_VITIS}/aietools/lib/aarch64.o \
           -ladf_api_xrt -lxrt_coreutil -lpthread -lrt -ldl -luuid
```

- VEK385 also compiles `_aie/ps/c_rts/aie_control_xrt.cpp` (the AIE control object) alongside `host.cpp`.
- `SYSROOT` resolves to `${YOCTO_ARTIFACTS}/<edf-app-sdk>/sdk/sysroots/cortexa72-cortexa53-amd-linux/`. The triple is the SDK machine name and is `cortexa72-cortexa53` even on the Cortex-A78 VEK385 SDK — do not "fix" it.
- `sw_emu` (optional) builds the host for X86 (`g++`) instead; `hw`/`hw_emu` require the aarch64 toolchain (QEMU PS).

## Per-board summary

| Stage | VEK385 (aie2ps) | VEK280 (aieml) | VCK190 (aie) | VRK160 (aie/GMIO) |
|-------|-----------------|----------------|--------------|-------------------|
| AIE compile | `aiecompiler … --output-archive=libsdf.a` | `v++ --mode aie … --aie.output-archive libadf.a` | `aiecompiler … --output-archive=libadf.a` | `aiecompiler … --output-archive=libadf.a` |
| PL kernels | 1 (`s2mm.xo`) | 3 (`mm2s_8_128`, `s2mm_16_128`, `s2mm_32_128`) | 2 (`mm2s.xo`, `s2mm.xo`) | **0** (pure GMIO) |
| Link XSA | `*_hw_emu.xsa` | `aieml.xsa` | `vck190_<target>.xsa` | `sys_gmio_async_xrt.xsa` |
| xclbin | `gm2aie.xclbin` (+ pdi, dtbo, emconfig, aiesim_options) | `krnl_aieml.xclbin` (+ emconfig, zocl dtbo, aiesim_options) | `vck190.xclbin` (+ emconfig, `vck190.dtbo`, aiesim_options) | `gmio_async_xrt.xclbin` (+ emconfig, pkg `*.dtbo`/`*.pdi`, aiesim_options) |
| Host | `application` (host.cpp + `aie_control_xrt.cpp`) | `aieml_system` (host.cpp) | `application` (host.cpp + `aie_control_xrt.cpp`) | `host.exe` (host.cpp) |

After packaging, continue in `references/edf/emulation-and-run.md` for image assembly and launch.
