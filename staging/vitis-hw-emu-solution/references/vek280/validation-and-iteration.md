<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Validation and Iteration

## Scope

Load this file when validating the VEK280 platform, building vadd or aieml applications, running hw_emu, or deciding which step to rerun after a change. Applies to both the pre-built and custom platform paths.

## Platform Validation with platforminfo

```bash
source /proj/xbuilds/2025.2_released/installs/lin64/2025.2/Vitis/settings64.sh

# Custom platform
platforminfo ws/vek280_custom/export/vek280_custom/vek280_custom.xpfm

# Pre-built platform
platforminfo /proj/rdi/xbuilds/released/2025.2/2025.2_released/internal_platforms/xilinx_vek280_base_202520_1/xilinx_vek280_base_202520_1.xpfm
```

A valid VEK280 platform shows:
- Platform: `vek280_custom` or `xilinx_vek280_base_202520_1`
- Processor: `psv_cortexa72`
- Domains: `xrt` (Linux) + AIE-ML domain
- QEMU supported: 1
- AIE-ML partitions listed

## Step 3 Applications

Two test applications run against the platform:

| Application | AIE type | Makefile | Run script | xclbin |
|-------------|---------|----------|-----------|--------|
| vadd | PL only | `makefile_vadd` | `run_vadd.sh` | `krnl_vadd.xclbin` |
| aieml | AIE-ML | `makefile_aieml` | `run_aieml.sh` | `krnl_aieml.xclbin` |

Sources are copied from `$XILINX_VITIS/samples/` at build time:
- vadd: `$XILINX_VITIS/samples/vadd/` → `vadd_work/`
- aieml: `$XILINX_VITIS/samples/aie_system_examples/aie-ml_sys_design/` → `aieml_work/`

> **Critical:** The aieml sample is `aie-ml_sys_design` (with hyphen and ml). Do NOT use `aie_sys_design` (VCK190 sample) — it uses AIE1, not AIE-ML, and will fail to compile against the VEK280 platform.

## Running hw_emu

### With Pre-built Platform (Path A)

```bash
VER=2025.2
PLATFORM=/proj/rdi/xbuilds/released/${VER}/${VER}_released/internal_platforms/xilinx_vek280_base_202520_1/xilinx_vek280_base_202520_1.xpfm
COMMON_IMAGE_VERSAL=/proj/rdi/xbuilds/released/${VER}/${VER}_released/internal_platforms/sw/versal/xilinx-versal-common-v${VER}/
SYSROOT=${COMMON_IMAGE_VERSAL}/sysroots/cortexa72-cortexa53-amd-linux/

source /proj/xbuilds/${VER}_released/installs/lin64/${VER}/Vivado/settings64.sh
source /proj/xbuilds/${VER}_released/installs/lin64/${VER}/Vitis/settings64.sh

# vadd hw_emu
make vadd_emu PLATFORM=$PLATFORM COMMON_IMAGE_VERSAL=$COMMON_IMAGE_VERSAL

# aieml hw_emu
make aieml_emu PLATFORM=$PLATFORM COMMON_IMAGE_VERSAL=$COMMON_IMAGE_VERSAL
```

### With Custom Platform (Path B)

```bash
# Full flow: hw → pfm → vadd_emu → aieml_emu
make all COMMON_IMAGE_VERSAL=$COMMON_IMAGE_VERSAL

# Or individual steps after platform exists:
make vadd_emu  COMMON_IMAGE_VERSAL=$COMMON_IMAGE_VERSAL
make aieml_emu COMMON_IMAGE_VERSAL=$COMMON_IMAGE_VERSAL
# PLATFORM defaults to ws/vek280_custom/... — no override needed for custom path
```

## Expected Results

### vadd hw_emu

```
INFO: host run completed.
```
(The `run_vadd.sh` script reports INFO on success, not "TEST PASSED".)

### aieml hw_emu

```
INFO: host run completed.
```
(The `run_aieml.sh` script has the same pattern.)

Both scripts return non-zero on failure and print `ERROR: host run failed, RC=<code>`.

## Validation Record (2025.2)

**Tested:** 2026-04-14 | **Path:** Pre-built xpfm

```
Pre-built xpfm  : PASS  (xilinx_vek280_base_202520_1.xpfm)
Steps 1 & 2     : SKIPPED (pre-built path)
vadd hw_emu     : PASS  (TEST PASSED, PMC+APU QEMU + XSIM)
aieml hw_emu    : PASS  (TEST PASSED, 64x64x64 MatMult, AIE-ML SystemC)
```

## Switching Between Pre-built and Custom Platform

At any point you can switch which platform is used for Step 3 without rebuilding the applications:

```bash
# Use pre-built:
make vadd_emu PLATFORM=/proj/rdi/.../xilinx_vek280_base_202520_1.xpfm

# Use custom:
make vadd_emu  # uses Makefile default: ws/vek280_custom/...
```

Clean the work directories before switching if xclbin was already linked against a different platform:
```bash
rm -rf vadd_work aieml_work
```

## Iteration Guidelines

| Change | Pre-built path | Custom path |
|--------|---------------|-------------|
| Kernel source change | Rebuild Step 3 only | Rebuild Step 3 only |
| Host app source change | Rebuild Step 3 host only | Rebuild Step 3 host only |
| system-user.dtsi change | N/A (use custom path) | Rebuild Step 2 → Step 3 |
| Common image updated | Rebuild Step 3 (sd_card) | Rebuild Step 2 → Step 3 |
| Hardware IP change | Switch to custom path | Rebuild Step 1 → 2 → 3 |
| Clock or AXI change | Switch to custom path | Rebuild Step 1 → 2 → 3 |

## Fast Triage

| Symptom | Check |
|---------|-------|
| `COMMON_IMAGE_VERSAL` not found | Export manually — not set by settings64.sh |
| vadd_emu fails: PLATFORM not found | For pre-built: pass PLATFORM explicitly; for custom: run `make pfm` first |
| aieml uses wrong source | Verify `aie-ml_sys_design` (with hyphen-ml), not `aie_sys_design` |
| AIE-ML domain missing in platforminfo | Re-run `make pfm` with clean `ws/` — check XSA includes AIE-ML |
| `INFO: host run completed` not printed | Check QEMU boot log — hand off to `the cosim runtime references (`references/cosim/`)` |
| hw_emu hangs after QEMU starts | Hand off to `the cosim runtime references (`references/cosim/`)` — check PMC/APU remote-port connection |
| Wrong xclbin for platform | Clean `vadd_work/` or `aieml_work/` and rebuild |
| XHUB download fails in Step 1 | Use pre-built xpfm (Path A) as workaround |
