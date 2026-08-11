<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Assertions and Coverage

Use assertions to check temporal invariants and coverage to measure whether planned scenarios were
observed. Neither substitutes for a result oracle.

## Assertion selection

Add applicable properties for:

- reset values and first legal activity;
- stable valid and payload while stalled;
- request/response ordering and bounded completion;
- mutual exclusion and one-hot state;
- legal state transitions;
- FIFO overflow and underflow;
- framing and metadata alignment;
- no unknowns on consumed or externally committed values;
- latency bounds and pipeline conservation.

Give every assertion a stable requirement-based name and useful failure message. Disable it only
under the exact reset or initialization condition in the contract. Avoid unbounded liveness claims
in simulation; use a justified finite bound.

Keep a portable subset for cross-backend tests. Load the selected simulator's supported-feature
matrix before using multiclock properties, advanced sequence features, or testbench-only assertion
constructs.

## Functional coverage

Derive coverpoints from requirements, boundary values, modes, errors, reset interactions, stalls,
and meaningful sequences. Use crosses only where interactions matter. Pair each required bin with
a checker; a covered scenario can still be wrong.

## Code coverage

Review uncovered statement/line, branch, condition/expression, toggle, and FSM items supported by
the backend. Classify each as:

- missing stimulus;
- missing requirement;
- unreachable by construction;
- defensive or error logic requiring injection;
- generated/vendor code outside the goal;
- legitimate exclusion with justification.

Do not set a universal numeric threshold without a project policy. Never exclude code solely to
raise the percentage.

## Cross-backend interpretation

Coverage models and metrics differ between XSim and Verilator. Do not compare percentages as if
they were identical. Trace both to the same requirement matrix and preserve tool-specific raw data.
