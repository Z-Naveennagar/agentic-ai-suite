<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Input Contract

This document defines strict, enforceable inputs for the Vitis Embedded App Generator skill.

## Required Inputs
- `inputs.xsa_path`: path to an existing `.xsa` file.
- `inputs.srs_path`: path to a markdown software requirements specification file.
- `inputs.execution_mode`: one of `plan-only` or `apply`.

## Optional Inputs
- `inputs.vitis_reference_doc`: path to README/PDF describing Vitis API/CLI usage for the installed tool version.
- `inputs.preferred_os`: one of `baremetal`, `freertos`, `linux`.
- `inputs.preferred_cpu`: one of `apu`, `rpu`, `microblaze`, plus optional core index.
- `inputs.preferred_domain_name`: explicit Vitis domain name.
- `inputs.workspace_path`: output workspace path.
- `inputs.max_retries`: integer, default `5`, range `0..10`.
- `inputs.build_profile`: one of `debug`, `release`.
- `inputs.optimization`: one of `O0`, `O1`, `O2`, `O3`, `Os`.

## XSA Path Validation Rules
`inputs.xsa_path` must satisfy all:
1. File exists and is readable.
2. Extension is exactly `.xsa` (case-insensitive).
3. File size is greater than 0 bytes.
4. Hardware parsing succeeds and yields minimum required facts:
   - At least one supported processor.
   - At least one executable memory region.
   - Peripheral inventory with base addresses for requested interfaces.

If any rule fails, return `PREREQ_XSA_INVALID` or `HW_MODEL_INCOMPLETE`.

## SRS Markdown Format Expectations
The SRS file must be markdown and should include these sections:
- `# Software Requirements Specification`
- `## Functional Requirements`
- `## Non-Functional Requirements`
- `## Acceptance Criteria`

Allowed requirement item formats:
- `- [FR-001] Requirement text`
- `- FR-001: Requirement text`
- `- Requirement text` (ID auto-generated)

Optional metadata line per requirement:
- `Owner: ...`
- `Priority: P0|P1|P2|P3`
- `Verification: build|test|review|analysis`

## Deterministic ID Policy for Missing IDs
When IDs are missing, assign stable IDs in parse order:
- Functional: `FR-001`, `FR-002`, ...
- Non-functional: `NFR-001`, `NFR-002`, ...
- Acceptance: `AC-001`, `AC-002`, ...

Stability rules:
- Preserve user-specified IDs.
- Preserve source anchors (`source_heading`, `source_line_start`).
- Re-run over unchanged file must produce same generated IDs.

## Allowed OS and CPU Values
- OS: `baremetal`, `freertos`, `linux`
- CPU family: `apu`, `rpu`, `microblaze`
- Core index: non-negative integer when applicable.

## Defaulting Rules (When OS/Domain Is Omitted)
1. If exactly one feasible OS/domain exists for requested features, select it.
2. Else apply preference order: `baremetal` -> `freertos` -> `linux`.
3. If multiple CPUs are feasible, choose first deterministic sort order by `(cpu_family, core_index)`.
4. Emit selected values and rationale in `report/summary.json` under `selection`.

## Vitis API Reference Requirement
- Preferred path: `inputs.vitis_reference_doc`.
- If omitted, the skill may use curated local reference docs under `skills/references/api/`.
- If neither source is usable for detected Vitis version, fail with `PREREQ_DOC_MISSING`.

## Prerequisite and Tooling Checks
The run must verify:
1. Supported Vitis version (see `compatibility_matrix.md`).
2. Supported Python runtime.
3. Required environment variables are present.
4. Tool invocation and license availability checks pass.

## Example
See `input_example.json` for a concrete valid payload.
