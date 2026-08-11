<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 multimedia appliance controller

Create a Vivado 2025.2 KV260 design containing
`kv260_multimedia_appliance`. An idle `start` begins one bounded run with
latched frame and audio-block targets. Count frame and audio events while
busy, ignore additional starts, and finish with sticky `done` and `pass` when
both targets are met. A DDR error or abort must terminate the run with
`error_code` 1 or 2 respectively. `clear` has highest priority and restores
the idle reset state. Handle simultaneous final events and zero targets
deterministically.

The public RTL is only the appliance run controller. Integrate it using IP
Integrator with the KV260 PS preset, a 100 MHz PL clock, platform-owned
camera/audio/DDR adapters, PS DMA, and the standard VIO/System-ILA hardware
test shell. Live sensors, codecs, displays, DDR traffic, and Linux services
are outside the deterministic public-kernel oracle and must be replaced by
bounded synthetic event sources for self-test. Use direct RTL, not HLS.
Generate a bitstream and XSA without programming hardware.
