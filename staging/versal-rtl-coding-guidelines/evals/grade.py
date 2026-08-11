#!/usr/bin/env python3
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
"""Create a portable grading skeleton from an eval definition and exact tool signals.

Usage: grade.py <eval_metadata.json> <signals.txt> <out.json>

Only exact STRUCTURE key=value tokens are parsed automatically. Protocol, CDC, timing,
reliability, and security expectations remain manual until the harness supplies an explicit
machine-readable result from the corresponding checker. Transcript prose is never graded.
"""
import json
import re
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    meta = json.load(stream)
with open(sys.argv[2], encoding="utf-8") as stream:
    signals_text = stream.read()

signals = {
    key: int(value)
    for key, value in re.findall(r"\b(BRAM|URAM|DSP|LUTRAM|LATCH|ASYNC_REG|DONT_TOUCH)=(\d+)\b", signals_text)
}

results = []
for expectation in meta.get("expectations", []):
    lowered = expectation.lower()
    passed = None
    evidence = "requires explicit report, simulation, formal, protocol, or review evidence"
    if "latch" in lowered and "no" in lowered and "LATCH" in signals:
        passed = signals["LATCH"] == 0
        evidence = f"LATCH={signals['LATCH']}"
    results.append({"text": expectation, "passed": passed, "evidence": evidence})

output = {
    "eval_id": meta.get("eval_id"),
    "eval_name": meta.get("eval_name"),
    "structural_signals": signals,
    "expectations": results,
}
with open(sys.argv[3] if len(sys.argv) > 3 else "grading.json", "w", encoding="utf-8") as stream:
    json.dump(output, stream, indent=2)
