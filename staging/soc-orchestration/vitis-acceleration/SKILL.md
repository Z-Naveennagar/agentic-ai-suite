---
name: soc-orchestration/vitis-acceleration
description: Integrate acceleration kernels (DPUCVDX8G, HLS, AIE graphs) into a Vitis extensible platform using v++ compile/link/package. Covers DPU configuration, AIE graph compilation, xclbin generation, arch.json extraction, and system packaging.
metadata:
  category: amd-soc-design
  tier: domain
  tags:
    - vitis-acceleration
    - v++
    - dpu
    - dpucvdx8g
    - aie
    - xclbin
    - versal
    - kernel-integration
  complexity: advanced
  estimated_duration: 30-120 minutes
  prerequisites_skills:
    - soc-orchestration
    - soc-orchestration/vitis-platform
  related_skills:
    - soc-orchestration/ps-software
    - soc-orchestration/partitioning
    - soc-orchestration/estimation
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# SKILL: Vitis Acceleration Kernel Integration (v++ Flow)

## Overview

This sub-skill integrates acceleration kernels — DPUCVDX8G (AI Engine DPU), HLS
kernels, or custom AIE graphs — into a Vitis extensible platform using the v++ CLI.
It produces an xclbin (device binary) and optionally a PDI (Programmable Device Image)
for Versal targets.

**When to use this skill:**
- The partition plan includes AIE, DPU, or HLS-kernel blocks
- An extensible XSA exists (from `vitis-platform/SKILL.md`)
- You need to compile kernels, link them to the platform, and generate deployment artifacts

**This skill does NOT cover:**
- Creating the extensible platform XSA → use `vitis-platform/SKILL.md`
- Model quantization/compilation for DPU → that is a Vitis AI workflow (Phase 3)
- PS firmware for traditional embedded → use `ps-software/SKILL.md`

## Prerequisites

- **Extensible platform XSA** from `vitis-platform/` skill
- **v++** at `/scratch/AMDDesignTools/2025.2/Vitis/bin/v++`
- **aiecompiler** at `/scratch/AMDDesignTools/2025.2/Vitis/aietools/bin/aiecompiler`
- **Shell access** for v++ invocations
- **Kernel source/IP** — DPU from Vitis-AI repo, HLS from user source, AIE from graph source

### Environment Setup

```bash
source /scratch/AMDDesignTools/2025.2/Vitis/settings64.sh
export XILINX_VITIS_DATA_DIR=/scratch/nshirazi_vitis_data
export PLATFORM_REPO_PATHS=/scratch/nshirazi_vitis_builds/platforms
```

## DPU IP Selection Guide

| Device Family         | DPU IP          | PG Doc | AI Engine Type | Notes                           |
|----------------------|-----------------|--------|----------------|---------------------------------|
| Versal AI Core       | DPUCVDX8G       | PG389  | AI Engine      | VCK190, VMK180                  |
| Versal AI Edge       | DPUCV2DX8G      | PG425  | AI Engine-ML   | VEK280, VEK385                  |
| Zynq UltraScale+     | DPUCZDX8G       | PG338  | N/A (PL only)  | KV260, ZCU104, ZCU102           |
| Versal Premium       | DPUCVDX8G       | PG389  | AI Engine      | VP1902 (same arch as AI Core)   |

**Matching DPU to device is critical.** Using the wrong DPU IP causes AIE compiler
failures or synthesis errors.

## Step 0 — Combined Resource Check (MANDATORY)

Before building ANY DPU overlay, run the combined resource estimation from
`estimation/SKILL.md` Phase T0 to verify the DPU arch + custom PL blocks fit
the target device. This is especially critical for Zynq UltraScale+ devices
(KV260, ZCU104) where URAM is scarce.

If the design has a custom PL pipeline (video, sensors, peripherals) that will
share the device with the DPU, you MUST:
1. Look up DPU resources from the tables in `estimation/SKILL.md`
2. Sum with custom PL block estimates
3. Verify total < 85% of device resources (especially URAM, BRAM)
4. If overflow: reduce DPU arch before proceeding

