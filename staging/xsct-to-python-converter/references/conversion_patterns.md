<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# XSCT to Python Conversion Patterns

## Standard Python Script Structure

All converted scripts should follow this pattern:

```python
#!/usr/bin/env python3
import vitis
import os
import shutil

# 1. Create client
client = vitis.create_client()

# 2. Set workspace
workspace = 'workspace_name'
if os.path.isdir(workspace):
    shutil.rmtree(workspace)
client.set_workspace(path=workspace)

# 3. Create and configure components
# ... (conversion logic)

# 4. Cleanup
vitis.dispose()
```

## Pattern 1: Embedded Linux Platform + Application

### XSCT
```tcl
setws linux_ws
platform create -name plat1 -hw design.xsa -proc psu_cortexa53 -os linux
platform generate
app create -name app1 -sysproj app1_system -platform plat1 -domain linux_domain -template "Linux Empty Application"
importsources -name app1 -path src
```

### Python (Single App - NO System Project)
```python
client.set_workspace(path='linux_ws')

platform = client.create_platform_component(
    name='plat1',
    hw_design='design.xsa',
    cpu='psu_cortexa53',
    os='linux',
    domain_name='linux_domain'
)
platform.build()

platform_xpfm = os.path.join('linux_ws', 'plat1', 'export', 'plat1', 'plat1.xpfm')

app = client.create_app_component(
    name='app1',
    platform=platform_xpfm,
    domain='linux_domain',
    template='linux_empty_application'
)

src_files = [f for f in os.listdir('src') if os.path.isfile(os.path.join('src', f))]
app.import_files(from_loc='src', files=src_files, dest_dir_in_cmp='src')
```

## Pattern 2: Standalone Platform + Application

### XSCT
```tcl
setws standalone_ws
platform create -name plat1 -hw design.xsa -proc psu_cortexa53 -os standalone
platform generate
app create -name app1 -sysproj app1_system -platform plat1 -domain standalone_domain -template "Hello World"
```

### Python
```python
client.set_workspace(path='standalone_ws')

platform = client.create_platform_component(
    name='plat1',
    hw_design='design.xsa',
    cpu='psu_cortexa53',
    os='standalone',
    domain_name='standalone_domain'
)
platform.build()

platform_xpfm = os.path.join('standalone_ws', 'plat1', 'export', 'plat1', 'plat1.xpfm')

app = client.create_app_component(
    name='app1',
    platform=platform_xpfm,
    domain='standalone_domain',
    template='hello_world'
)
```

## Pattern 3: Multiple Domains

### XSCT
```tcl
setws multi_domain_ws
platform create -name plat1 -hw design.xsa -proc psu_cortexa53 -os linux
domain create -name standalone_domain -os standalone -proc psu_cortexr5_0
platform generate
```

### Python
```python
client.set_workspace(path='multi_domain_ws')

platform = client.create_platform_component(
    name='plat1',
    hw_design='design.xsa',
    cpu='psu_cortexa53',
    os='linux',
    domain_name='linux_domain'
)

# Add additional domain
platform.add_domain(
    name='standalone_domain',
    os='standalone',
    cpu='psu_cortexr5_0'
)

platform.build()
```

## Pattern 4: Multiple Applications (Requires System Project)

### XSCT
```tcl
setws multi_app_ws
platform create -name plat1 -hw design.xsa -proc psu_cortexa53 -os standalone
platform generate
app create -name app1 -sysproj multi_app_system -platform plat1 -domain standalone_domain -template "Hello World"
app create -name app2 -sysproj multi_app_system -platform plat1 -domain standalone_domain -template "Empty Application"
```

### Python (WITH System Project)
```python
client.set_workspace(path='multi_app_ws')

platform = client.create_platform_component(
    name='plat1',
    hw_design='design.xsa',
    cpu='psu_cortexa53',
    os='standalone',
    domain_name='standalone_domain'
)
platform.build()

platform_xpfm = os.path.join('multi_app_ws', 'plat1', 'export', 'plat1', 'plat1.xpfm')

# Create system project for multiple apps
sys_proj = client.create_sys_project(
    name='multi_app_system',
    platform=platform_xpfm,
    template=client.get_template('app', 'empty')
)

# Create applications
app1 = client.create_app_component(
    name='app1',
    platform=platform_xpfm,
    domain='standalone_domain',
    template='hello_world'
)

app2 = client.create_app_component(
    name='app2',
    platform=platform_xpfm,
    domain='standalone_domain',
    template='empty_application'
)

# Add to system project
sys_proj.add_component('app1')
sys_proj.add_component('app2')
```

## Pattern 5: HLS Component (Acceleration - Requires System Project)

### XSCT
```tcl
setws hls_ws
# HLS creation in XSCT varies
# Typically involves platform + system project
```

### Python (WITH System Project)
```python
client.set_workspace(path='hls_ws')

# Assume platform already exists or created
platform_xpfm = client.find_platform_in_repos('xilinx_u250_gen3x16')

# Create system project for acceleration
sys_proj = client.create_sys_project(
    name='hls_system',
    platform=platform_xpfm,
    template=client.get_template('accl_app', 'empty')
)

# Create HLS component
hls_comp = client.create_hls_component(name='vadd_kernel')

hls_comp.import_files(
    from_loc='src',
    files=['vadd.cpp'],
    dest_dir_in_cmp='src'
)

# Add to system project
sys_proj.add_component('vadd_kernel')
```

## Pattern 6: BSP Configuration

### XSCT
```tcl
platform active plat1
domain active linux_domain
bsp setlib -name xilskey
bsp config stdin psu_uart_1
```

### Python
```python
platform = client.get_component(name='plat1')
domain = platform.get_domain('linux_domain')

# Add library
domain.set_lib('xilskey')

# Configure OS parameter
domain.set_config('os', 'stdin', 'psu_uart_1')
```

## Common Gotchas

1. **System Project Decision**:
   - Single app → NO system project
   - Multiple apps → CREATE system project
   - Acceleration (HLS/AIE) → CREATE system project

2. **Platform Reference**:
   - XSCT uses platform name
   - Python needs full .xpfm path

3. **Template Names**:
   - Convert Title Case to snake_case
   - Remove quotes

4. **File Import**:
   - XSCT imports directory automatically
   - Python needs explicit file list

5. **Object-Oriented**:
   - XSCT uses global commands
   - Python uses object methods (platform.build(), app.build())
