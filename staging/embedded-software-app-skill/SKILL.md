---
name: vitis-embedded-app-generator
description: >-
  This skill should be used when the user wants to "generate an embedded application from an XSA and requirements",
  "create a Vitis workspace from XSA", "build a bare-metal or FreeRTOS or Linux app from XSA",
  "plan a Vitis embedded project", "create platform and app from XSA with software requirements",
  or provides an XSA file path together with software requirements and wants a complete embedded
  C application built, verified, and reported using the Vitis Python API.
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
# Vitis Embedded App Generator (XSA -> Vitis Workspace + Embedded C App)
Create a Vitis workspace and embedded C application from a Vivado `.xsa` plus software requirements, with feasibility verification, build automation, and self-repair.

Primary outcome:
Given a hardware export (`.xsa`) and software requirements, generate a complete Vitis workspace (platform + domain(s) + BSP + app) and compilable application code, or stop early with a clear infeasibility report.

Supported OS targets: Bare-metal, FreeRTOS, Linux.

## Scope and Assumptions
- Hardware design is complete before this skill starts.
- The user must provide an existing `.xsa` file.
- This skill never modifies hardware and never regenerates an `.xsa`.
- Internet access is optional; workflow is offline-first.

## Contract Documents (Normative)
Use these documents as the source of truth for strict inputs/outputs and operational behavior:
- `references/input_contract.md`
- `references/input_schema.json`
- `references/input_example.json`
- `references/summary_json_schema.md`
- `references/summary.schema.json`
- `references/validation_report_template.md`
- `references/failure_taxonomy.md`
- `references/compatibility_matrix.md`
- `references/quickstart_runbook.md`

## Required Inputs
1. XSA path (`inputs.xsa_path`)
2. Software requirements markdown path (`inputs.srs_path`)
3. Execution mode (`inputs.execution_mode`): `plan-only` or `apply`

## Vitis API Reference Rule
- Preferred: user provides a Vitis API/CLI reference document path (`inputs.vitis_reference_doc`).
- Allowed fallback: if omitted, use the curated local API references under `references/api/`.
- If both are missing or incompatible with detected Vitis version, stop with a prerequisite failure.

## Execution Modes
### plan-only
- Must not mutate any Vitis workspace.
- Must produce normalized requirements, hardware model, feasibility report, command plan, and final reports.
- Must emit `generate_workspace.py` from the command plan, but must not execute it.
- Build steps are simulated/planned only.

### apply
- Creates/updates workspace artifacts and runs builds.
- Includes remediation loop under the safety boundaries below.

## Deterministic Requirement ID Policy
When SRS lacks explicit IDs:
- Functional requirements: `FR-001`, `FR-002`, ...
- Non-functional requirements: `NFR-001`, `NFR-002`, ...
- Acceptance criteria: `AC-001`, `AC-002`, ...

Rules:
- Preserve source anchors (`source_section`, `source_heading`, `source_line_start`).
- IDs must be stable for identical SRS content.
- Never renumber existing user-provided IDs.

## Required Outputs
The following are required in both modes unless explicitly documented as mode-specific:
1. `hardware_model.json`
2. `normalized_requirements.json`
3. `feasibility_report.md`
4. `implementation_plan.md`
5. `vitis_command_plan.json`
6. `generate_workspace.py` (executable workspace-generation script derived from command plan)
7. `report/validation_report.md`
8. `report/summary.json` (must validate against `references/summary.schema.json`)
9. `report/execution_feedback.md`

Mode-specific:
- `apply` additionally requires `bsp_inspection_report.md`, generated workspace, source code, and build logs.

## Remediation Safety Boundary
Allowed automatic fixes:
- Include path and compile-definition fixes
- Library/BSP enablement fixes within selected domain
- Template re-selection when tool template mismatch occurs
- Domain/app configuration corrections that do not require hardware changes
- Linker/config file fixes inside generated software components

Forbidden automatic fixes:
- Modifying or replacing `.xsa`
- Changing hardware address map assumptions not present in extracted hardware model
- Making kernel-space Linux changes when user requested userspace-only
- Any action that violates ownership/safety constraints in the feasibility report

If only forbidden fixes would resolve the issue, stop and emit failure details.

## Strict Workflow
### Stage 0 - Intake and Preconditions

