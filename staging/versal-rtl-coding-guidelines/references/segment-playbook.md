<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Versal Application-to-Rule Router

Use this table to identify likely rule files. Load only rules for constructs actually present
in the requested module; no design needs every rule merely because it targets Versal. Confirm
protocol and IP configuration instead of inferring requirements from a market label alone.

| Application area | Common constructs | Load when present |
|---|---|---|
| Wireless/RF/radar | RFdc streams, JESD, FIR/FFT/CORDIC, complex MAC | rf-datapath, high-speed-io, dsp, dsp-datapath, interfaces, cdc |
| Networking/SmartNIC | Ethernet streams, parsers, tables, PCIe/NoC | packet-processing, interfaces, memory, high-speed-io, versal-hardblocks |
| Video/vision/broadcast | AXI4-Stream Video, line/frame buffers, pixel arithmetic | streaming-video, interfaces, memory, dsp, cdc |
| AI/compute | systolic arithmetic, BRAM/URAM, NoC/AIE/DDR | dsp, dsp-datapath, memory, interfaces, versal-hardblocks |
| Automotive/aerospace/medical | supervisory FSMs, ECC, redundancy, fault response | safety-reliability plus the rules for each implemented resource |
| Security-sensitive systems | keys, zeroization, access control, crypto boundaries | security plus applicable product security documentation and threat model |
| Industrial/control | deterministic state machines, arithmetic, sensor CDC | fsm, timing-driven, dsp, interfaces, cdc, reset |

## Routing procedure

1. Identify the concrete module, configured IP interfaces, clocks, reset contract, latency,
   throughput, and fault/security requirements.
2. Load the relevant foundation rule for each construct: reset, clocking, memory, DSP, FSM,
   CDC, XPM, interfaces, general RTL, or timing.
3. Add a domain rule only when the module implements that domain behavior.
4. Use the generated IP configuration and matching product guide as the source of truth for
   widths, sidebands, framing, clocks, and reset sequencing.
5. Author complete RTL and XDC, then run the structural and functional checks in `SKILL.md`
   and `references/rule-check-map.md`.

Do not infer security or safety compliance from the application segment. For cryptographic
logic, distinguish fixed transaction latency from power/EM/fault resistance. For TMR/ECC,
state the fault model and verify coverage with fault injection.
