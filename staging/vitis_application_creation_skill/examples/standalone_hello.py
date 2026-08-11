#!/usr/bin/env python3
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
# Example: ZynqMP XSA -> standalone hello_world application
#
# Run with the Vitis-bundled Python:
#   source /path/to/Vitis/settings64.sh
#   VITIS=/path/to/Vitis
#   LD_LIBRARY_PATH=$VITIS/tps/lnx64/python-3.13.0/lib:$LD_LIBRARY_PATH \
#   PYTHONPATH=$VITIS/cli:$VITIS/cli/proto:$PYTHONPATH \
#   $VITIS/tps/lnx64/python-3.13.0/bin/python3 standalone_hello.py

import vitis
import os
import shutil

# ── Edit these ────────────────────────────────────────────────────────────────
XSA_PATH      = "/path/to/your/design.xsa"   # <-- change this (absolute path)
PLATFORM_NAME = "my_platform"
CPU           = "psu_cortexa53_0"             # ZynqMP Cortex-A53 core 0
OS_TYPE       = "standalone"
DOMAIN_NAME   = "standalone_psu_cortexa53_0"
APP_NAME      = "hello_world"
TEMPLATE      = "hello_world"
WORKSPACE     = os.path.join(os.getcwd(), f"{PLATFORM_NAME}_ws")  # CWD/<platform>_ws
# ──────────────────────────────────────────────────────────────────────────────

try:
    client = vitis.create_client()

    if os.path.isdir(WORKSPACE):
        shutil.rmtree(WORKSPACE)
    client.set_workspace(WORKSPACE)

    # Step 1: Create and build platform
    print(f"[1/3] Creating platform from {XSA_PATH} ...")
    platform = client.create_platform_component(
        name         = PLATFORM_NAME,
        hw_design    = XSA_PATH,
        cpu          = CPU,
        os           = OS_TYPE,
        domain_name  = DOMAIN_NAME,
        generate_dtb = False,
    )
    platform.build()

    # Step 2: Locate .xpfm
    platform_xpfm = client.find_platform_in_repos(PLATFORM_NAME)
    print(f"[2/3] Platform XPFM: {platform_xpfm}")

    # Step 3: Create and build application
    print(f"[3/3] Creating app '{APP_NAME}' ...")
    app = client.create_app_component(
        name     = APP_NAME,
        platform = platform_xpfm,
        domain   = DOMAIN_NAME,
        template = TEMPLATE,
    )
    app.build()

    elf = os.path.join(WORKSPACE, APP_NAME, "build", f"{APP_NAME}.elf")
    print(f"\nDone!")
    print(f"  Workspace : {WORKSPACE}")
    print(f"  XPFM      : {platform_xpfm}")
    print(f"  ELF       : {elf}")

finally:
    vitis.dispose()
