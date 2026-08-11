<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Skill Tooling

This folder contains helper tooling for the Vitis Embedded App Generator skill.

## Scripts
- `inspect_xsa.py` — XSA hardware introspection (processor/platform metadata extraction)
- `save_vitis_path.py` — Vitis installation path persistence (read/write `vitis_config.json`)
- `validate_contracts.py` — contract artifact validation (input/summary schemas + artifact checks)
- `vitis_env.sh` — Vitis installation verification and bundled Python detection (Linux)

---

## inspect_xsa.py

Extracts processor and platform metadata directly from a `.xsa` file using pure ZIP + XML parsing (no Vitis installation required).

### Supported device families
- Zynq-7000 (Cortex-A9)
- Zynq UltraScale+ (Cortex-A53, Cortex-R5, PMU)
- Versal (Cortex-A72, Cortex-R5, AI Engine, PMC)
- Versal NET (Cortex-A78, Cortex-R52, PMC)
- MicroBlaze soft processors in PL

### Usage
```bash
python skills/tools/inspect_xsa.py <path_to.xsa>
```

### Output
- **stdout**: structured JSON with `arch`, `board`, `part`, `ps_ips`, and `processors` array
- **stderr**: human-readable summary table

Each processor entry includes: `cpu` (exact Vitis name), `domain_standalone`, `domain_linux`, `supports_linux`, `description` with clock frequency.

This script is used in **Stage 1 (Hardware Parse)** to build `hardware_model.json` and in **Stage 3 (Feasibility Analysis)** to validate SRS requirements against actual hardware capabilities.

---

## save_vitis_path.py

Reads or writes the saved Vitis installation path to `vitis_config.json` in the skill root directory. Provides a "remember me" capability so the user does not need to re-enter the Vitis install path on every run.

### Usage
```bash
# Read the saved path (prints to stdout, empty if none)
python skills/tools/save_vitis_path.py get

# Save a new path
python skills/tools/save_vitis_path.py set /tools/Xilinx/Vitis/2025.2
```

This script is used in **Stage 0 (Intake and Preconditions)** during the Vitis Environment Resolution Procedure — Step B (read last-used path) and Step D (persist verified path).

---

## vitis_env.sh

Bash script that verifies a Vitis installation path and resolves the bundled Python environment. It performs four checks:
1. Confirms `settings64.sh` exists at the given path.
2. Auto-detects the newest bundled Python under `<VITIS_PATH>/tps/lnx64/python-*/`.
3. Confirms the bundled `python3` binary is executable.
4. Sources `settings64.sh`, sets `LD_LIBRARY_PATH` and `PYTHONPATH`, and smoke-tests `import vitis`.

### Usage
```bash
bash skills/tools/vitis_env.sh /tools/Xilinx/Vitis/2025.2
```

### Output (stdout on success)
```
VITIS_PATH=/tools/Xilinx/Vitis/2025.2
VITIS_PYTHON=/tools/Xilinx/Vitis/2025.2/tps/lnx64/python-3.13.0/bin/python3
VITIS_PYLIB=/tools/Xilinx/Vitis/2025.2/tps/lnx64/python-3.13.0/lib
```

On failure, prints a specific error to stderr and exits 1.

This script is used in **Stage 0 (Intake and Preconditions)** during the Vitis Environment Resolution Procedure — Step C (verify path and detect bundled Python). On Windows, the equivalent checks are performed manually since bash is not available.

---

## validate_contracts.py

## Dependency
Install once in your environment:

```bash
pip install jsonschema
```

## Usage
Validate both input and summary using default example files:

```bash
python skills/tools/validate_contracts.py --all
```

Validate only input payload:

```bash
python skills/tools/validate_contracts.py --validate-input \
  --input-json skills/references/input_example.json \
  --input-schema skills/references/input_schema.json
```

Validate only summary payload:

```bash
python skills/tools/validate_contracts.py --validate-summary \
  --summary-json skills/references/examples/minimal_e2e/expected_summary.json \
  --summary-schema skills/references/summary.schema.json
```

Validate summary and check that declared artifacts exist in a workspace:

```bash
python skills/tools/validate_contracts.py --validate-summary --check-artifacts \
  --summary-json path/to/report/summary.json \
  --workspace-root path/to/workspace_root
```

Note:
- The summary schema now requires an execution feedback artifact path (`artifacts.execution_feedback_report`), typically `report/execution_feedback.md`.
- The summary schema also requires a workspace-generation script path (`artifacts.generate_workspace_script`), typically `generate_workspace.py`.

## Exit Codes
- `0`: validation passed
- `1`: schema/artifact validation failed
- `2`: runtime/configuration error (invalid JSON, missing files, missing dependency)
