<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# vitis-xsa-app

A Claude Code skill that takes an XSA file and builds a complete Vitis platform and application — no IDE needed. It generates a Python build script, runs it with the Vitis-bundled Python, and hands you a ready-to-use ELF.

---

## Requirements

- **Claude Code** CLI installed and running
- **Vitis 2024.1 or later** (e.g. `/proj/gsd/vivado/2025.2/Vitis`)
- An **XSA file** exported from Vivado for your target board

---

## Installation

```bash
cp -r vitis-xsa-app ~/.claude/skills/
```

Claude Code picks up skills automatically from `~/.claude/skills/` — no restart needed.

> **Tip:** The first time you use the skill it will ask for your Vitis installation path and remember it for future runs.

---

## Directory Structure

```
vitis-xsa-app/
├── SKILL.md                    # Instructions Claude follows — edit to change behavior
├── README.md                   # This file
├── vitis_config.json           # Saved Vitis path (auto-updated)
│
├── scripts/
│   ├── inspect_xsa.py          # Parses an XSA to list available processor cores
│   ├── save_vitis_path.py      # Reads/writes the saved Vitis path
│   └── vitis_env.sh            # Verifies a Vitis install and finds the bundled Python
│
├── references/
│   └── api-cheatsheet.md       # Vitis Python API quick reference
│
└── examples/
    ├── standalone_hello.py     # ZynqMP → standalone hello_world
    └── linux_app.py            # ZynqMP → Linux app with custom sources
```

---

## Usage

Just tell Claude what you want in plain English. The skill is triggered automatically:

```
"create an application from zcu102.xsa"
"build vck190.xsa with ./src"
"use vck190.xsa and ./src to create a standalone app on a72"
"build all XSA files"
```

You can also pass explicit arguments to skip interactive questions:

```
<xsa_path | --all>  [--os standalone|linux]  [--cpu <cpu_name>]
                    [--app <name>]            [--template <template>]
                    [--src <src_dir>]         [--vitis <install_path>]
```

| Argument | Effect |
|----------|--------|
| `<xsa_path>` | Path to the `.xsa` file |
| `--all` | Build every `*.xsa` found in the current directory |
| `--os` | Set the OS — skips the OS question. Accepts `standalone`, `bare-metal`, or `linux` |
| `--cpu` | Set the processor core — skips the CPU question |
| `--app` | Override the generated application name |
| `--template` | Use this template directly — skips the template question |
| `--src <dir>` | Import `.c`/`.h`/`.cpp` files from this directory into the app |
| `--vitis` | Override the Vitis installation path for this run |

---

## How Many Questions Will It Ask?

The skill tries to ask as few questions as possible. Each piece of information you provide up front eliminates one interactive step:

| You provide | Skill skips |
|-------------|-------------|
| `--os` | OS selection question |
| `--cpu` | Processor selection question |
| `--src` + standalone OS | Template question (auto-selects `empty_application`) |
| `--src` | Source directory question |
| `--template` | Template question |

**Example — fully non-interactive:**
```
"use vck190.xsa --os standalone --cpu psv_cortexa72_0 --src ./src --template hello_world"
```
No questions asked at all — the script is generated and the build starts immediately.

**Example — two questions (OS + CPU):**
```
"build vck190.xsa with ./src"
```
The skill knows to use `empty_application` (standalone + custom source) so it only asks which OS and which core.

---

## Interactive Questions (single-XSA mode)

When information is not provided up front, the skill asks these questions in order:

### 1 — OS type

| Option | When available |
|--------|---------------|
| `standalone` | Always |
| `linux` | Only when the XSA contains at least one Linux-capable A-class core |

If no A-class Linux-capable core exists (e.g. MicroBlaze-only), `standalone` is selected automatically.

### 2 — Processor / core *(filtered by OS)*

- **Standalone**: all cores are shown (A-class, R5, PMU/PMC), first Cortex-A recommended
- **Linux**: only Linux-capable CPUs shown, using the SMP name (e.g. `psv_cortexa72`, no `_0` suffix)

### 3 — Template *(standalone, no `--src`)*

`peripheral_tests` (recommended) · `hello_world` · `freertos_hello_world` · `empty_application`

Skipped automatically when:
- `--src` is provided with standalone OS → `empty_application` is used
- Linux OS is selected → `empty_application` is used

### 4 — Source directory

Only asked if `--src` was not provided. You can choose to use the template's built-in sources or import your own files.

---

## Supported Devices

| Family | Linux-capable CPU (SMP name) | Standalone-only cores |
|--------|-----------------------------|-----------------------|
| Zynq-7000 | `ps7_cortexa9` | — |
| ZynqMP / Zynq US+ | `psu_cortexa53` | R5 (`psu_cortexr5_0/1`), PMU |
| Versal | `psv_cortexa72` | R5 (`psv_cortexr5_0/1`), PMC |
| Versal NET | `psx_cortexa78` | R52 (`psx_cortexr52_0–3`), PMC |
| MicroBlaze (PL) | — | Standalone only |

---

## Multi-XSA Batch Mode

Say "build all XSA files" or pass `--all` to discover every `*.xsa` in the current directory and build them all in one script. Each board gets its own platform and app; they share a single workspace. Batch mode always uses **standalone** — Linux is not supported here.

---

## What Gets Created

| Artifact | Location |
|----------|----------|
| Build script | `./<xsa_stem>_build_app.py` |
| Workspace | `./<platform_name>_ws/` |
| Platform XPFM | `<ws>/<platform>/export/<platform>/<platform>.xpfm` |
| Application ELF | `<ws>/<app>/build/<app>.elf` |

---

## Vitis Path Resolution

The skill finds Vitis in this order — stopping as soon as it finds a valid path:

1. `--vitis <path>` argument
2. `$XILINX_VITIS` environment variable
3. Path saved from a previous run (`vitis_config.json`)
4. Interactive prompt (saved automatically for next time)

---

## Troubleshooting

| Problem | Likely cause | Fix |
|---------|-------------|-----|
| `ModuleNotFoundError: No module named 'vitis'` | Wrong Python used | The skill handles this automatically; if running the script manually, use `scripts/vitis_env.sh` to get the correct Python path |
| `No processor found` / `Invalid cpu` | Incorrect CPU name | Run `python3 scripts/inspect_xsa.py <your.xsa>` to see exact names |
| Vitis path rejected | Config is stale or Vitis was moved | Delete `vitis_config.json` or use `--vitis <new_path>` |
| `Can't find a usable init.tcl` in build output | Harmless Tcl noise from the Vitis server | Safe to ignore — the build completes successfully |
