---
name: vitis-functional-sim
description: >-
  Generate Python or MATLAB functional verification test scripts for AMD Versal
  hardware implementations using VFS (Vitis Functional Simulation). Supports HLS
  kernels, AI Engine graphs, LogiCORE IPs (xFFT, FIR Compiler), Versal RF Hard IPs
  (vrfFFT, vrfChannelizer, vrfADC, vrfDAC), and multi-component chained pipelines.
  Use when: user wants to functionally verify their implementation, build a test
  framework, simulate their kernel in Python/MATLAB, compare against a reference
  model, create a VFS testbench, or functionally simulate their design.
author: Faisal El-Shabani
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
# Vitis Functional Simulation (VFS)

Generate functional verification test scripts that wrap hardware implementations in Python or MATLAB using the VFS framework. VFS provides bit-accurate C-model simulation of HLS kernels, AI Engine graphs, and HDL IPs — no synthesis or place-and-route required.

---

## Prerequisites

Before generating any test script, verify the following. Halt and inform the user if any check fails.

### 1. Vitis Environment

```bash
echo $XILINX_VITIS
```

- If `$XILINX_VITIS` is empty or the command fails: run `ts 2026.1_daily_latest` (or ask user for their preferred Vitis version)
- Confirm: `which v++` returns a valid path

### 2. Language-Specific Setup

#### Python

1. Ask the user: **"Do you have an existing Python virtual environment for this project, or should I create one?"**
   - If existing: `source <user_path>/bin/activate`
   - If new: `python3 -m venv vfs_env && source vfs_env/bin/activate`
2. Verify Python version is 3.9–3.14: `python3 --version`
3. Verify NumPy: `python3 -c "import numpy"` — if fails, run `pip install numpy`
4. Verify VFS: `python3 -c "import vfs; import varray as va; print('VFS OK')"`

#### MATLAB

1. Check: `which matlab`
   - If not available: run `ts -matlab R2024a`
2. Verify VFS available: `matlab -batch "varray.ver"`

### 3. Source Files

- Confirm all user-specified source files (`.cpp`, `.h`, `.cfg`) exist and are accessible
- Confirm any specified include paths are valid directories

---

## Workflow

### Step 1: Detect Components

Read the user's source files and classify:

| Indicator | Component Type |
|-----------|---------------|
| `hls::stream<T>`, `ap_int`, `ap_fixed`, standalone C++ function with `#pragma HLS` | **HLS Kernel** |
| `adf::graph`, `input_port`, `output_port`, `aie::` namespace, `kernel::create` | **AIE Graph** |
| User explicitly names vrfFFT, xFFT, firCompiler, vrfChannelizer, vrfADC, vrfDAC | **HDL IP** |
| Multiple of the above | **Chained Pipeline** |

Load the relevant reference document:
- HLS → [./references/hls-kernel-api.md](./references/hls-kernel-api.md)
- AIE → [./references/aie-graph-api.md](./references/aie-graph-api.md)
- HDL IP → [./references/hdl-ip-api.md](./references/hdl-ip-api.md)
- Chained → [./references/chaining-patterns.md](./references/chaining-patterns.md)
- Data types → [./references/varray-types.md](./references/varray-types.md)

### Step 2: Determine Test Strategy

Ask the user: **"Do you have an existing reference model (Python or MATLAB script) that produces golden output to compare against?"**

#### Path A: Existing Reference Model

1. Read the existing script to identify:
   - Input stimuli (variable names, data shapes, types)
   - Expected output (golden vectors)
   - Data flow and processing order
2. Inject VFS component creation into the same script (or a companion script if the user prefers)
3. Feed the SAME stimuli to the VFS component
4. Add comparison logic after both reference and VFS produce output

**Script ordering when integrating with existing reference:**
```
[reference model]   ← runs first, produces golden_output
[VFS section]       ← creates kernel, feeds same stimuli, runs
[comparison logic]  ← compares golden vs VFS output, reports error in LSBs
```

#### Path B: No Reference Model

