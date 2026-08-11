<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Config QoR Helper Skill -- Usage Guide

## What This Skill Does

This Cursor Agent Skill automates the **Config QoR Helper** workflow for AMD/Xilinx Vitis DSP Library IPs. It guides you through predicting optimal AIE configurations based on your design constraints, then generates all the code and build files needed to validate the selected configuration via x86 simulation.

**Currently supported IPs**: `fft_ifft_dit_1ch` (extensible to other DSP library IPs)

## Prerequisites

Before using this skill, ensure you have access to:

- **Vitis DSP Library** (`DSPLIB_ROOT`) installed on your system
- **Python environment** capable of running the `config_qor_helper.py` script
- **MATLAB** (for FFT test vector generation and regression checking)
- **Vitis tools** (for AIE compilation and simulation)

## How to Trigger the Skill

The agent activates this skill automatically when you mention any of the following in your prompt:

- Config QoR Helper
- Configuration prediction / QoR optimization
- FFT or DSP IP configuration for AIE
- AIE design configuration
- Running `config_qor_helper`

**Example prompts:**

```
I need to find the best FFT configuration for a 512-point cint16 FFT with throughput > 1000 MSPS on AIE.
```

```
Help me run the config_qor_helper for fft_ifft_dit_1ch with AIE-ML.
```

```
I want to predict configurations for an FFT IP and validate the best one.
```

## Workflow Overview (5 Stages)

### Stage 1 -- Specify Design Requirements

You provide:
- **IP name** (e.g., `fft_ifft_dit_1ch`)
- **AIE Variant** (AIE, AIE-ML, or AIE-MLv2)
- **Parameter constraints** (data type, point size, etc.)
- **QoR targets** (throughput, latency)

The agent creates a constraint JSON file under `constraints/`.

### Stage 2 -- Set Configuration Priorities

The agent configures sort order for the predicted results. Default: fewest AIE tiles first, highest throughput first. You can customize.

### Stage 3 -- Execute the Prediction Script

The agent will ask you for:
1. Your `DSPLIB_ROOT` path
2. Commands to set up the Python environment

Then it runs `config_qor_helper.py` and stores results in `results/`.

### Stage 4 -- Analyze Predicted Configurations

The agent presents a table of valid configurations. You select a row to proceed with.

### Stage 5 -- Validate the Selected Configuration

The agent generates all project files, asks for your platform/part preference, then builds and simulates:

| Step | What Happens | User Action Needed? |
|------|-------------|---------------------|
| 5a | Creates project directory under `designs/` | No |
| 5b | Generates `graph.h` and `graph.cpp` | No |
| 5c | Generates `Makefile` | **Yes** -- choose platform option |
| 5d | Deploys shared utility scripts | No |
| 5e | Generates `gen_vectors.m` and `regression.m` (FFT only) | No |
| 5f | Runs `make gen_vectors x86all` | **Yes** -- provide tool source commands |

## Points Where You Must Provide Input

The agent will pause and wait for your input at these points:

| When | What To Provide |
|------|----------------|
| Stage 1 | AIE Variant choice (AIE / AIE-ML / AIE-MLv2) |
| Stage 3 | `DSPLIB_ROOT` path and Python environment setup commands |
| Stage 4 | Which configuration row to use |
| Stage 5c | Platform option: (1) default, (2) custom platform, or (3) PART number |
| Stage 5f | Commands to source MATLAB and Vitis tools |

## Generated File Structure

After a complete run, your workspace will look like this:

```
<project_root>/
├── constraints/
│   └── fft_512_1000.json              # Constraint file
├── results/
│   └── fft_512_1000.csv               # Predicted configurations
└── designs/
    ├── utility_scripts/
    │   ├── extract_aie_resources.py    # AIE resource extraction
    │   ├── extract_latency.py          # Latency metric extraction
    │   └── extract_throughput.py       # Throughput metric extraction
    └── fft_ifft_dit_1ch_2_1041/       # <IP>_<Row>_<Throughput>
        ├── src/
        │   ├── fft_128_graph.h         # AIE graph code
        │   └── fft_128_app.cpp         # Testbench
        ├── Makefile
        ├── aie.cfg
        ├── gen_vectors.m               # MATLAB test vector generator (FFT)
        └── regression.m                # MATLAB regression checker (FFT)
```

## Skill File Reference

| File | Description |
|------|-------------|
| `SKILL.md` | Main workflow instructions (5-stage methodology) |
| `helper_syntax.md` | `config_qor_helper.py` command syntax and path handling |
| `constraint_syntax.md` | Constraint JSON format, AIE variant mapping, sort options |
| `ip_parameters.md` | IP template parameters and derived value calculations |
| `validation.md` | Code templates (graph.h, graph.cpp, Makefile, gen_vectors.m, regression.m) |

## Extending to Other IPs

The skill is designed to support additional DSP library IPs beyond `fft_ifft_dit_1ch`. The constraint file structure, Makefile, utility scripts, and workflow stages are IP-agnostic. Only the following are FFT-specific:

- `gen_vectors.m` -- MATLAB test vector generation
- `regression.m` -- MATLAB simulation verification
- IP parameter details in `ip_parameters.md`

To add a new IP, update `ip_parameters.md` with the IP's template parameters and add corresponding test vector/regression templates to `validation.md`.
