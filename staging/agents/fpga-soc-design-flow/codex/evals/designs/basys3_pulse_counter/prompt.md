<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

Create a direct-RTL Vivado design for a Basys 3 (`xc7a35tcpg236-1`) that counts rising edges on an event input.

Use the 100 MHz board clock and an active-high synchronous reset. The counter is 8 bits, wraps at 255, and emits a one-cycle overflow pulse when it wraps. A synchronous clear has priority over event counting, while reset has priority over clear. Drive the count and overflow indication to LEDs.

Provide synthesizable SystemVerilog, complete XDC pin and timing constraints, a self-checking cocotb regression, Vivado implementation evidence, and a `.bit` file. Use handwritten RTL, not HLS.
