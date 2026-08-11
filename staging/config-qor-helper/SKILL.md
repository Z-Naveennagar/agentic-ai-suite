---
name: config-qor-helper
description: Guides the Config QoR Helper workflow for AMD/Xilinx Vitis DSP Library IPs. Use when the user asks about configuration prediction, QoR optimization, FFT/DSP IP configuration, AIE design configuration, or running config_qor_helper. Covers constraint file creation, script execution, graph code generation, Makefile creation, and x86 simulation validation.
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
# Config QoR Helper Workflow

Config QoR Helper returns predicted optimal AIE configurations for Vitis DSP Library IPs based on user design constraints. The agent guides the user through a 5-stage methodology, presenting clear stage headers at each step.

## Stage 1 -- Specifying design requirements in the constraint file

1. Gather requirements from the user:
   - **IP name** (e.g., `fft_ifft_dit_1ch`)
   - **AIE Variant** -- present these choices to the user:
     - AIE → `AIE_VARIANT: 1`
     - AIE-ML → `AIE_VARIANT: 2`
     - AIE-MLv2 → `AIE_VARIANT: 22`
   - **Parameter constraints** (data types, point size, etc.)
   - **QoR constraints** (throughput target, latency target)

2. Build the constraint JSON. See [constraint_syntax.md](constraint_syntax.md) for format and [ip_parameters.md](ip_parameters.md) for IP-specific parameters.

3. Present a summary before proceeding:
   ```
   Based on your requirements:
   AIE VARIANT: <variant_name> (<variant_value>)
   IP: <ip_name> (<description>)
   Data type: <data_type>
   Point size: <point_size>
   Throughput: > <value> MSPS
   Let me create the constraint file.
   ```

4. Store the constraint file at `<ABSOLUTE_PATH>/constraints/<constraint_file>.json`.
   Use naming convention: `<ip_short>_<point_size>_<throughput>.json` (e.g., `fft_512_1000.json`).

## Stage 2 -- Setting configuration priorities for sorting predicted results

Default sort settings (inform the user):
- `sort_by: ["num_aie", "THROUGHPUT"]`
- `ascending: [true, false]` — fewer AIE tiles first, higher throughput first

If the user requests different sorting, update accordingly.

```
Configurations will be sorted by NUM_AIE (ascending, prefer fewer AIE tiles)
then by Throughput (descending, prefer higher throughput). This is the default priority.
```

## Stage 3 -- Executing the Config QoR Helper script

**CRITICAL**: Before running the script, ask the user for TWO things:
1. The `DSPLIB_ROOT` path (root directory of Vitis DSP Library installation)
2. The Python environment setup commands

**The agent must NOT set these on its own. Wait for user input.**

Once provided, run:
```bash
cd ${DSPLIB_ROOT}/L2/meta/scripts/qor_helper
python config_qor_helper.py \
  --ip <IP_NAME> \
  --constraints_file <ABSOLUTE_PATH>/constraints/<CONSTRAINT_FILE>.json \
  --out_csv_file <ABSOLUTE_PATH>/results/<CONSTRAINT_FILE>.csv
```

Create `<ABSOLUTE_PATH>/results/` directory if it doesn't exist.
See [helper_syntax.md](helper_syntax.md) for full syntax reference.

## Stage 4 -- Analyzing key parameters from predicted configurations

1. Read the output CSV file from `<ABSOLUTE_PATH>/results/`.
2. Present results to the user showing key columns: Row, NUM_AIE, CASC_LEN, PARALLEL_POWER, WIN_SIZE, Throughput, Latency.
3. Highlight recommended rows (fewest AIE tiles with highest throughput meeting constraints).
4. Ask the user to **select a row** for building the graph.
5. Record all parameters from the selected row for code generation.

## Stage 5 -- Validation Results

See [validation.md](validation.md) for complete templates and detailed instructions.

### Sub-step summary:

**5a. Create project directory**
`<ABSOLUTE_PATH>/designs/<IP_NAME>_<ROW_NO>_<throughput_value>/`

**5b. Generate graph code**
Generate `graph.h` and `graph.cpp` under the `src/` subdirectory using parameters from the selected configuration row.
- `TP_SHIFT = log2(TP_POINT_SIZE)` — inform the user this is computed from log2(TP_POINT_SIZE).

**5c. Generate Makefile**
Before creating the Makefile, **ask the user** which platform option they want:
1. Use the default platform (show the platform name)
2. Change to a different platform name
3. Use a PART number instead

Default platforms by variant:
- AIE → `xilinx_vck190_base_202520_1`
- AIE-ML → `xilinx_vek280_base_202520_1`
- AIE-MLv2 → `vek385_base_revb`

**Agent must wait for user input before proceeding.**

Tell the user which platform/part will be used, then proceed.

**5d. Deploy utility scripts**
Copy `extract_aie_resources.py`, `extract_latency.py`, `extract_throughput.py` to `<ABSOLUTE_PATH>/designs/utility_scripts/`.
Source location: `/group/techsup/cbalakr/various_tasks/config_qor_helper/utility_scripts/`

**5e. FFT-specific test vectors** (only for `fft_ifft_dit_1ch`)
Inform the user: "This step is only for IP fft_ifft_dit_1ch."
Generate `gen_vectors.m` and `regression.m` in the project directory.

**5f. Build and simulate**
Ask the user to provide commands to source MATLAB and Vitis tools.
**Agent must NOT source tools on its own. Wait for user input.**

After receiving commands from user, run:
```bash
make gen_vectors x86all
```

## Final Summary

After completing all stages, present a summary table:

```
Stage | Result
------|-------
1. Constraint file      | constraints/<name>.json created
2. Sort priority        | NUM_AIE (ascending), Throughput (descending)
3. Config QoR Helper    | <N> valid configurations found
4. Selected config      | Row <N>: <NUM_AIE> AIE tiles, CASC_LEN=<val>, PARALLEL_POWER=<val>, <throughput> MSPS
5. Validation           |
  5a. Project directory  | designs/<IP_NAME>_<ROW>_<throughput>/
  5b. Graph code         | graph.h and graph.cpp under src/
  5c. Makefile           | Generated with <platform_or_part>
  5d. Utility scripts    | designs/utility_scripts/
  5e. Test vectors       | gen_vectors.m and regression.m (FFT-specific)
  5f. Build & simulate   | make gen_vectors x86all

Results:
Test vector generation  | <N> input/output ports generated
x86 compilation         | Compiled successfully (0 errors)
x86 simulation          | Completed successfully
Regression check        | PASSED/FAILED (max error ~<val> on all ports)
```
