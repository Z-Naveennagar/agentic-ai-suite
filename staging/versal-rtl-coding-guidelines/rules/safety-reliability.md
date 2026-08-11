<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Safety and Reliability Guidelines

Sources: AM007 memory ECC capabilities, UG901 synthesis attributes/FSM safe state, UG1387
methodology, and the applicable product safety documentation. These techniques support a
safety case; no single Vivado report proves compliance with ISO 26262, DO-254, or another
standard.

## SAF-1 — Configure and test ECC deliberately

Use a BRAM/UltraRAM/XPM configuration that supports the required ECC mode, width, latency,
scrubbing, and error-reporting behavior. Instantiate all required ports and parameters from
the applicable XPM or primitive template. Verify single-bit correction, double-bit detection,
status handling, and any injection interface in simulation.

A URAM/BRAM primitive count does not prove ECC is enabled.

## SAF-2 — Preserve and separate redundancy

`DONT_TOUCH` can prevent selected optimization, but AMD warns that it can inhibit retiming,
replication, RAM absorption, and other QoR optimizations. Use it only where netlist analysis
shows that a required redundant cone or voter would otherwise be removed or merged.

A TMR acceptance check must establish:

- three functionally independent logic cones survived synthesis;
- voter placement/topology meets the architecture;
- physical separation and common-mode risks are addressed;
- configuration-memory mitigation is included where required; and
- fault injection demonstrates detection or recovery.

Counting `DONT_TOUCH` cells is not a TMR proof.

## SAF-3 — Implement safe-state recovery in hardware

When an FSM must recover from illegal encodings, combine a defined default transition with the
UG901 `FSM_SAFE_STATE` attribute that matches the required destination, then inject illegal
states or prove recovery formally. A default case alone can be optimized under normal FSM
assumptions.

## SAF-4 — Protect control and stored data according to the fault model

Use parity, CRC, duplication, ECC, watchdogs, or end-to-end protection according to the
specified fault model and diagnostic coverage. Verify coverage, latency, error containment,
and reset/recovery behavior. Do not infer safety coverage solely from the presence of a CRC or
parity bit.

## SAF-5 — Reset supervisory state; qualify datapath validity

Reset control and supervisory state that must start deterministically. Wide datapath registers
can remain unreset when the architecture invalidates or flushes their data. Verify that no
uninitialized datapath value can be consumed as valid.

## Checklist

- [ ] The fault model and required diagnostic coverage are stated.
- [ ] ECC mode and error paths are configured and injected in simulation.
- [ ] Redundant cones, voters, and physical separation are verified independently.
- [ ] Required FSM recovery uses `FSM_SAFE_STATE` and is fault-injected.
- [ ] Supervisory state resets deterministically and datapath validity is controlled.
- [ ] Preservation attributes are used sparingly and not treated as proof.
