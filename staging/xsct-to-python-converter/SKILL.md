---
name: xsct-to-python-converter
description: Converts XSCT (Xilinx Software Command-Line Tool) Tcl scripts to Vitis Python API for Vitis Unified IDE. Use when users request migration of XSCT scripts, conversion from Tcl to Python for Vitis workflows, or modernization of classic Vitis IDE automation scripts. Handles embedded (Linux/Standalone), HLS, and AIE workflows. Critical: System projects are optional in Python API (mandatory in XSCT) - only create for multiple applications or acceleration projects.
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
# XSCT to Python API Converter

Convert XSCT Tcl scripts to Vitis Python API for Vitis Unified IDE.

## Conversion Workflow

### 1. Analyze the TCL Script

Read the XSCT script and identify:
- Workspace operations (`setws`)
- Platform creation (`platform create`)
- Domain operations (`domain create`, `bsp` commands)
- Application creation (`app create`)
- Source imports (`importsources`)
- Build commands (`platform generate`, `app build`)

Count the number of applications being created - this determines system project strategy.

### 2. Determine System Project Strategy

**CRITICAL DECISION**:

```
Does the script create multiple applications?
│
├─ NO (single app, embedded workflow)
│  └─> NO system project needed
│
└─ YES (multiple apps OR acceleration with HLS/AIE)
   └─> CREATE system project
```

System projects in Python API:
- **Optional** (unlike XSCT where `-sysproj` is mandatory)
- Only needed for: multiple applications OR acceleration projects (HLS/AIE)
- Created via `create_sys_project()` + `add_component()` pattern

### 3. Convert Commands

Use these mappings:

| XSCT | Python |
|------|--------|
| `setws <path>` | `client.set_workspace(path='<path>')` |
| `platform create -name <n> -hw <xsa> -proc <cpu> -os <os>` | `client.create_platform_component(name='<n>', hw_design='<xsa>', cpu='<cpu>', os='<os>', domain_name='<domain>')` |
| `platform generate` | `platform.build()` |
| `app create ... -template "<Title Case>"` | `client.create_app_component(..., template='snake_case')` |
| `importsources -name <n> -path <p>` | `app.import_files(from_loc='<p>', files=file_list, dest_dir_in_cmp='src')` |

**See references/api_mappings.md for complete mapping table.**

### 4. Convert Template Names

Convert Title Case with spaces to snake_case:
- `"Linux Empty Application"` → `'linux_empty_application'`
- `"Hello World"` → `'hello_world'`
- `"Empty Application"` → `'empty_application'`

### 5. Handle Platform References

After `platform.build()`, construct .xpfm path:

```python
platform_xpfm = os.path.join(
    workspace,
    platform_name,
    'export',
    platform_name,
    f'{platform_name}.xpfm'
)
```

Use this path (not platform name) in `create_app_component()` and `create_sys_project()`.

### 6. Convert Source Imports

XSCT imports directory automatically; Python needs explicit file list:

```python
src_files = [f for f in os.listdir(src_path) if os.path.isfile(os.path.join(src_path, f))]
app.import_files(from_loc=src_path, files=src_files, dest_dir_in_cmp='src')
```

### 7. Structure the Python Script

Use standard structure:

```python
#!/usr/bin/env python3
import vitis
import os
import shutil

# Create client
client = vitis.create_client()

# Set workspace
workspace = 'workspace_name'
if os.path.isdir(workspace):
    shutil.rmtree(workspace)
client.set_workspace(path=workspace)

# Create platform
platform = client.create_platform_component(...)
platform.build()

# Get platform path
platform_xpfm = os.path.join(workspace, platform_name, 'export', platform_name, f'{platform_name}.xpfm')

# If multiple apps or acceleration: create system project
if multiple_apps_or_acceleration:
    sys_proj = client.create_sys_project(
        name='system_name',
        platform=platform_xpfm,
        template=client.get_template('app', 'empty')  # or 'accl_app' for acceleration
    )

# Create application(s)
app = client.create_app_component(
    name='app_name',
    platform=platform_xpfm,
    domain='domain_name',
    template='template_name'
)

# If system project exists: add components
if sys_proj:
    sys_proj.add_component('app_name')

# Import sources
src_files = [f for f in os.listdir('src') if os.path.isfile(os.path.join('src', f))]
app.import_files(from_loc='src', files=src_files, dest_dir_in_cmp='src')

# Cleanup
vitis.dispose()
```

