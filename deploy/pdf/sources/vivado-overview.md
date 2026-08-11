<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Vivado MCP Server and Agent Skills

The Vivado MCP Server connects to AMD documentation, drives a live Vivado session, and automates entire FPGA workflows — all through natural language.

## How It Works — Closed-Loop Automation

The agent executes commands, hits an error, searches docs for the fix, applies it, and verifies — automatically.

<div markdown="0">
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 520" font-family="'Segoe UI','Helvetica Neue',Arial,sans-serif" style="width:100%;max-width:960px;margin:1.5em auto;display:block;">
  <defs>
    <marker id="seq-arrowCyan" viewBox="0 0 10 7" refX="9" refY="3.5" markerWidth="8" markerHeight="6" orient="auto"><polygon points="0 0,10 3.5,0 7" fill="#06b6d4"/></marker>
    <marker id="seq-arrowGray" viewBox="0 0 10 7" refX="9" refY="3.5" markerWidth="8" markerHeight="6" orient="auto"><polygon points="0 0,10 3.5,0 7" fill="#94a3b8"/></marker>
    <marker id="seq-arrowGreen" viewBox="0 0 10 7" refX="9" refY="3.5" markerWidth="8" markerHeight="6" orient="auto"><polygon points="0 0,10 3.5,0 7" fill="#10b981"/></marker>
    <marker id="seq-arrowAmber" viewBox="0 0 10 7" refX="9" refY="3.5" markerWidth="8" markerHeight="6" orient="auto"><polygon points="0 0,10 3.5,0 7" fill="#d97706"/></marker>
  </defs>

  <!-- Background -->
  <rect width="960" height="520" rx="12" fill="#f8fafc" stroke="#e2e8f0" stroke-width="1"/>

  <!-- Column headers -->
  <rect x="60" y="16" width="160" height="36" rx="6" fill="#fef3c7" stroke="#f59e0b" stroke-width="1.2"/>
  <text x="140" y="40" text-anchor="middle" font-size="13" font-weight="700" fill="#92400e">FPGA Engineer</text>

  <rect x="310" y="16" width="160" height="36" rx="6" fill="#dbeafe" stroke="#3b82f6" stroke-width="1.2"/>
  <text x="390" y="40" text-anchor="middle" font-size="13" font-weight="700" fill="#1e40af">AI Agent</text>

  <rect x="560" y="16" width="160" height="36" rx="6" fill="#ffedd5" stroke="#f97316" stroke-width="1.2"/>
  <text x="640" y="40" text-anchor="middle" font-size="13" font-weight="700" fill="#9a3412">Vivado (Live)</text>

  <rect x="790" y="16" width="160" height="36" rx="6" fill="#d1fae5" stroke="#10b981" stroke-width="1.2"/>
  <text x="870" y="40" text-anchor="middle" font-size="12" font-weight="700" fill="#065f46">Knowledge Base</text>

  <!-- Lifelines -->
  <line x1="140" y1="56" x2="140" y2="490" stroke="#f59e0b" stroke-width="1.5" stroke-dasharray="6,4" opacity="0.4"/>
  <line x1="390" y1="56" x2="390" y2="490" stroke="#3b82f6" stroke-width="1.5" stroke-dasharray="6,4" opacity="0.4"/>
  <line x1="640" y1="56" x2="640" y2="490" stroke="#f97316" stroke-width="1.5" stroke-dasharray="6,4" opacity="0.4"/>
  <line x1="870" y1="56" x2="870" y2="490" stroke="#10b981" stroke-width="1.5" stroke-dasharray="6,4" opacity="0.4"/>

  <!-- Step 1: Engineer -> Agent: prompt -->
  <line x1="145" y1="90" x2="383" y2="90" stroke="#d97706" stroke-width="2" marker-end="url(#seq-arrowAmber)"/>
  <text x="264" y="83" text-anchor="middle" font-size="11.5" font-weight="500" fill="#92400e">"Run synthesis on my design"</text>
  <circle cx="30" cy="90" r="12" fill="#3b82f6"/><text x="30" y="94" text-anchor="middle" font-size="10" font-weight="700" fill="#fff">1</text>

  <!-- Step 2: Agent -> Vivado: vivado_execute -->
  <line x1="395" y1="140" x2="633" y2="140" stroke="#06b6d4" stroke-width="2" marker-end="url(#seq-arrowCyan)"/>
  <text x="514" y="133" text-anchor="middle" font-size="11" font-weight="600" fill="#0891b2" font-family="'Roboto Mono',monospace">vivado_execute launch_runs synth_1</text>
  <circle cx="30" cy="140" r="12" fill="#3b82f6"/><text x="30" y="144" text-anchor="middle" font-size="10" font-weight="700" fill="#fff">2</text>

  <!-- Step 3: Vivado -> Agent: error -->
  <line x1="633" y1="195" x2="397" y2="195" stroke="#94a3b8" stroke-width="2" stroke-dasharray="6,3" marker-end="url(#seq-arrowGray)"/>
  <text x="514" y="188" text-anchor="middle" font-size="11" font-weight="500" fill="#dc2626" font-family="'Roboto Mono',monospace">ERROR: [Synth 8-3352]</text>
  <circle cx="30" cy="195" r="12" fill="#3b82f6"/><text x="30" y="199" text-anchor="middle" font-size="10" font-weight="700" fill="#fff">3</text>

  <!-- Loop bracket -->
  <rect x="350" y="225" width="570" height="155" rx="8" fill="none" stroke="#06b6d4" stroke-width="1.5" stroke-dasharray="8,4"/>
  <rect x="350" y="225" width="110" height="22" rx="4" fill="#06b6d4"/>
  <text x="405" y="240" text-anchor="middle" font-size="10" font-weight="700" fill="#fff">CLOSED LOOP</text>

  <!-- Step 4: Agent -> Docs: doc_search -->
  <line x1="395" y1="270" x2="863" y2="270" stroke="#10b981" stroke-width="2" marker-end="url(#seq-arrowGreen)"/>
  <text x="629" y="263" text-anchor="middle" font-size="11" font-weight="600" fill="#059669" font-family="'Roboto Mono',monospace">vivado_doc_search "Synth 8-3352 resolution"</text>
  <circle cx="30" cy="270" r="12" fill="#3b82f6"/><text x="30" y="274" text-anchor="middle" font-size="10" font-weight="700" fill="#fff">4</text>

  <!-- Step 5: Docs -> Agent: KBA result -->
  <line x1="863" y1="320" x2="397" y2="320" stroke="#94a3b8" stroke-width="2" stroke-dasharray="6,3" marker-end="url(#seq-arrowGray)"/>
  <text x="629" y="313" text-anchor="middle" font-size="11" font-weight="500" fill="#065f46">KBA with fix and Tcl command</text>
  <circle cx="30" cy="320" r="12" fill="#3b82f6"/><text x="30" y="324" text-anchor="middle" font-size="10" font-weight="700" fill="#fff">5</text>

  <!-- Step 6: Agent -> Vivado: apply fix -->
  <line x1="395" y1="365" x2="633" y2="365" stroke="#06b6d4" stroke-width="2" marker-end="url(#seq-arrowCyan)"/>
  <text x="514" y="358" text-anchor="middle" font-size="11" font-weight="600" fill="#0891b2" font-family="'Roboto Mono',monospace">vivado_execute apply fix</text>
  <circle cx="30" cy="365" r="12" fill="#3b82f6"/><text x="30" y="369" text-anchor="middle" font-size="10" font-weight="700" fill="#fff">6</text>

  <!-- Step 7: Vivado -> Agent: success -->
  <line x1="633" y1="420" x2="397" y2="420" stroke="#94a3b8" stroke-width="2" stroke-dasharray="6,3" marker-end="url(#seq-arrowGray)"/>
  <text x="514" y="413" text-anchor="middle" font-size="11" font-weight="500" fill="#059669" font-family="'Roboto Mono',monospace">synthesis complete · 0 errors</text>
  <circle cx="30" cy="420" r="12" fill="#3b82f6"/><text x="30" y="424" text-anchor="middle" font-size="10" font-weight="700" fill="#fff">7</text>

  <!-- Step 8: Agent -> Engineer: done -->
  <line x1="383" y1="470" x2="147" y2="470" stroke="#d97706" stroke-width="2" marker-end="url(#seq-arrowAmber)"/>
  <text x="264" y="463" text-anchor="middle" font-size="11.5" font-weight="500" fill="#065f46">"Fixed the error — synthesis passed"</text>
  <circle cx="30" cy="470" r="12" fill="#10b981"/><text x="30" y="474" text-anchor="middle" font-size="10" font-weight="700" fill="#fff">8</text>

  <!-- Footer labels -->
  <rect x="60" y="494" width="160" height="22" rx="4" fill="#fef3c7" stroke="#f59e0b" stroke-width="0.8"/>
  <text x="140" y="509" text-anchor="middle" font-size="10" font-weight="600" fill="#92400e">FPGA Engineer</text>
  <rect x="310" y="494" width="160" height="22" rx="4" fill="#dbeafe" stroke="#3b82f6" stroke-width="0.8"/>
  <text x="390" y="509" text-anchor="middle" font-size="10" font-weight="600" fill="#1e40af">AI Agent</text>
  <rect x="560" y="494" width="160" height="22" rx="4" fill="#ffedd5" stroke="#f97316" stroke-width="0.8"/>
  <text x="640" y="509" text-anchor="middle" font-size="10" font-weight="600" fill="#9a3412">Vivado (Live)</text>
  <rect x="790" y="494" width="160" height="22" rx="4" fill="#d1fae5" stroke="#10b981" stroke-width="0.8"/>
  <text x="870" y="509" text-anchor="middle" font-size="10" font-weight="600" fill="#065f46">Knowledge Base</text>
