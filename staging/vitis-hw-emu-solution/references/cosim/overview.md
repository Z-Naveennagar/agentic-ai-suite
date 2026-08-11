<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Vitis Cosim

## Overview

Treat Vitis `hw_emu` as a distributed co-simulation system, not as a single command. Start by identifying the device family, the generated artifacts, and the failing boundary between QEMU, the RTL simulator, and the SystemC/TLM infrastructure.

Use this skill as the top-level orchestration layer for the Vitis cosim skill family:
- keep cosim, QEMU, remote-port, DTB-overlay, and runtime-boundary work here
- delegate platform-construction and pre-cosim validation work to platform-specific sub-agents
- pull the task back here once the platform is validated and the issue is in `hw_emu` or runtime interaction

## Workflow

1. Classify the request:
   - architecture or explanation
   - bring-up or setup
   - debug or failure analysis
   - custom flow or standalone cosim
   - cross-stage orchestration across platform build and cosim
2. Identify the platform and flow:
   - Zynq-7000
   - Zynq UltraScale+ MPSoC
   - Versal Gen1
   - Versal Gen2
   - VSS-only AIE+PL flow
   - XSIM or 3rd-party simulator
   - Vitis-packaged or standalone
3. Decide whether a platform sub-agent should own the current stage:
   - if the XSA, boot artifacts, DTB, `.xpfm`, or sample-app validation are incomplete, hand off to the relevant platform sub-agent
   - if the platform is already validated and the issue is in `launch_hw_emu.sh`, QEMU, remote-port, simulator behavior, or PS/PL runtime interaction, stay in `the cosim runtime references (`references/cosim/`)`
   - if the request spans both stages, sequence the work: platform sub-agent first, then `the cosim runtime references (`references/cosim/`)`
4. Ask for or inspect the smallest useful artifact set:
   - `launch_hw_emu.sh`
   - `qemu_args.txt`
   - `pmc_args.txt`
   - cosim DTB path
   - Vivado Tcl or XSA generation settings
   - simulator transcript, waveforms, or `xsc_report.log`
5. Build a boundary map before proposing a fix:
   - launcher generation
   - QEMU APU, PMC, and ASU boot chain
   - QEMU to simulator remote-port connection
   - PS to PL, NoC, and AIE bridges
   - shared DDR backing files
6. Load only the reference needed for the task:
   - `references/cosim/architecture.md`
   - `references/cosim/setup-and-variants.md`
   - `references/cosim/debugging.md`
   - `references/cosim/gaps-and-improvements.md`
7. Produce an actionable answer:
   - state the most likely failing interface
   - name the exact file, flag, env var, or generated artifact to inspect next
   - propose the smallest validating experiment

## Fast Triage

- If the system fails before the app runs, inspect launcher generation, boot artifacts, QEMU arguments, and DTB selection.
- If PL never sees PS traffic, inspect remote-port channel mapping, simulator startup order, and whether the Vivado design uses TLM where cosim requires it.
- If DDR contents differ between QEMU and the simulator, compare `ddr_memspec.dtsi` against `noc_memory_config.txt`.
- If QEMU exits or hangs with little diagnostic output, inspect remote-port socket paths, sync behavior, and QEMU trace options.
- If the user wants a custom or non-Vitis flow, reconstruct the hidden hand-off steps that `v++ --link` and `v++ --package` normally automate.
- If the user is still building the board platform itself, switch to the matching platform's references (`references/zcu104/`, `references/vck190/`, `references/vek280/`, or `references/edf/`) before spending time on cosim symptoms.

## Expected Inputs

- Generated Vitis package files or package directory contents
- Vivado block-design Tcl or simulation settings
- QEMU command lines, DTBs, or boot images
- Simulator logs, waveforms, or TLM logs
- Target board or device name and simulator choice

## Reference Selection

### `references/cosim/architecture.md`

Load for overall PS/PL/AIE/NoC architecture, startup sequencing, remote-port protocol concepts, device-tree structure, and DDR sharing.

### `references/cosim/setup-and-variants.md`

Load for device-family differences, Vivado simulation-model settings, generated `launch_hw_emu.sh` behavior, standalone cosim setup, and VSS-specific flow notes.

### `references/cosim/debugging.md`

Load for debugger attachment, waveform and transaction logging, common failure signatures, and stepwise debug tactics.

### `references/cosim/gaps-and-improvements.md`

Load when planning custom hardware flows, documenting what Vitis hides, or proposing infrastructure improvements and validation tooling.

### Platform build vs cosim runtime

This `references/cosim/` set covers the **emulator runtime** (QEMU, remote-port, DTB overlays, SystemC). When the task is still about building a board's platform or the EDF image, switch to that platform's references (`references/zcu104/`, `references/vck190/`, `references/vek280/`, `references/edf/`). The umbrella `SKILL.md` is the authoritative router.

## Output Style

- State assumptions explicitly when artifacts are missing.
- Use exact filenames, flags, ports, and environment variables when known.
- Separate confirmed facts from inference.
- Prefer a concrete next step over a broad summary.
- When routing to a platform sub-agent, say why the current bottleneck is still pre-cosim.
