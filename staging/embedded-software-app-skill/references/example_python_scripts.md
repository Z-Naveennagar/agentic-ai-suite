<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->


```
import vitis

client = vitis.create_client()
client.set_workspace(path="example_python_scripts")

platform = client.create_platform_component(name = "platform",hw_design = "vck190",os = "standalone",cpu = "psv_cortexa72_0",domain_name = "standalone_psv_cortexa72_0",compiler = "gcc")

platform = client.get_component(name="platform")
status = platform.build()

comp = client.create_app_component(name="hello_world",platform = "$COMPONENT_LOCATION/../platform/export/platform/platform.xpfm",domain = "standalone_psv_cortexa72_0",template = "hello_world")

status = platform.build()

comp = client.get_component(name="hello_world")
comp.build()

platform = client.create_platform_component(name = "new_platform",hw_design = "/user_scratchpad/microblaze_v_preset_wrapper.xsa",os = "standalone",cpu = "microblaze_riscv_0",domain_name = "standalone_microblaze_riscv_0",compiler = "gcc")

platform = client.get_component(name="new_platform")
status = platform.build()

comp = client.create_app_component(name="app_component",platform = "$COMPONENT_LOCATION/../new_platform/export/new_platform/new_platform.xpfm",domain = "standalone_microblaze_riscv_0")

comp = client.get_component(name="app_component")
status = comp.import_files(from_loc="", files=["/user_scratchpad/hello_world/src/main.c"], is_skip_copy_sources = False)

status = platform.build()

comp.build()

platform = client.get_component(name="platform")
domain = platform.get_domain(name="standalone_psv_cortexa72_0")

status = domain.set_lib(lib_name="lwip220", path="/vitis_install_dir/installs/lin64/2026.1/Vitis/data/embeddedsw/ThirdParty/sw_services/lwip220_v1_4")

status = platform.build()
```