## Output Requirements

Generate three files:

### 1. Main Python Script (`<name>.py`)
- Complete conversion with comments explaining each step
- Include docstring mapping to original TCL operations
- Add informative print statements
- Handle workspace cleanup (remove if exists)

### 2. Verification Script (`verify_<name>.py`)
```python
#!/usr/bin/env python3
import vitis
import os
import sys

def verify_workspace():
    workspace = 'workspace_name'

    if not os.path.isdir(workspace):
        print(f"ERROR: Workspace '{workspace}' not found")
        return False

    client = vitis.create_client()
    client.set_workspace(path=workspace)

    components = client.list_components()
    print(f"Found {len(components)} component(s)")

    # List expected components
    expected = ['platform_name', 'app_name']  # Adjust based on script

    for comp_info in components:
        comp_name = comp_info['name']
        print(f"  ✓ {comp_name}")
        if comp_name in expected:
            expected.remove(comp_name)

    if expected:
        print(f"Missing components: {expected}")
        return False

    # Check platform .xpfm
    xpfm_path = os.path.join(workspace, 'platform_name', 'export', 'platform_name', 'platform_name.xpfm')
    if not os.path.isfile(xpfm_path):
        print(f"ERROR: Platform .xpfm not found")
        return False

    print("✓ Verification passed")
    vitis.dispose()
    return True

if __name__ == "__main__":
    success = verify_workspace()
    sys.exit(0 if success else 1)
```

### 3. Documentation (`CONVERSION_NOTES.md`)
- Summary of what was converted
- System project decision explanation
- Key differences from TCL
- Running instructions
- Expected workspace structure

Example:
```markdown
# XSCT to Python Conversion Notes

## Original TCL Script
- Workspace: <workspace_name>
- Platform: <platform_name> (<OS> on <CPU>)
- Applications: <count> app(s)
- System Project: [YES/NO - explain decision]

## System Project Decision
[Single app - no system project needed]
OR
[Multiple apps detected - created system project '<name>']
OR
[Acceleration workflow - created system project '<name>']

## Key Differences
1. System projects are optional in Python API
2. Template names converted to snake_case
3. Platform referenced by .xpfm path
4. File import requires explicit file list

## Running
```bash
source /path/to/Vitis/settings64.sh
vitis -s <name>.py
vitis -s verify_<name>.py
```

## Expected Workspace Structure
```
workspace_name/
├── platform_name/
│   └── export/platform_name/platform_name.xpfm
├── app_name/
│   └── src/
└── _ide/
```
```

## Key Conversion Rules

1. **NO `sys_proj_name` parameter**: XSCT's `-sysproj` flag does not map to a parameter
2. **System project is separate**: Use `create_sys_project()` + `add_component()` when needed
3. **Template names lowercase**: Title Case → snake_case
4. **Platform by path**: Use `.xpfm` file path, not platform name
5. **Explicit imports**: List files explicitly, no automatic directory import
6. **Object methods**: Use `platform.build()` not global `platform generate`

## When to Request Additional Information

If the TCL script references:
- Custom platforms not in standard repos: Ask for `PLATFORM_REPO_PATHS`
- Versal Linux: Ask for `IDE_VERSAL_SYSROOT`, `IDE_VERSAL_ROOT_FS`
- HLS kernels: Ask for kernel source files
- BSP libraries: Ask if library configuration is critical

If unclear about:
- Application templates: Request access to `$XILINX_VITIS/cli_docs` for template names
- API details: Request access to `$XILINX_VITIS/cli/examples` for reference

## Pattern Reference

**See references/conversion_patterns.md** for complete examples:
- Pattern 1: Embedded Linux Platform + Application
- Pattern 2: Standalone Platform + Application
- Pattern 3: Multiple Domains
- Pattern 4: Multiple Applications (with system project)
- Pattern 5: HLS Component (with system project)
- Pattern 6: BSP Configuration

## Common Issues

1. **Template not found**: Verify snake_case conversion
2. **Platform not found**: Check .xpfm path construction
3. **Workspace locked**: Remove `<workspace>/_ide/.wsdata/.lock`
4. **Import failed**: Check file list is not empty