**Do NOT build first and discover the overflow after a multi-hour v++ run.**

## Step 1 — Obtain DPU Kernel IP

### DPUCZDX8G (Zynq UltraScale+ — KV260, ZCU104)

The DPUCZDX8G is a PL-only DPU (no AIE). Obtain the kernel from the DPU TRD:

```bash
# Download the DPUCZDX8G TRD archive
cd /scratch/nshirazi_vitis_builds
# Source: https://docs.amd.com/r/en-US/pg338-dpu → Design Files
# File: DPUCZDX8G.tar.gz

tar xzf DPUCZDX8G.tar.gz
ls DPUCZDX8G/
# Contains: dpu_ip/ (encrypted IP cores), prj/Vitis/scripts/, prj/Vitis/dpu_conf.vh
```

#### DPU Kernel Generation (CRITICAL — read carefully)

The DPU RTL is **encrypted** (`.vp` files). The architecture configuration in
`dpu_conf.vh` is interpreted at IP packaging time by the TRD's Tcl scripts, NOT at
synthesis time. This has critical implications:

1. **You cannot swap `dpu_conf.vh` into a pre-built XO and expect a different arch.**
   The encrypted RTL modules are parameterized during IP creation. A B4096 XO contains
   B4096-specific encrypted netlists that ignore a B512 `dpu_conf.vh` dropped in later.

2. **You must generate the XO from scratch for each architecture** using the full TRD
   flow. The TRD's `package_dpu_kernel.tcl` reads `dpu_conf.vh` from the current
   working directory, creates a Vivado project, packages the IP, and produces the XO.

3. **IP caching can silently reuse stale architectures.** Always delete `.ipcache` and
   bump the IP version in `component.xml` when regenerating with a different arch.

#### Correct XO generation procedure:

```tcl
# Step 1: Edit dpu_conf.vh IN THE TRD to set the desired architecture
# File: <TRD_ROOT>/prj/Vitis/dpu_conf.vh
# Change `define B4096 to `define B512 (or whichever arch)
# Ensure `define URAM_ENABLE or URAM_DISABLE as needed
# Ensure `define MPSOC is present (for Zynq UltraScale+)

# Step 2: Set the TRD_PATH environment variable
set ::env(TRD_PATH) <TRD_ROOT>

# Step 3: cd to the dpu_conf.vh directory (package_dpu_kernel.tcl reads from CWD)
cd <TRD_ROOT>/prj/Vitis

# Step 4: Source the packaging script with correct arguments
set ::argv [list <output.xo> DPUCZDX8G hw <device_part>]
set ::argc 4
source <TRD_ROOT>/prj/Vitis/scripts/package_dpu_kernel.tcl
```

**CRITICAL warnings:**
- Do NOT use `gen_dpu_xo.tcl` in a persistent Vivado MCP session — it contains an
  `exit` command that will kill the session. Source `package_dpu_kernel.tcl` directly.
- The `source` command in Vivado Tcl does NOT accept positional arguments. You MUST
  set `::argv` and `::argc` before calling `source`.
- `package_dpu_kernel.tcl` uses relative paths like `../../dpu_ip/` — it MUST be
  sourced from `<TRD_ROOT>/prj/Vitis/` or with `TRD_PATH` set correctly.
- After generation, verify the XO contains `S_AXI_CONTROL` in its `kernel.xml`. If
  this interface is missing, v++ link will fail with "No available control master".

#### Verifying the generated XO:

```bash
# Unzip and check kernel.xml for S_AXI_CONTROL
mkdir -p /tmp/xo_check && cd /tmp/xo_check
unzip -o <output.xo> kernel.xml
grep -c "S_AXI_CONTROL" kernel.xml
# Must return >= 1. If 0, the XO is broken — regenerate from scratch.
```

### Configuration (dpu_conf.vh)

```verilog
// B512 for combined designs on KV260 (B512 is the practical max with a video pipeline)
// B1024 fits on ZCU104 (504 BRAM) but overflows KV260 BRAM after v++ interconnect
`define B512

// URAM recommended for weight storage efficiency
`define URAM_ENABLE
`ifdef URAM_ENABLE
    `define def_UBANK_IMG_N    5
    `define def_UBANK_WGT_N   17
    `define def_UBANK_BIAS     1
