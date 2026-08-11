<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 Vivado board probe

Probe date: 2026-07-28
Tool: Vivado 2025.2 through Vivado MCP
Session: `vivado-20260728-122125`

## Confirmed target

- Board part: `xilinx.com:kv260_som:part0:1.4`
- Device part: `xck26-sfvc784-2LV-c`
- Other installed KV260 board revisions: `1.2`, `1.3`

## Confirmed IP catalog

- Zynq UltraScale+ MPSoC `zynq_ultra_ps_e:3.5`
- AXI GPIO `axi_gpio:2.0`
- AXI DMA `axi_dma:7.1`
- AXI4-Stream FIFO and switch
- SmartConnect, Clocking Wizard, and Processor System Reset
- Video Test Pattern Generator, frame-buffer read/write, and Video Processing Subsystem
- MIPI CSI-2 Receiver Subsystem
- HDMI TX Subsystem

The regression suite uses the board part rather than inventing carrier-card pin
constraints. IP-integrator cases receive clocks, resets, DDR, and fixed I/O from
the KV260 board preset and must export an XSA in addition to the programming
image.
