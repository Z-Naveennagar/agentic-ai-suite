<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Flow Gaps And Improvements

## Scope

Load this file when the user wants to understand what Vitis automates, why custom flows are brittle, or how the infrastructure could be improved.

## The Hidden Hand-Off Problem

A large part of the cosim flow is implicit when the user stays inside the standard Vitis packaging path. For custom hardware or standalone flows, the user must effectively reconstruct several hidden hand-offs:

1. enable TLM-friendly Vivado design settings
2. generate simulation wrappers and scripts
3. export simulation-capable hardware content
4. generate QEMU boot artifacts and cosim DTBs
5. generate DDR memory-sharing configuration
6. assemble launch scripts and runtime packaging
7. coordinate software deployment and simulator launch order

When the user says, "I can run the hardware but not the cosim flow," assume one of these hand-offs is missing or undocumented.

## Common Structural Gaps

### Component-Level Isolation

There is often no simple public flow for testing only one communication boundary at a time. That makes it hard to isolate whether a failure belongs to:
- an HLS kernel
- a TLM wrapper
- remote-port wiring
- shared memory configuration
- boot orchestration

### Poor Disconnect Diagnostics

Remote-port failures can surface as:
- silent exits
- hangs with little context
- fatal socket errors without precise blame

When explaining a failure, distinguish:
- confirmed disconnect
- suspected simulator-side crash
- likely protocol mismatch
- unproven deadlock

### Custom-Hardware Friction

Custom designs often fail because public tooling focuses on the mainstream Vitis acceleration path. If the user is outside that path, they usually need explicit help reconstructing the launch and configuration artifacts.

## How To Use This In Answers

When a user wants to streamline or productize the flow:

1. name the hidden hand-off that needs tooling
2. state which artifact should be generated or validated automatically
3. propose the smallest validation script or checker that would catch the issue earlier

Examples:
- validate Vivado simulation-model settings before export
- validate DTB selection before launch
- validate DDR backing consistency before boot
- validate remote-port socket rendezvous before running software

## Good Near-Term Improvements

- add a dedicated validation script for Vivado and packaging prerequisites
- enable remote-port tracing by default in debug-focused launch variants
- make disconnect failures return a detectable non-zero exit code
- document the required hand-off steps for nonstandard flows
- provide a supported standalone reference flow for manual bring-up

## Guidance For Custom-Flow Requests

If the user wants a flow without standard Vitis packaging:

- reconstruct the flow as explicit stages
- avoid assuming Vitis generated every required file
- ask for the exact missing artifact rather than generic "setup details"
- separate what must come from Vivado, what must come from QEMU assets, and what the simulator consumes
