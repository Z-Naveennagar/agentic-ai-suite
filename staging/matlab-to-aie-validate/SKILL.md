---
name: matlab-to-aie-validate
description: >-
  Generates validation infrastructure for AI Engine kernels ported from MATLAB.
  Creates test data files from MATLAB golden reference, builds comparison scripts
  (Python or MATLAB) that run x86 simulation and compare output against golden
  data, reporting error in LSBs or max absolute error. Optionally integrates with
  VFS (Vitis Functional Simulation) for bit-accurate verification.
  Use when: validating an AIE kernel against its MATLAB reference, generating
  test vectors, or creating automated pass/fail comparison scripts.
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# MATLAB-to-AIE: Validate

Generate test data and comparison scripts to verify AIE kernel correctness against the MATLAB reference.

---

## Prerequisites

- Kernel files (.h, .cpp), graph files, and Makefile have been generated
- Original MATLAB function and test harness are available
- MATLAB is accessible (`which matlab` succeeds, or user has Octave)
- Target data type is known (determines comparison tolerance)

---

## Workflow

### Step 1: Generate Test Stimuli from MATLAB

Run the MATLAB test harness (or create a data generation script) to produce input/output data files:

```matlab
% generate_test_data.m
% Produces input and golden output files for AIE kernel validation

% Parameters (must match kernel template parameters)
M = 64; N = 128; L = 32;

% Generate reproducible random inputs
rng(0);
A = rand(M, N, 'single');
B = rand(N, L, 'single');

% Compute golden output using MATLAB reference
C_golden = gemm(A, B);  % Call the original MATLAB function

% Write to text files in AIE data format
write_aie_data('data/input_A.txt', A);
write_aie_data('data/input_B.txt', B);
write_aie_data('data/golden_C.txt', C_golden);

fprintf('Test data generated: A[%dx%d], B[%dx%d] -> C[%dx%d]\n', ...
    M, N, N, L, M, L);
```

**Data format helper function**:

```matlab
function write_aie_data(filename, matrix)
% Write matrix to AIE-compatible text file (column-major, one element per line)
    fid = fopen(filename, 'w');
    data = matrix(:);  % Column-major linearization
    for i = 1:length(data)
        if isreal(data(i))
            fprintf(fid, '%g\n', data(i));        % float
        else
            fprintf(fid, '%g %g\n', real(data(i)), imag(data(i)));  % complex
        end
    end
    fclose(fid);
end
```

**For fixed-point targets (int16)**:

```matlab
% Quantize to int16 with specified fractional bits
FRAC_BITS = 12;
A_q = int16(round(A * 2^FRAC_BITS));
B_q = int16(round(B * 2^FRAC_BITS));
C_golden_q = int32(A_q) .* int32(B_q);  % Full-precision golden

% Write integer values
write_aie_data_int('data/input_A.txt', A_q);
write_aie_data_int('data/input_B.txt', B_q);
write_aie_data_int('data/golden_C.txt', C_golden_q);
```

### Step 2: Choose Comparison Language

Ask the user if not already clear: **"Python or MATLAB for the comparison script?"**

### Step 3: Generate Comparison Script

#### Python Version

