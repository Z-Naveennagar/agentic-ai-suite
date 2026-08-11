<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Setup And Variants

## Scope

Load this file when the user is bringing up a flow, comparing device families, inspecting `launch_hw_emu.sh`, or recreating a standalone cosim setup.

## Device-Family Differences

### Zynq-7000

- single QEMU instance for the PS
- PL runs in RTL simulation
- cosim DTB generation is platform-specific
- timing knobs and boot setup differ from Versal

### Zynq UltraScale+ MPSoC

- single AArch64 QEMU instance
- no AIE and no Versal-style NoC stack
- simpler than Versal, but still depends on matching cosim DTB and simulator wiring

### Versal Gen1

- two QEMU instances: PMC and APU
- PL in RTL simulation
- AIE in SystemC
- NoC in TLM by default for cosim
- common example board families include VCK190

### Versal Gen2

- three QEMU instances: PMC, APU, and ASU
- newer boot flow and DTB set
- common example board families include VEK385
- flow often uses EDF-style packaging and login orchestration

### VSS CoSim

This is a separate flow for AIE plus PL designs without QEMU. Use it when the design does not need PS software execution and the user is working from a Vitis subsystem flow.

## Required Vivado Settings

Two settings are central for QEMU-driven cosim:

```tcl
set_property preferred_sim_model "tlm" [current_project]
set_param bd.generateHybridSystemC true
```

Also inspect per-IP simulation model selection when relevant:

```tcl
get_property ALLOWED_SIM_MODELS [get_bd_cells /axi_noc_0]
set_property SELECTED_SIM_MODEL tlm [get_bd_cells /axi_noc_0]
```

Important constraint:
- if the NoC participates in cosim with shared DDR backing, keep the NoC in TLM where the flow expects that model

## Vivado Outputs

Vivado can generate the simulation side without launching the run:

```tcl
launch_simulation -scripts_only
```

Expect outputs such as:
- `sim_tlm/`
- generated SystemC wrapper content
- `<top>_sim_wrapper`
- simulator compile and elaborate scripts

If those artifacts are absent, the design was likely not exported with the right simulation content.

## What `launch_hw_emu.sh` Usually Does

The generated launcher often handles:

- starting the QEMU instances
- setting the machine path and cosim connection settings
- starting XSIM or a supported third-party simulator
- passing optional flags for waveforms or transaction logging
- arranging embedded software execution inside the guest

Common launch options to remember:
- `-g`
- `-aie-sim-options ...`
- `-xtlm-aximm-log`
- `-run-app ...`
- `-user-pre-sim-script ...`
- `-no-reboot`

When a user asks where a behavior comes from, check the generated launcher before assuming it is hardcoded in QEMU or Vivado.

## Packaged Flow Versus Standalone Flow

### Vitis-Packaged Flow

Use this when the user has a standard acceleration or packaged platform flow.

Typical properties:
- `v++ --link` and `v++ --package` generate the orchestration
- boot images, DTBs, and simulation wrappers are assembled for the user
- failures are often hidden behind generated scripts and intermediate artifacts

### Standalone Flow

Use this when the user wants to debug below the Vitis layer or bring up custom hardware manually.

Minimal standalone outline:

1. Enable TLM and hybrid SystemC generation in Vivado.
2. Generate simulation scripts and wrappers.
3. Generate or collect QEMU boot artifacts and the correct cosim DTBs.
4. Launch QEMU separately from the simulator.
5. Attach software or deploy test applications independently.

Treat standalone bring-up as rebuilding the orchestration that Vitis normally synthesizes.

## Hidden Hand-Off Areas To Check

When setup fails, inspect these transitions explicitly:

1. block design settings produce the needed simulation models
2. simulation content is exported into the generated outputs or XSA
3. QEMU boot artifacts exist and match the target device family
4. DDR backing files are generated and consistent
5. launcher arguments line up with actual file locations and machine-path sockets

## VSS-Only Note

In VSS cosim:
- there is no QEMU
- the AIE SystemC model and PL RTL run directly under the simulator
- a user-written or generated testbench drives the flow

Do not apply remote-port or QEMU debugging advice to VSS-only requests unless the design also includes PS emulation.
