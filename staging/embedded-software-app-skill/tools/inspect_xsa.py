#!/usr/bin/env python3
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
"""
inspect_xsa.py - Extract processor information from a Vitis XSA file.
Supports ALL AMD/Xilinx embedded device families:
  - Zynq-7000          (processing_system7)        → ps7_cortexa9_*
  - ZynqMP / Zynq US+  (zynq_ultra_ps_e)           → psu_cortexa53_*, psu_cortexr5_*, psu_pmu_0
  - Versal             (versal_cips)                → psv_cortexa72_*, psv_cortexr5_*, ai_engine
  - Versal NET /       (versal_net_cips)            → psx_cortexa78_*, psx_cortexr52_*,
    Telluride                                         psx_pmc_0
  - MicroBlaze         (microblaze IPTYPE=PROCESSOR) → microblaze_*  (detected dynamically)
  - Data-center /      (no embedded PS)             → only MicroBlaze if present
    pure PL devices
Usage:
    python3 inspect_xsa.py <path_to.xsa>
Outputs JSON to stdout + human-readable summary to stderr.
Exit 0 on success, 1 on error.
"""

import sys
import json
import zipfile
import xml.etree.ElementTree as ET
import re


# ── Helpers ───────────────────────────────────────────────────────────────────

def _param(params: dict, name: str, default: str = "") -> str:
    return params.get(name, default)

def _enabled(params: dict, name: str) -> bool:
    """Return True if parameter exists and equals '1'."""
    return params.get(name, "0") == "1"

def _freq(params: dict, name: str) -> str:
    """Return formatted frequency string or '' if not available."""
    v = params.get(name, "")
    if v and v != "0":
        try:
            mhz = float(v)
            return f"{mhz:.0f} MHz"
        except ValueError:
            pass
    return ""

def _desc(base: str, freq: str) -> str:
    return f"{base} @ {freq}" if freq else base


# ── Device-family detectors ───────────────────────────────────────────────────

def _detect_zynq7(inst: str, params: dict, arch: str) -> list:
    """
    Zynq-7000 (processing_system7) — dual Cortex-A9.
    Both cores are always present; individual enable params rarely appear.
    """
    freq = _freq(params, "PCW_APU_PERIPHERAL_FREQMHZ")
    cores = [
        {
            "cpu":               "ps7_cortexa9_0",
            "cpu_linux":         "ps7_cortexa9",
            "description":       _desc("Cortex-A9 core 0 (32-bit, dual-core APU)", freq),
            "domain_standalone": "standalone_ps7_cortexa9_0",
            "domain_linux":      "linux_ps7_cortexa9",
            "supports_linux":    True,
        },
        {
            "cpu":               "ps7_cortexa9_1",
            "cpu_linux":         "ps7_cortexa9",
            "description":       _desc("Cortex-A9 core 1 (32-bit, dual-core APU)", freq),
            "domain_standalone": "standalone_ps7_cortexa9_1",
            "domain_linux":      "linux_ps7_cortexa9",
            "supports_linux":    True,
        },
    ]
    return cores


