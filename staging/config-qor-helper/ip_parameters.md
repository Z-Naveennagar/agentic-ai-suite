<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Config QoR IP Parameters

## fft_ifft_dit_1ch

Template class: `xf::dsp::aie::fft::dit_1ch::fft_ifft_dit_1ch_graph`

Reference: https://docs.amd.com/r/en-US/Vitis_Libraries/dsp/rst/class_xf_dsp_aie_fft_dit_1ch_fft_ifft_dit_1ch_graph.html_0

### Parameters for Constraint File

| Parameter | Type | Description |
|-----------|------|-------------|
| AIE_VARIANT | int | 1=AIE, 2=AIE-ML, 22=AIE-MLv2 |
| TT_DATA | string | Input data type (e.g., "cint16", "cint32", "cfloat") |
| TT_TWIDDLE | string | Twiddle factor type (e.g., "cint16", "cint32") |
| TP_POINT_SIZE | int | FFT point size (must be power of 2) |
| TP_FFT_NIFFT | int | 1=FFT, 0=IFFT |
| TT_OUT_DATA | string | Output data type |

Only include parameters the user specifies. Not all need to be set in the constraint file.

### Parameters from Predicted Configuration (CSV Output)

These appear in the output CSV and are used for graph code generation:

| Parameter | Description |
|-----------|-------------|
| TP_CASC_LEN | Cascade length |
| TP_PARALLEL_POWER | Parallel power (log2 of parallelism) |
| TP_WINDOW_SIZE / WIN_SIZE | Window size for processing |
| TP_API | 0=window-based, 1=stream-based |
| TP_DYN_PT_SIZE | Dynamic point size (0=static, 1=dynamic) |
| TP_SHIFT | Scaling shift value |
| NUM_AIE | Number of AIE tiles used |
| THROUGHPUT | Predicted throughput (MSPS) |
| LATENCY | Predicted latency |

### Derived Values

**TP_SHIFT**: Compute as `log2(TP_POINT_SIZE)`. Always inform the user that this value is generated from log2(TP_POINT_SIZE).

**NPORTS_IO** (number of I/O ports):
```
If TP_API == 0:  NPORTS_IO = 2^TP_PARALLEL_POWER
If TP_API == 1:  NPORTS_IO = 2^(TP_PARALLEL_POWER + 1)
```

## Extending to Other IPs

The constraint file structure (`parameter_constraints`, `qor_constraints`, `sort_by`, `ascending`) is the same for all DSP library IPs. Only the fields within `parameter_constraints` differ per IP. Refer to the Vitis DSP Library documentation for each IP's template parameters.