`endif

`define MPSOC
```

### v++ link config (prj_config)

```ini
[clock]
freqHz=300000000:DPUCZDX8G_1.aclk
freqHz=600000000:DPUCZDX8G_1.ap_clk_2

[connectivity]
sp=DPUCZDX8G_1.M_AXI_GP0:HPC0
sp=DPUCZDX8G_1.M_AXI_HP0:HPC1
sp=DPUCZDX8G_1.M_AXI_HP2:HP3
```

Adjust HP/HPC port assignments based on which ports are already used by the platform's
custom PL pipeline. The sptag names (HPC0, HPC1, HP3) must match the `PFM.AXI_PORT`
tags on the extensible XSA — check with `platforminfo` or by inspecting the BD.

**Port mapping logic:** The DPU has three AXI master groups:
- `M_AXI_GP0` — instruction fetch (low bandwidth, map to any HPC/HP)
- `M_AXI_HP0` — weight/feature read (high bandwidth, prefer HPC for cache coherency)
- `M_AXI_HP2` — feature write (high bandwidth, map to remaining HP/HPC)

### DPUCZDX8G Architecture Variants (Zynq UltraScale+)

**Use ACTUAL numbers, not PG338 estimates.** See `estimation/SKILL.md` for full table
with PG338 vs measured comparisons. PG338 underestimates BRAM by 1.5-2x and LUTs by
2-2.5x because it omits AXI interfaces, CDC FIFOs, and control logic.

| Arch  | Actual LUTs | Actual BRAM tiles | Actual URAMs | DSPs | Notes                         |
|-------|-------------|-------------------|--------------|------|-------------------------------|
| B512  | ~26K        | ~12               | ~15          | 118  | KV260 max with video pipeline |
| B1024 | ~53K        | ~82               | ~46          | 710  | Overflows KV260 BRAM. OK on ZCU104 |
| B2304 | ~85K (est)  | ~130 (est)        | ~58 (est)    | ~1050| ZCU104+ only                  |
| B4096 | ~115K (est) | N/A               | N/A          | ~1400| DPU-only overlay, large devices only |

**KV260 combined design ceiling: B512.** B1024 v++ link failed with:
`ERROR: [VPL UTLZ-1] RAMB18/RAMB36 over-utilized... requires 318, only 288 available`
This was with a 4K MIPI video pipeline consuming ~10 BRAM tiles — the v++ interconnect
added ~20 more BRAM tiles, pushing the total past the 144-tile device limit.

### DPUCVDX8G (Versal AI Core — VCK190)

The DPU kernel comes from the Vitis-AI repository. It includes encrypted RTL
(PL logic) and an AIE graph (compiled by aiecompiler).

```bash
# Clone the Vitis-AI repository (use the branch matching your tools)
cd /scratch/nshirazi_vitis_builds
git clone --depth 1 --branch v3.0 https://github.com/Xilinx/Vitis-AI.git

# DPU IP location
ls Vitis-AI/dpu/
# Contains: DPUCVDX8G/ (kernel source + config)

# Reference design for VCK190
ls Vitis-AI/dpu/ref_design/
# Contains pre-configured projects with Makefile-based v++ flows
```

The VCK190 Base TRD (`vck190-base-trd`) also provides a complete XVDPU overlay
build with Makefile, config generators, and NoC connectivity scripts:

```bash
git clone --depth 1 --branch 2022.1 https://github.com/Xilinx/vck190-base-trd.git
ls vck190-base-trd/overlays/xvdpu/kernels/vitis_prj/
# Makefile, scripts/system.cfg, scripts/xvdpu_aie_noc.py
```

## Step 2 — Configure DPU Parameters

### DPUCVDX8G Configuration (dpu_conf.vh / Makefile variables)

| Parameter           | Value (B4096)    | Description                              |
|---------------------|------------------|------------------------------------------|
| DPUCVDX8G_ARCH      | B4096            | 4096 MACs/cycle (max for single CU)     |
| BATCH_N             | 2                | Concurrent inference batches             |
| AIE_TILES_PER_BATCH | 32               | AIE cores per batch handler              |
| AXI_DATA_WIDTH      | 128              | Memory interface width (bits)            |
| LOAD_PARALLEL       | 2                | Parallel weight load channels            |
| SAVE_PARALLEL       | 2                | Parallel result save channels            |
| CONV_PARALLEL       | 2                | Parallel convolution engines             |

### Configuration file (system.cfg)

```ini
[connectivity]
# Kernel instance count
nk=DPUCVDX8G:1:DPUCVDX8G_1