def _detect_zynqmp(inst: str, params: dict, arch: str) -> list:
    """
    ZynqMP / Zynq UltraScale+ (zynq_ultra_ps_e).
    Uses per-core PSU__ACPU[N]__POWER__ON for A53 and PSU__RPU__POWER__ON for R5.
    Falls back to including all standard cores if params are absent.
    """
    cores = []
    a53_freq = _freq(params, "PSU__CRF_APB__ACPU_CTRL__ACT_FREQMHZ") or \
               _freq(params, "PSU__CRF_APB__ACPU_CTRL__FREQMHZ")
    r5_freq  = _freq(params, "PSU__CRL_APB__CPU_R5_CTRL__ACT_FREQMHZ") or \
               _freq(params, "PSU__CRL_APB__CPU_R5_CTRL__FREQMHZ")

    # ── Cortex-A53 cores (APU) ──
    has_any_a53_param = any(f"PSU__ACPU{i}__POWER__ON" in params for i in range(4))
    for i in range(4):
        param_name = f"PSU__ACPU{i}__POWER__ON"
        # Include core if param says enabled, or if no individual power params exist at all
        if params.get(param_name, "1") == "1":
            cores.append({
                "cpu":               f"psu_cortexa53_{i}",
                "cpu_linux":         "psu_cortexa53",
                "description":       _desc(f"Cortex-A53 core {i} (64-bit APU)", a53_freq),
                "domain_standalone": f"standalone_psu_cortexa53_{i}",
                "domain_linux":      "linux_psu_cortexa53",
                "supports_linux":    True,
            })

    # ── Cortex-R5 cores (RPU) ──
    rpu_on = params.get("PSU__RPU__POWER__ON", "1")  # default include
    if rpu_on == "1":
        # R5 lockstep vs split mode
        # Lockstep: only r5_0 makes sense; split: r5_0 and r5_1 are independent
        lockstep = params.get("PSU__RPU0__VINITHI", "") == "1" and \
                   params.get("PSU__RPU1__VINITHI", "") == "1"
        cores.append({
            "cpu":               "psu_cortexr5_0",
            "cpu_linux":         None,
            "description":       _desc("Cortex-R5 core 0 (32-bit RPU, real-time)", r5_freq),
            "domain_standalone": "standalone_psu_cortexr5_0",
            "domain_linux":      None,
            "supports_linux":    False,
        })
        if not lockstep:
            cores.append({
                "cpu":               "psu_cortexr5_1",
                "cpu_linux":         None,
                "description":       _desc("Cortex-R5 core 1 (32-bit RPU, split-mode)", r5_freq),
                "domain_standalone": "standalone_psu_cortexr5_1",
                "domain_linux":      None,
                "supports_linux":    False,
            })

    # ── PMU ──
    cores.append({
        "cpu":               "psu_pmu_0",
        "cpu_linux":         None,
        "description":       "PMU MicroBlaze (platform management unit, advanced use only)",
        "domain_standalone": "standalone_psu_pmu_0",
        "domain_linux":      None,
        "supports_linux":    False,
    })

    return cores


def _detect_versal(inst: str, params: dict, arch: str) -> list:
    """
    Versal (versal_cips) — Cortex-A72 APU + Cortex-R5 RPU + optional AIE.
    Covers: Versal Prime, AI Core, HBM, Premium, AI Edge.
    """
    cores = []
    a72_freq = _freq(params, "PSV__CRF__ACPU_CTRL__ACT_FREQMHZ") or \
               _freq(params, "PSV__CRF__ACPU_CTRL__FREQMHZ")
    r5_freq  = _freq(params, "PSV__CRL__CPU_R5_CTRL__ACT_FREQMHZ") or \
               _freq(params, "PSV__CRL__CPU_R5_CTRL__FREQMHZ")

    # ── Cortex-A72 cores (APU) ──
    for i in range(2):
        param_name = f"PSV__CORTEXA72__{i}__ENABLE"
        if params.get(param_name, "1") == "1":
            cores.append({
                "cpu":               f"psv_cortexa72_{i}",
                "cpu_linux":         "psv_cortexa72",
                "description":       _desc(f"Cortex-A72 core {i} (64-bit APU)", a72_freq),
                "domain_standalone": f"standalone_psv_cortexa72_{i}",
                "domain_linux":      "linux_psv_cortexa72",
                "supports_linux":    True,
            })

    # ── Cortex-R5 cores (RPU) ──
    for i in range(2):
        param_name = f"PSV__CORTEXR5__{i}__ENABLE"
        if params.get(param_name, "1") == "1":
            cores.append({
                "cpu":               f"psv_cortexr5_{i}",
                "cpu_linux":         None,
                "description":       _desc(f"Cortex-R5 core {i} (32-bit RPU, real-time)", r5_freq),
                "domain_standalone": f"standalone_psv_cortexr5_{i}",
                "domain_linux":      None,
                "supports_linux":    False,
            })

    # ── PMC (Platform Management Controller) ──
    cores.append({
        "cpu":               "psv_pmc_0",
        "cpu_linux":         None,
        "description":       "PMC MicroBlaze (platform management controller, advanced use only)",
        "domain_standalone": "standalone_psv_pmc_0",
        "domain_linux":      None,
        "supports_linux":    False,
    })

    return cores


def _detect_versal_net(inst: str, params: dict, arch: str) -> list:
    """
    Versal NET / Telluride (versal_net_cips) — Cortex-A78 APU + Cortex-R52 RPU.
    Devices: VHK158, VPKL085, VHK158, VP1202, VP1502, VP1702, VP1802 etc.
    """
    cores = []
    a78_freq = _freq(params, "PSX__CRF__ACPU_CTRL__ACT_FREQMHZ") or \
               _freq(params, "PSX__CRF__ACPU_CTRL__FREQMHZ")
    r52_freq = _freq(params, "PSX__CRL__CPU_R52_CTRL__ACT_FREQMHZ") or \
               _freq(params, "PSX__CRL__CPU_R52_CTRL__FREQMHZ")

    # ── Cortex-A78 cores (APU, up to 4) ──
    for i in range(4):
        param_name = f"PSX__CORTEXA78__{i}__ENABLE"
        if params.get(param_name, "1") == "1":
            cores.append({
                "cpu":               f"psx_cortexa78_{i}",
                "cpu_linux":         "psx_cortexa78",
                "description":       _desc(f"Cortex-A78 core {i} (64-bit APU)", a78_freq),
                "domain_standalone": f"standalone_psx_cortexa78_{i}",
                "domain_linux":      "linux_psx_cortexa78",
                "supports_linux":    True,
            })

    # ── Cortex-R52 cores (RPU, up to 4) ──
    for i in range(4):
        param_name = f"PSX__CORTEXR52__{i}__ENABLE"
        if params.get(param_name, "1") == "1":
            cores.append({
                "cpu":               f"psx_cortexr52_{i}",
                "cpu_linux":         None,
                "description":       _desc(f"Cortex-R52 core {i} (32-bit RPU, real-time)", r52_freq),
                "domain_standalone": f"standalone_psx_cortexr52_{i}",
                "domain_linux":      None,
                "supports_linux":    False,
            })

    # ── PMC ──
    cores.append({
        "cpu":               "psx_pmc_0",
        "cpu_linux":         None,
        "description":       "PMC MicroBlaze (platform management controller, advanced use only)",
        "domain_standalone": "standalone_psx_pmc_0",
        "domain_linux":      None,
        "supports_linux":    False,
    })

    return cores


# ── PS IP → detector function map ─────────────────────────────────────────────
# Key: substring that must appear in the MODULE VLNV
PS_DETECTORS = {
    "processing_system7":  ("Zynq-7000",    _detect_zynq7),
    "zynq_ultra_ps_e":     ("ZynqMP",       _detect_zynqmp),
    "versal_net_cips":     ("Versal NET",   _detect_versal_net),  # check before versal_cips
    "versal_cips":         ("Versal",       _detect_versal),
}

# AIE IP substrings → description
AIE_VLNV_MAP = {
    "ai_engine_vr2": "AI Engine 2 (AIE-ML vector array, Versal NET)",
    "ai_engine":     "AI Engine (AIE vector array, Versal)",
}

AIE_CORE = {
    "cpu":               "ai_engine",
    "cpu_linux":         None,
    "description":       "AI Engine (vector DSP array)",   # overridden per device
    "domain_standalone": "aie",
    "domain_linux":      None,
    "supports_linux":    False,
}


# ── XSA parsing ───────────────────────────────────────────────────────────────

def _find_hwh(zf: zipfile.ZipFile) -> str | None:
    for name in zf.namelist():
        if name.endswith(".hwh"):
            return name
    return None


def _parse_hwh(zf: zipfile.ZipFile, hwh_name: str):
    content = zf.read(hwh_name).decode("utf-8-sig")   # strip BOM
    root = ET.fromstring(content)
    sysinfo = {}
    for si in root.iter("SYSTEMINFO"):
        sysinfo = dict(si.attrib)
        break
    modules = []
    for mod in root.iter("MODULE"):
        entry = {
            "instance": mod.get("INSTANCE", ""),
            "vlnv":     mod.get("VLNV", "").lower(),
            "iptype":   mod.get("IPTYPE", ""),
            "params":   {p.get("NAME", ""): p.get("VALUE", "") for p in mod.iter("PARAMETER")},
        }
        modules.append(entry)
    return root, sysinfo, modules


def _board_info(zf: zipfile.ZipFile, sysinfo: dict) -> dict:
    info = {
        "board": sysinfo.get("BOARD", ""),
        "part":  "",
    }
    if "xsa.json" in zf.namelist():
        try:
            data = json.loads(zf.read("xsa.json").decode())
            board = data.get("board", {})
            info["board"] = board.get("name", info["board"])
            info["part"]  = board.get("part", "")
        except Exception:
            pass
    if not info["part"]:
        info["part"] = sysinfo.get("DEVICE", "") + sysinfo.get("PACKAGE", "")
    return info


