<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# KV260 DMA descriptor queue

Create a Vivado 2025.2 KV260 design containing
`kv260_dma_descriptor_queue`. Implement a fixed-depth four-entry RTL FIFO for
64-bit DMA addresses, 24-bit byte lengths, and 8-bit tags. Preserve descriptor
ordering and output stability under backpressure, support wraparound and
same-cycle push/pop, expose the queued-entry count, and independently count
completion pulses.

The public kernel is descriptor control logic only. Integrate it using IP
Integrator with the KV260 PS preset, a 100 MHz PL clock, a platform-owned AXI
DMA path, and the standard VIO/System-ILA hardware test shell. DMA engines,
DDR, Linux drivers, cache management, and physical data movement are outside
the deterministic public-kernel oracle. Use direct synthesizable RTL, not
HLS. Verify empty/full behavior, ordering, wraparound, simultaneous transfers,
backpressure stability, and completion counting. Generate a bitstream and XSA
without programming hardware.
