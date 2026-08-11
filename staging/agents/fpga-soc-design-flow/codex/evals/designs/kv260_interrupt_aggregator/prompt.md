<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 interrupt aggregator

Create a Vivado 2025.2 KV260 design containing `kv260_interrupt_aggregator`.
Latch eight source pulses into a sticky pending register. `clear` wins over a
simultaneous source assertion for the same bit. Apply an independent active
mask to IRQ generation without destroying pending state. Assert `irq` when any
masked pending bit is active and report the lowest-numbered active source as
the priority index.

Integrate the kernel with the KV260 PS PL-to-PS interrupt path, AXI-visible
mask/clear registers, a 100 MHz PL clock, and standard VIO/ILA hardware-test
instrumentation. Driver policy and Linux interrupt handling are outside the
public RTL oracle. Use direct RTL, not HLS. Verify sticky capture, masking,
priority, simultaneous events, clear precedence, and reset. Generate a
bitstream and XSA without programming hardware.
