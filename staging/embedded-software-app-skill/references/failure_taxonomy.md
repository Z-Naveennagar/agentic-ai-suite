<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Failure Taxonomy

Use this taxonomy to classify failures consistently and map them to actionable next steps.

## PREREQ Class
- `PREREQ_XSA_INVALID`
  - Meaning: XSA path missing/unreadable/not `.xsa`/empty.
  - Action: Provide valid `.xsa` path and rerun.
- `PREREQ_SRS_INVALID`
  - Meaning: SRS path missing/unreadable/not markdown.
  - Action: Provide valid markdown SRS.
- `PREREQ_DOC_MISSING`
  - Meaning: No user reference doc and no usable local references.
  - Action: Provide Vitis API reference doc or curated local references.
- `PREREQ_DOC_VERSION_MISMATCH`
  - Meaning: Reference commands conflict with detected Vitis behavior and no safe equivalent exists.
  - Action: Provide matching reference for installed version or switch tool version.
- `PREREQ_TOOL_UNAVAILABLE`
  - Meaning: Required Vitis runtime/client/tool invocation unavailable.
  - Action: Fix installation/environment.
- `PREREQ_PYTHON_RUNTIME_MISMATCH`
  - Meaning: selected Python runtime is incompatible with installed Vitis Python packages (for example grpc ABI mismatch).
  - Action: switch to Vitis-bundled runtime and re-validate `import vitis`.
- `PREREQ_PYTHONPATH_INCOMPLETE`
  - Meaning: required Vitis Python module paths are missing from `PYTHONPATH` (for example `cli/proto`).
  - Action: add required Vitis Python/package paths and retry preflight.
- `PREREQ_LICENSE_UNAVAILABLE`
  - Meaning: License/entitlement blocks required operation.
  - Action: Resolve licensing and rerun.

## REQUIREMENTS Class
- `REQ_PARSE_FAILED`
  - Meaning: SRS markdown could not be parsed into required sections.
  - Action: Fix SRS headings/format.
- `REQ_AMBIGUOUS_BLOCKING`
  - Meaning: unresolved ambiguity blocks planning/implementation.
  - Action: answer clarification questions.

## HARDWARE Class
- `HW_MODEL_INCOMPLETE`
  - Meaning: minimum extractable hardware facts were not found.
  - Action: verify XSA integrity/export.
- `HW_FEATURE_MISSING`
  - Meaning: required peripheral/interrupt/memory does not exist.
  - Action: change requirements, pick another domain, or revise hardware.
- `HW_OWNERSHIP_CONFLICT`
  - Meaning: domain/OS ownership conflict (for example Linux-managed peripheral conflict).
  - Action: reassign responsibilities or switch architecture.

## BSP_DOMAIN Class
- `BSP_DRIVER_UNAVAILABLE`
  - Meaning: required driver/lib not available for selected OS/domain.
  - Action: change OS/domain or requirement set.
- `BSP_CONFIG_PARAM_INVALID`
  - Meaning: BSP/domain config key is invalid for selected OS/domain (for example `stdin` instead of `standalone_stdin`).
  - Action: query valid keys via `list_params(...)` and retry with exact parameter names.
- `DOMAIN_SELECTION_FAILED`
  - Meaning: no valid domain could satisfy constraints.
  - Action: provide explicit OS/CPU/domain override or revise SRS.

## BUILD Class
- `BUILD_FAILED_UNRESOLVED`
  - Meaning: build still failing after allowed remediation retries.
  - Action: inspect logs, apply manual fix, rerun.
- `BUILD_SDT_API_MISMATCH`
  - Meaning: generated app code uses legacy BSP macros/APIs incompatible with SDT-mode headers.
  - Action: inspect generated BSP headers (for example `xparameters.h`) and regenerate code with SDT-compatible macros/APIs.
- `REMEDIATION_FORBIDDEN_FIX_REQUIRED`
  - Meaning: only forbidden fix paths remain (for example changing XSA/hardware).
  - Action: user decision required; hardware/spec change needed.

## REPORTING Class
- `REPORT_SCHEMA_VIOLATION`
  - Meaning: generated summary does not conform to `summary.schema.json`.
  - Action: regenerate report and validate schema before completion.

## Mandatory Failure Payload
Every failure report must include:
- `code`
- `class`
- `root_cause`
- `evidence`
- `next_steps`
