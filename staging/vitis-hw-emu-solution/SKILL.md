---
name: vitis-hw-emu-solution
description: Umbrella skill for AMD Vitis hardware emulation (hw_emu) and QEMU/RTL/SystemC co-simulation across all supported platforms and flows. Routes the user to the right platform: ZCU104 (Zynq UltraScale+ MPSoC), VCK190 (Versal Gen1 ACAP), VEK280 (Versal AI Edge, AIE-ML), the EDF turnkey flow (VEK385 Gen2, VEK280, VCK190, VRK160 — pre-built base platform + Yocto images), and cross-platform cosim runtime debugging (launch_hw_emu.sh, QEMU PMC/APU, remote-port, cosim DTBs, AIE SystemC). Use this whenever the user wants to build a Vitis embedded platform, run hardware emulation, package an EDF image, or debug a hw_emu/cosim failure and has not already picked a specific platform. On invocation, ask which platform or flow they want and load that platform's references.
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
# Vitis HW EMU Solution

## Overview

This is the single entry point for the Vitis hardware-emulation / co-simulation solution. It does not do the work itself — it **routes** the user to the correct platform or flow, then drives that flow from the per-platform references under `references/`.

The solution covers two stages:
- **Platform build** (per board): Vivado hardware design → XSA → Vitis `.xpfm` → sample-app `hw_emu` validation.
- **EDF turnkey flow**: link kernels onto a *pre-built* base platform + *pre-built* Yocto images → `wic cp` → QEMU (no Vivado, no PetaLinux).
- **Cosim runtime** (cross-platform): the emulator itself — `launch_hw_emu.sh`, QEMU (PMC/APU), remote-port, cosim DTBs, AIE/AIE-ML SystemC, runtime mismatches.

## Workflow

1. **Determine the target.** If the user has not already named a platform/flow, ask them with a single multiple-choice question (use the AskUserQuestion picker) with these options:
   - **ZCU104** — Zynq UltraScale+ MPSoC platform creation + hw_emu (vadd)
   - **VCK190** — Versal Gen1 ACAP platform creation + hw_emu (vadd + AIE adder)
   - **VEK280** — Versal AI Edge platform (pre-built or custom) + hw_emu (vadd + AIE-ML matmul)
   - **EDF flow** — pre-built base platform + Yocto EDF images for VEK385 / VEK280 / VCK190 / VRK160 (`make all` → wic cp → QEMU)
   - **Cosim runtime debug** — any platform; the emulator/QEMU/remote-port/SystemC layer
   If the user's message already implies the target (board name, `vek385_base`, `wic cp`, `launch_hw_emu.sh`, `platform_creation.py`, etc.), skip the question and go straight to the matching references.
2. **Load that target's references** (see Reference Selection). Read `references/<target>/overview.md` first — it carries the per-platform workflow, fast triage, and boundaries — then open the deeper references only as the task needs them.
3. **Help them launch.** Each platform's references contain concrete quick-start / fast-path commands (and for EDF, the `make all TARGET=hw_emu` pipeline). Surface those, offer to run the appropriate step, and name the next artifact to expect.
4. **Cross into cosim runtime when needed.** Platform-build targets hand off to `references/cosim/` once the `.xpfm` (or EDF package) is valid and the failure is inside `launch_hw_emu.sh`, QEMU, remote-port, or SystemC. Say so explicitly when you switch.

## Platform / Flow Map

| Choice | Device | Stage | References |
|--------|--------|-------|-----------|
| ZCU104 | Zynq UltraScale+ MPSoC (xczu7ev) | platform build → hw_emu | `references/zcu104/` |
| VCK190 | Versal Gen1 ACAP (xcvc1902) | platform build (CIPS+NOC+AIE1) → hw_emu | `references/vck190/` |
| VEK280 | Versal AI Edge (xcve2802, AIE-ML) | pre-built or custom platform → hw_emu | `references/vek280/` |
| EDF flow | VEK385 (Gen2), VEK280, VCK190, VRK160 | pre-built base + Yocto images → hw_emu / SD | `references/edf/` |
| Cosim runtime | all of the above | emulator / QEMU / remote-port / SystemC | `references/cosim/` |

## Reference Selection

- **`references/<platform>/overview.md`** — load first for any platform; per-platform workflow, fast triage, output style, and boundaries.
- **ZCU104 / VCK190 / VEK280** (`references/<board>/`): `tutorial-overview.md` (flow, names, target table, artifact chain), `hardware-platform.md` (Vivado/XSA), `software-platform.md` (common image, `platform_creation.py`, domains), `validation-and-iteration.md` (`platforminfo`, sample apps, validation record, iteration).
- **EDF** (`references/edf/`): `tutorial-overview.md` (EDF concept + 4-board matrix), `build-flow.md` (aiecompiler/v++ compile→link→package), `emulation-and-run.md` (`qemu_combined`, BOOT.bin swap, `wic cp`, `launch_hw_emu.sh`), `validation-and-iteration.md` (env, downloads, troubleshooting).
- **Cosim runtime** (`references/cosim/`): `overview.md` (orchestration), `architecture.md` (QEMU/RTL/SystemC boundaries), `setup-and-variants.md` (device-family differences, packaged vs standalone), `debugging.md` (failure signatures), `gaps-and-improvements.md`.

## Output Style

- Always name the platform/flow the answer applies to.
- Name the concrete next artifact (`*.xpfm`, `*.xsa`, `*.wic.ufs`, `launch_hw_emu.sh`, `TEST PASSED`).
- Distinguish platform **build** from cosim **runtime**, and EDF (pre-built base + Yocto) from custom platform creation (PetaLinux common image).
- When the task crosses from platform build into the emulator, say you're switching to `references/cosim/`.

## Dependencies

See `DEPENDENCIES.md` for toolchain, environment variables, common images, and EDF Yocto-artifact requirements before running any flow.
