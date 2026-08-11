<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Quickstart Runbook

This runbook shows exact invocation flow and expected artifacts.

## 1. Prepare Inputs
Required:
- `input_example.json` (or equivalent conforming to `input_schema.json`)
- Valid `.xsa`
- Valid SRS markdown

Optional but recommended:
- Vitis API reference README/PDF for installed version

## 2. Validate Input Contract
- Validate payload against `input_schema.json`.
- Validate SRS section structure using `input_contract.md`.
- Validate prerequisites against `compatibility_matrix.md`.

### 2.1 Runtime Preflight (Recommended)
- Verify the selected Python runtime can import `vitis`.
- If system Python cannot import `vitis`, switch to the Vitis-bundled runtime environment.
- Do not pre-create the exact Vitis workspace path; let Vitis create/manage it.
- If your run root already exists for reports, use a child folder for Vitis workspace (for example `<run_root>/vitis_ws`).
- For Vitis 2025.2 on Linux, include `cli/proto` in `PYTHONPATH` in addition to `cli/python-packages/lnx64`.

## 3. Run in plan-only Mode (Safe First Pass)
Set:
- `inputs.execution_mode = "plan-only"`

Expected artifacts:
- `hardware_model.json`
- `normalized_requirements.json`
- `feasibility_report.md`
- `implementation_plan.md`
- `vitis_command_plan.json`
- `generate_workspace.py`
- `report/validation_report.md`
- `report/summary.json`
- `report/execution_feedback.md`

No Vitis workspace mutation is allowed in this mode.

## 4. Run in apply Mode
Set:
- `inputs.execution_mode = "apply"`

Expected additional artifacts:
- Generated Vitis workspace with platform/domain/BSP/app
- Source under app component
- `generate_workspace.py` (saved script used to create workspace)
- `logs/build.log`
- `logs/remediation.log`
- Runtime sanity artifact
- `report/execution_feedback.md` with issue log, investigation, and fixes

Execution recommendations:
- Discover app template names from the live API (`get_templates(type='EMBD_APP')`) and use exact identifiers.
- For modern SDT BSP flows, confirm generated headers and adapt code to BASEADDR lookup when DEVICE_ID macros are absent.
- Handle build status returns as version-dependent (`SUCCESS`/`FAILURE` strings or integer status values such as `0` success).
- Before setting BSP stdin/stdout, query valid names from `list_params(option='os')`; for standalone this is commonly `standalone_stdin` and `standalone_stdout`.
- For SDT GPIO drivers, verify available APIs in generated headers and adapt to BSP-exported calls (for example `XGpioPs_Read`/`XGpioPs_Write` versus legacy variants).

## 5. Validate Outputs
- Confirm `report/summary.json` conforms to `summary.schema.json`.
- Confirm every normalized requirement has a traceability record.
- Confirm OS-specific checklist is present in validation report.

Suggested automated check command:

```bash
python skills/tools/validate_contracts.py --all
```

For real run outputs:

```bash
python skills/tools/validate_contracts.py --validate-input \
	--input-json path/to/run_input.json \
	--input-schema skills/references/input_schema.json

python skills/tools/validate_contracts.py --validate-summary --check-artifacts \
	--summary-json path/to/workspace/report/summary.json \
	--summary-schema skills/references/summary.schema.json \
	--workspace-root path/to/workspace
```

## 6. Failure Handling
If run fails:
1. Look up `result.failure.code` in `failure_taxonomy.md`.
2. Follow listed action steps.
3. Re-run first in `plan-only` after changes.

## 7. Recommended Artifact Layout
`workspace_<timestamp>/`
- `hardware_model.json`
- `normalized_requirements.json`
- `feasibility_report.md`
- `implementation_plan.md`
- `vitis_command_plan.json`
- `generate_workspace.py`
- `logs/`
- `report/validation_report.md`
- `report/summary.json`
- `report/execution_feedback.md`
