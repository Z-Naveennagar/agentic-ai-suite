<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# cocotb with Verilator

Use this backend for live Python verification of portable synthesizable Verilog/SystemVerilog.
Current cocotb documentation supports Verilator 5.036 or later; detect the installed versions and
use their matching documentation rather than assuming a version.

## Build and test

Prefer the cocotb Python runner so Windows and Linux do not depend on GNU Make syntax. Copy and
adapt `assets/cocotb-verilator/runner.py`.

Keep these artifacts per test or seed:

- build and simulator logs;
- `results.xml` or equivalent JUnit result;
- seed and parameters;
- FST/VCD only on request or failure;
- coverage data when enabled;
- normalized result JSON.

Use `--timing` when the RTL or HDL helper uses delays, event controls, waits, or forks. Enable
assertions explicitly. Enable trace and coverage only when needed because both add runtime cost.

## Test structure

Use pytest for build/test selection and cocotb coroutines for simulated behavior. Separate:

- drivers that own signal writes;
- monitors that reconstruct accepted transactions;
- an independent reference model;
- a scoreboard that compares ordered or tagged results;
- test orchestration and timeouts.

Use `cocotb.start_soon(Clock(...).start())`, `RisingEdge`, `Timer`, and bounded async waits. Avoid
wall-clock sleeps for simulated behavior.

Treat `dut.signal.value` as a logic value, not an ordinary integer, until unknown handling is
resolved. Preserve width, signedness, byte order, and ready/valid acceptance rules.

## Verilator limitations

Verilator is primarily two-state. Its experimental four-state mode is not a replacement for XSim
X/Z testing. `specify` blocks and timing checks are ignored. Assertions and functional coverage are
partial, and encrypted RTL is unavailable. Vendor models may use unsupported constructs.

Therefore:

- randomize uninitialized-state substitutions when useful, but do not call that X-propagation;
- run reset and unknown-sensitive tests in XSim;
- keep synthesizable cycle assertions portable where possible;
- do not use this backend for post-layout timing simulation;
- fail preflight if required AMD models do not compile.

## Coverage

Enable Verilator line, expression, toggle, FSM, or user coverage deliberately. Write a unique
coverage file per test or seed, then merge with `verilator_coverage`. Preserve raw databases and
report exclusions. Python `coverage.py` measures Python execution and is not RTL code coverage.

## Failure triage

First reproduce with the same seed and no waves. Then enable focused FST tracing. Classify the
failure as DUT, testbench, reference model, unsupported construct, build environment, or two-state
semantic gap. Confirm suspected semantic gaps with the XSim compatibility suite.

## Sources

- https://docs.cocotb.org/en/stable/simulator_support.html
- https://docs.cocotb.org/en/stable/library_reference.html
- https://verilator.org/guide/latest/languages.html
- https://verilator.org/guide/latest/exe_verilator_coverage.html
