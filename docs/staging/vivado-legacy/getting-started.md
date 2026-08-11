<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Getting Started — VS Code Extension v0.6.8

Set up the Vivado AI Assistant in VS Code for use with the **vivado-ai-assistant-examples-0.6.8.zip** example designs.

## Prerequisites

- **Vivado 2025.2** installed and on your `PATH`
- **VS Code** (version 1.114 or later)
- The **Vivado AI Assistant Extension** VSIX v0.6.8 — download from the Downloads page

## Step 1 — Install the Extension

The VSIX extension bundles both the Vivado AI Assistant UI and the MCP server — no separate binary install needed.

### From VSIX file

1. Download `vivado-ai-extension-0.6.8.vsix` from the Downloads page
2. Open VS Code
3. Go to **Extensions** sidebar → click `⋯` → **Install from VSIX...**
4. Select the downloaded `.vsix` file

### From command line

```bash
code --install-extension vivado-ai-extension-0.6.8.vsix
```

## Step 2 — Configure Vivado Path

After installing the extension, set the path to your Vivado 2025.2 executable:

1. Open **Settings** (Ctrl+,)
2. Search for **Vivado Path**
3. Enter the full path to your Vivado binary (e.g., `/tools/Xilinx/Vivado/2025.2/bin/vivado`)

> If Vivado is already on your system `PATH`, this step is optional — the extension will auto-detect it.

## Step 3 — Download and Extract Examples

Download `vivado-ai-assistant-examples-0.6.8.zip` from the Downloads page, then extract:

```bash
unzip vivado-ai-assistant-examples-0.6.8.zip
```

Open any example folder (e.g., `rtl-lint/`) as your VS Code workspace.

## Step 4 — Configure Agent Skills

Each example includes pre-configured skills under `.claude/skills/`. When you open an example folder as your workspace, the skills are automatically available to the AI agent.

Skills can also be placed in your home directory for global access:

```
~/.claude/
└── skills/
    └── rtl-lint/
        └── SKILL.md
```

## Step 5 — Verify the Setup

1. Open the **Copilot Chat** panel in VS Code (Ctrl+Alt+B)
2. Switch to **Agent** mode (click the mode selector)
3. Type: `List the available MCP tools`
4. You should see Vivado-related tools like `vivado_execute`, `vivado_connect`, etc.

You're ready! Open one of the example designs and try the prompts from its `prompts.md` file.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Copilot Chat panel not visible | Use Ctrl+Alt+B or search for 'Copilot Chat' in the Command Palette (Ctrl+Shift+P) |
| Vivado MCP tools missing | Click **Configure tools** in the chat panel and ensure Vivado MCP tools are listed. Reload the window if needed (Ctrl+Shift+P → `Developer: Reload Window`) |
| "Connection refused" | Reload the window and verify MCP tools are available. Check **Output → Vivado MCP** for errors |
| Skills not loading | Open **Settings** → search for **skills**. Ensure **Chat: Use Agent Skills** is checked and paths include `.claude/skills` |