Goal: Ensure required inputs exist and are coherent.
- Validate all required inputs against `references/input_schema.json`.
- Enforce tool prerequisites from `references/compatibility_matrix.md`.
- Resolve and bootstrap the Vitis runtime environment using the procedure below.
- Validate that the Vitis workspace directory is owned by Vitis (do not pre-create the exact target workspace path).
- If OS/domain omitted, apply deterministic defaults from `references/input_contract.md` and record rationale.

If anything critical is missing: stop and request it.

#### Vitis Environment Resolution Procedure

Resolve the Vitis installation path using this priority order:

**Step A — Check explicit input and environment variable.**
If the user provided `inputs.vitis_install_path`, use that value directly and skip to Step C.
Otherwise check the shell environment:
```
echo "XILINX_VITIS=${XILINX_VITIS}"
```
If `XILINX_VITIS` is set and non-empty, use it and skip to Step C.

**Step B — Check saved path or ask the user.**
Read the last-used path from the config file:
```
python3 tools/save_vitis_path.py get
```
This reads `vitis_config.json` in the skill root. The result is either a saved path or empty.
- If a saved path exists, offer it to the user as the default ("last used") and allow them to accept or enter a different path.
- If empty, ask the user to provide the Vitis installation path (e.g. `C:\Xilinx\Vitis\2025.2` or `/tools/Xilinx/Vitis/2025.2`).

**Step C — Verify the path and detect bundled Python.**
On Linux, run the verification script:
```
bash tools/vitis_env.sh <VITIS_PATH>
```
The script validates the installation directory, auto-detects the newest bundled Python, and smoke-tests `import vitis`. On success it prints three lines:
```
VITIS_PATH=/tools/Xilinx/Vitis/2025.2
VITIS_PYTHON=/tools/Xilinx/Vitis/2025.2/tps/lnx64/python-3.13.0/bin/python3
VITIS_PYLIB=/tools/Xilinx/Vitis/2025.2/tps/lnx64/python-3.13.0/lib
```
Parse and store `VITIS_PATH`, `VITIS_PYTHON`, and `VITIS_PYLIB` for use in later stages.

On Windows (where bash is unavailable), perform the equivalent checks manually:
1. Confirm `<VITIS_PATH>\settings64.bat` exists.
2. Locate the bundled Python under `<VITIS_PATH>\tps\win64\python-<ver>\python.exe`.
3. Locate the bundled Python library directory alongside it.

On failure, show the error and ask the user to provide the correct path (retry Step C).

**Step D — Save the verified path for next time.**
After successful verification, persist the path so it becomes the default for subsequent runs:
```
python3 tools/save_vitis_path.py set <VITIS_PATH>
```

**Step E — Set runtime environment for script execution.**
When executing `generate_workspace.py` or any Vitis Python script, invoke it with:
```
source <VITIS_PATH>/settings64.sh   # Linux
LD_LIBRARY_PATH=<VITIS_PYLIB>:$LD_LIBRARY_PATH \
PYTHONPATH=<VITIS_PATH>/cli:<VITIS_PATH>/cli/proto:$PYTHONPATH \
<VITIS_PYTHON> ./generate_workspace.py 2>&1
```
On Windows use the equivalent `settings64.bat` and `set` commands.
Always use the Vitis-bundled Python — never system Python.

### Stage 1 - Hardware Parse
Goal: Build a verified hardware model from the XSA before any planning begins.

Run `tools/inspect_xsa.py <xsa_path>` to extract processor and platform metadata directly from the `.xsa` file (pure ZIP + XML parsing, no Vitis session required). The script outputs structured JSON to stdout containing:
- Architecture family (zynq / zynquplus / versal / versalnet)
- Board name and part number
- Complete processor list with exact `cpu` names, `domain_standalone` / `domain_linux` naming, Linux support flags, and clock frequencies
- PS IP identification and AI Engine / MicroBlaze detection

Use this output as the authoritative source for processor names and domain naming throughout all subsequent stages.

In addition to the `inspect_xsa.py` output, extract or confirm:
- Memory regions usable for code/data
- Peripheral inventory with base addresses for required interfaces
- Interrupt availability for interrupt-driven requirements

Stop if any of the following are missing:
- At least one supported processor identifier
- At least one executable memory region
- Peripheral base addresses for interfaces referenced in the SRS

Write `hardware_model.json`.