# DPU AXI masters → NoC slave ports (DDR access)
# These map DPU data ports to the PFM-tagged NoC NSU ports
sp=DPUCVDX8G_1.M00_INSTR_AXI:DDR
sp=DPUCVDX8G_1.M01_WGTS_AXI:DDR
sp=DPUCVDX8G_1.M02_WGTS_AXI:DDR
sp=DPUCVDX8G_1.M03_IFMAP_AXI:DDR
sp=DPUCVDX8G_1.M04_IFMAP_AXI:DDR
sp=DPUCVDX8G_1.M05_OFMAP_AXI:DDR
sp=DPUCVDX8G_1.M06_OFMAP_AXI:DDR

[advanced]
param=hw_emu.enableProfiling=false
param=compiler.addOutputTypes=hw_export
param=compiler.worstNegativeSlack=-1

[vivado]
# Implementation strategy for timing closure with DPU
prop=run.impl_1.strategy=Performance_ExploreWithRemap
```

### AIE-NoC connectivity config (generated)

The DPU's AIE graph requires stream connections between AIE tiles and the DPU's
PL-side AXI-Stream interfaces. The VCK190 Base TRD uses `xvdpu_aie_noc.py` to
generate these `[connectivity]` entries:

```ini
[connectivity]
# AIE ↔ DPU stream connections (auto-generated)
stream_connect=ai_engine_0.M00_AXIS:DPUCVDX8G_1.S00_AXIS
stream_connect=DPUCVDX8G_1.M00_AXIS:ai_engine_0.S00_AXIS
# ... (32+ stream connections for B4096 dual-batch)
```

## Step 3 — Compile AIE Graph

The DPUCVDX8G includes an AIE graph that must be compiled before system linking:

```bash
# AIE compilation is handled by v++ in aie mode
# The DPU kernel package typically includes a pre-compiled libadf.a
# If you need to recompile:

v++ --mode aie \
    --target hw \
    --platform /path/to/platform.xsa \
    --config aie_config.cfg \
    --part xcvc1902-vsva2197-2MP-e-S \
    -o libadf.a

# For DPUCVDX8G, the AIE graph is usually pre-packaged in the kernel .xo
# Check Vitis-AI/dpu/DPUCVDX8G/ for the exact flow
```

## Step 4 — Link System (v++ --link)

This is the core step — v++ links the kernel(s) to the extensible platform,
placing PL logic and connecting AIE streams:

```bash
# Set tool paths
export VITIS=/scratch/AMDDesignTools/2025.2/Vitis
export PATH=$VITIS/bin:$PATH

# System link
v++ --link \
    --target hw \
    --platform /path/to/platform.xsa \
    --config system.cfg \
    --config xvdpu_aie_noc.cfg \
    --clock.freqHz 333000000:DPUCVDX8G_1.m_axi_aclk \
    --clock.freqHz 333000000:ai_engine_0.aclk0 \
    --clock.freqHz 150000000:DPUCVDX8G_1.s_axi_aclk \
    --save-temps \
    --temp_dir /scratch/nshirazi_vitis_builds/aibox_reid/_x \
    --output /scratch/nshirazi_vitis_builds/aibox_reid/aibox_reid.xsa \
    DPUCVDX8G_1.xo
