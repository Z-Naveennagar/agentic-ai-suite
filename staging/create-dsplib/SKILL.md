---
name: create-dsplib
description: Use this skill to create all files required for an AI Engine project using the DSP Library
author: Florent Werbrouck
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
# Create DSPLib Project

## What This Skill Does

This Cursor Agent Skill automates the **DSP Library Project Creation** workflow for AMD Vitis DSP Library IPs. It guides you through creating all the necessary files for an AI Engine project using the AMD Vitis DSP Library, including the graph application, AI Engine compiler configuration file, and Makefile, based on your design requirements.

This is an orchestration skill that invokes the following sub-skills in sequence to generate the complete project scaffold.

| Skill | Description | 
| --- | --- |
| `get-vitis-library` | Retrieves the AMD Vitis DSP Library repository reference files for the specified library version. |
| `create-dsplib-graph` | Generates the AI Engine graph header file
| `create-kernel-app` | Creates the AI Engine graph testbench application file |
| `create-dsplib-makefile` | Generates the Makefile for building the AI Engine project |
| `create-dsplib-stimuli` | Creates input stimuli files for testing the graph application |
| `create-dsplib-readme` | Generates a README file documenting the project setup and usage instructions |

---


## How to Trigger the Skill

The agent activates this skill automatically when you mention any of the following in your prompt:

- DSP Library project creation

**Example prompts:**

```
I want to create a new AI Engine project using the DSP Library for an FFT application.
```

```
Help me create a DSP Library project for an FFT application on AIE-ML.
```

```
I want to create a DSP Library project performing a symmetric 18-tap FIR application targeting a VEK280 board.
```

## Workflow Steps

1. Get Vitis Library Repository using `get-vitis-library` skill
2. Create AI Engine graph with DSP Library using `create-dsplib-graph` skill
3. Create AI Engine application using `create-kernel-app` skill
4. Create graph Makefile using `create-dsplib-makefile` skills
5. Create input stimuli files using `create-dsplib-stimuli` skill
6. Create a README file for the project using `create-dsplib-readme` skill

## Generated File Structure

After a complete run, your workspace will look like this:

```
<project_root>/
└── Makefile/
└── src/
    ├── <graph_name>_graph.hpp         # AI Engine graph header file
    └── <graph_name>_app.cpp           # AI Engine graph testbench
```