1. Create a new test script from scratch
2. Use `getInputSpec()` on the VFS component to determine port names, types, and widths
3. Generate random stimuli with appropriate shape and dtype:
   - Integer ports: `np.random.randint(low, high, size=N)` bounded by bit-width
   - Float ports: `np.random.randn(N)` scaled appropriately
   - Complex ports: `np.random.randn(N) + 1j * np.random.randn(N)`
4. Run the VFS component and print/plot outputs for user inspection

### Step 3: Select Language

If not already obvious from context (e.g., user said "MATLAB" or has `.m` files), ask: **"Python or MATLAB for the test script?"**

### Step 4: Generate Test Script

Follow this structure:

```
1. Imports (vfs, varray, numpy/scipy or MATLAB built-ins)
2. Path setup (use absolute paths — VFS compiles from a work directory)
3. Component instantiation (constructor with source paths)
4. Stimulus preparation (varray creation from golden data or random)
5. Execution (component.run())
6. Comparison (if reference exists):
   - Compute error in LSBs (1 LSB = 1 integer unit at output precision)
   - Report max mismatch in LSBs (0 = bit-exact)
   - Pass/fail assertion against LSB tolerance
7. Results display (print LSB mismatch, pass/fail)
```

**Path setup pattern** (always use absolute paths for source files):

```python
import os
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
kernel = vfs.hlsKernel(
    input_files=os.path.join(SCRIPT_DIR, "kernels.cpp"),
    hls_function="my_function"
)
```

```matlab
script_dir = fileparts(mfilename('fullpath'));
kernel = vfs.hlsKernel(input_files=fullfile(script_dir, 'kernels.cpp'), ...
    hls_function="my_function");
```

#### Comparison Logic Templates