```python
#!/usr/bin/env python3
"""
validate_kernel.py
Compare AIE x86sim output against MATLAB golden reference.
"""

import numpy as np
import subprocess
import sys
import os

# Configuration
DATA_DIR = "data"
GOLDEN_FILE = os.path.join(DATA_DIR, "golden_C.txt")
OUTPUT_FILE = "Work_x86/x86simulator_output/data/output_C.txt"  # x86sim output location
DATA_TYPE = "float"  # or "int16", "int32"
MAX_ABS_ERROR_TOL = 1e-5   # For floating-point comparison
MAX_LSB_TOL = 0             # For fixed-point comparison (0 = bit-exact)

def load_data(filepath, dtype="float"):
    """Load AIE data file into numpy array."""
    data = np.loadtxt(filepath)
    if dtype == "float":
        return data.astype(np.float32)
    elif dtype == "int16":
        return data.astype(np.int16)
    elif dtype == "int32":
        return data.astype(np.int32)
    return data

def run_x86sim():
    """Run x86 simulation."""
    print("Running x86 simulation...")
    result = subprocess.run(["make", "x86sim"], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"x86sim FAILED:\n{result.stderr}")
        sys.exit(1)
    print("x86 simulation completed successfully.")

def compare_float(golden, actual):
    """Compare floating-point outputs."""
    abs_error = np.abs(golden - actual)
    max_abs_err = np.max(abs_error)
    mean_abs_err = np.mean(abs_error)
    
    print(f"Max absolute error: {max_abs_err:.8e}")
    print(f"Mean absolute error: {mean_abs_err:.8e}")
    
    if max_abs_err <= MAX_ABS_ERROR_TOL:
        print(f"PASS: Max error {max_abs_err:.2e} within tolerance {MAX_ABS_ERROR_TOL:.2e}")
        return True
    else:
        print(f"FAIL: Max error {max_abs_err:.2e} exceeds tolerance {MAX_ABS_ERROR_TOL:.2e}")
        return False

def compare_fixed(golden, actual):
    """Compare fixed-point outputs in LSBs."""
    error = golden.astype(np.int64) - actual.astype(np.int64)
    max_lsb_err = int(np.max(np.abs(error)))
    
    print(f"Max mismatch: {max_lsb_err} LSBs")
    
    if max_lsb_err <= MAX_LSB_TOL:
        if max_lsb_err == 0:
            print("PASS: Bit-exact match (0 LSBs)")
        else:
            print(f"PASS: {max_lsb_err} LSBs within tolerance ({MAX_LSB_TOL})")
        return True
    else:
        print(f"FAIL: {max_lsb_err} LSBs exceeds tolerance ({MAX_LSB_TOL})")
        return False

def main():
    # Run simulation
    run_x86sim()
    
    # Load golden and actual outputs
    golden = load_data(GOLDEN_FILE, DATA_TYPE)
    actual = load_data(OUTPUT_FILE, DATA_TYPE)
    
    # Verify sizes match
    if golden.shape != actual.shape:
        print(f"FAIL: Shape mismatch - golden {golden.shape} vs actual {actual.shape}")
        sys.exit(1)
    
    print(f"Output size: {golden.shape[0]} elements")
    
    # Compare
    if DATA_TYPE == "float":
        passed = compare_float(golden, actual)
    else:
        passed = compare_fixed(golden, actual)
    
    sys.exit(0 if passed else 1)

if __name__ == "__main__":
    main()
```

#### MATLAB Version

```matlab
% validate_kernel.m
% Compare AIE x86sim output against golden reference.
%
% Copyright (C) <year>, Advanced Micro Devices, Inc. All rights reserved.
% SPDX-License-Identifier: MIT

%% Configuration
DATA_DIR = 'data';
GOLDEN_FILE = fullfile(DATA_DIR, 'golden_C.txt');
OUTPUT_FILE = 'Work_x86/x86simulator_output/data/output_C.txt';
DATA_TYPE = 'float';  % 'float' or 'int16'
MAX_ABS_ERROR_TOL = 1e-5;
MAX_LSB_TOL = 0;

%% Run x86 simulation
fprintf('Running x86 simulation...\n');
[status, output] = system('make x86sim');
if status ~= 0
    error('x86sim FAILED:\n%s', output);
end
fprintf('x86 simulation completed successfully.\n');

%% Load data
golden = load(GOLDEN_FILE);
actual = load(OUTPUT_FILE);

%% Verify sizes
assert(numel(golden) == numel(actual), ...
    'Size mismatch: golden %d vs actual %d', numel(golden), numel(actual));
fprintf('Output size: %d elements\n', numel(golden));

%% Compare
if strcmp(DATA_TYPE, 'float')
    abs_error = abs(golden - actual);
    max_abs_err = max(abs_error);
    mean_abs_err = mean(abs_error);
    
    fprintf('Max absolute error: %.8e\n', max_abs_err);
    fprintf('Mean absolute error: %.8e\n', mean_abs_err);
    
    if max_abs_err <= MAX_ABS_ERROR_TOL
        fprintf('PASS: Max error %.2e within tolerance %.2e\n', ...
            max_abs_err, MAX_ABS_ERROR_TOL);
    else
        error('FAIL: Max error %.2e exceeds tolerance %.2e', ...
            max_abs_err, MAX_ABS_ERROR_TOL);
    end
else
    error_lsb = int64(golden(:)) - int64(actual(:));
    max_lsb_err = max(abs(error_lsb));
    
    fprintf('Max mismatch: %d LSBs\n', max_lsb_err);
    
    if max_lsb_err <= MAX_LSB_TOL
        if max_lsb_err == 0
            fprintf('PASS: Bit-exact match (0 LSBs)\n');
        else
            fprintf('PASS: %d LSBs within tolerance (%d)\n', ...
                max_lsb_err, MAX_LSB_TOL);
        end
    else
        error('FAIL: %d LSBs exceeds tolerance (%d)', max_lsb_err, MAX_LSB_TOL);
    end
end
```

