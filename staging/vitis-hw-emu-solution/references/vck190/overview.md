<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Vitis Cosim VCK190 Platform

## Overview

Use this skill to build or review the VCK190 platform-creation flow that sits upstream of `hw_emu` and cosim. Keep this skill focused on platform construction and validation; when the user reaches emulator launch, QEMU (PMC + APU), remote-port, or PS/PL/AIE runtime behavior, hand off to `the cosim runtime references (`references/cosim/`)`.

In the agent hierarchy:
- `the cosim runtime references (`references/cosim/`)` is the top-level orchestrator
- `the VCK190 references (`references/vck190/`)` is the VCK190 Versal Gen1 platform sub-agent

## Workflow

1. Classify the request:
   - hardware platform creation (Vivado CIPS + NOC + DDR configuration)
   - software platform assembly (common image, DTB, AIE domain)
   - platform validation (`platforminfo`, vadd, AIE adder)
   - iteration after a hardware or software change
2. Ask for or inspect the core artifacts:
   - Vivado project or `run.tcl` block-design script
   - exported XSA (hw and hwemu variants)
   - boot components and Versal Linux common image inputs
   - generated `.xpfm`
   - platform metadata or `platforminfo` output
3. Work through the tutorial stages in order:
   - Step 1: create Versal hardware design and export XSA (hw + hwemu)
   - Step 2: assemble Versal software platform with AIE domain and boot artifacts
   - Step 3: validate with vadd (PL) and aie_adder (AIE+PL) applications
   - iteration: regenerate only the layers affected by the change
4. Keep the outputs explicit:
   - identify the exact missing or stale artifact
   - name which stage must be rerun
   - state whether the issue is pre-cosim platform construction or actual cosim behavior
5. Hand off to `the cosim runtime references (`references/cosim/`)` when the platform is built and the user is now debugging
   `hw_emu`, QEMU PMC/APU startup, remote-port, AIE SystemC bridge, or runtime behavior.

When invoked as a sub-agent by `the cosim runtime references (`references/cosim/`)`:
- keep the answer scoped to the VCK190 platform stage
- report the exact artifact that unblocks later emulation work
- state explicitly when ownership should return to `the cosim runtime references (`references/cosim/`)`

## Fast Triage

- If the user does not yet have an XSA, stay in hardware-platform mode.
- If the XSA exists but boot files, DTB, rootfs, AIE domain, or platform packaging are missing, stay in software-platform mode.
- If the `.xpfm` exists but applications do not build or `platforminfo` is wrong, stay in validation mode.
- If the platform builds but `hw_emu`, QEMU (PMC or APU instance), AIE SystemC, or cosim fails, switch to `the cosim runtime references (`references/cosim/`)`.
- If the user reports PLM IPI issues or AIE debugging hangs, check FAQ: these are known Versal-specific failure modes.

## Reference Selection

### `references/vck190/tutorial-overview.md`

Load for the overall purpose of the tutorial, stage ordering, expected artifacts, Versal-specific naming conventions, and the boundary between this skill and `the cosim runtime references (`references/cosim/`)`.

### `references/vck190/hardware-platform.md`

Load for the Vivado-side work: CIPS configuration, NOC DDR4/LPDDR4 setup, ddr.xdc constraints, XSA export expectations, and TLM simulation model requirements for hw_emu.

### `references/vck190/software-platform.md`

Load for Versal Linux common image, boot artifacts (bl31.elf, u-boot.elf), DTB auto-generation, AIE domain setup, and the `platform_creation.py` Vitis API flow.

### `references/vck190/validation-and-iteration.md`

Load for `platforminfo` validation, vadd and AIE adder application builds, hw_emu run flow, and deciding which step to rerun after hardware or software changes.

## Output Style

- Separate hardware-platform issues from software-platform issues.
- Distinguish Versal-specific concerns (PLM, AIE domain, dual-NOC, CIPS) from generic Vitis platform issues.
- Name the concrete file or artifact that should exist next.
- Prefer stage-based guidance over generic platform advice.
- Explicitly say when the task has crossed into `the cosim runtime references (`references/cosim/`)` territory.
- When the platform is ready, hand back to `the cosim runtime references (`references/cosim/`)` with the next emulation artifact to inspect.