Always report mismatch in **LSBs** (1 LSB = 1 integer unit at the output word's least significant bit position). For floating-point outputs, report max absolute error instead.

**When to expect bit-exact (0 LSBs):**
- Integer-only paths (e.g., int16 → int16) with identical quantization
- Reference model uses the same fixed-point arithmetic as the implementation

**When to expect small LSB mismatch (1–2 LSBs):**
- Same word widths but different rounding at intermediate stages

**When to expect larger mismatch (>2 LSBs):**
- Reference is floating-point, implementation is fixed-point
- Cascaded fixed-point operations with different intermediate precision

**Python — LSB comparison (integer/fixed-point paths):**
```python
import numpy as np

MAX_LSB_TOLERANCE = 0  # 0 = require bit-exact; adjust per design

reference = np.asarray(golden_output).flatten()
actual = np.asarray(vfs_output).flatten()
error = reference.astype(np.int64) - actual.astype(np.int64)
max_err_lsb = int(np.max(np.abs(error)))

print(f"Max mismatch: {max_err_lsb} LSBs")
if max_err_lsb == 0:
    print("PASS: Bit-exact match (0 LSBs)")
elif max_err_lsb <= MAX_LSB_TOLERANCE:
    print(f"PASS: {max_err_lsb} LSBs within tolerance ({MAX_LSB_TOLERANCE})")
else:
    raise AssertionError(
        f"FAIL: {max_err_lsb} LSBs exceeds tolerance ({MAX_LSB_TOLERANCE})")
```

**MATLAB — LSB comparison (integer/fixed-point paths):**
```matlab
MAX_LSB_TOLERANCE = 0;  % 0 = require bit-exact

reference = int64(golden_output(:));  % Column vector
actual = int64(double(vfs_output(:)));  % Column vector — VFS outputs are columns
error = reference - actual;
max_err_lsb = max(abs(error));

fprintf('Max mismatch: %d LSBs\n', max_err_lsb);
if max_err_lsb == 0
    fprintf('PASS: Bit-exact match (0 LSBs)\n');
elseif max_err_lsb <= MAX_LSB_TOLERANCE
    fprintf('PASS: %d LSBs within tolerance (%d)\n', max_err_lsb, MAX_LSB_TOLERANCE);
else
    error('FAIL: %d LSBs exceeds tolerance (%d)', max_err_lsb, MAX_LSB_TOLERANCE);
end
```

**Python — Floating-point paths (when LSB doesn't apply):**
```python
reference = np.asarray(golden_output).flatten()
actual = np.asarray(vfs_output).flatten()
max_err = np.max(np.abs(reference - actual))
print(f"Max absolute error: {max_err:.6e}")
assert max_err < TOLERANCE, f"FAIL: max error {max_err:.6e} exceeds {TOLERANCE}"
print("PASS")
```

### Step 5: Validate

After generating the script:

1. **Run it** — execute the generated script to confirm no import/syntax/runtime errors
2. **Check paths** — verify all referenced source files resolve
3. **Check types** — confirm varray dtype matches what the kernel port expects
4. **Warn about buffering** — if the kernel uses buffer/array interfaces, warn the user that partial inputs produce no output until the buffer fills (see [hls-kernel-api.md](./references/hls-kernel-api.md) for details)

---

## Component-Specific Patterns

### HLS Kernel (Quick Reference)

```python
import vfs
import varray as va
import numpy as np
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

kernel = vfs.hlsKernel(
    input_files=os.path.join(SCRIPT_DIR, "kernels.cpp"),
    hls_function="my_function",
    include_paths=[os.path.join(SCRIPT_DIR, "include/")],  # optional
)

# Inspect ports
print(kernel.getInputSpec())
print(kernel.getOutputSpec())

# Run
input_data = va.array(np.arange(1, 9, dtype=np.int32))
output = kernel.run(input_data)
result = np.asarray(output)
```

### AIE Graph (Quick Reference)

```python
import vfs
import varray as va
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

graph = vfs.aieGraph(
    input_file=os.path.join(SCRIPT_DIR, "graph.cpp"),
    include_paths=[os.path.join(SCRIPT_DIR, "src/")],
)

output = graph.run(va.array(input_data, dtype=va.cint16))
```

### HDL IP (Quick Reference)

```python
from vfs.vrfFFT import vrfFFT

config = vrfFFT.getDefaultConfig()
config.data_width_in = 16
fft = vrfFFT(config)

ctrl = fft.Control(point_size=10, direction=1, scaling_factor=1/1024)
output, overflow = fft.run(va.array(data, va.cdouble), ctrl)
```

### Chained Pipeline (Quick Reference)

```python
# Components chain freely — output varray feeds next input
stage1_out = aie_graph.run(input_data)
stage2_out = hls_kernel.run(stage1_out)
final_out = hdl_ip.run(stage2_out, control)
```

---

## Important Notes

- **Stream vs Buffer**: HLS kernels with `hls::stream<T>` produce output immediately per sample. Kernels with array/buffer interfaces accumulate data internally — partial inputs yield empty output until the buffer is full. Always size inputs to match the kernel's expected block size.
- **varray is universal**: All VFS components consume and produce `varray`. Use `va.array()` to create from NumPy, `np.asarray()` to convert back.
- **AXI-Stream sideband**: If a kernel port uses `ap_axis<>` or `hls::stream<ap_axis<>>`, wrap data with `axis=va.axis()` and set `tlast` on the final sample.
- **All components are stateful**: HLS kernels with `static` variables, AIE graphs with internal buffers, and HDL IPs (FFT, FIR, channelizer) all maintain state across `run()` calls. Call `reset()` between independent test vectors if you don't want state carryover.
- **Port inspection**: Always call `getInputSpec()` / `getOutputSpec()` first if unsure about port names, types, or widths.
- **MATLAB vector orientation**: VFS outputs are column vectors in MATLAB. Always coerce to consistent orientation before comparison: `golden(:)` and `double(vfs_output(:))`.
- **Use absolute paths**: VFS compiles from an internal work directory. Always use absolute paths for `input_files` and `include_paths` (use `os.path.abspath()` in Python, `fileparts(mfilename('fullpath'))` in MATLAB).
