<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Compatibility Matrix

This matrix defines supported toolchain combinations for this skill.

## Supported Versions
| Skill Contract Version | Vitis Version | Python Version | Status |
|---|---|---|---|
| 1.x | 2025.2 | System Python 3.10/3.11, or Vitis-bundled runtime | Supported |
| 1.x | 2026.1 | System Python 3.10/3.11 for tooling, Vitis-bundled runtime (Python 3.13) for `vitis` module | Supported |
| 1.x | Other versions | Any | Best effort, must fail fast if API mismatch blocks flow |

## Runtime Bootstrap Rule
- Prefer launching through the Vitis-provided runtime environment rather than raw system Python.
- If `import vitis` fails on system Python, switch to the Vitis-bundled runtime and apply the environment expected by the installed Vitis release.
- Typical variables that may need to be set for direct Python invocation include `PYTHONHOME`, `PYTHONPATH`, and `LD_LIBRARY_PATH` (Linux), using values derived from the active Vitis installation.

### Vitis 2025.2 practical bootstrap notes (Linux)
- `vitis` Python stack may require the bundled Python 3.13 runtime for grpc compatibility.
- Ensure `PYTHONPATH` includes both:
	- `$XILINX_VITIS/cli/python-packages/lnx64`
	- `$XILINX_VITIS/cli/proto`
- Ensure `LD_LIBRARY_PATH` includes bundled Python libs (for example `$XILINX_VITIS/tps/lnx64/python-3.13.0/lib`) when invoking bundled Python directly.

## Required Environment Variables
At least one of these Vitis installation selectors must be available:
- `XILINX_VITIS`
- `XILINX_VIVADO`

Recommended:
- `PATH` contains Vitis Python/API executables needed by the selected flow.

## Required Tool Checks
Before planning or apply execution, validate:
1. Vitis client can be created.
2. Workspace can be set/read.
3. Platform creation APIs are reachable.
4. Build API is reachable for selected component type.
5. `import vitis` succeeds in the selected runtime.
6. Template discovery call succeeds (for example `get_templates(type='EMBD_APP')`).
7. Domain config parameter discovery succeeds (`list_params(option='os')`) before applying stdin/stdout settings.

## License/Availability Checks
The skill must verify and record:
- API invocation does not fail with license-denied class errors.
- Build step does not fail due to missing entitlements.

If unavailable, fail with:
- `PREREQ_TOOL_UNAVAILABLE` for missing executables/runtime.
- `PREREQ_LICENSE_UNAVAILABLE` for entitlement/license failures.

## Version Mismatch Policy
If user-provided reference doc indicates commands not supported by detected tool version:
1. Prefer detected tool version behavior.
2. Mark mismatch in validation report.
3. Continue only if a safe equivalent sequence exists.
4. Else fail with `PREREQ_DOC_VERSION_MISMATCH`.
