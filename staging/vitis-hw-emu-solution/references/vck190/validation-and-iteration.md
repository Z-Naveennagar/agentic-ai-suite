<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Validation and Iteration

## Scope

Load this file when validating the VCK190 platform with `platforminfo`, building the vadd or AIE adder test applications, running hw_emu, or deciding which step to rerun after a hardware or software change.

## Step 3 Directory Name

The VCK190 tutorial uses `step3_application` — NOT `step3_validate` (which is the ZCU104 name).
Always use the correct directory when running make commands.

## Platform Validation with platforminfo

Run `platforminfo` to verify the platform is complete and correctly configured before building applications:

```bash
cd step2_pfm
make getplatforminfo
# or directly:
platforminfo step2_pfm/ws/custom_platform/export/custom_platform/custom_platform.xpfm
```

A valid VCK190 platform report should show:
- Platform: `custom_platform`
- Board: VCK190 (xcvc1902)
- Domains:
  - `xrt` (Linux, psv_cortexa72)
  - `aie_runtime` (AI Engine)
- Clock IDs and frequencies from the Vivado design
- AXI ports and memory maps

If `aie_runtime` domain is missing, the platform_creation.py AIE domain step failed — re-run Step 2.

## Step 3 Applications

The VCK190 tutorial includes **two** test applications (unlike ZCU104 which has one):

| Application | Type | Makefile | Run Script |
|-------------|------|----------|------------|
| vadd | PL kernel only | `makefile_vadd` | `run_vadd.sh` |
| aie_adder | AIE + PL kernels | `makefile_aie` | `run_aie.sh` |

The top-level step3_application Makefile dispatches to both:
```bash
make vadd_emu       # builds and runs vadd in hw_emu
make aie_adder_emu  # builds and runs aie_adder in hw_emu
```

Source code is copied from `$XILINX_VITIS/samples/` at build time. Verify `XILINX_VITIS` is set by sourcing Vitis settings64.sh before running make.

## vadd Application (PL Only)

### Build and Run

```bash
cd step3_application
make vadd_emu \
  PLATFORM=<path/to/custom_platform.xpfm> \
  COMMON_IMAGE_VERSAL=<path/to/xilinx-versal-common-v2025.2/>
```

### What it does

1. Cross-compiles `simple_vadd` host app with `aarch64-linux-gnu-g++` against SYSROOT
2. Compiles PL vadd kernel with `v++ -c -t hw_emu`
3. Links xclbin with `v++ -l -t hw_emu`
4. Packages with `v++ -p` → generates `package.hw_emu/launch_hw_emu.sh`
5. Runs: `launch_hw_emu.sh -run-app run_vadd.sh`
6. Expected result: `TEST PASSED` from `simple_vadd`

### run_vadd.sh

```bash
export XILINX_XRT=/usr
./simple_vadd -x krnl_vadd.xclbin -d 0
```

### SYSROOT and Host Compilation

SYSROOT for VCK190 (identical triplet to ZCU104):
```
{COMMON_IMAGE_VERSAL}/sysroots/cortexa72-cortexa53-amd-linux
```

The Makefile uses `cortexa72-cortexa53-xilinx-linux` (symlink) — both resolve correctly.

## aie_adder Application (AIE + PL)

### Build and Run

```bash
cd step3_application
make aie_adder_emu \
  PLATFORM=<path/to/custom_platform.xpfm> \
  COMMON_IMAGE_VERSAL=<path/to/xilinx-versal-common-v2025.2/>
```

### What it does

1. Compiles AIE graph with `aiecompiler` → generates `adf.a` and AIE metadata
2. Compiles PL kernels (s2mm, mm2s, polar_clip) with `v++ -c -t hw_emu` → XO files
3. Links all kernels + AIE graph with `v++ -l -t hw_emu` → `krnl_adder.xclbin`
4. Cross-compiles `aie_adder` host app
5. Packages with `v++ -p` → generates `package.hw_emu/launch_hw_emu.sh`
6. Runs: `launch_hw_emu.sh -run-app run_aie.sh`
7. Expected result: `INFO: host run completed.` without errors

### run_aie.sh

```bash
./aie_adder krnl_adder.xclbin
return_code=$?
if [ $return_code -ne 0 ]; then
    echo "ERROR: host run failed, RC=$return_code"
fi
echo "INFO: host run completed."
```

### AIE Compilation Dependency

`aiecompiler` requires:
- The platform's AIE architecture description (from `custom_platform.xpfm`)
- `XILINX_VITIS` set to locate aiecompiler binary and include files
- AIE domain (`aie_runtime`) present in the platform

If aiecompiler fails with "cannot find platform AIE device", the `aie_runtime` domain is missing from the platform.

## PLATFORM Path Issue

The step3 Makefile default PLATFORM may not match the actual ws/ output path. Always pass explicitly:

```bash
PLATFORM=/path/to/03_Edge_VCK190/ref_files/step2_pfm/ws/custom_platform/export/custom_platform/custom_platform.xpfm
```

## hw_emu Execution (Versal Gen1)

When hw_emu launches for VCK190:
- **Two QEMU instances** start: PMC QEMU and APU QEMU (unlike ZCU104 which has one)
- PMC QEMU loads PLM and device configuration
- APU QEMU boots Linux using `Image`, `rootfs.ext4`, DTB
- XSIM starts the RTL simulation for PL
- AIE SystemC model starts for the AI Engine
- All connect via remote-port sockets

If hw_emu hangs at boot, switch to `the cosim runtime references (`references/cosim/`)` for diagnosis.

## Known Versal-Specific Issues (from FAQ)

### PLM IPI Errors

PLM may log IPI errors for peripherals that are configured in CIPS but not active at runtime. These appear as:
```
[PLM] ERROR: IPI request from module 0x... failed
```
Root cause: CIPS was configured with certain peripheral enables but the device tree or boot configuration does not initialize them. Usually non-blocking for PL/AIE workloads.

### AIE Application Hanging

If the AIE adder application hangs indefinitely:
- Check whether the AIE was compiled with debug instrumentation — debug AIE images may wait for a debugger attachment
- Verify the xclbin was built for `hw_emu` target, not `hw` target
- Ensure `XCL_EMULATION_MODE=hw_emu` is set before running the host app

### Hardware Emulation vs Hardware Target Confusion

The `run_aie.sh` and `run_vadd.sh` scripts do not export `XCL_EMULATION_MODE`. The `launch_hw_emu.sh` wrapper sets this before calling the run script. If running the host app outside of `launch_hw_emu.sh`, set:
```bash
export XCL_EMULATION_MODE=hw_emu
```

## Iteration Guidelines

Use this decision table when any artifact changes:

| Change | Re-run |
|--------|--------|
| CIPS peripheral or DDR setting | Step 1 (full Vivado rebuild) → Step 2 → Step 3 |
| AXI port or clock added/removed | Step 1 → Step 2 → Step 3 |
| system-user.dtsi change | Step 2 only → Step 3 |
| Common image updated | Step 2 only → Step 3 |
| PL kernel source change | Step 3 kernel build only (`make build`) |
| AIE graph source change | Step 3 AIE graph + link (`make graph build`) |
| Host application source change | Step 3 host only (`make host`) |
| Platform XSA unchanged, xpfm rebuilt | Step 3 clean + rebuild |

Do not re-run Step 1 for software-only changes. Do not re-run Step 2 for application-only changes.

## Validation Record (2025.2)

**Tested:** 2026-04-14

```
Step 1 — XSA build         : PASS  (CIPS + DDR4 + LPDDR4 + AIE)
Step 2 — Platform build    : PASS  (Linux xrt + AIE1 domains, DTB auto-gen)
Step 3 — vadd hw_emu       : PASS  (TEST PASSED, PMC+APU QEMU + XSIM)
Step 3 — aie_adder hw_emu  : PASS  (TEST PASSED, PMC+APU QEMU + XSIM + AIE SystemC)
```