### Step 4: Generate Complete Validation Flow Script

Create a single script that orchestrates the entire validation:

```bash
#!/bin/bash
# validate.sh - End-to-end validation of AIE kernel against MATLAB golden

set -e

echo "=== Step 1: Generate test data from MATLAB ==="
matlab -batch "run('generate_test_data.m')"

echo "=== Step 2: Run x86 simulation ==="
make x86sim

echo "=== Step 3: Compare outputs ==="
python3 validate_kernel.py  # or: matlab -batch "run('validate_kernel.m')"

echo "=== Validation complete ==="
```

### Step 5: Optional VFS Integration

If the user wants VFS-based verification (bit-accurate C-model without compilation):

**Instruct the agent**: Invoke the `vitis-functional-sim` skill with the generated kernel source files to create a VFS test wrapper. This provides an alternative validation path that doesn't require the full `aiecompiler` + `x86simulator` flow.

---

## Tolerance Guidelines

| Data Type | Comparison Method | Expected Tolerance |
|---|---|---|
| `float` → `float` | Max absolute error | ≤ 1e-5 (single-precision rounding) |
| `float` → `float` (with `aie::inv()`) | Max absolute error | ≤ 1e-4 (reduced precision from `optimize-aie-scalar-divide`) |
| `float` → `int16` | LSB comparison | Design-dependent (quantization noise) |
| `int16` → `int16` | LSB comparison | 0 (should be bit-exact) |
| `bfloat16` → `bfloat16` | Max absolute error | ≤ 1e-2 (reduced precision) |
| `cfloat` → `cfloat` | Max abs error (real + imag) | ≤ 1e-5 per component |
| `cfloat` → `cfloat` (with `aie::inv()`) | Max abs error (real + imag) | ≤ 1e-4 per component |

**Tolerance adjustment for optimization skills**:

When `optimize-aie-scalar-divide` has been applied (replacing `/` with `aie::inv()`),
the kernel uses hardware-accelerated reciprocal with ~20-bit mantissa precision instead
of full IEEE-754 division (~23-bit mantissa). This introduces additional error of ~1e-6
per division operation. For algorithms with multiple chained divisions (e.g., Jacobi SVD
with rotation angle computation), errors accumulate and the tolerance should be relaxed:

| Algorithm Complexity | Recommended Tolerance |
|---|---|
| Single division (normalization) | ≤ 1e-5 |
| Few divisions (Cholesky, simple ratio) | ≤ 1e-4 |
| Many chained divisions (iterative SVD, eigendecomp) | ≤ 1e-3 |

When `optimize-aie-split-accumulator` has been applied, floating-point addition order
changes slightly (partial sums combined differently). This typically introduces no
measurable error for well-conditioned data, but for ill-conditioned matrices the
tolerance may need slight relaxation (~1e-6 additional).

**If comparison fails**:
1. Check data layout (row-major vs column-major mismatch is the #1 failure cause)
2. Check buffer dimension padding (trailing zeros may shift output alignment)
3. Check accumulator shift value for fixed-point (wrong shift = scaled error)
4. Print first few elements of both golden and actual to visually identify the pattern

---

## Output Files

This sub-skill produces:

1. **`generate_test_data.m`** — MATLAB script to produce input/golden data
2. **`data/input_A.txt`**, **`data/input_B.txt`** — Input stimuli files
3. **`data/golden_C.txt`** — MATLAB golden output
4. **`validate_kernel.py`** or **`validate_kernel.m`** — Comparison script
5. **`validate.sh`** — End-to-end orchestration script

---

## Completion

This is the final sub-skill in the workflow. After validation passes, the user has a complete, verified AI Engine kernel ported from their MATLAB reference with:
- Kernel source (vectorized with AIE API iterators and intrinsics)
- Graph and application wrapper
- Build system (Makefile)
- Automated validation against MATLAB golden reference
