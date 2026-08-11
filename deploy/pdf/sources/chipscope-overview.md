<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# ChipScope MCP Server

**Debug AMD Versal™ devices straight from your AI environment.** ChipScope brings
agentic AI to hardware debug — drive ChipScoPy, `hw_server`, and `cs_server` in
plain language. Run an ILA capture, an IBERT eye scan, a DDR margin check, or a
NoC performance analysis just by asking your AI client.

!!! info "Requirements"
    ChipScope MCP supports **AMD Versal™ devices only** and requires
    **Vivado 2026.1 or later**.

## What it does

| Capability | What you can ask for |
|------------|----------------------|
| **ILA capture** | Configure triggers, arm, capture, and upload waveforms |
| **IBERT / GT links** | Eye scans and YK scans with inline plots, link tuning |
| **DDR memory** | Calibration status and margin (eye) scans |
| **NoC** | Element discovery, status, and performance/latency analysis |
| **System monitor** | Temperature, voltage, and alarm readings |
| **Device & memory** | Scan for debug cores, read/write memory, device management |

## How it fits

- **Versal-native** — purpose-built MCP tools backed by the ChipScoPy API.
- **Uses your lab servers** — connects to your existing `hw_server` and
  `cs_server`. Bring your own board.
- **Inline results** — eye diagrams and plots render directly in chat, with no
  GUI round-trip.
- **Local-only** — the server runs as a local subprocess of your AI client over
  the stdio transport. No network listener, no remote access, and it runs with
  the same privileges as the client that launched it.

## Supported clients

VS Code + GitHub Copilot (recommended), Cursor, Claude Code, Codex, or any
other MCP-compatible agentic AI IDE or CLI.
