<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Vitis Cosim ZCU104 Platform

## Overview

Use this skill to build or review the ZCU104 platform-creation flow that sits upstream of `hw_emu` and cosim. Keep this skill focused on platform construction and validation; when the user reaches emulator launch, `launch_hw_emu.sh`, DTB issues, or PS/PL runtime behavior, hand off to `the cosim runtime references (`references/cosim/`)`.

In the agent hierarchy:
- `the cosim runtime references (`references/cosim/`)` is the top-level orchestrator
- `the ZCU104 references (`references/zcu104/`)` is the ZCU104 platform sub-agent

## Workflow

1. Classify the request:
   - hardware platform creation
   - software platform assembly
   - platform validation
   - iteration after a hardware or software change
2. Ask for or inspect the core artifacts:
   - Vivado project or block-design Tcl
   - exported XSA
   - boot components and Linux image inputs
   - generated `.xpfm`
   - platform metadata or `platforminfo` output
3. Work through the tutorial stages in order:
   - Step 1: create hardware and export the platform hardware
   - Step 2: assemble the software platform and boot artifacts
   - Step 3: validate the platform with an application
   - iteration: regenerate only the layers affected by the change
4. Keep the outputs explicit:
   - identify the exact missing or stale artifact
   - name which stage must be rerun
   - state whether the issue is pre-cosim platform construction or actual cosim behavior
5. Hand off to `the cosim runtime references (`references/cosim/`)` when the platform is built and the user is now debugging `hw_emu`, QEMU, remote-port, DTBs for cosim, or runtime PS/PL interaction.

When invoked as a sub-agent by `the cosim runtime references (`references/cosim/`)`:
- keep the answer scoped to the ZCU104 platform stage
- report the exact artifact that unblocks later emulation work
- state explicitly when ownership should return to `the cosim runtime references (`references/cosim/`)`

## Fast Triage

- If the user does not yet have an XSA, stay in hardware-platform mode.
- If the XSA exists but boot files, DTB, rootfs, or platform packaging are missing, stay in software-platform mode.
- If the `.xpfm` exists but applications do not build or `platforminfo` is wrong, stay in validation mode.
- If the platform builds but `hw_emu` or cosim fails, switch to `the cosim runtime references (`references/cosim/`)`.

## Reference Selection

### `references/zcu104/tutorial-overview.md`

Load for the overall purpose of the tutorial, stage ordering, expected artifacts, and the boundary between this skill and `the cosim runtime references (`references/cosim/`)`.

### `references/zcu104/hardware-platform.md`

Load for the Vivado-side work: hardware design scope, export expectations, and what to verify before moving to software packaging.

### `references/zcu104/software-platform.md`

Load for Linux and boot artifacts, software-platform assembly, and the inputs that become the platform package.

### `references/zcu104/validation-and-iteration.md`

Load for `platforminfo`, sample-application validation, and deciding which step to rerun after a change.

## Output Style

- Separate hardware-platform issues from software-platform issues.
- Name the concrete file or artifact that should exist next.
- Prefer stage-based guidance over generic platform advice.
- Explicitly say when the task has crossed into `the cosim runtime references (`references/cosim/`)` territory.
- When the platform is ready, hand back to `the cosim runtime references (`references/cosim/`)` with the next emulation artifact to inspect.