```

**Key flags:**
- `--target hw` — full hardware build (not emulation)
- `--platform` — the extensible XSA from Phase 1
- `--config` — connectivity and Vivado strategy configs
- `--clock.freqHz` — per-port clock frequency assignments
- `--save-temps` — preserve intermediate files for debugging
- `--temp_dir` — build scratch space (use /scratch)

**Build time:** 2-6 hours for DPUCVDX8G B4096 on a 16-core machine. The link
step runs Vivado synthesis + implementation internally.

### Monitoring the build

```bash
# v++ creates a log in the temp directory
tail -f /scratch/nshirazi_vitis_builds/aibox_reid/_x/logs/link/v++.log

# Check Vivado implementation progress (inside the temp dir)
ls /scratch/nshirazi_vitis_builds/aibox_reid/_x/link/vivado/
```

## Step 5 — Generate xclbin

After linking, package the result into an xclbin:

```bash
v++ --package \
    --target hw \
    --platform /path/to/platform.xsa \
    --package.boot_mode sd \
    --package.out_dir /scratch/nshirazi_vitis_builds/aibox_reid/package \
    /scratch/nshirazi_vitis_builds/aibox_reid/aibox_reid.xsa
```

This produces:
- `dpu.xclbin` — device binary (FPGA bitstream + kernel metadata)
- `BOOT.BIN` — bootable image (PDI + PLM + PSM FW for Versal)
- `boot.scr` — U-Boot boot script

### Alternative: combined link+package

```bash
v++ --link --package \
    --target hw \
    --platform platform.xsa \
    --config system.cfg \
    --package.boot_mode sd \
    -o aibox_reid.xclbin \
    DPUCVDX8G_1.xo
```

## Step 6 — Extract arch.json (DPU Fingerprint)

The `arch.json` file describes the DPU architecture configuration. It is required
by the Vitis AI compiler (Phase 3) to compile neural network models that match the
deployed DPU hardware.

```bash
# arch.json is generated during the v++ link step
# Location varies by DPU version:

# Option 1: From the v++ temp directory
find /scratch/nshirazi_vitis_builds/aibox_reid/_x -name "arch.json" -type f

# Option 2: From the xclbin using xclbinutil
xclbinutil --input aibox_reid.xclbin --dump-section DPU_METADATA:JSON:arch.json

# Option 3: Generate from DPU configuration manually
# The arch.json contains a fingerprint like:
# {"fingerprint":"0x1000020F2014404"}
```

**Copy `arch.json` to the Vitis AI workspace** for Phase 3 model compilation:
```bash
cp arch.json /scratch/nshirazi_vitis_ai/workspace/arch.json
```

## Pattern: Custom AIE + HLS Kernel Integration (Non-DPU)

Not all v++ flows involve the DPU. For custom signal processing chains (radar,
communications, audio), the pattern is:

### HLS Data Mover Kernels (mm2s / s2mm)

Custom HLS data movers are preferred over platform-embedded `axi_dma` IP for v++ flows:

```cpp
// mm2s: DDR → AXI-Stream (128-bit, ap_axiu<128,0,0,0>)
extern "C" void mm2s(ap_uint<128>* mem, hls::stream<ap_axiu<128,0,0,0>>& s, int size) {
    #pragma HLS INTERFACE m_axi port=mem bundle=mem
    #pragma HLS INTERFACE axis port=s
    for (int i = 0; i < size; i++) {
        #pragma HLS PIPELINE II=1
        ap_axiu<128,0,0,0> v;
        v.data = mem[i];
        v.keep = -1;
        v.last = (i == size - 1);
        s.write(v);
    }
}
```

Compile as v++ kernel:
```bash
v++ --mode hls --config hls_mm2s.cfg --part xcvc1902-vsva2197-2MP-e-S
```

### system.cfg for AIE + HLS Flow

```ini
[connectivity]
nk=mm2s:1:mm2s_1
nk=s2mm:1:s2mm_1
nk=cfar_detector:1:cfar_detector_1

# DDR → mm2s → AIE PLIO input
stream_connect=mm2s_1.s:ai_engine_0.adc_in

