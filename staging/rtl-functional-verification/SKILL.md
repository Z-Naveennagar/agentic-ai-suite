---
name: rtl-functional-verification
description: Plan, build, run, diagnose, and report self-checking functional verification for Verilog or SystemVerilog RTL. Use for verification plans, testbenches, cocotb with open-source Verilator, XSim behavioral simulation, Python or NumPy reference models and vectors, assertions, scoreboards, directed or seeded-random tests, functional or code coverage, regression automation, waveform-based failure triage, and requests to prove RTL behavior before synthesis. Prefer cocotb plus Verilator for fast portable pure-RTL testing, XSim plus SystemVerilog for AMD IP and four-state behavior, or a hybrid XSim plus Python-vector flow.
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# RTL Functional Verification

Verify behavior against an explicit contract. Do not equate compilation, simulator exit, elapsed
time, or code coverage with functional correctness.

## Load only the relevant guidance

- Read [references/backend-selection.md](references/backend-selection.md) before choosing a flow.
- Read [references/verification-planning.md](references/verification-planning.md) to derive tests and coverage from requirements.
- Read [references/cocotb-verilator.md](references/cocotb-verilator.md) for live Python verification of portable Verilog or SystemVerilog.
- Read [references/xsim-systemverilog.md](references/xsim-systemverilog.md) for AMD-native, mixed-language, X/Z-sensitive, XPM, primitive, or IP simulation.
- Read [references/xsim-python-vectors.md](references/xsim-python-vectors.md) when Python supplies stimulus or a reference model while an HDL testbench drives XSim.
- Read [references/assertions-coverage.md](references/assertions-coverage.md) when adding temporal checks, functional coverage, code coverage, or exclusions.
- Read [references/result-contract.md](references/result-contract.md) before declaring PASS or integrating a regression with CI.

## Core workflow

### 1. Establish the contract

Inspect the specification, RTL, interfaces, parameters, clocks, resets, latency, throughput,
backpressure, errors, and legal configuration changes. Record uncertainties instead of inventing
behavior. Ask only when an unresolved choice would materially change the test oracle.

Create a verification matrix that maps every applicable requirement to:

- stimulus and corner cases;
- an observable result;
- a checker or reference model;
- temporal assertions;
- functional coverage;
- one or more named tests.

State exclusions and system-level boundaries. Verification is incomplete when a requirement has
neither a check nor a justified exclusion.

### 2. Select the backend

Select the smallest backend that satisfies the design:

1. Use **cocotb + Verilator** for fast live-Python verification of portable synthesizable RTL.
2. Use **XSim + SystemVerilog** for AMD models, encrypted IP, mixed HDL, four-state behavior,
   broader simulator semantics, or Vivado project integration.
3. Use **XSim + Python vectors** when Python or NumPy is the natural golden model but live Python
   control is unnecessary.
4. Use a **two-tier regression** for AMD production RTL: broad fast testing with Verilator, then
   a focused XSim compatibility and X/Z-sensitive suite.

Do not silently replace one backend with another. Report capability gaps before changing the
verification strategy.

### 3. Build a self-checking environment

Generate only what the selected plan needs:

- clock and reset drivers;
- interface drivers and monitors;
- transactions and deterministic seed handling;
- a scoreboard or reference model;
- protocol and design assertions;
- functional coverage;
- watchdogs and bounded waits;
- focused waveform capture;
- machine-readable results.

Prefer a lean testbench for a block-level DUT. Use transaction classes or a reusable verification
component when multiple tests share protocol behavior. Do not introduce UVM unless the requested
environment or scale justifies it.

Keep cycle-precise invariants close to the DUT as supported SystemVerilog assertions. Use Python
for transaction generation, data science reference models, orchestration, and reporting.

### 4. Test risk, not just nominal behavior

Select applicable categories:

- power-up, reset assertion/deassertion, reset during traffic, and first legal transaction;
- minimum, maximum, boundary, illegal, and unknown inputs;
- backpressure, pipeline fill/drain, bubbles, latency, and sustained throughput;
- simultaneous operations, arbitration, ordering, and resource exhaustion;
- overflow, underflow, saturation, rounding, truncation, and signedness;
- framing, partial beats, packet boundaries, and metadata alignment;
- error injection, reporting, containment, and recovery;
- configuration changes while idle and active;
- deadlock, livelock, missing response, and timeout;
- long seeded-random traffic and reproducibility.

Avoid random stimulus without an oracle and coverage model.

### 5. Run incrementally

Run in this order:

1. compile and elaborate;
2. reset and smoke test;
3. directed feature tests;
4. corner and error tests;
5. seeded-random regression;
6. assertion and functional-coverage review;
7. code-coverage review and justified exclusions;
8. alternate-backend compatibility tests when required.

Stop on infrastructure failures. Distinguish DUT failures, testbench failures, unsupported
constructs, timeouts, and simulator crashes.

### 6. Diagnose failures

Preserve the backend, tool version, test, seed, parameters, command, first causal error, and
artifacts. Reproduce the smallest failing test. Add focused waves only for clocks, resets,
interfaces, checker state, and suspected logic.

Decide whether the specification, DUT, checker, stimulus, reference model, or backend assumption
is wrong. Do not modify RTL unless the user requested a fix. After a fix, rerun the failing test,
the affected feature group, reset tests, and a proportional regression.

### 7. Enforce honest PASS

Require all of the following:

- compile and elaboration succeeded;
- simulator process completed successfully;
- an explicit terminal PASS condition was observed;
- zero failed checks and unexpected assertion failures;
- no timeout or premature finish;
- every required test ran;
- results match the verification plan;
- required coverage was reviewed, not merely generated;
- exclusions and unverified boundaries are listed.

Validate normalized JSON with `scripts/verify_result.py`. Use `scripts/detect_backends.py` before
planning a runnable flow. Treat detection as discovery, not proof of readiness: compile and
elaborate a representative smoke test, including required vendor libraries or IP, before reporting
a backend ready for the design. Never write a PASS summary unconditionally after launching a
simulator.

## Deliverables

Return:

- the requirement-to-test matrix;
- sources and reproducible run commands;
- backend and version;
- test and seed results;
- assertion failures or PASS counts;
- functional and code coverage with exclusions;
- waveform and log paths for failures;
- remaining risks and unverified boundaries;
- the normalized result JSON.

For a multi-tier regression, emit and validate one result object per backend. Create a separate
rollup that references those results and passes only when every required tier passes; do not merge
unexecuted or unsupported tiers into a single backend result.

Do not claim CDC correctness, timing closure, formal proof, equivalence, safety compliance,
security assurance, or hardware validation from functional simulation alone.
