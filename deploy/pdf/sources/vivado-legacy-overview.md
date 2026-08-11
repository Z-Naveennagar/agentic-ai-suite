<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Vivado AI Assistant — Examples Archive (v0.6.8)

This document covers the example designs bundled in **vivado-ai-assistant-examples-0.6.8.zip** — a frozen archive targeting **Vivado 2025.2** with the **Vivado AI Assistant VS Code Extension v0.6.8** and **MCP Server v0.6.8**.

> **Note:** This archive is frozen at version 0.6.8. For the latest Vivado AI Assistant with updated skills, tools, and examples, see the current release at the [EA Lounge](https://pages.gitenterprise.xilinx.com/swm/AMD-Embedded-Agentic-AI-Suite/latest/).

## What's in the Zip

```
vivado-ai-assistant-examples-0.6.8/
├── design-creation-prototype/     # Spec-driven block design assembly (Kria KV260)
├── rtl-lint/                      # RTL linting with synth_design -lint
├── multi-run-analysis/            # Compare 6 implementation strategies
├── opt-design-analysis/           # Parse opt_design logs with -debug_log
├── timing-closure-prototype/      # Iterative timing closure with constraints
├── axi4-debug-simulation/         # AXI4 protocol debug via XSim
└── ila-insertion-flow/            # AXIS-ILA & VIO insertion on Versal VCK190
```

Each example is self-contained with RTL sources, constraints, agent skills (`.claude/skills/`), and a prompt library (`prompts.md`).

## Version Matrix

| Component | Version |
|-----------|---------|
| Vivado | **2025.2** |
| Vivado AI Assistant VS Code Extension | **0.6.8** |
| Vivado MCP Server | **0.6.8** |
| Example Designs Zip | `vivado-ai-assistant-examples-0.6.8.zip` |

## Architecture

The Vivado AI Assistant uses an MCP (Model Context Protocol) server to drive Vivado:

```
Your IDE  ──MCP protocol──▶  Vivado MCP Server  ──Tcl──▶  Vivado
```

1. **Your IDE** (VS Code with Copilot) connects to the MCP server via the bundled extension
2. **The MCP server** translates AI agent requests into Vivado Tcl commands
3. **Vivado** executes the commands and returns results through the same chain

## Examples at a Glance

| Example | Category | Target Device | Key Skill |
|---------|----------|--------------|-----------|
| Design Creation Prototype | Design Capture | Kria KV260 (Zynq UltraScale+) | Spec-driven IPI build |
| RTL Lint | Design Analysis | xcvu9p (VU9P) | `rtl-lint` |
| Multi-Run Analysis | Design Analysis | xcvu9p (VU9P) | `multi-run-analysis` |
| Opt Design Analysis | Design Analysis | xcu200 (Alveo U200) | `opt-design-analysis` |
| Timing Closure | Design Closure | xcvu9p (VU9P, multi-SLR) | `post-route-dcp-analysis` + `timing-closure-prototype` |
| AXI4 Debug Simulation | Design Analysis | xc7a35t (Artix-7) | `axi4-debug-simulation` |
| ILA & VIO Insertion | Hardware Debug | xcvc1902 (Versal VCK190) | `bd-ila-insertion` + `bd-vio-insertion` |
