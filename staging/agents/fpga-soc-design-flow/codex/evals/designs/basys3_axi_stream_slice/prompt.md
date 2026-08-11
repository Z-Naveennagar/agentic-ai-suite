<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

Create a direct-RTL Vivado design containing a one-entry AXI4-Stream elastic register slice for a Basys 3 (`xc7a35tcpg236-1`).

The stream data width is 32 bits and includes `TVALID`, `TREADY`, `TDATA`, and `TLAST`. The slice must sustain one transfer per clock after filling, hold output data stable during downstream backpressure, never drop or duplicate a transfer, and become empty after an active-high synchronous reset. Use the 100 MHz board clock.

Also provide a synthesizable on-board self-test wrapper that drives the slice internally and reports pass/fail on LEDs, complete XDC pin and timing constraints, a self-checking cocotb regression for the register-slice module, Vivado implementation evidence, and a `.bit` file. Use handwritten RTL, not HLS.
