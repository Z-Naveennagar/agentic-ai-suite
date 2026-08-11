#!/usr/bin/env python3
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import json
import sys
from pathlib import Path

REQUIRED = {"schema_version", "request_id", "from_agent", "to_agent", "reason", "status", "input_artifacts", "required_output"}


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: validate_handoff.py HANDOFF.json", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    missing = sorted(REQUIRED - set(value))
    if missing:
        print(f"ERROR: missing fields: {', '.join(missing)}", file=sys.stderr)
        return 1
    print("PASS: handoff contains all required fields")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