# AIE PLIO output → HLS processing kernel
stream_connect=ai_engine_0.cfar_out:cfar_detector_1.data_in

# HLS kernel output → s2mm → DDR
stream_connect=cfar_detector_1.detections_out:s2mm_1.s

# Map kernel memory interfaces to DDR via NoC sptag
sp=mm2s_1.mem:DDR
sp=s2mm_1.mem:DDR

[vivado]
prop=run.impl_1.STEPS.OPT_DESIGN.ARGS.DIRECTIVE=Explore
prop=run.impl_1.STEPS.PLACE_DESIGN.ARGS.DIRECTIVE=Explore
```

Key rules:
- `stream_connect` source format: `<kernel>.<port>` or `ai_engine_0.<plio_name>`
- `sp=` maps `m_axi` bundle names to platform sptags (`DDR`, `LPDDR`)
- AIE PLIO names in `stream_connect` must match the graph's PLIO constructor names
- 128-bit PLIO at 312.5 MHz provides 5 GB/s throughput per interface

### AIE DSP Library Kernels with PLIO

AIE graphs using DSP Library (FFT, FIR, etc.) compile with `v++ --mode aie` and
integrate via PLIO at the graph boundary:

```cpp
// Graph PLIO declaration (in graph.h)
adf::input_plio adc_in = adf::input_plio::create("adc_in",
    adf::plio_128_bits, "data/adc_input.txt");
adf::output_plio cfar_out = adf::output_plio::create("cfar_out",
    adf::plio_128_bits, "data/cfar_output.txt");
```

The PLIO names (`"adc_in"`, `"cfar_out"`) become the connection targets in
`system.cfg` via `ai_engine_0.<plio_name>`.

## v++ CLI Quick Reference

```bash
# HLS kernel → .xo
v++ --mode hls --config hls.cfg --part <device> --output kernel.xo

# AIE graph → libadf.a
v++ --mode aie --config aie.cfg --part <device> --output libadf.a

# System link → .xsa / .xclbin
v++ --link --platform <extensible.xsa> --config system.cfg \
    <kernel.xo> [libadf.a] -t hw -o linked.xsa

# Package → SD card boot image
v++ --package --platform <platform.xsa> -t hw \
    --package.boot_mode sd --package.out_dir ./package linked.xsa

# Export to Vivado (alternative to integrated link)
v++ --link --platform <extensible.xsa> --config system.cfg \
    <kernel.xo> --export_archive -o design.vma
