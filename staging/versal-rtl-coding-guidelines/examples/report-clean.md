<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Verification Report Template

Use this as a schema, not as evidence from a real run. Replace every placeholder and attach or
reference the raw artifacts produced by the selected tools.

## Scope

- Module/top: `<name>`
- Target part: `<versal-part>`
- Vivado version: `<version>`
- Source revision: `<revision>`
- Requested clocks, latency, throughput, reset, and protocol requirements: `<requirements>`

## Files changed

- `<path>` — `<reason>`

## Documentation applied

| Topic | AMD guide/section | Design-specific decision |
|---|---|---|
| `<topic>` | `<document and section>` | `<decision and configuration dependency>` |

## Verification evidence

| Check | Command/tool | Raw artifact | Expected | Observed | Result |
|---|---|---|---|---|---|
| Lint | `synth_design -lint ...` | `<lint.rpt>` | `<criteria>` | `<observation>` | PASS/FAIL |
| Mapping | Vivado synthesis queries | `<utilization.rpt>` | `<primitive/latency>` | `<observation>` | PASS/FAIL |
| CDC/XDC | CDC, exception coverage, methodology | `<reports>` | `<criteria>` | `<observation>` | PASS/FAIL |
| Timing | timing summary/design analysis | `<reports>` | `<clock requirement>` | `<observation>` | PASS/FAIL |
| Functional | simulation/formal/protocol checker | `<artifact>` | `<properties>` | `<observation>` | PASS/FAIL |

## Limitations and open findings

- `<check not run, warning justified, or unresolved requirement>`

Do not declare readiness from file existence, primitive counts, `DONT_TOUCH`, or a clean DRC
alone. State "unverified RTL review" when required Vivado or functional checks were not run.
