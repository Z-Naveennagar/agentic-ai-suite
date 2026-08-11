<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Security-Sensitive RTL Guidance

Vivado synthesis guidance describes implementation attributes and optimization behavior; it
does not by itself prove confidentiality, resistance to side channels, secure zeroization, or
anti-tamper properties. Apply this file only after stating a threat model and consulting the
applicable Versal security architecture and product security documentation.

## SEC-1 — Do not treat preservation as secret protection

`DONT_TOUCH`, `KEEP`, and hierarchy controls preserve selected implementation structures and
can reduce optimization quality. They do not prevent information leakage, replication by
other mechanisms, physical probing, or side-channel observation. Use them sparingly when a
reviewed implementation structure must remain inspectable, and verify the netlist effect.

## SEC-2 — Specify and verify zeroization

Define which state is sensitive, what event triggers clearing, the maximum allowed latency,
clock/reset dependencies, retention domains, and behavior during partial reset or power loss.
Verify zeroization by simulation and, where required, formal or gate-level checks. A preserved
clear net does not prove every physical copy of a secret was cleared.

## SEC-3 — Separate functional timing from side-channel claims

Constant transaction latency can prevent a class of timing leakage, but it does not make a
cryptographic implementation side-channel secure. Data-dependent switching, memory access,
placement, routing, power, EM behavior, faults, and interfaces still require analysis under
the threat model.

Avoid claiming "constant time" from cycle count alone. State exactly which observable was
checked and use the appropriate security evaluation methodology.

## SEC-4 — Verify boundaries and information flow

Use clear hierarchy and interfaces to support review, but do not claim that hierarchy or
control-set separation creates a security boundary. Check access control, reset/clock domain
behavior, debug exposure, information flow, shared resources, and implementation constraints
with security-specific verification.

## Checklist

- [ ] A threat model and sensitive state inventory exist.
- [ ] Zeroization events, coverage, and latency are tested.
- [ ] Preservation attributes have a narrow implementation purpose and measured QoR impact.
- [ ] Timing, power/EM, fault, debug, and information-flow claims are kept distinct.
- [ ] No Vivado structural report is presented as a complete security proof.
