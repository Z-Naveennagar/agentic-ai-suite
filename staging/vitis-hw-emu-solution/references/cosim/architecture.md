<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Vitis CoSim Architecture

## Scope

Load this file when the user needs to understand how Vitis `hw_emu` is assembled, where processes connect, or which generated artifacts carry the cosim configuration.

## System Model

In Vitis hardware emulation, different compute domains run in different simulators:

| Domain | Engine | Typical model |
|--------|--------|---------------|
| PS | QEMU | Functional |
| PL | XSIM, Xcelium, or Questa | RTL behavioral |
| AIE | SystemC AIE simulator | Cycle-approximate |
| NoC | SystemC TLM or RTL | Cycle-approximate or near-accurate |
| CIPS and SmartConnect | SystemC TLM | Functional or throughput-approximate |

The generated launch flow stitches these pieces together. Do not treat a single tool log as the full system truth.

## Startup Sequence

Use this startup order when reasoning about bring-up failures:

1. `launch_hw_emu.sh` starts.
2. APU QEMU starts first and opens a machine-path directory for sockets.
3. PMC QEMU starts and connects to the APU-side socket.
4. PMC waits for the simulator-side remote-port endpoint.
5. The RTL simulator starts and connects through the expected socket or TCP endpoint.
6. Boot begins:
   - PMC loads PLM and device configuration content
   - PLM configures the device
   - APU boots Linux or baremetal software
   - the host application runs with `XCL_EMULATION_MODE=hw_emu`

If the sequence stops early, identify which process failed to connect to the next boundary.

## QEMU Roles

### PMC QEMU

- Typically emulates the management processor used for boot orchestration.
- Loads PLM, CDO, and boot-header artifacts.
- Usually consumes arguments from `pmc_args.txt`.

### APU QEMU

- Runs Linux or baremetal software for the application processor domain.
- Uses a cosim-specific hardware DTB that contains remote-port nodes.
- Usually consumes arguments from `qemu_args.txt`.
- Common arguments include:
  - `-M arm-generic-fdt`
  - `-sync-quantum ...`
  - `-hw-dtb ...`
  - `-machine-path ...`
  - `-gdb tcp::9000`

### ASU QEMU

- Appears in newer Versal Gen2 flows.
- Adds a third emulated machine for the security subsystem.

## Remote-Port Essentials

Remote-port is the transport between QEMU and the external simulator.

Core properties:
- uses Unix domain sockets or TCP
- transports reads, writes, interrupts, stream traffic, and sync messages
- relies on shared understanding of device-channel numbering
- acts as the PS-to-simulator bridge, not as a general debug layer

Useful mental model:
- QEMU drives functional software execution.
- The simulator owns the PL and part of the platform modeling.
- Remote-port is the boundary where software-visible transactions cross from QEMU into the modeled hardware world.

### Common Socket Conventions

The machine-path directory usually contains socket endpoints such as:

- `qemu-rport-_amba@0_cosim@0`
- `qemu-rport-_pmc@0`

On the simulator side, connection state is often controlled with:

- `COSIM_MACHINE_PATH=unix:<path>`
- `COSIM_MACHINE_TCPIP_ADDRESS=<host:port>`

If one side points to a different socket path, the flow can look like a hang even though the real issue is a mismatch in rendezvous configuration.

## Synchronization Model

QEMU and the simulator synchronize at a configured quantum and also around bus activity.

Practical consequences:
- a large quantum improves speed but can hide timing sensitivity
- a very small quantum improves responsiveness but can slow the run significantly
- active bus traffic can create additional implicit sync points

When debugging hangs, always ask:
- Did QEMU reach the next sync point?
- Did the simulator accept and answer the sync?
- Is one side blocked waiting for a response that the other side never emits?

## Device Trees for Cosim

Cosim requires hardware DTBs that differ from guest Linux DTBs.

Expected properties:
- a `remote-port` compatible node exists
- the node is tied to the correct chardev or socket backend
- channel mappings match what the simulator expects

Typical layering:

- base board DTB
- remote-port overlay
- Vitis-specific overlay

Do not assume a standard board DTB is sufficient. A non-cosim DTB is a common root cause for silent failures.

## Shared DDR Backing

PS software running in QEMU and the NoC or memory model in the simulator must agree on shared DDR backing regions.

The two files to compare are:
- `ddr_memspec.dtsi`
- `noc_memory_config.txt`

If software writes data but the PL side cannot observe it, or vice versa, assume a DDR region mismatch until proven otherwise.

## Generated Artifacts Worth Inspecting

- `launch_hw_emu.sh`
- `qemu_args.txt`
- `pmc_args.txt`
- generated cosim DTB path
- `sim_tlm/` outputs from Vivado
- simulator wrappers such as `<top>_sim_wrapper`
- `ddr_memspec.dtsi`
- `noc_memory_config.txt`

## Boundary-Oriented Questions

Use these questions to anchor analysis:

1. Did the right processes launch in the expected order?
2. Did QEMU use a cosim DTB rather than a standard DTB?
3. Did the simulator bind to the same socket or TCP endpoint that QEMU exposed?
4. Are channel mappings and TLM wrappers present in the generated simulation content?
5. Do both sides agree on shared DDR backing regions?
