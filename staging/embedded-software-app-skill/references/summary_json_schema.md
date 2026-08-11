<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Summary JSON Schema Contract

`report/summary.json` is a required artifact for both `plan-only` and `apply` modes.

Canonical machine-readable schema:
- `summary.schema.json`

## Required Top-Level Keys
- `run`
- `inputs`
- `selection`
- `hardware_facts`
- `artifacts`
- `requirements_traceability`
- `checks`
- `result`

## Behavioral Rules
1. Every normalized requirement must appear in `requirements_traceability`.
2. Every artifact path listed in `artifacts` must be workspace-relative.
3. `result.status` must be one of `success` or `failure`.
4. On failure, `result.failure` must include code, class, root_cause, and next_steps.
5. In `plan-only`, `checks.build.attempted` must be `false`.
6. In `apply`, `checks.build.attempted` must be `true` unless blocked by feasibility failure.
7. `artifacts.execution_feedback_report` must point to the run feedback markdown file (typically `report/execution_feedback.md`).
8. `artifacts.generate_workspace_script` must point to the generated workspace-creation script (typically `generate_workspace.py`).

## ID Policy Link
Requirement IDs in this file must follow deterministic policy from `input_contract.md`.
