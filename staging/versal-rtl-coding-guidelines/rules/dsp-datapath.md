<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# DSP Datapath Building Blocks

Sources: AM004 DSP Engine and the applicable AMD FIR/FFT/CORDIC product guides. Treat these as
architecture-selection rules; use a documented inference template or IP when exact cascade,
rounding, saturation, or numerical behavior matters.

## DSPD-1 — FIR and systolic structures

Use the documented UG901/AM004 systolic FIR pattern or a configured FIR IP. A behavioral
sum-of-products expression does not guarantee DSP cascade routing. Pipeline according to the
sample rate and latency contract, then verify DSP58 count, A/B/M/P registers, cascade pins,
placement, arithmetic behavior, and latency.

## DSPD-2 — Complex arithmetic

Make signed widths, conjugation, scaling, rounding, saturation, and overflow behavior explicit.
Balance real and imaginary paths to identical latency. Verify numerical corner cases as well
as DSP mapping.

## DSPD-3 — Pipeline iterative kernels correctly

For a pipelined CORDIC, each stage must choose the rotation direction from the current sign and
apply that direction consistently to X, Y, and angle:

```systemverilog
logic dir;
dir = y_pipe[i][XY_W-1];
x_pipe[i+1] <= dir ? x_pipe[i] + (y_pipe[i] >>> i)
                         : x_pipe[i] - (y_pipe[i] >>> i);
y_pipe[i+1] <= dir ? y_pipe[i] - (x_pipe[i] >>> i)
                         : y_pipe[i] + (x_pipe[i] >>> i);
z_pipe[i+1] <= dir ? z_pipe[i] + atan_lut[i]
                         : z_pipe[i] - atan_lut[i];
```

This is a stage pattern, not a complete module. Define vectoring versus rotation mode,
quadrant preprocessing, widths, guard bits, gain compensation, valid propagation, and reset
behavior. Prefer the supported CORDIC IP when its contract fits.

## DSPD-4 — FFT stages require matched storage and control

Pipeline butterflies, store/reorder data with supported BRAM/URAM templates, and keep twiddle,
valid, frame, and address metadata aligned. Use the FFT IP when its architecture and interface
meet requirements. Verify ordering, scaling schedule, overflow, throughput, and backpressure.

## Checklist

- [ ] A documented inference template or configured IP defines specialized structures.
- [ ] Numerical widths and error behavior are explicit and tested.
- [ ] Valid/control latency matches every arithmetic stage.
- [ ] Cascade connectivity and memory mapping are verified, not inferred from counts alone.
- [ ] CORDIC direction updates X, Y, and Z consistently.
