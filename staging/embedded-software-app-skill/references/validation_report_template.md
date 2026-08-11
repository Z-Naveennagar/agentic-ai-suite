<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Validation Report Template

## 1. Run Metadata
- Run ID:
- Timestamp (UTC):
- Execution mode (`plan-only` or `apply`):
- Detected Vitis version:
- Detected Python version:

## 2. Input Summary
- XSA path:
- SRS path:
- Vitis reference doc path (or local fallback):
- User overrides:

## 3. Prerequisite Checks
- Vitis version supported: Pass/Fail
- Python version supported: Pass/Fail
- Environment variables present: Pass/Fail
- Tool availability: Pass/Fail
- License availability: Pass/Fail

## 4. Hardware Extraction Summary
- Processors found:
- Memory regions found:
- Peripherals found:
- Minimum extraction criteria met: Pass/Fail

## 5. Requirement Normalization
- Requirement ID policy applied:
- Total FR count:
- Total NFR count:
- Total AC count:
- Ambiguities/questions raised:

## 6. Selection Rationale
- Selected OS:
- Selected CPU/core:
- Selected domain:
- Why selected:

## 7. Feasibility Results
- Hardware capability checks:
- Driver/BSP checks:
- Ownership/safety checks:
- Overall feasibility: Pass/Fail

## 8. Command Plan Summary
- Reference source used for commands:
- Planned Vitis APIs/CLI steps:
- Version mismatch handling (if any):

## 9. Build and Remediation (apply mode)
- Build attempted: Yes/No
- Build result: Pass/Fail
- Retry count:
- Applied fixes (allowed list only):
- Blocked fixes (forbidden list):

## 10. OS-Specific Validation Checklist
### Bare-metal
- BSP generated: Pass/Fail
- App build succeeded: Pass/Fail
- Runtime sanity artifact captured: Pass/Fail

### FreeRTOS
- Task/scheduler path validated: Pass/Fail
- Stack/heap settings validated: Pass/Fail
- Runtime sanity artifact captured: Pass/Fail

### Linux (userspace)
- Userspace build succeeded: Pass/Fail
- Peripheral ownership checks passed: Pass/Fail
- Runtime sanity artifact captured: Pass/Fail

## 11. Artifacts
- `hardware_model.json`:
- `normalized_requirements.json`:
- `feasibility_report.md`:
- `implementation_plan.md`:
- `vitis_command_plan.json`:
- `report/summary.json`:
- Build logs:

## 12. Requirement Traceability Summary
- FR status summary:
- NFR status summary:
- AC status summary:
- Blocked requirements:

## 13. Final Result
- Status (`success` or `failure`):
- If failure: code/class/root cause:
- Recommended next actions:

## 14. Execution Feedback Artifact
- `report/execution_feedback.md` generated: Yes/No
- Number of issues documented:
- Key recurring friction points:
