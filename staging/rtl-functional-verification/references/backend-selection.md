<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Backend Selection

Choose a backend from design requirements, not preference alone.

| Requirement | cocotb + Verilator | XSim + SystemVerilog | XSim + Python vectors |
|---|---:|---:|---:|
| Live Python signal access | Yes | No | No |
| NumPy/SciPy golden model | Native | Via files or DPI bridge | Native before/after simulation |
| Fast portable RTL regression | Preferred | Supported | Supported |
| Four-state X/Z sensitivity | Limited | Preferred | Preferred in HDL checks |
| AMD XPM, primitives, or IP models | Limited; prove compatibility | Preferred | Preferred |
| IEEE P1735 encrypted RTL | No | Preferred | Preferred |
| Mixed VHDL/SystemVerilog | No | Preferred | Preferred |
| Post-synthesis or SDF timing simulation | No | Use a separate timing-simulation scope | Use a separate timing-simulation scope |
| Open-source simulator requirement | Yes | No; AMD tool | No; AMD tool |

## Preflight

1. Run `scripts/detect_backends.py --json`.
2. Identify the HDL languages and every vendor model.
3. Check whether the selected simulator supports the testbench constructs.
4. Compile and elaborate a representative smoke test with the required libraries or IP.
5. Record discovery separately from design-specific readiness and record tool versions in the result.
6. Do not install tools or packages without authorization.

`detect_backends.py` reports whether the required executables and Python packages are discoverable.
It does not prove licensing, library compilation, XPM/IP elaboration, or compatibility with a
particular design.

## Selection rules

Use cocotb plus Verilator when the DUT is portable synthesizable Verilog/SystemVerilog and Python
needs live control. Treat Verilator as primarily two-state. Do not use its experimental four-state
mode as sign-off evidence.

Use XSim plus SystemVerilog when the test depends on X/Z propagation, AMD simulation libraries,
XPMs, encrypted IP, mixed HDL, or an existing Vivado project.

Use XSim plus Python vectors for algorithmic blocks when a Python model can generate all required
stimulus and expected results in advance. Keep an HDL checker so failures are localized in
simulation.

Use two tiers for AMD production RTL when practical:

1. broad cocotb/Verilator regression for speed;
2. focused XSim tests for reset, X/Z, simulator semantics, and AMD model integration.

A pass on one backend does not waive known gaps in another.

Emit one normalized result per tier. A regression rollup must identify required tiers and fail if
any required result is missing, unsupported, erroneous, or failed.

## Ground-truth sources

- Verilator language and limitation reference: https://verilator.org/guide/latest/languages.html
- cocotb simulator support: https://docs.cocotb.org/en/stable/simulator_support.html
- AMD Vivado Logic Simulation guide: https://docs.amd.com/r/en-US/ug900-vivado-logic-simulation
