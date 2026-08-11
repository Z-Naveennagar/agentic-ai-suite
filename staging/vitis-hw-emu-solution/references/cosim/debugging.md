<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Debugging Vitis CoSim

## Scope

Load this file when the user reports hangs, disconnects, missing traffic, boot failures, waveform mismatches, or unclear simulator interactions.

## Debug Order

Debug from outside inward:

1. confirm which processes launched
2. confirm each process used the expected files and socket paths
3. confirm the simulator attached to the intended remote-port endpoint
4. confirm the expected traffic crossed the PS-to-PL boundary
5. confirm shared DDR backing and model selection

Do not start with waveform analysis if the launch topology is already broken.

## High-Value Checks

### Launch And Connection

- Verify `launch_hw_emu.sh` launched every expected process.
- Compare the QEMU `-machine-path` against the simulator-side socket or environment variable.
- Verify the DTB is the cosim variant, not the standard board DTB.
- If the flow is Versal Gen2, verify whether ASU and EDF-specific elements are required.

### Traffic Visibility

- If the PS software runs but PL behavior is absent, inspect remote-port endpoint wiring and channel mapping assumptions.
- If AXI traffic appears in software but not in the simulator, enable TLM logging and compare against simulator observations.
- If PL reads stale memory, inspect DDR backing-file configuration first.

### Synchronization

- Suspect quantum and sync issues when the run appears stalled with no fatal error.
- Remember that remote-port synchronization is asymmetric in some implementations, so one side can appear healthy while the other is effectively blocked.

## Useful Debug Facilities

### QEMU GDB Server

QEMU often exposes:

```text
-gdb tcp::9000
```

Use this when the user needs to inspect software execution, early boot state, or guest control flow.

### Waveforms

For XSIM-driven flows, launch with waveform support and add signals through a user pre-sim script if needed.

### TLM Transaction Logging

Use:

```text
-xtlm-aximm-log
```

This is useful when confirming whether the PS side is emitting transactions and whether the simulator-side bridge is seeing them.

### QEMU Trace

If remote-port behavior is suspect, add QEMU tracing for remote-port activity. This is the fastest path to seeing command flow without patching the entire stack.

## Common Failure Signatures

### Symptom: QEMU exits unexpectedly

Likely causes:
- remote-port peer disconnected
- fatal socket error
- protocol or version mismatch

Next checks:
- inspect simulator logs for earlier failure
- inspect whether the socket endpoint disappeared
- add remote-port trace output

### Symptom: Flow hangs during boot

Likely causes:
- socket path mismatch
- cosim DTB mismatch
- simulator never connected
- sync barrier not advancing

Next checks:
- compare `-machine-path` and simulator endpoint
- confirm the DTB includes the remote-port node
- confirm the simulator reached connection setup

### Symptom: Application runs, but hardware behavior is wrong

Likely causes:
- wrong simulation model selection
- DDR memory-sharing mismatch
- incomplete simulator wrapper generation
- wrong board or device-family assumptions

Next checks:
- inspect Vivado TLM settings
- compare DDR config files
- confirm generated wrapper content exists

### Symptom: Gen2 bring-up differs from Gen1 bring-up

Likely causes:
- missing Gen2-specific boot artifacts
- wrong DTB family
- EDF-style workflow assumptions not reflected in the launch setup

Next checks:
- verify board family and boot mode assumptions
- inspect any external qemuboot configuration

## Minimal Triage Questions

Ask these when artifacts are incomplete:

1. Which board or device family is this?
2. Which simulator is being used?
3. Does the run stop before Linux or baremetal software starts, or after that?
4. Do you have `launch_hw_emu.sh`, QEMU args, and simulator logs?
5. Is the failure a hang, an exit, bad data, or missing traffic?

## Smallest Useful Experiments

- Replace the standard DTB with the known cosim DTB and rerun.
- Turn on transaction logging without changing the design.
- Compare socket paths and force both sides to use the same absolute endpoint.
- Reduce the problem to bring-up without the full application.
- Re-run with only the minimal waveform set needed to confirm traffic reaches the wrapper boundary.

## Practical Rule

Always name the failing boundary in the answer. If the boundary is unknown, say so and propose the smallest experiment that distinguishes launch failure, connection failure, synchronization failure, or memory-visibility failure.