</svg>
</div>

## Capabilities

- **Documentation Search** — RAG-powered search across 15+ User Guides, Application Notes, and Knowledge Base Articles
- **Session Control** — Start, stop, and monitor Vivado sessions (TCL or GUI mode)
- **Design Execution** — Run any Tcl command through a standardized MCP API
- **Agent Skills** — Expert-authored workflow files that encode FPGA methodology. Use the bundled example designs to get started; official standalone skills are coming in upcoming releases.
- **Documentation Chat** — The same knowledge base is also available as a standalone web chat at vivado.amd.com/chat — no setup required.

## What's Included

### agentic-ai-suite.zip

Agent skills, getting started guides, and the MCP tools reference.

| Category | Skill / Content | Description |
|----------|----------------|-------------|
| Timing | timing-methodology-checks | Run 55+ timing methodology checks (UG906) on synthesized designs, identify violations, and generate actionable RTL/XDC fixes |
| Revision Control | vivado-revision-control | Automate revision control setup — detect project type, analyze sources, export components, capture settings, and generate a build script for reproducible project recreation |
| Hardware Debug | hw-ila-debug | Interact with ILA debug cores on live hardware — discover cores, configure triggers, arm, capture, upload, and export waveform data (CSV/VCD) |
| Hardware Debug | hw-noc-debug | Debug Versal NoC issues — autonomous pipeline: connect, scan, design correlation, root-cause analysis for AXI failures, decode errors, and timeouts |
| Hardware Debug | hw-vio-debug | Interact with VIO debug cores on live hardware — read input probes, drive output probes, monitor activity, and reset outputs |
| Setup | Getting Started Guides | Setup guides for VS Code, Cursor, and CLI tools |
| Reference | MCP Tools Reference | Complete reference for all Vivado MCP tools |

### vivado-ai-assistant-examples-0.6.8.zip

Self-contained example workspaces with design files, agent skills, and step-by-step walkthroughs.

| Category | Example | Description |
|----------|---------|-------------|
| Design Capture | Design Creation Prototype | AI-guided project creation, IP instantiation, and block design assembly |
| Design Analysis | RTL Lint | Run `synth_design -lint` to catch RTL issues before synthesis |
| Design Analysis | Multi-Run Analysis | Compare results across multiple implementation runs |
| Design Analysis | Opt Design Log Analysis | Parse and analyze optimization logs for actionable insights |
| Design Closure | Timing Closure Prototype | End-to-end timing analysis and constraint fixing |
| Design Closure | AXI4 Debug Simulation | Debug AXI4 protocol issues through AI-guided simulation |
| Hardware Debug | ILA & VIO Insertion Flow | Insert AXIS-ILA and AXIS-VIO debug cores into a Versal VCK190 block design |
