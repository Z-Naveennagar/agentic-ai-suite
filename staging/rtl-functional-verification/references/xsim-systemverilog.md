<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# XSim with SystemVerilog

Use XSim for AMD-aware functional verification, four-state behavior, mixed HDL, XPMs, primitives,
IP simulation models, and existing Vivado projects.

## Project flow

1. Open or create the project without changing implementation sources unnecessarily.
2. Add verification sources only to a simulation fileset.
3. Set the simulation top explicitly.
4. Set compile/elaboration options and supported coverage properties explicitly.
5. Update compile order.
6. Launch behavioral simulation.
7. Read an explicit terminal pass signal and simulation messages.
8. Save normalized results, then close the simulation and project.

Copy and adapt `assets/xsim-systemverilog/run_checked_sim.tcl`. A successful
`launch_simulation` return is not sufficient: `$fatal` or an early `$finish` can still leave Tcl
control available. Gate PASS on a testbench terminal flag, zero checker failures, zero unexpected
assertions, and completion of all required tests.

## Testbench rules

Use `timeunit` and `timeprecision` or a deliberate timescale. Initialize testbench controls. Model
clock and reset contracts accurately. Drive protocol payload and valid before the active edge and
sample handshakes according to the interface contract.

Build self-checking monitors and scoreboards. Use `$fatal` for failed checks, a watchdog for every
test, and a terminal `test_pass` set only after all checks complete. Keep pass state observable to
Tcl with `get_value`.

For XPMs or configurable IP, derive the oracle from the instantiated configuration and its
documented simulation behavior. Record material parameters such as memory mode, latency, ECC,
collision behavior, and reset values. Do not infer disabled features from unused-looking ports, and
do not claim behavior for an unconfigured feature such as ECC injection.

Avoid hierarchical force/deposit as normal stimulus. Use it only for a documented fault-injection
or illegal-state test that cannot be expressed through the interface.

## Assertions and coverage

Use only constructs supported by the selected UG900 SystemVerilog feature matrix. XSim supports
concurrent assertions, constrained randomization, functional covergroups, and statement, branch,
condition, and toggle code coverage with documented limitations.

Use `write_xsim_coverage`, `export_xsim_coverage`, or `xcrg` as appropriate. Store raw databases per
run before merging. Coverage generation is not a pass criterion until reviewed against the plan.

## Debugging

Preserve the first failure time and assertion. Add a focused waveform configuration after a failure
or enable WDB capture for the reproduction. Prefer top-level interface signals, checker state, and a
small internal cone. Do not dump the entire hierarchy by default.

## Sources

- https://docs.amd.com/r/en-US/ug900-vivado-logic-simulation/Simulating-with-Vivado-Simulator
- https://docs.amd.com/r/en-US/ug900-vivado-logic-simulation/Test-Bench-Feature
- https://docs.amd.com/r/en-US/ug900-vivado-logic-simulation/Code-Coverage-Support
