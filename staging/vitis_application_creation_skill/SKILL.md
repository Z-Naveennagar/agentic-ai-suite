---
name: vitis-xsa-app
description: This skill should be used when the user wants to "create an application from an XSA file", "build an embedded app from XSA", "generate a Vitis application using an XSA", "create platform and app from XSA", "make a Vitis project from XSA file", "build for all XSA files", or provides an XSA file path and wants an embedded software application built with the Vitis Python API.
argument-hint: <xsa_path|--all> [--os standalone|linux] [--cpu <cpu_name>] [--app <name>] [--template <template>] [--src <src_dir>] [--vitis <install_path>]
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
# Vitis XSA → Application Skill

Generate and run a Vitis Python API script that creates a platform from an XSA file and builds an embedded application component on top of it. The workspace is always the **current working directory**.

Supports **single-XSA** mode (one XSA path) and **multi-XSA** mode (`--all` or "all given XSA" phrasing), which discovers every `*.xsa` in the CWD and builds all of them in a single script.

## What This Skill Does

1. **Resolve Vitis environment** — find or ask for the Vitis installation path
2. **Detect mode** — single XSA or all XSAs in CWD
3. **Inspect XSA(s)** — discover processor cores per XSA
4. **Present choices** — processor, OS type, and template (skipped / auto-selected in multi mode)
5. **Generate** a complete Python script using the `vitis` module
6. **Save** the script and **run** it using the Vitis-bundled Python

---

## Step 0: Resolve the Vitis Environment

Before anything else, determine the Vitis installation path using this priority order:

### 0a — Check `--vitis` argument and `$XILINX_VITIS` env var

If the user passed `--vitis <path>` in `$ARGUMENTS`, extract and use that path directly → skip to Step 0c.

Otherwise check the shell environment:
```bash
echo "XILINX_VITIS=${XILINX_VITIS}"
```
If `XILINX_VITIS` is set and non-empty → use it → skip to Step 0c.

### 0b — Read saved path; ask user to confirm or change

Read the saved path from the config file:
```bash
python3 <skill_base_dir>/scripts/save_vitis_path.py get
```

This reads `<skill_base_dir>/vitis_config.json`. The result is either a saved path (e.g. `/proj/gsd/vivado/2025.2/Vitis`) or empty.

Present `AskUserQuestion` with:
- If a saved path exists → show it as the first option labelled **"<saved_path> (last used)"**
- Always include **"Enter a different path"** as the last option

```
Example question options:
  [0] /proj/gsd/vivado/2025.2/Vitis  (last used)   ← if saved path exists
  [1] Enter a different path
```

If the user selects "Enter a different path", prompt them to type the new path as free text.

### 0c — Verify the path and detect bundled Python

Run the verification script:
```bash
bash <skill_base_dir>/scripts/vitis_env.sh <VITIS_PATH>
```

On success it prints three lines:
```
VITIS_PATH=/proj/gsd/vivado/2025.2/Vitis
VITIS_PYTHON=/proj/gsd/vivado/2025.2/Vitis/tps/lnx64/python-3.13.0/bin/python3
VITIS_PYLIB=/proj/gsd/vivado/2025.2/Vitis/tps/lnx64/python-3.13.0/lib
```

Parse and store `VITIS_PATH`, `VITIS_PYTHON`, `VITIS_PYLIB` for use in Step 6.

On failure → show the error message, ask the user to provide the correct path, retry Step 0c.

### 0d — Save the path for next time

After a successful verification, persist the path so it becomes the default next time:
```bash
python3 <skill_base_dir>/scripts/save_vitis_path.py set <VITIS_PATH>
```

---

## Step 1: Detect Mode and Resolve XSA(s)

### Single-XSA mode (default)

If `$ARGUMENTS` contains an explicit XSA path (e.g. `./zcu106.xsa`):
- Convert to absolute path
- Proceed with that single XSA
- Continue to Step 2 (ask processor/OS/template interactively)

### Multi-XSA mode

