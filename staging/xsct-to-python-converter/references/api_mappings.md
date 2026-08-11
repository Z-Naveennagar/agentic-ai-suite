<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# XSCT TCL to Vitis Python API Command Mappings

## Core Command Mappings

| XSCT TCL Command | Python API Equivalent | Notes |
|------------------|----------------------|-------|
| `setws <path>` | `client.set_workspace(path='<path>')` | Creates directory automatically |
| `platform create -name <n> -hw <xsa> -proc <cpu> -os <os>` | `client.create_platform_component(name='<n>', hw_design='<xsa>', cpu='<cpu>', os='<os>', domain_name='<domain>')` | Must specify `domain_name` explicitly |
| `platform generate` | `platform.build()` | Returns object, not global command |
| `platform active <name>` | `platform = client.get_component(name='<name>')` | Get component object |
| `app create -name <n> -platform <p> -domain <d> -template "<t>"` | `client.create_app_component(name='<n>', platform=<xpfm_path>, domain='<d>', template='<t>')` | **NO `sys_proj_name` parameter** |
| `app create -name <n> -sysproj <s> -platform <p> -domain <d> -template "<t>"` | See System Project Pattern | `-sysproj` is NOT a parameter; create system project separately |
| `importsources -name <n> -path <p>` | `app.import_files(from_loc='<p>', files=[...], dest_dir_in_cmp='src')` | Requires explicit file list |
| `domain create -name <n> -os <os> -proc <cpu>` | `platform.add_domain(name='<n>', os='<os>', cpu='<cpu>')` | Method on platform object |
| `domain active <name>` | `domain = platform.get_domain('<name>')` | Get domain object |
| `bsp setlib -name <lib>` | `domain.set_lib('<lib>')` | Method on domain object |
| `bsp config <key> <value>` | `domain.set_config('os', '<key>', '<value>')` | Specify config type |

## System Project Pattern

**CRITICAL**: System projects are optional in Python API (mandatory in XSCT).

### Single Application (NO system project)
```python
# XSCT: app create -name app1 -sysproj sys1 -platform plat -domain dom -template "Hello World"
# Python: Just create the app - ignore -sysproj
app = client.create_app_component(
    name='app1',
    platform=platform_xpfm,
    domain='dom',
    template='hello_world'
)
```

### Multiple Applications OR Acceleration Projects (WITH system project)
```python
# Step 1: Create system project
sys_proj = client.create_sys_project(
    name='sys1',
    platform=platform_xpfm,
    template=client.get_template('app', 'empty')  # or 'accl_app'
)

# Step 2: Create applications
app1 = client.create_app_component(name='app1', platform=platform_xpfm, domain='dom', template='hello_world')
app2 = client.create_app_component(name='app2', platform=platform_xpfm, domain='dom', template='empty_application')

# Step 3: Add to system project
sys_proj.add_component('app1')
sys_proj.add_component('app2')
```

## Template Name Conversions

| XSCT Template (Title Case) | Python Template (snake_case) |
|----------------------------|------------------------------|
| `"Linux Empty Application"` | `'linux_empty_application'` |
| `"Hello World"` | `'hello_world'` |
| `"Empty Application"` | `'empty_application'` |
| `"Zynq MP FSBL"` | `'zynqmp_fsbl'` |
| `"Zynq FSBL"` | `'zynq_fsbl'` |
| `"FreeRTOS Hello World"` | `'freertos_hello_world'` |

**Rule**: Convert to lowercase and replace spaces with underscores.

## Platform Path Pattern

After `platform.build()`, reference platform by .xpfm path:

```python
platform_xpfm = os.path.join(
    workspace,
    platform_name,
    'export',
    platform_name,
    f'{platform_name}.xpfm'
)
```

## File Import Pattern

XSCT imports entire directory; Python requires explicit file list:

```python
# Get all files in directory
src_files = [f for f in os.listdir(src_path) if os.path.isfile(os.path.join(src_path, f))]

# Import to component
app.import_files(
    from_loc=src_path,
    files=src_files,
    dest_dir_in_cmp='src'
)
```

## Build and Clean

| XSCT | Python |
|------|--------|
| `platform generate` | `platform.build()` |
| `platform clean` | `platform.clean()` |
| `app build -name <n>` | `app.build()` |
| `app clean -name <n>` | `app.clean()` |
| `projects -remove <n>` | `client.delete_component(name='<n>')` |

**Note**: `clean()` removes build artifacts; `delete_component()` removes component entirely.