### Stage 2 - Requirement Normalization
Goal: Convert free text into a structured spec.
Parse SRS markdown using required format in `references/input_contract.md`.
Apply deterministic ID policy.
Ambiguity handling - If requirements are ambiguous or conflicting ask precise clarification questions and pause planning until answered.
Write `normalized_requirements.json`.

### Stage 3 - Feasibility Analysis
Goal: Confirm that the application is implementable on the hardware + chosen domain/OS.

Cross-reference the normalized requirements from Stage 2 against the hardware model produced by `tools/inspect_xsa.py` in Stage 1. For every SRS requirement that references a peripheral, processor, OS, or domain, verify that the hardware model confirms the capability exists.

Run hardware/OS/driver/domain checks:

3.1 Hardware capability checks
Using the `inspect_xsa.py` processor list and hardware model, verify:

- The chosen processor (`cpu` name) exists in the processor list and is accessible for the chosen domain
- The chosen OS is compatible with the selected processor (`supports_linux` flag for Linux; all processors support standalone)
- The correct `domain_standalone` or `domain_linux` name is used (take exact values from `inspect_xsa.py` output)
- IP/peripherals exist for each required feature (and addressability is valid)
- Memory regions exist and match needs (code/data/heap/stack; DMA buffers if needed)
- Interrupt routing exists for interrupt-driven requirements
- Clock/reset topology can support required rates (e.g., UART baud, timer ticks)

3.2 BSP/driver feasibility checks
Verify for the chosen OS/domain:

- BSP can be generated for the selected processor and domain
- Required drivers/libraries exist (xilffs, lwIP, OpenAMP, etc.)

3.3 Safety & domain ownership checks
- If Linux is requested: ensure no bare-metal driver plan conflicts with Linux-owned peripherals.
- Detect illegal memory access or unsupported OS features.

On failure, classify using `references/failure_taxonomy.md` and stop.
Write `feasibility_report.md`.

### Stage 4 - Implementation Planning
Goal: Create a detailed plan before writing code. For each feature:

 - Identify the exact driver/library/API and init sequence
 - Define runtime logic (polling vs interrupt, tasking model, buffers)
 - Define error handling strategy and timeouts
 - Define any linker script or memory section needs
Multi-processor handling If multiple processors/cores exist:

- Select the best domain and justify the choice
- Handle RPU split vs lock-step where applicable (document rationale)
- Generate API/driver mapping and runtime design.
- Detect SDT-mode BSP/API expectations from generated headers/config and plan driver init accordingly.
- For SDT mode, prefer BASEADDR lookup patterns over legacy DEVICE_ID patterns when DEVICE_ID macros are absent.
Write `implementation_plan.md`.

### Stage 5 - Command Planning
Derive Vitis command/API sequence from provided reference doc or curated local references.
Parse the reference doc and extract:
- How to set workspace
- How to create platform from .xsa
- How to create domain(s)
- How to generate BSP and add libs
- How to create app components and import sources
- How to build platform/app and collect logs
Write `vitis_command_plan.json`.

### Stage 6 - Platform and BSP Generation (apply mode only)
Goal: Create the workspace, platform, domain, and BSP so that generated driver headers and libraries are available for code generation.

Actions:

- Create workspace (clean/recreate if configured)
- Create platform component from .xsa
- Build platform to generate .xpfm
- Create domain(s) for the chosen OS/processor
- Enable required libraries/drivers in the domain (xilffs, lwIP, OpenAMP, etc.) based on the implementation plan from Stage 4
- Generate/build the BSP

OS-specific handling:

- Bare-metal: ensure deterministic init + correct BSP drivers
- FreeRTOS: configure tasks, stacks, priorities, sync primitives
- Linux: generate userspace scaffolding; kernel-space only if explicitly required

Additional rules:

- Resolve application templates by querying the live tool (`get_templates(type='EMBD_APP')`) and selecting an exact returned identifier - store the selected template for use in Stage 9.
- Use a dedicated Vitis workspace subdirectory when the run root already contains planning/report artifacts.

Do **not** create the application component or import sources in this stage - that happens in Stage 9 after code generation.

#### `generate_dtb` Rule (per architecture)

When creating a platform component, set `generate_dtb` according to the architecture family:

| Architecture family | `generate_dtb` value |
|---------------------|---------------------|
| Zynq-7000 (`zynq`) | `False` |
| Zynq UltraScale+ (`zynquplus`) | `True` |
| Versal (`versal`) | `True` |
| Versal Net (`versalnet`) | `True` |

For standalone/FreeRTOS domains, `generate_dtb` is typically `False`.
For Linux domains, apply the table above - DTB generation is required for ZynqMP, Versal, and Versal Net platforms.

### Stage 7 - BSP Inspection (apply mode only)
Goal: Inspect the generated BSP to confirm driver/library availability and discover the correct API patterns before writing application code.

After the platform and BSP are built in Stage 6, scan the generated BSP output directory and perform the following checks:

**7.1 - Driver and library presence verification**
- Locate the BSP include directory (e.g. `<domain>/bsp/include/`).
- For each peripheral required by the implementation plan (Stage 4), confirm the corresponding driver header exists (e.g. `xuartps.h`, `xgpiops.h`, `xiicps.h`).
- For each library enabled in Stage 6 (xilffs, lwIP, etc.), confirm its headers are present in the BSP include path.
- If any required driver or library header is missing, stop and report a `BSP_DRIVER_MISSING` failure before attempting code generation.

**7.2 - API pattern detection (SDT vs legacy)**
- Check for `xparameters.h` in the BSP include directory.
  - If present: legacy mode - use `XPAR_*` macros and `DEVICE_ID` patterns for driver init.
  - If absent or incomplete: SDT mode - use `BASEADDR` lookup patterns and device-tree-derived config structures.
- Record the detected mode in the implementation plan so Stage 8 generates code with the correct init pattern.

**7.3 - API familiarisation**
- Read the driver headers for each required peripheral to identify:
  - Config lookup function (e.g. `XUartPs_LookupConfig()`)
  - Init function and its signature (e.g. `XUartPs_CfgInitialize()`)
  - Key operational functions for the planned features
  - Any version-specific type definitions or struct layouts
- Use these actual signatures - not assumptions - when generating application code in Stage 8.

**7.4 - Cross-reference with implementation plan**
- Compare the discovered drivers/APIs against the implementation plan from Stage 4.
- Update the plan if the BSP reveals different function names, parameter orders, or init patterns than originally assumed.
- Record any plan amendments in `implementation_plan.md`.

Write `bsp_inspection_report.md` summarising: discovered drivers, detected API mode, header paths, and any plan amendments.

### Stage 8 - Generate C Application Code (+ Tests)

Goal: Produce clean, safe C that matches the plan and uses the actual BSP APIs discovered in Stage 7.

- Use the driver headers and API signatures confirmed in the BSP inspection - not assumptions from planning.
- Use the correct init pattern (SDT or legacy) as detected in Stage 7.
- Use the exact `#include` paths from the generated BSP.
- Implement the application logic per the (possibly amended) implementation plan.
- Use correct AMD driver APIs and OS APIs.
- Add a minimal "smoke test" where feasible:
  - init peripheral
  - perform a simple I/O
  - report result
- Ensure explicit error checks, bounds checks, timeouts; avoid UB.

Output: src/ + headers, plus test/ if applicable.

### Stage 9 - App Component Creation and Source Import (apply mode only)
Goal: Create the application component in the workspace and import the generated source code.

Actions:

- Create application component using the template resolved in Stage 6.
- Import the generated source files from Stage 8 into the app component's `src/` directory.
- Apply any linker script customisations or OS configuration overrides from the implementation plan.
- Configure include paths and compile definitions to reference the BSP output from Stage 6.

### Stage 10 - Build and Repair (apply mode only)
Goal: Build successfully or stop with a strong diagnostic report.
- Invoke build through Vitis CLI/API (per doc-derived commands).
- Capture full logs under `logs/`.
- Parse common failure signatures.
- Treat build return values as version-dependent (`SUCCESS`/`FAILURE` strings or integer status codes such as `0` success and non-zero failure).
- Apply fixes and retry up to `inputs.max_retries` (default 5).

**Common remediation playbook (examples)**

- Missing include paths -> adjust component includes / BSP config
- Missing library linkage -> enable BSP libs (lwIP, xilffs, etc.)
- Wrong domain settings -> correct CPU/OS/domain name
- Linux DT node missing -> generate overlay recommendation and mark as blocking if required
- Template mismatch -> use available templates from tool version and reselect

