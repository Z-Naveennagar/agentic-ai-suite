<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# XSim with Python Vectors and Models

Use this flow when Python or NumPy is the natural reference model but XSim must execute the RTL.
Python does not drive the running XSim process in this mode.

## Data flow

1. Python reads a versioned test manifest and deterministic seed.
2. Python generates stimulus and expected transactions independently of the RTL.
3. Python writes unambiguous interchange files.
4. A SystemVerilog testbench reads stimulus, drives the DUT, and checks results in simulation.
5. The testbench writes observed transactions and a terminal result.
6. Python optionally performs a second independent comparison and emits normalized JSON.

Prefer hexadecimal text or a small documented CSV schema. Include width, signedness, radix, byte
order, transaction ID, expected latency policy, and end-of-test marker. Do not use Python pickle or
an undocumented binary layout as a long-lived verification interface.

## Correctness rules

- Generate expected data from an independent model, not translated DUT code.
- Record package versions and numeric modes when NumPy/SciPy results can vary.
- Quantize explicitly before comparison.
- Define rounding, saturation, overflow, NaN, denormal, and tolerance policies.
- Compare accepted transactions, not merely clock cycles, for backpressured interfaces.
- Check the HDL result online when practical so the first mismatch has simulation context.
- Treat malformed, truncated, empty, or extra vector data as failure.
- Require both the HDL terminal pass flag and the Python result gate.

## Good fits

Use for FIR/IIR filters, FFT wrappers, image or video transforms, RF datapaths, checksums, packet
transforms, matrix arithmetic, codecs, and fixed-point conversion.

Do not use vector-only checking when correctness depends on adaptive live responses that cannot be
precomputed. Select cocotb or a SystemVerilog transaction environment instead.
