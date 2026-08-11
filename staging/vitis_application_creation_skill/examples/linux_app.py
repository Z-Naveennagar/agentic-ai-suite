#!/usr/bin/env python3
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
# Example: ZynqMP XSA -> Linux application with custom source files
# Run with: python3 linux_app.py (after sourcing Vitis settings64.sh)

import vitis
import os
import shutil

# ── Edit these ────────────────────────────────────────────────────────────────
XSA_PATH      = "/path/to/your/design.xsa"   # <-- change this
PLATFORM_NAME = "my_linux_platform"
CPU           = "psu_cortexa53"               # ZynqMP Linux (no _0 suffix)
OS_TYPE       = "linux"
DOMAIN_NAME   = "linux_psu_cortexa53"
APP_NAME      = "my_linux_app"
TEMPLATE      = "empty_application"
WORKSPACE     = "/tmp/vitis_ws_linux"
SRC_DIR       = "/path/to/your/sources"       # <-- directory with .c files
SRC_FILES     = ["main.c"]                    # <-- files to import from SRC_DIR
# ──────────────────────────────────────────────────────────────────────────────

try:
    client = vitis.create_client()

    # Clean workspace
    if os.path.isdir(WORKSPACE):
        shutil.rmtree(WORKSPACE)
    client.set_workspace(WORKSPACE)

    # Step 1: Create and build platform (generate_dtb=True for ZynqMP Linux)
    print(f"[1/3] Creating Linux platform from {XSA_PATH} ...")
    platform = client.create_platform_component(
        name         = PLATFORM_NAME,
        hw_design    = XSA_PATH,
        cpu          = CPU,
        os           = OS_TYPE,
        domain_name  = DOMAIN_NAME,
        generate_dtb = True,
    )
    platform.build()

    # Step 2: Locate .xpfm
    platform_xpfm = client.find_platform_in_repos(PLATFORM_NAME)
    print(f"[2/3] Platform XPFM: {platform_xpfm}")

    # Step 3: Create app, import sources, and build
    print(f"[3/3] Creating app '{APP_NAME}' ...")
    app = client.create_app_component(
        name     = APP_NAME,
        platform = platform_xpfm,
        domain   = DOMAIN_NAME,
        template = TEMPLATE,
    )

    # Import custom source files
    app.import_files(
        from_loc        = SRC_DIR,
        files           = SRC_FILES,
        dest_dir_in_cmp = "src",
    )

    app.build()

    elf = os.path.join(WORKSPACE, APP_NAME, "build", "Debug", f"{APP_NAME}.elf")
    print(f"\nDone!")
    print(f"  Workspace : {WORKSPACE}")
    print(f"  XPFM      : {platform_xpfm}")
    print(f"  ELF       : {elf}")

finally:
    vitis.dispose()
