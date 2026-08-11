<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# AMD Documentation Index

Use the document revision matching the installed Vivado release. Search the live AMD
Documentation portal when a command, property, primitive, or IP configuration is uncertain.

## Core RTL methodology

- **UG1387 — Versal Adaptive SoC Hardware, IP, and Platform Development Methodology**
  - synchronous versus asynchronous reset
  - reset/clock-enable precedence and control signals
  - clock gating conversion and dedicated clock buffers
  - BRAM output-register inference and reset compatibility
  - DSP register packing with mixed reset behavior
  - CDC constraint selection and exception precedence
- **UG949 — UltraFast Design Methodology**
  - control sets, clock enables, high fanout, register replication
  - RAM/DSP performance and implementation-driven optimization
  - CDC path classification, max delay, bus skew, and clock-group collisions
- **UG901 — Vivado Synthesis**
  - registers/latches and memory/FSM coding templates
  - `RAM_STYLE`, `ASYNC_REG`, `FSM_ENCODING`, and `FSM_SAFE_STATE`
  - documented FIR/DSP inference patterns and retiming
- **UG903 — Using Constraints**
  - primary/generated clocks, max delay, bus skew, false paths, multicycle paths
  - timing-exception precedence and coverage
- **UG835 — Tcl Command Reference**
  - `synth_design`, report commands, and option syntax
- **UG912 — Properties Reference**
  - cell/net properties and effects of `KEEP`, `DONT_TOUCH`, and mapping properties
- **UG906 — Design Analysis and Closure Techniques**
  - timing exception status, ignored exceptions, and `report_exceptions -coverage`

## Architecture and macros

- **AM004 — Versal DSP Engine**: DSP58 registers, cascade paths, PATTERNDETECT, pattern/mask
- **AM007 — Versal Memory Resources**: BRAM/UltraRAM ports, ECC, output/cascade registers
- **UG953/UG974 and Vivado Language Templates**: Versal primitives and XPM instances
- **XPM documentation**: memory/FIFO/CDC parameters, ports, simulation, and scoped constraints

## Interfaces and domain IP

- **UG1037 and AMBA AXI**: independent AXI channels and ready/valid stability
- **PG313 and generated NoC configuration**: NoC interfaces and QoS
- **AI Engine documentation/generated graph interfaces**: PLIO/stream/window width and framing
- **DDRMC, GT, CPM/PCIe product guides**: configuration-specific boundaries and reset/clocking
- **PG269 RF Data Converter**: generated sample packing and stream behavior
- **Video, Ethernet, JESD204, Aurora, FIR, FFT, and CORDIC product guides**: use the guide
  matching the instantiated IP version and configuration

## Reliability and security boundary

- Use AM007 and applicable product safety material for ECC and memory fault handling.
- Use UG901/UG912 only to describe what synthesis preservation attributes do. AMD recommends
  using `KEEP`/`DONT_TOUCH` sparingly because they can inhibit optimization; they do not prove
  TMR, zeroization, confidentiality, isolation, or side-channel resistance.
- Use the applicable Versal security architecture/product security documents and a stated
  threat model for security claims.
- Compliance with ISO 26262, DO-254, or another safety standard requires a system safety case
  and verification evidence beyond Vivado structural reports.

## Topic routing

| Topic | Primary documents |
|---|---|
| Reset/clocking/control sets | UG1387, UG949, UG901 |
| Memory | UG901, UG1387, AM007 |
| DSP/FIR | AM004, UG901 |
| FSM | UG901 `FSM_ENCODING` and `FSM_SAFE_STATE` |
| CDC/XDC | UG949/UG1387, UG903, XPM documentation |
| AXI/interfaces | UG1037 and AMBA AXI |
| Tcl/properties | UG835, UG912 |
| Hard blocks/domain IP | Generated configuration plus matching product guide |
| Reliability/security | AM007, product safety/security docs, UG901/UG912 only for tool behavior |