# Then import VMA in Vivado for manual implementation control
```

## DPUCVDX8G Architecture Variants

| Arch    | MACs/cycle | AIE Tiles | LUTs  | BRAMs | URAMs | Typical Use           |
|---------|-----------|-----------|-------|-------|-------|-----------------------|
| B512    | 512       | 4         | ~15K  | 20    | 5     | Low-power, single model|
| B1024   | 1024      | 8         | ~25K  | 35    | 10    | Medium throughput      |
| B2048   | 2048      | 16        | ~45K  | 60    | 18    | High throughput        |
| B4096   | 4096      | 32        | ~80K  | 110   | 32    | Maximum throughput     |

Resource numbers are per-batch. Dual-batch (BATCH_N=2) doubles these.

## Build Time Expectations

### DPU Builds (DPUCVDX8G)

| Configuration         | Link Time | Impl Strategy              | Machine      |
|-----------------------|-----------|----------------------------|--------------|
| B512 single-batch     | ~45 min   | Default                    | 8-core, 32GB |
| B1024 single-batch    | ~1.5 hr   | Performance_Explore        | 16-core, 64GB|
| B4096 single-batch    | ~3 hr     | Performance_ExploreWithRemap| 16-core, 64GB|
| B4096 dual-batch      | ~5 hr     | Performance_ExploreWithRemap| 32-core, 128GB|

### Custom AIE + HLS Builds (from actual runs)

| Configuration                                    | Step          | Time   | Notes                              |
|--------------------------------------------------|---------------|--------|------------------------------------|
| 4-ch radar (FFT+FIR DSPLib, CFAR HLS, VCK190)   | AIE compile   | ~180s  | 50 AIE columns, DSPLib FFT+FIR     |
| 4-ch radar (FFT+FIR DSPLib, CFAR HLS, VCK190)   | HLS compile   | ~60s   | CFAR + mm2s + s2mm (3 kernels)     |
| 4-ch radar (FFT+FIR DSPLib, CFAR HLS, VCK190)   | v++ link      | ~867s  | system_link 10s + VPL 857s         |
| 4-ch radar — final timing                        | WNS / WHS     | —      | 0.132ns / 0.014ns (all met)        |
| 4-ch radar — PL utilization                      | user kernels  | —      | 2.1% LUT, 7.6% DSP, 2.3% BRAM     |

Use `--jobs <N>` to control v++ parallelism. Set to number of CPU cores / 2.

## Troubleshooting

### "No matching platform clock for frequency X"

The requested `--clock.freqHz` does not match any PFM-tagged clock. Check the
platform's available clocks:
```bash
platforminfo -p platform.xsa
```

### "AIE compilation failed: insufficient tiles"

The DPU arch requires more AIE tiles than the device provides or than are reserved
in the platform. Reduce BATCH_N or use a smaller arch (B2048 → B1024).

### "Pin mapping failure: PSPSNOCCCIAXI0CLK" during v++ link

This indicates the extensible platform has a PS-NoC clock routing defect. The custom
platform's `axi_noc` was manually created with Tcl rather than board automation.
**Solution:** Use an AMD-provided base platform (e.g., `xilinx_vck190_base_202520_1`).
See `vitis-platform/SKILL.md` "Known Limitation: PS-NoC Clock Routing" for full details.

### Invalid Vivado implementation directive for Versal

`EarlyBlockPlacement` is **not valid** for Versal `PLACE_DESIGN`. If specified in
`system.cfg`, v++ will warn or error. Use `Explore` or `Default` instead:
```ini
[vivado]
prop=run.impl_1.STEPS.PLACE_DESIGN.ARGS.DIRECTIVE=Explore
```
Check UG904 for the complete list of Versal-supported directives.

### "Routing failed" during v++ link

The DPU's PL logic is congestion-heavy. Options:
1. Use `Performance_ExploreWithRemap` Vivado strategy (in system.cfg)
2. Reduce DPU arch size
3. Ensure sufficient NoC ports are tagged (reduces AXI interconnect congestion)

### v++ link runs out of memory

DPUCVDX8G builds need 64-128 GB RAM. Check with:
```bash
free -h
```
If insufficient, reduce `--jobs` to lower concurrent Vivado processes.

### "DPU kernel .xo not found"

The DPU kernel is distributed as a pre-compiled `.xo` in the Vitis-AI repository.
Check `Vitis-AI/dpu/DPUCVDX8G/` for the correct `.xo` file matching your tool version.

### "kernel.xml indicates S_AXI_CONTROL, which does not exist in component.xml"

The XO was generated incorrectly — the DPU's `S_AXI_CONTROL` AXI-Lite slave interface
was stripped during IP packaging. This happens when:
1. You copied a pre-built XO and swapped `dpu_conf.vh` without regenerating
2. The IP cache served a stale version from a previous architecture
3. `package_dpu_kernel.tcl` was run from the wrong directory

**Fix:** Delete the `.ipcache` directory, edit `dpu_conf.vh` directly in the TRD, and
regenerate the XO from scratch following the procedure in Step 1. Verify the output
XO contains `S_AXI_CONTROL` in `kernel.xml` before attempting `v++ link`.

### "gen_dpu_xo.tcl killed the Vivado session"

`gen_dpu_xo.tcl` contains an `exit` command that terminates the Vivado process. In a
persistent MCP session, this kills the connection. Instead, source
`package_dpu_kernel.tcl` directly (it does the actual work without exiting). Set
`::env(TRD_PATH)` and `::argv`/`::argc` before sourcing.

### v++ link BRAM overflow on KV260 (xck26)

```
ERROR: [VPL UTLZ-1] Resource utilization: RAMB18 and RAMB36/FIFO over-utilized
```

The DPU's actual BRAM consumption (post-synthesis) is significantly higher than PG338
estimates. Additionally, v++ adds 15-25 BRAM tiles for its own interconnect, protocol
converters, and CDC FIFOs. For KV260 combined designs:
- B1024 requires ~82 DPU + ~10 pipeline + ~20 v++ interconnect = ~112 tiles (> 85% of 144)
  → **failed** in practice at 318 BRAM (RAMB18+RAMB36 combined count)
- B512 requires ~12 DPU + ~10 pipeline + ~20 v++ interconnect = ~42 tiles
  → **fits** comfortably

**Fix:** Downgrade to B512 for KV260 combined designs. See `estimation/SKILL.md` for
the full device-specific DPU ceiling analysis.

### arch.json not generated

The DPU generates `arch.json` during compilation. If missing:
1. Check `_x/link/` for partial outputs
2. Use `xclbinutil --dump-section DPU_METADATA` on the output xclbin
3. As last resort, construct from DPU configuration parameters (PG389 Table 3)

## Step 7 — Compile AI Model for DPU Fingerprint

After `v++ link` succeeds, extract the DPU fingerprint and compile the target neural
network model. The fingerprint encodes the DPU architecture and must match exactly.

### Extract fingerprint (arch.json)

```bash
# From v++ temp directory
find <v++_temp_dir> -name "arch.json" -type f

