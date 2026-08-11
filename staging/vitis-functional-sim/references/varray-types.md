<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# varray Data Types Reference

`varray` is the universal data container for all VFS components. It provides hardware-compatible typed arrays that preserve bit-exact precision across Python, MATLAB, and C++.

---

## Type Table

### Integer Types

| Type | Bits | Range | Python | MATLAB |
|------|------|-------|--------|--------|
| int4 | 4 | -8 to 7 | `va.int4` | `varray.int4` |
| uint4 | 4 | 0 to 15 | `va.uint4` | `varray.uint4` |
| int8 | 8 | -128 to 127 | `va.int8` | `varray.int8` |
| uint8 | 8 | 0 to 255 | `va.uint8` | `varray.uint8` |
| int16 | 16 | -32768 to 32767 | `va.int16` | `varray.int16` |
| uint16 | 16 | 0 to 65535 | `va.uint16` | `varray.uint16` |
| int32 | 32 | -2³¹ to 2³¹-1 | `va.int32` | `varray.int32` |
| uint32 | 32 | 0 to 2³²-1 | `va.uint32` | `varray.uint32` |
| int64 | 64 | -2⁶³ to 2⁶³-1 | `va.int64` | `varray.int64` |
| uint64 | 64 | 0 to 2⁶⁴-1 | `va.uint64` | `varray.uint64` |

### Floating-Point Types

| Type | Bits | Python | MATLAB |
|------|------|--------|--------|
| half / float16 | 16 | `va.half` or `va.float16` | `varray.half` |
| bfloat16 | 16 | `va.bfloat16` | `varray.bfloat16` |
| float | 32 | `va.float32` | `varray.single` |
| double | 64 | `va.double` | `varray.double` |
| float8 | 8 | `va.float8` | `varray.float8` |
| bfloat8 | 8 | `va.bfloat8` | `varray.bfloat8` |

### Complex Types

| Type | Python | MATLAB |
|------|--------|--------|
| cint8 | `va.cint8(real, imag)` | `varray.cint8` |
| cint16 | `va.cint16(real, imag)` | `varray.cint16` |
| cint32 | `va.cint32(real, imag)` | `varray.cint32` |
| cint64 | `va.cint64(real, imag)` | `varray.cint64` |
| cfloat | `va.cfloat` | `varray.csingle` |
| cdouble | `va.cdouble` | `varray.cdouble` |
| chalf | `va.chalf` | `varray.chalf` |
| cbfloat16 | `va.cbfloat16` | `varray.cbfloat16` |

### Fixed-Point Types

| Type | Python | MATLAB |
|------|--------|--------|
| fi (signed fixed-point) | `va.fi(wordLength=W, fractionLength=F)` | `varray.fi('WordLength', W, 'FractionLength', F)` |
| cfi (complex fixed-point) | `va.cfi(wordLength=W, fractionLength=F)` | `varray.cfi('WordLength', W, 'FractionLength', F)` |

### Microscaling Types (AIE-ML Only)

| Type | Elements/Block | Python | MATLAB |
|------|---------------|--------|--------|
| mx4 | 16 | `va.mx4` | `varray.mx4` |
| mx6 | 16 | `va.mx6` | `varray.mx6` |
| mx9 | 16 | `va.mx9` | `varray.mx9` |

### AXI-Stream (Sideband)

| Type | Python | MATLAB |
|------|--------|--------|
| axis | `va.axis()` | `varray.axis()` |

---

## Creating varray from NumPy (Python)

```python
import varray as va
import numpy as np

# Auto-infer dtype from NumPy array
arr = va.array(np.array([1, 2, 3], dtype=np.int32))

# Explicit dtype
arr = va.array(np.arange(100), dtype=va.int16)

# From Python list
arr = va.array([1.0, 2.0, 3.0], dtype=va.double)

# Complex from NumPy
arr = va.array(np.array([1+2j, 3+4j]), dtype=va.cdouble)

# Fixed-point
fi_type = va.fi(wordLength=16, fractionLength=15)
arr = va.array([0.5, 0.25, -0.125], dtype=fi_type)

# Complex fixed-point
cfi_type = va.cfi(wordLength=16, fractionLength=15)
arr = va.array([0.5+0.25j, -0.1+0.3j], dtype=cfi_type)
```

