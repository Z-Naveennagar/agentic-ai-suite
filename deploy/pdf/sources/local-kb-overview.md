<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# AMD Embedded — Local Knowledge Base (Local RAG Database)

**Search the full AMD Embedded documentation set — Vivado, Vitis, Power
Design Manager, ChipScope, System Software, example designs, Wiki, and
Answer Records — from your AI assistant, with retrieval running entirely on
your own machine and no outbound network calls.**

This is built for engineers who work in **disconnected or air-gapped
environments** — secure labs, classified programs, or any network-restricted
site. You get grounded, cited answers from real AMD documentation without
your questions or the retrieved content ever leaving the machine.

The database (embedding model + vector search + MCP server) is deployed
once and works identically no matter which model writes the final answer.
You then pick one of two ways to generate answers, based on your hardware
and network policy.

## Prerequisites

| Requirement | Notes |
|---|---|
| **Docker** (Engine + Compose, or Docker Desktop) | Required — the RAG database runs as three containers. |
| **Disk** | ~8 GB free (documentation snapshot + embedding model + container images). |
| **Operating system** | Verified on **Windows** and **Linux**. The fully local-LLM path is documented for Linux with a supported AMD GPU (ROCm). |
| **An answering model** | A frontier cloud model (e.g. GitHub Copilot) *or* a local GPU-hosted LLM. |
| **An MCP client** | VS Code (recommended) or OpenCode. |

## What's in this guide

Chapters 1–3 apply to **every** deployment. Chapters 4 and 5 are
**alternatives, not a sequence** — read whichever one matches your
answering-model choice:

- **Quick Start** — The fastest path on a connected machine
- **RAG Database Setup** — Full architecture, concepts, and air-gapped deployment
- **Operate & Troubleshoot** — CLI reference, validation, and troubleshooting
- **Frontier Model** — Use with a cloud model (GitHub Copilot); no GPU needed
- **Local LLM** — Fully air-gapped deployment with a local LLM on AMD GPU (ROCm)
