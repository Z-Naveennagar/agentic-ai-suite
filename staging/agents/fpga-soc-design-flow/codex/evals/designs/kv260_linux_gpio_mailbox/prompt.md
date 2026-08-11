<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 Linux GPIO mailbox kernel

Create a Vivado 2025.2 KV260 design containing
`kv260_linux_gpio_mailbox`. Implement a one-entry ready/valid command-response
mailbox with opcodes: 0 NOP, 1 ECHO, 2 ADD to a 32-bit accumulator and return
the new value, 3 READ the accumulator, and 4 CLEAR it. Unsupported opcodes
must assert `rsp_error` and return `0xDEAD0000 | opcode`. Hold the response
stable under backpressure and accept a replacement command when the old
response advances.

Integrate the public RTL kernel using IP Integrator with the KV260 PS preset, a
100 MHz PL clock, a platform-owned AXI GPIO/register adapter, and the standard
VIO/System-ILA hardware test shell. Linux GPIO drivers, device-tree overlays,
and physical GPIO pins are outside the deterministic public-kernel oracle.
Use direct RTL, not HLS. Verify all commands, errors, accumulator wraparound,
response stalls, and back-to-back replacement. Generate a bitstream and XSA
without programming hardware.