## Creating varray from MATLAB

```matlab
% Integer types
arr = varray.int32(int32([1, 2, 3, 4]));
arr = varray.int16(int16(1:100));
arr = varray.uint8(uint8([255, 128, 0]));

% Floating-point
arr = varray.double([1.0, 2.0, 3.0]);
arr = varray.single(single([1.0, 2.0, 3.0]));

% Complex
arr = varray.cdouble(complex([1, 2, 3], [4, 5, 6]));
arr = varray.cint16(int16([1, 2]), int16([3, 4]));  % (real, imag)

% Fixed-point
arr = varray.fi([0.5, 0.25], 'WordLength', 16, 'FractionLength', 15);
```

---

## Converting varray Back to Native Types

### Python → NumPy

```python
import numpy as np

# Universal conversion
numpy_arr = np.asarray(varray_output)

# For complex integer types (cint16, cint32)
# Access individual elements
for sample in output:
    r = sample.real()
    i = sample.imag()

# Bulk conversion to complex numpy
data = np.array([complex(s.real(), s.imag()) for s in output])
```

### MATLAB → Native

```matlab
% To double
result = double(varray_output);

% To int32
result = int32(varray_output);

% To int16
result = int16(varray_output);

% Length
n = length(varray_output);
```

---

## AXI-Stream Sideband Setup

When an HLS kernel port uses `hls::stream<ap_axis<W,U,T,D>>`, the input varray must include sideband signals.

### Python

```python
import varray as va
import numpy as np

# Create data with axis sideband
data = np.arange(1, 9, dtype=np.int32)
arr = va.array(data, dtype=va.int32, axis=va.axis())

# Set sideband fields
arr.tlast[-1] = 1          # Mark last sample (required for packet boundary)
arr.tkeep = [0xFF] * 8     # All bytes valid (optional, depends on kernel)

# Other sideband fields (use only if kernel expects them)
arr.tstrb = [0xFF] * 8
arr.tuser = [0] * 8
arr.tid = [0] * 8
arr.tdest = [0] * 8
```

### MATLAB

```matlab
data = int32(1:8);
arr = varray.array(data, 'dtype', varray.int32, 'axis', varray.axis());

% Set sideband
arr.tlast(end) = 1;
arr.tkeep = repmat(uint8(255), 1, 8);
```

---

## Type Matching Guide

Use this to match C++ kernel types to varray types:

| C++ Type in Kernel | Python varray | MATLAB varray | NumPy dtype (for stimulus) |
|-------------------|---------------|---------------|---------------------------|
| `int8_t` | `va.int8` | `varray.int8` | `np.int8` |
| `int16_t`, `short` | `va.int16` | `varray.int16` | `np.int16` |
| `int32_t`, `int` | `va.int32` | `varray.int32` | `np.int32` |
| `uint32_t` | `va.uint32` | `varray.uint32` | `np.uint32` |
| `float` | `va.float32` | `varray.single` | `np.float32` |
| `double` | `va.double` | `varray.double` | `np.float64` |
| `ap_int<N>` | `va.int<N>` (closest) | `varray.int<N>` | N/A — use va directly |
| `ap_fixed<W,I>` | `va.fi(wordLength=W, fractionLength=W-I)` | `varray.fi(...)` | N/A |
| `cint16` (AIE) | `va.cint16(r, i)` | `varray.cint16` | N/A — use va directly |
| `cfloat` (AIE) | `va.cfloat` | `varray.csingle` | `np.complex64` |
| `bfloat16` (AIE-ML) | `va.bfloat16` | `varray.bfloat16` | N/A — use va directly |
| `hls::stream<ap_axis<32>>` | `va.int32` + `axis=va.axis()` | `varray.int32` + `axis` | N/A |

---

## Important Notes

- **varray is the universal glue** — all VFS components consume and produce varray
- **Precision is preserved** — varray stores data at hardware precision (no silent float conversion)
- **bfloat16 is AIE-ML only** — do not use with HLS kernels (will error)
- **Complex integer types** (cint16, cint32) are element-wise — create with `va.cint16(real, imag)` per element, or use list comprehension for bulk
- **Fixed-point overflow** — varray does NOT automatically saturate; values wrap on overflow just like hardware
- **axis is required** when the kernel port is `ap_axis<>` — VFS will error if you omit it
