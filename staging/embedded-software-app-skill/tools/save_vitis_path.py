#!/usr/bin/env python3
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
"""
save_vitis_path.py — Read or write the saved Vitis installation path.

Usage:
    python3 save_vitis_path.py get              → print saved path (or empty)
    python3 save_vitis_path.py set <path>       → save path to vitis_config.json
"""
import sys
import json
import os

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "..", "vitis_config.json")
CONFIG_FILE = os.path.abspath(CONFIG_FILE)


def get_path() -> str:
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f).get("vitis_path", "")
    except Exception:
        return ""


def set_path(path: str):
    data = {}
    try:
        with open(CONFIG_FILE) as f:
            data = json.load(f)
    except Exception:
        pass
    data["vitis_path"] = path
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Saved: {path}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "get":
        print(get_path())
    elif cmd == "set" and len(sys.argv) >= 3:
        set_path(sys.argv[2])
    else:
        print(__doc__)
        sys.exit(1)
