---
name: hardware-validation
description: Run portable, authorized on-target validation of FPGA and Adaptive SoC designs using a target capability profile, SSH/Linux control, Vivado Hardware Manager, VIO stimulus/status, ILA capture, and deterministic evidence contracts.
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->


# Hardware Validation

Validate a closed implementation on physical hardware without embedding
lab-specific assumptions in the design contract.

## Required inputs

- PASS `implementation-result.json`
- matching programming image and XSA when required
- matching `.ltx` debug-probes file and debug map
- case `hardware-test.json`
- schema-valid hardware-target profile
- explicit authorization for programming and VIO drive actions

Never store passwords, private keys, tokens, or board-specific secrets in a
run artifact. Target profiles name environment variables or SSH aliases.

## Portability model

The test plan declares required capabilities. The target profile declares
available capabilities. Run only when every mandatory capability is present.
The target profile also contains typed `peripheral_instances`. Match a test to
an instance by kind and capabilities, then verify its physical connector,
route, interface parameters, operator confirmations, and discovery checks.
Keep these states separate:

- `declared`: the operator says the peripheral is connected;
- `discovered`: software or Hardware Manager can inventory it; and
- `validated`: its required functional checks have passed.

Official compatibility evidence can support `declared`; it cannot by itself
promote a peripheral to `discovered` or `validated`.

Use independent adapters:

| Adapter | Responsibilities |
|---|---|
| `vivado_hw_manager` | JTAG target discovery, programming, `.ltx` association, VIO, ILA, JTAG-to-AXI |
| `ssh_linux` | Driver quiesce, overlay/application control, DMA buffers, logs, recovery |
| `linux_fpga_manager` | Deployment-like PL loading and device-tree overlays |
| `external_equipment` | Camera, display, loopback, instruments, or power control explicitly declared by the profile |

SSH reachability never implies JTAG reachability. `hw_server` must run where
the JTAG adapter is physically visible, or on a declared remote lab host.

## Standard test shell

Every hardware-qualified design has:

- one or more VIO cores with safe initial values;
- VIO controls for test reset, enable/start, mode/configuration as needed;
- VIO status for busy, done, pass, and an error code;
- one or more ILA/System ILA cores in each observed clock domain;
- a 1024-sample minimum capture depth;
- an immediate-capture connectivity check;
- a deterministic trigger and bounded capture;
- a logical-to-physical debug probe map; and
- a board-independent self-test path.

VIO is low bandwidth. Do not drive pixel streams, AXI bursts, or sustained
traffic from VIO. Use PS software, DMA, JTAG-to-AXI, or an on-chip traffic
generator; use VIO to configure and start that engine. Use ILA/System ILA to
observe the transaction.

## Required sequence

1. Validate plan and target-profile schemas.
2. Discover SSH and Hardware Manager endpoints read-only.
3. Verify target part, board identity where available, and required equipment.
4. Verify programming-image and probes-file hashes from the same build.
5. Obtain explicit authorization for programming and probe drive.
6. Quiesce drivers and applications named by the plan.
7. Program through the selected backend.
8. Associate the `.ltx`, refresh the device, and inventory actual VIO/ILA cores.
9. Reset or synchronize VIO outputs to their safe design-time values.
10. Trigger one immediate ILA capture to prove debug connectivity.
11. Configure stimulus and the bounded functional trigger.
12. Arm ILA. Drive VIO in a separate Vivado MCP call.
13. Wait with a timeout, upload data, and export CSV or VCD.
14. Read VIO status and PS/software results.
15. Evaluate every mandatory criterion without averaging failures.
16. Restore safe VIO values, stop test software, and record cleanup.
17. Write schema-valid `hardware-validation-result.json`.

## Evidence rules

PASS requires actual values for:

- target identity and transport endpoints used;
- programming image and `.ltx` hashes;
- discovered debug core and probe names;
- VIO values and actions;
- ILA configuration, trigger, status, sample count, and capture path;
- test commands, return codes, measurements, and criterion results; and
- cleanup status.

An implementation-valid image is not hardware-qualified until this stage
passes. Missing equipment or authorization is BLOCKED, not FAIL. A functional
mismatch is FAIL and must be routed to its artifact owner.

For camera validation, establish the sensor/ISP/media topology and pass a
deterministic test-pattern capture before using a live scene. For audio,
validate I2S clocks, framing, channel order, samples, and DMA separately from
the analog path. A microphone on a line input must provide compatible
line-level amplitude or use appropriate bias/preamplification. Internal I2S
activity does not prove that a speaker produced sound. Automated analog
qualification needs a loopback capture path, instrument, or calibrated
microphone; otherwise record bounded manual observation evidence.

## Safety

- Never program, reset, power-cycle, or drive a probe without authorization.
- Never drive a signal whose safe value is not specified.
- Never enable speaker output before confirming a safe line-level load,
  amplification, and initial volume.
- Never expose `hw_server` or credentials in an artifact.
- Never use an unmatched `.ltx`.
- Never wait indefinitely for ILA or software completion.
- Always attempt safe cleanup after a test failure.

## Contracts

- `contracts/hardware-test.schema.json`
- `contracts/hardware-target.schema.json`
- `contracts/hardware-validation-result.schema.json`
- `HARDWARE_VALIDATION_STANDARD_v0.1.md`
