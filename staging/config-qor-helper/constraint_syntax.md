<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Config QoR Constraint File Syntax

## Structure

The constraint JSON has four fields:

```json
{
    "parameter_constraints": { ... },
    "qor_constraints": "<expression_string>",
    "sort_by": ["<param1>", "<param2>"],
    "ascending": [true, false]
}
```

## parameter_constraints

IP configuration parameters. Only include parameters specified by the user — not all parameters need to be set.

### AIE Variant (required)

| Choice | Value |
|--------|-------|
| AIE | `"AIE_VARIANT": 1` |
| AIE-ML | `"AIE_VARIANT": 2` |
| AIE-MLv2 | `"AIE_VARIANT": 22` |

Always ask the user which variant they want.

## qor_constraints

A string expression with comparison operators and `and` conjunctions.

**Available metrics**: `Throughput`, `Latency`, `Confidence`, `NUM_AIE`
**Operators**: `>`, `<`
**Confidence range**: -10 to -2 (default: **-5**)

Example: `"Throughput>400 and Latency<20000 and Confidence>-5"`

## sort_by and ascending

- `sort_by`: Array of parameter names to sort results by.
- `ascending`: Array of booleans matching `sort_by` order.

**Default** (use unless user specifies otherwise):
```json
"sort_by": ["num_aie", "THROUGHPUT"],
"ascending": [true, false]
```
This sorts by fewest AIE tiles first, then highest throughput first.

## Complete Example (fft_ifft_dit_1ch)

```json
{
    "parameter_constraints": {
        "AIE_VARIANT": 1,
        "TT_DATA": "cint16",
        "TT_TWIDDLE": "cint32",
        "TP_POINT_SIZE": 128,
        "TP_FFT_NIFFT": 1,
        "TT_OUT_DATA": "cint16"
    },
    "qor_constraints": "Throughput>400 and Latency<20000 and Confidence>-5",
    "sort_by": ["num_aie", "THROUGHPUT"],
    "ascending": [true, false]
}
```