**Stopping conditions**
- Build succeeds
- Retry limit reached
- A fix would violate constraints (e.g., requires changing .xsa)

### Stage 11 - Validation and Reporting
Use `references/validation_report_template.md` to generate `report/validation_report.md`.
Emit `report/summary.json` that conforms to `references/summary.schema.json`.
Ensure `generate_workspace.py` is emitted and its path is included in summary artifacts.
Generate `report/execution_feedback.md` using `references/execution_feedback_template.md`, including:
- all encountered errors/failures in chronological order,
- investigation actions taken,
- exact remediation applied,
- unresolved issues and suggested skill/reference improvements.


## Post-Build Validation Checklist (Required)
In `apply` mode, include pass/fail checklist per selected OS:
- Bare-metal:
  - BSP generation completed
  - App build completed
  - UART or equivalent runtime sanity print available
- FreeRTOS:
  - Task creation/scheduler start path validated
  - Stack/heap settings validated
  - One runtime sanity artifact recorded (log, capture, or test output)
- Linux (userspace flow):
  - Userspace app builds against selected sysroot/toolchain
  - Ownership conflicts checked against Linux-managed peripherals
  - Runtime sanity artifact recorded (stdout or functional probe)

**Quality Rules for Generated C Code**
- Always check return codes from driver calls
- Use explicit initialization order (clocks → reset → config → enable)
- Add timeouts to polling loops
- Use bounds checks for buffers and I/O
- Avoid undefined behavior (alignment, overflow, invalid pointers)
- Include at least one minimal smoke test where feasible

**Quality Checklist for `generate_workspace.py`**

Every generated workspace script must satisfy all of the following:
- Use **absolute XSA path** (expand any relative path with `os.path.abspath()`).
- Set workspace path using `os.path.join(os.getcwd(), ...)` so it is always relative to the run directory.
- **Clean the workspace** before creation with `shutil.rmtree()` if it already exists.
- Wrap all Vitis operations in **`try/finally`** to ensure `vitis.dispose()` always runs.
- **Print platform XPFM and application ELF paths** after each build step completes.
- Set `generate_dtb` correctly per the architecture rule in Stage 6.
- Include clear `print()` statements and comments documenting each major step.
- Exit with a non-zero status code on any unrecoverable error.

## Quick-Reference Troubleshooting Table

| Error | Likely Cause | Fix |
|-------|-------------|-----|
| `ModuleNotFoundError: No module named 'vitis'` | Using system Python instead of Vitis-bundled Python | Use `VITIS_PYTHON` resolved in Stage 0 environment procedure |
| `ModuleNotFoundError: No module named 'grpc'` | Missing `PYTHONPATH` or wrong Python | Add `<VITIS_PATH>/cli/proto` to `PYTHONPATH`; use bundled Python |
| `libpython3.x.so not found` | Missing `LD_LIBRARY_PATH` | Set `LD_LIBRARY_PATH=<VITIS_PYLIB>:$LD_LIBRARY_PATH` |
| `FileNotFoundError: <xsa_path>` | XSA path is relative or does not exist | Expand to absolute path with `os.path.abspath()`; verify file exists |
| `No processor found` / `Invalid cpu` | Wrong CPU name passed to platform/domain creation | Re-inspect the XSA; use exact processor name from hardware model |
| `platform.xpfm not found` | Platform build failed silently | Check platform build logs; call `platform.report()` for diagnostics |
| Domain mismatch between platform and app | `domain_name` in `create_platform_component` differs from `domain` in `create_app_component` | Use the exact same domain name string in both calls |
| Build returns unexpected type | Vitis version returns string (`SUCCESS`/`FAILURE`) or integer (`0`/non-zero) | Treat build return as version-dependent; check both string and integer forms |
| `Can't find a usable init.tcl` (Tcl warning) | Harmless Tcl bootstrap noise | Ignore — build succeeds despite this warning |

## Acceptance Criteria
Success means either:
- `apply` mode: compilable workspace and generated app with required artifacts and reports, or
- `plan-only` mode: complete planning and feasibility/report artifacts without workspace mutation.

Failure must include:
- Failure class/code from `references/failure_taxonomy.md`
- Root cause summary
- Blocking evidence (file and log references)
- Actionable next steps

## Security and Privacy
- Do not transmit `.xsa`, source, requirements, or logs externally unless explicitly configured.
- Redact secrets from logs and reports.