def _detect_all_processors(arch: str, modules: list) -> tuple[str, list, list]:
    """
    Returns (family_name, ps_ips_found, processor_list).
    Handles multiple PS IPs in a single design (rare but possible in SSoC/multi-die).
    """
    all_cores = []
    ps_ips_found = []
    aie_added = False

    for mod in modules:
        vlnv     = mod["vlnv"]
        instance = mod["instance"]
        iptype   = mod["iptype"]
        params   = mod["params"]

        # ── Check known PS IPs ──
        for ps_key, (family, detector_fn) in PS_DETECTORS.items():
            if ps_key in vlnv:
                ps_ips_found.append(f"{ps_key} ({instance})")
                cores = detector_fn(instance, params, arch)
                all_cores.extend(cores)
                break   # one PS IP per module

        # ── Detect AI Engine (separate IP alongside versal_cips / versal_net_cips) ──
        if not aie_added:
            for aie_vlnv, aie_desc in AIE_VLNV_MAP.items():
                if aie_vlnv in vlnv:
                    core = dict(AIE_CORE)
                    core["description"] = aie_desc
                    all_cores.append(core)
                    aie_added = True
                    break

        # ── Detect MicroBlaze soft processors in PL ──
        if "microblaze" in vlnv and iptype.upper() == "PROCESSOR":
            cpu = instance   # e.g. microblaze_0
            freq = _freq(params, "C_FREQ")
            all_cores.append({
                "cpu":               cpu,
                "cpu_linux":         None,
                "description":       _desc(f"MicroBlaze soft processor ({cpu}) in PL", freq),
                "domain_standalone": f"standalone_{cpu}",
                "domain_linux":      None,
                "supports_linux":    False,
            })

    return ps_ips_found, all_cores


# ── Main ──────────────────────────────────────────────────────────────────────

def inspect_xsa(xsa_path: str) -> dict:
    import os
    xsa_path = os.path.abspath(xsa_path)
    if not os.path.isfile(xsa_path):
        raise FileNotFoundError(f"XSA not found: {xsa_path}")

    with zipfile.ZipFile(xsa_path) as zf:
        hwh_name = _find_hwh(zf)
        if hwh_name is None:
            raise ValueError("No .hwh file found — may not be a hardware XSA.")
        _, sysinfo, modules = _parse_hwh(zf, hwh_name)
        board = _board_info(zf, sysinfo)

    arch = sysinfo.get("ARCH", "unknown").lower()
    ps_ips, raw_cores = _detect_all_processors(arch, modules)

    # ── Build final processor list ──
    processor_list = []
    seen_cpus = set()
    for p in raw_cores:
        cpu = p["cpu"]
        if cpu in seen_cpus:
            continue
        seen_cpus.add(cpu)
        entry = {
            "cpu":               cpu,
            "description":       p["description"],
            "domain_standalone": p["domain_standalone"],
            "supports_linux":    p["supports_linux"],
        }
        if p.get("cpu_linux") and p.get("domain_linux"):
            entry["cpu_linux"]    = p["cpu_linux"]
            entry["domain_linux"] = p["domain_linux"]
        processor_list.append(entry)

    return {
        "xsa":        xsa_path,
        "arch":       arch,
        "board":      board["board"],
        "part":       board["part"],
        "ps_ips":     ps_ips,
        "processors": processor_list,
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 inspect_xsa.py <path_to.xsa>", file=sys.stderr)
        sys.exit(1)

    try:
        result = inspect_xsa(sys.argv[1])
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, indent=2))

    print(f"\n=== XSA Processor Summary ===", file=sys.stderr)
    print(f"  Board  : {result['board']}", file=sys.stderr)
    print(f"  Part   : {result['part']}", file=sys.stderr)
    print(f"  Arch   : {result['arch']}", file=sys.stderr)
    print(f"  PS IPs : {', '.join(result['ps_ips']) or 'none (PL-only design)'}", file=sys.stderr)
    print(f"\n  Available processors:", file=sys.stderr)
    for i, p in enumerate(result["processors"]):
        linux_note = " [+linux]" if p.get("supports_linux") else ""
        print(f"    [{i}] {p['cpu']:<35s} {p['description']}{linux_note}", file=sys.stderr)


if __name__ == "__main__":
    main()