# Or from xclbin
xclbinutil --input <output.xclbin> --dump-section DPU_METADATA:JSON:arch.json

# Example content: {"fingerprint":"0x101000016010200"}
```

### Compile model with Vitis AI

The model compiler (`vai_c_xir`) runs inside the Vitis AI Docker container. The Conda
environment must be explicitly activated — `vai_c_xir` is NOT on the default PATH.

```bash
# Launch Vitis AI Docker (from host)
docker run --rm -it \
    -v /scratch:/scratch \
    xilinx/vitis-ai-pytorch-cpu:latest \
    bash

# Inside Docker: activate Conda environment FIRST
source /opt/vitis_ai/conda/etc/profile.d/conda.sh
conda activate vitis-ai-pytorch

# Compile the quantized model for the DPU fingerprint
vai_c_xir \
    -x /scratch/models/movenet_quantized.xmodel \
    -a /scratch/deploy/arch.json \
    -o /scratch/deploy/ \
    -n movenet_pose_b512

# Output: /scratch/deploy/movenet_pose_b512.xmodel
```

**Common failure:** `bash: vai_c_xir: command not found` — you forgot to activate the
Conda environment. The `source ... conda.sh && conda activate` step is mandatory.

**Fingerprint mismatch:** If the model was compiled for a different DPU fingerprint
(e.g., B1024) than what is deployed (B512), the DPU will reject the model at runtime.
Always recompile the model when changing DPU architecture.

## Output Artifacts

```
/scratch/nshirazi_vitis_builds/aibox_reid/
    aibox_reid.xsa          # Linked system (intermediate)
    aibox_reid.xclbin        # Device binary for deployment
    _x/                      # Build temp directory
        logs/                # v++ and Vivado logs
        link/vivado/         # Vivado project (for debug)
    package/                 # Packaged boot artifacts
        BOOT.BIN             # Versal boot image
        boot.scr             # U-Boot script
        dpu.xclbin           # Renamed xclbin for deployment
    arch.json                # DPU fingerprint for Vitis AI compiler
```

## References

- PG389 — DPUCVDX8G Product Guide (Versal AI Core DPU)
- PG425 — DPUCV2DX8G Product Guide (Versal AI Edge DPU)
- PG338 — DPUCZDX8G Product Guide (Zynq UltraScale+ DPU)
- UG1393 — Vitis Application Acceleration Development
- UG1076 — Vitis AI User Guide (model compilation, arch.json)
- VCK190 Base TRD: `Xilinx/vck190-base-trd/overlays/xvdpu/`
- Vitis-AI DPU Reference: `Xilinx/Vitis-AI/dpu/`
