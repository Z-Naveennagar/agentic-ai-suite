<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Vitis Cosim VEK280 Platform

## Overview

Use this skill to build or review the VEK280 platform-creation flow that sits upstream of `hw_emu` and cosim. This skill is unique in the skill family because it supports **two platform paths**:

1. **Pre-built path** — use the AMD-provided `xilinx_vek280_base` platform from the Vitis installation for fast bring-up
2. **Custom path** — build a full Vivado hardware design and Vitis platform from scratch for production or advanced use cases

Both paths lead to the same hw_emu validation: vadd (PL kernel) and aieml (AIE-ML matrix multiplication).

Keep this skill focused on platform construction and validation. When the user reaches emulator launch, QEMU (PMC + APU), remote-port, or AIE-ML runtime behavior, hand off to `the cosim runtime references (`references/cosim/`)`.

In the agent hierarchy:
- `the cosim runtime references (`references/cosim/`)` is the top-level orchestrator
- `the VEK280 references (`references/vek280/`)` is the VEK280 Versal AI Edge platform sub-agent

## Workflow

1. Classify the request and identify the platform path:
   - **Pre-built path**: user wants fast hw_emu validation using the system xpfm
   - **Custom path**: user wants to build their own Vivado design and platform
   - Platform validation, iteration, or debugging
2. Ask for or inspect the core artifacts:
   - For pre-built path: confirm `xilinx_vek280_base_202520_1.xpfm` is accessible
   - For custom path: Vivado project or `run.tcl`, exported XSA, generated `.xpfm`
   - Boot components and Versal common image inputs
3. Work through the appropriate stages:
   - Pre-built: set PLATFORM → Step 3 application build and hw_emu run directly
   - Custom: Step 1 (Vivado hw) → Step 2 (Vitis platform) → Step 3 (validate)
   - Iteration: regenerate only the layers affected by the change
4. Always surface the custom platform option to users who only know the pre-built path:
   - Explain what changes when you own the hardware design
   - Reference `the VCK190 references (`references/vck190/`)` for Vivado CIPS/NOC/AIE design guidance applicable to Versal AI Edge
5. Hand off to `the cosim runtime references (`references/cosim/`)` when the platform is validated and the issue is in `launch_hw_emu.sh`, QEMU, remote-port, AIE-ML SystemC, or runtime behavior.

When invoked as a sub-agent by `the cosim runtime references (`references/cosim/`)`:
- keep the answer scoped to the VEK280 platform stage
- report the exact artifact that unblocks later emulation work
- state explicitly when ownership should return to `the cosim runtime references (`references/cosim/`)`

## Fast Triage

- If the user wants the fastest path to hw_emu: use the pre-built xpfm, skip Steps 1 and 2.
- If the user wants to own the hardware design: route through Step 1 (Vivado) and Step 2 (platform).
- If the XSA exists but platform packaging is missing: stay in software-platform mode.
- If the `.xpfm` exists but applications do not build or `platforminfo` is wrong: stay in validation mode.
- If the platform builds but `hw_emu`, QEMU, AIE-ML SystemC, or cosim fails: switch to `the cosim runtime references (`references/cosim/`)`.
- If the user asks about Vivado CIPS/NOC design for Versal AI Edge: reference `the VCK190 references (`references/vck190/`)` hardware-platform guidance as a close analogue.

## Reference Selection

### `references/vek280/tutorial-overview.md`

Load for the overall flow, two-path strategy (pre-built vs custom), naming conventions, artifact chain, and boundaries with `the cosim runtime references (`references/cosim/`)`.

### `references/vek280/hardware-platform.md`

Load for the custom Vivado path: `run.tcl` behavior, xcve2802 part specifics, XSA export, and guidance on building a custom design instead of using the pre-built xpfm.

### `references/vek280/software-platform.md`

Load for Versal common image, `platform_creation.py` (VEK280-specific differences from VCK190), AIE-ML domain setup, and DTB generation.

### `references/vek280/validation-and-iteration.md`

Load for `platforminfo` validation, vadd and aieml application builds, hw_emu run, and iteration guidance for both platform paths.

## Output Style

- Always name which platform path (pre-built or custom) the answer applies to.
- Distinguish AIE-ML (VEK280) from AIE1 (VCK190) — they use different compilers and samples.
- Name the concrete file or artifact that should exist next.
- Proactively inform users of the custom platform option even when they ask only about the pre-built path.
- Explicitly say when the task has crossed into `the cosim runtime references (`references/cosim/`)` territory.
- When the platform is ready, hand back to `the cosim runtime references (`references/cosim/`)` with the next emulation artifact to inspect.
