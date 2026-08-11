<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Verification Planning

Start from observable requirements. Do not start by writing random stimulus.

## Requirement matrix

Create one row per behavior:

| ID | Requirement | Preconditions | Stimulus | Expected result | Checker | Assertion | Coverage | Tests | Status |
|---|---|---|---|---|---|---|---|---|---|

Use stable IDs so tests, assertions, coverage bins, failures, and waivers trace to the same
requirement.

## Derive the oracle

For each requirement, choose one oracle:

- exact expected value or sequence;
- transaction-level reference model;
- invariant or temporal property;
- protocol checker;
- equivalence to a supplied golden model;
- explicitly justified observational check.

Do not copy the DUT algorithm line-for-line into the reference model. Prefer an independent
formulation, standard library, executable specification, or known vector set.

## Partition tests

Use named groups:

- `smoke`: reset and one legal transaction;
- `feature`: one or more tests per requirement;
- `corner`: boundaries, simultaneous events, and error paths;
- `random`: deterministic seeds with scoreboards and coverage;
- `compatibility`: backend-sensitive X/Z, reset, AMD model, and language tests;
- `long`: throughput, wraparound, exhaustion, and stress.

Every bounded wait needs a timeout and diagnostic. Every random test must print and preserve its
seed. Prefer many short reproducible tests over one opaque long test.

## Plan coverage

Functional coverage measures the specification. Code coverage measures exercised implementation
structure. Neither replaces checking.

Define coverpoints for meaningful values and events. Add crosses only for combinations that affect
behavior. Mark illegal bins only when the specification makes them illegal. Justify exclusions with
a requirement, structural reason, or unreachable proof; never exclude a bin merely to reach a goal.

## Completion review

Before declaring the plan complete, identify:

- unobservable requirements;
- external-system assumptions;
- CDC, analog, timing, security, safety, or physical properties outside simulation scope;
- unsupported simulator features;
- vendor IP that needs a different backend;
- coverage goals and permitted exclusions.
