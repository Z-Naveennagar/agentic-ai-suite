#!/usr/bin/env python3
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
"""Extract an address map from a Vivado .hwh hardware-handoff file.

Parses the XML to produce a JSON mapping of IP instances to their base/high
addresses, IP type, and interrupt connectivity.  Used by the ps-software
sub-skill of soc-orchestration to generate firmware that references the
correct hardware addresses.

Usage:
    python3 extract_addr_map.py  path/to/design.hwh                   # stdout
    python3 extract_addr_map.py  path/to/design.hwh -o addr_map.json  # file
    python3 extract_addr_map.py  path/to/design.hwh --pretty          # indented
"""

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def _find_interrupt_connections(root: ET.Element) -> dict[str, list[dict]]:
    """Build a map:  instance -> [{port, target_instance, target_port}]."""
    irq_map: dict[str, list[dict]] = {}
    for module in root.iter("MODULE"):
        inst = module.get("INSTANCE", "")
        for port in module.iter("PORT"):
            if port.get("SIGIS") != "INTERRUPT" or port.get("DIR") != "O":
                continue
            port_name = port.get("NAME", "")
            for conn in port.iter("CONNECTION"):
                target_inst = conn.get("INSTANCE", "")
                target_port = conn.get("PORT", "")
                if target_inst:
                    irq_map.setdefault(inst, []).append({
                        "port": port_name,
                        "target_instance": target_inst,
                        "target_port": target_port,
                    })
    return irq_map


def extract_addr_map(hwh_path: Path) -> dict:
    """Parse a .hwh file and return the address-map dictionary.

    Returns
    -------
    dict with keys:
        device_info : {arch, device, package, speedgrade}
        peripherals : {instance_name: {base, high, type, vlnv, memtype, interrupts}}
    """
    tree = ET.parse(hwh_path)
    root = tree.getroot()

    # Device metadata
    sysinfo = root.find("SYSTEMINFO")
    device_info = {}
    if sysinfo is not None:
        device_info = {
            "arch": sysinfo.get("ARCH", ""),
            "device": sysinfo.get("DEVICE", ""),
            "package": sysinfo.get("PACKAGE", ""),
            "speedgrade": sysinfo.get("SPEEDGRADE", ""),
            "board_name": sysinfo.get("NAME", ""),
        }

    # Module catalog: instance -> {modtype, vlnv, is_pl}
    modules: dict[str, dict] = {}
    for mod in root.iter("MODULE"):
        inst = mod.get("INSTANCE", "")
        if not inst:
            continue
        modules[inst] = {
            "modtype": mod.get("MODTYPE", ""),
            "vlnv": mod.get("VLNV", ""),
            "is_pl": mod.get("IS_PL", "TRUE") != "FALSE",
        }

    irq_map = _find_interrupt_connections(root)

    # MEMRANGE entries — only REGISTER type (peripherals addressable from PS)
    peripherals: dict[str, dict] = {}
    for mr in root.iter("MEMRANGE"):
        if mr.get("MEMTYPE") != "REGISTER":
            continue
        inst = mr.get("INSTANCE", "")
        if not inst:
            continue
        base = mr.get("BASEVALUE", "")
        high = mr.get("HIGHVALUE", "")
        mod_info = modules.get(inst, {})

        entry = {
            "base": base,
            "high": high,
            "type": mod_info.get("modtype", "unknown"),
            "vlnv": mod_info.get("vlnv", ""),
        }
        if inst in irq_map:
            entry["interrupts"] = irq_map[inst]

        # If multiple MEMRANGE entries exist for the same instance (rare),
        # keep the first one (it's the primary control register block).
        if inst not in peripherals:
            peripherals[inst] = entry

    return {
        "device_info": device_info,
        "peripherals": peripherals,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Extract address map from Vivado .hwh hardware-handoff file"
    )
    parser.add_argument("hwh_file", type=Path, help="Path to .hwh file")
    parser.add_argument("-o", "--output", type=Path, default=None,
                        help="Output JSON file (default: stdout)")
    parser.add_argument("--pretty", action="store_true",
                        help="Pretty-print JSON output")
    args = parser.parse_args()

    if not args.hwh_file.exists():
        print(f"Error: {args.hwh_file} not found", file=sys.stderr)
        sys.exit(1)

    addr_map = extract_addr_map(args.hwh_file)

    indent = 2 if args.pretty else None
    text = json.dumps(addr_map, indent=indent) + "\n"

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
        print(f"Wrote {args.output}  ({len(addr_map['peripherals'])} peripherals)")
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