Triggered when the user says "all given XSA", "all XSA files", uses `--all`, or provides no XSA path and there are multiple `*.xsa` in the CWD.

Find all XSA files, **excluding** any inside workspace subdirectories (`*_ws/`):
```bash
find "$(pwd)" -maxdepth 1 -name "*.xsa" | sort
```

Inspect each XSA in parallel:
```bash
python3 <skill_base_dir>/scripts/inspect_xsa.py <absolute_xsa_path>
```

**Ask the user to select options** using a single `AskUserQuestion` call with up to 4 questions:
- One question per XSA asking which processor to use (list all non-PMU/PMC processors from that XSA's inspect JSON as options, recommend first Cortex-A)
- One final question for the template (asked once for all XSAs):
  - `peripheral_tests` (Recommended)
  - `hello_world`
  - `empty_application`
  - `freertos_hello_world`

If there are more XSAs than fit in a single call (>3), batch them — ask 3 processors at a time, then template.

If the user passes `--template <name>` in arguments, skip the template question and use that value directly.

All builds use **standalone** OS — Linux is not supported in multi-XSA batch mode. App name per XSA = `<template>_<board_name>` where `board_name` = XSA stem (filename without `.xsa`).

---

## Step 2: Present OS, Processor, Template, and Source Choices (single-XSA mode only)

Ask questions in this order. Use a single `AskUserQuestion` call for up to 4 questions at once.

### 2a — Select OS type (FIRST question)

**Skip this question if `--os <value>` was provided in `$ARGUMENTS`** — use that value directly.
- Accept `standalone`, `bare-metal`, or `baremetal` as equivalent to `standalone`.
- Accept `linux` as `linux`.

Determine which OS options are available for this XSA:
- **Always available**: `standalone`
- **Available only if** at least one processor has `"supports_linux": true`: `linux`

**If linux IS available**, ask:

| Option | Label | Description |
|--------|-------|-------------|
| 1 | `standalone` (Recommended) | Bare-metal or FreeRTOS; you select a specific core (core 0, 1, 2, …) |
| 2 | `linux` | SMP Linux across all A-class cores simultaneously; R5/PMU cores not available |

**If linux is NOT available** (e.g. MicroBlaze-only, all processors have `supports_linux: false`):
- Skip this question, auto-select `standalone`, and inform the user ("All processors in this XSA are standalone-only; Linux is not available.")

### 2b — Select processor / core (SECOND question)

**Skip this question if `--cpu <name>` was provided in `$ARGUMENTS`** — use that value directly as the `cpu` field. Skip the inspect JSON lookup for processor selection (but still run `inspect_xsa.py` to get `domain_name` and other metadata).

Filter the processor list based on the OS selected in 2a.

**If OS = `standalone`**: Show ALL processors from the inspect JSON.
- Label: `cpu` field (e.g. `psu_cortexa53_0`, `psu_cortexr5_0`, `psu_pmu_0`)
- Description: `description` from inspect JSON
- Recommend the first Cortex-A core; place PMU/PMC entries last with "(advanced use only)" in description

**If OS = `linux`**: Show ONLY processors with `"supports_linux": true`.
- Deduplicate by `cpu_linux` — all cores sharing the same `cpu_linux` value (e.g. all four A53 cores → `psu_cortexa53`) appear as **one** entry
- Label: `cpu_linux` field (e.g. `psu_cortexa53`, `psv_cortexa72`)
- Description: `description` from inspect JSON + " (SMP — Linux manages all cores)"
- R5 / PMU / PMC / MicroBlaze processors are never shown for Linux

### 2c — Select template (THIRD question)

Skip if `--template <name>` was provided in `$ARGUMENTS`.

**If OS = `standalone` AND `--src` was provided (or source directory is already known):**
- Auto-select `empty_application`; skip this question entirely.
- Inform the user: "Using `empty_application` template — custom sources will be imported directly."

**Standalone OS (no source provided):**
- `peripheral_tests` (Recommended)
- `hello_world`
- `freertos_hello_world`
- `empty_application`

**Linux OS:**
- Auto-select `empty_application` (only supported template for linux); skip this question.

### 2d — Source code (FOURTH question)

**Skip this question if `--src <dir>` was provided in `$ARGUMENTS`** — use that path directly, list files that will be imported, and generate the `import_files()` block automatically. No confirmation needed.

Otherwise ask:

| Option | Label | Description |
|--------|-------|-------------|
| 1 | No (Recommended) | Use the template's built-in source files |
| 2 | Yes — provide a directory | Import custom `.c`/`.h`/`.cpp` files from a directory I specify |

If the user picks **Yes**, prompt for the source directory as free text:
```
Please enter the path to your source directory (e.g., /home/user/myapp/src):
```
Then list the files that will be imported to confirm:
```bash
ls <src_dir>/*.{c,h,cpp,cc} 2>/dev/null
```
Store the result as the `SRC_FILES_LIST` for use in Step 4's `{IMPORT_BLOCK}`.

---

## Step 3: Derive Remaining Parameters

| Parameter | Standalone | Linux |
|-----------|------------|-------|
| `platform_name` | XSA filename without `.xsa`, append `_platform` | same |
| `cpu` | `cpu` field from inspect JSON (e.g. `psu_cortexa53_0`) | `cpu_linux` field from inspect JSON (e.g. `psu_cortexa53`, no core suffix — SMP) |
| `domain_name` | `domain_standalone` field from inspect JSON | `domain_linux` field from inspect JSON |
| `generate_dtb` | `False` | `True` if arch is `zynquplus`, `versal`, or `versalnet`; `False` for `zynq` (Zynq-7000) |
| `workspace` | `os.path.join(os.getcwd(), "<platform_name>_ws")` | same |
| `app_name` | From `--app` arg if provided; otherwise `<template>_<xsa_stem>` | same |
| `src_dir` | From `--src` arg or Step 2d answer (empty if none) | same |

---

## Step 4: Generate the Python Script

### Single-XSA script

Use the template below, substituting all `{PLACEHOLDERS}`. Save as `./<xsa_stem>_build_app.py` (e.g., `zc702_build_app.py`).

```python
#!/usr/bin/env python3
# Vitis XSA → App script (generated by vitis-xsa-app skill)
import vitis
import os
import shutil

# ── Configuration ─────────────────────────────────────────────────────────────
XSA_PATH      = "{XSA_PATH}"           # absolute path to the .xsa file
PLATFORM_NAME = "{PLATFORM_NAME}"
CPU           = "{CPU}"
OS_TYPE       = "{OS_TYPE}"            # standalone or linux
DOMAIN_NAME   = "{DOMAIN_NAME}"
APP_NAME      = "{APP_NAME}"
TEMPLATE      = "{TEMPLATE}"
WORKSPACE     = os.path.join(os.getcwd(), "{PLATFORM_NAME}_ws")
# ──────────────────────────────────────────────────────────────────────────────

try:
    client = vitis.create_client()

    if os.path.isdir(WORKSPACE):
        shutil.rmtree(WORKSPACE)
    client.set_workspace(WORKSPACE)

    # Step 1: Create and build platform
    print(f"[1/3] Creating platform '{PLATFORM_NAME}' from {XSA_PATH} ...")
    platform = client.create_platform_component(
        name         = PLATFORM_NAME,
        hw_design    = XSA_PATH,
        cpu          = CPU,
        os           = OS_TYPE,
        domain_name  = DOMAIN_NAME,
        generate_dtb = {GENERATE_DTB},
    )
    platform.build()
    print("Platform built.")

    # Step 2: Locate the exported .xpfm
    platform_xpfm = client.find_platform_in_repos(PLATFORM_NAME)
    print(f"[2/3] Platform XPFM: {platform_xpfm}")

    # Step 3: Create application component
    print(f"[3/3] Creating app '{APP_NAME}' with template '{TEMPLATE}' ...")
    app = client.create_app_component(
        name     = APP_NAME,
        platform = platform_xpfm,
        domain   = DOMAIN_NAME,
        template = TEMPLATE,
    )

    {IMPORT_BLOCK}

    app.build()

    elf = os.path.join(WORKSPACE, APP_NAME, "build", f"{APP_NAME}.elf")
    print(f"\nApp '{APP_NAME}' built successfully.")
    print(f"  Workspace : {WORKSPACE}")
    print(f"  XPFM      : {platform_xpfm}")
    print(f"  ELF       : {elf}")

finally:
    vitis.dispose()
```

**Linux variant** — same script but:
- `CPU` = `cpu_linux` (no `_0` suffix)
- `OS_TYPE = "linux"`
- `DOMAIN_NAME` = `domain_linux`
- `generate_dtb = True` for ZynqMP/Versal
- `TEMPLATE = "empty_application"`

**Import block** (only when `--src` provided):
```python
app.import_files(
    from_loc        = "{SRC_DIR}",
    files           = {SRC_FILES_LIST},
    dest_dir_in_cmp = "src",
)
```

Otherwise replace `{IMPORT_BLOCK}` with `# (using template sources)`.

---

### Multi-XSA script

Save as `./<template>_build_all_apps.py` (e.g., `peripheral_tests_build_all_apps.py`). One Vitis client session, one shared workspace named `<template>_ws`.

Each entry in `BUILDS` is derived from the inspected XSA + auto-selected processor. App name = `<template>_<board>`.

```python
#!/usr/bin/env python3
# Vitis multi-XSA build script (generated by vitis-xsa-app skill)
import vitis
import os
import shutil

TEMPLATE  = "{TEMPLATE}"
WORKSPACE = os.path.join(os.getcwd(), f"{TEMPLATE}_ws")

# One entry per XSA — generated from inspect_xsa.py output
BUILDS = [
    {
        "xsa":          "{XSA_PATH_1}",
        "platform":     "{PLATFORM_NAME_1}",
        "cpu":          "{CPU_1}",
        "os":           "standalone",
        "domain":       "{DOMAIN_NAME_1}",
        "app":          "{APP_NAME_1}",
        "generate_dtb": {GENERATE_DTB_1},
    },
    # ... repeat for each XSA
]

try:
    client = vitis.create_client()

    if os.path.isdir(WORKSPACE):
        shutil.rmtree(WORKSPACE)
    client.set_workspace(WORKSPACE)

    results = []
    for b in BUILDS:
        print(f"\n{'='*60}")
        print(f"Building: {b['platform']} / {b['app']}")
        print(f"{'='*60}")

        # Create and build platform
        print(f"[1/3] Creating platform '{b['platform']}' from {b['xsa']} ...")
        platform = client.create_platform_component(
            name         = b["platform"],
            hw_design    = b["xsa"],
            cpu          = b["cpu"],
            os           = b["os"],
            domain_name  = b["domain"],
            generate_dtb = b["generate_dtb"],
        )
        platform.build()
        print("Platform built.")

        # Locate XPFM
        xpfm = client.find_platform_in_repos(b["platform"])
        print(f"[2/3] XPFM: {xpfm}")

        # Create and build app
        print(f"[3/3] Creating app '{b['app']}' with template '{TEMPLATE}' ...")
        app = client.create_app_component(
            name     = b["app"],
            platform = xpfm,
            domain   = b["domain"],
            template = TEMPLATE,
        )
        app.build()

        elf = os.path.join(WORKSPACE, b["app"], "build", f"{b['app']}.elf")
        results.append({"app": b["app"], "xpfm": xpfm, "elf": elf})
        print(f"App '{b['app']}' built.")

    print(f"\n{'='*60}")
    print("All builds complete:")
    for r in results:
        print(f"  {r['app']}")
        print(f"    XPFM : {r['xpfm']}")
        print(f"    ELF  : {r['elf']}")

finally:
    vitis.dispose()
```

---

## Step 5: Save the Script

- **Single mode**: save as `./<xsa_stem>_build_app.py` (e.g. `zc702_build_app.py`). Show full script and parameter summary table.
- **Multi mode**: save as `./<template>_build_all_apps.py` (e.g. `peripheral_tests_build_all_apps.py`). Show the BUILDS list as a summary table:

  | Board | XSA | CPU | Domain | App |
  |-------|-----|-----|--------|-----|
  | zcu106 | zcu106.xsa | psu_cortexa53_0 | standalone_psu_cortexa53_0 | peripheral_tests_zcu106 |
  | vck190 | vck190.xsa | psv_cortexa72_0 | standalone_psv_cortexa72_0 | peripheral_tests_vck190 |

---

## Step 6: Run the Script

Use the Vitis-bundled Python and environment resolved in Step 0:

**Single mode:**
```bash
source {VITIS_PATH}/settings64.sh && \
  LD_LIBRARY_PATH={VITIS_PYLIB}:$LD_LIBRARY_PATH \
  PYTHONPATH={VITIS_PATH}/cli:{VITIS_PATH}/cli/proto:$PYTHONPATH \
  {VITIS_PYTHON} ./{xsa_stem}_build_app.py 2>&1
```

**Multi mode:**
```bash
source {VITIS_PATH}/settings64.sh && \
  LD_LIBRARY_PATH={VITIS_PYLIB}:$LD_LIBRARY_PATH \
  PYTHONPATH={VITIS_PATH}/cli:{VITIS_PATH}/cli/proto:$PYTHONPATH \
  {VITIS_PYTHON} ./{template}_build_all_apps.py 2>&1
```

Set a long timeout (20 minutes for multi mode) — platform + app builds take time.

Report results:
- **Success**: show workspace path, all XPFM/ELF paths; confirm ELFs exist with `ls -lh`
- **Failure**: show the error, diagnose which board failed, suggest fix

**Note:** Tcl warnings (`Can't find a usable init.tcl`) during build are harmless noise — the build succeeds despite them.

---

## Common Problems and Fixes

| Error | Likely Cause | Fix |
|-------|-------------|-----|
| `ModuleNotFoundError: No module named 'vitis'` | Using system python3 instead of Vitis bundled python | Use `{VITIS_PYTHON}` from Step 0 |
| `ModuleNotFoundError: No module named 'grpc'` | Missing PYTHONPATH or wrong Python | Add `/cli/proto` to PYTHONPATH; use bundled Python |
| `libpython3.x.so not found` | Missing LD_LIBRARY_PATH | Set `LD_LIBRARY_PATH={VITIS_PYLIB}:$LD_LIBRARY_PATH` |
| `FileNotFoundError: <xsa_path>` | XSA path is relative | Expand to absolute path with `os.path.abspath()` |
| `No processor found` / `Invalid cpu` | Wrong CPU name | Re-run `inspect_xsa.py`, use exact name from output |
| `platform.xpfm not found` | Platform build failed | Check logs; call `platform.report()` |
| Domain mismatch | `domain_name` in create_platform ≠ `domain` in create_app | Use exact values from `inspect_xsa.py` JSON |

---

## Script Quality Checklist

Every generated script must:
- Use **absolute XSA path**
- Set workspace inside CWD with `os.path.join(os.getcwd(), ...)`
- **Clean the workspace** before creation with `shutil.rmtree`
- Wrap in **`try/finally`** to ensure `vitis.dispose()` always runs
- **Print XPFM and ELF paths** after each build
- Use `generate_dtb=True` for Linux on ZynqMP/Versal

---

## Additional Resources

- **`scripts/inspect_xsa.py`** — Inspects XSA and returns processor list as JSON
- **`references/api-cheatsheet.md`** — Vitis Python API signatures, templates, domain naming
- **`examples/standalone_hello.py`** — ZynqMP XSA → standalone hello_world
- **`examples/linux_app.py`** — ZynqMP XSA → linux empty_application with custom sources
