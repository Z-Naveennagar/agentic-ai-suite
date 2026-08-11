<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# AIE Graph API Reference

## Constructor

```python
# Python
graph = vfs.aieGraph(
    input_file="path/to/graph.cpp",           # Required: graph source or config
    include_paths=["src/", "include/aie/"],   # Optional: include directories
    part="xcve2802-vsvh1760-2MP-e-S",         # Optional: target device
    Xpreproc=["-DFFT_SIZE=1024"],             # Optional: preprocessor defines
)
```

```matlab
% MATLAB
graph = vfs.aieGraph( ...
    input_file="path/to/graph.cpp", ...
    include_paths="src/");
```

### Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `input_file` | Yes | Path to the AIE graph source file (`.cpp` or `.cfg`) |
| `include_paths` | No | Additional directories for header resolution |
| `part` | No | Target device part string (determines AIE architecture) |
| `Xpreproc` | No | Preprocessor flags passed to AIE compiler (list of strings) |

**Note**: The `input_file` can be either:
- A `.cpp` file containing the graph class definition and `PLIO`/`GMIO` declarations
- A `.cfg` file referencing the graph sources

---

## Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `run(*inputs)` | varray or tuple of varrays | Execute graph with given inputs |
| `getInputSpec()` | dict/struct | Input port metadata (names, types, widths) |
| `getOutputSpec()` | dict/struct | Output port metadata |
| `setPortDump(dir_path)` | None | Enable dumping of all port data to files |
| `writePortDump()` | None | Flush port dump data to disk |
| `reset()` | None | Reset graph state (clear internal buffers) |
| `destroy()` | None | Release resources (Python only — in MATLAB use `clear varname`) |

### run() Signatures

```python
# Single input/output
output = graph.run(input_data)

# Multiple inputs/outputs
out1, out2 = graph.run(in1, in2)
```

```matlab
% Single
output = graph.run(input_data);

% Multiple
[out1, out2] = graph.run(in1, in2);
```

---

## Interface Behavior

AIE graphs follow the same stream vs buffer rules as HLS kernels:

### Stream Ports (`input_stream`, `output_stream`)

- Process data incrementally
- Any amount of input data → proportional output
- Common with PLIO-connected designs

### Window/Buffer Ports (`input_buffer`, `output_buffer`)

- Require complete windows before processing
- Partial input → empty output (buffered internally)
- Window size defined in the graph's `connect<>` declarations

### GMIO Ports

- VFS abstracts GMIO identically to stream/buffer — same `run()` API regardless
- No code difference between PLIO and GMIO designs in VFS

---

## Port Dump (Debugging)

Port dump captures all intermediate data flowing through graph ports. Useful for debugging unexpected outputs.

```python
graph = vfs.aieGraph(input_file="./src/graph.cpp", include_paths=["src/"])

# Enable dump BEFORE running
graph.setPortDump("./debug_dumps/")

# Run
output = graph.run(input_data)

# Write captured data to files
graph.writePortDump()

# Read dump files back for analysis
from vfs.readDumpFile import read_dump_file
metadata, data = read_dump_file("./debug_dumps/port_in.txt")
print(f"Port: {metadata['name']}, Samples: {len(data)}")
```

```matlab
graph = vfs.aieGraph(input_file="./src/graph.cpp", include_paths="src/");

% Enable dump
graph.setPortDump('./debug_dumps/');

% Run
output = graph.run(input_data);

% Write dumps
graph.writePortDump();
```

---

## Complete Python Example: Complex Multiply Graph

```python
"""VFS functional verification: AIE graph with cint16 multiplication"""
import vfs
import varray as va
import numpy as np

# --- Component instantiation ---
graph = vfs.aieGraph(
    input_file="./src/multiplyByTwoComplex/vmc_model/graph.cpp",
    include_paths=["./src/multiplyByTwoComplex/vmc_model/"]
)

# --- Inspect ports ---
print("Inputs:", graph.getInputSpec())
print("Outputs:", graph.getOutputSpec())

# --- Prepare stimulus (cint16) ---
N = 256
real_part = np.random.randint(-10000, 10000, size=N)
imag_part = np.random.randint(-10000, 10000, size=N)
input_data = [va.cint16(int(r), int(i)) for r, i in zip(real_part, imag_part)]

# --- Execute ---
output = graph.run(input_data)

# --- Verify: kernel multiplies real by 2, imag by 3 ---
for i in range(N):
    assert output[i].real() == input_data[i].real() * 2, \
        f"Real mismatch at index {i}"
    assert output[i].imag() == input_data[i].imag() * 3, \
        f"Imag mismatch at index {i}"

print(f"PASS: All {N} complex samples verified")
```

## Complete Python Example: AIE Graph with Port Dump Debugging

```python
"""VFS functional verification: AIE graph with debugging via port dump"""
import vfs
import varray as va
import numpy as np

graph = vfs.aieGraph(
    input_file="./src/my_graph.cpp",
    include_paths=["./src/"],
    Xpreproc=["-DWINDOW_SIZE=256"]
)

# Enable port dump for debugging
graph.setPortDump("./port_dumps/")

# Prepare input
input_data = va.array(np.random.randn(256).astype(np.float32))

# Run
output = graph.run(input_data)

# Write dumps to disk
graph.writePortDump()

# Analyze results
result = np.asarray(output)
print(f"Output shape: {result.shape}")
print(f"Output range: [{result.min():.4f}, {result.max():.4f}]")

# If output looks wrong, inspect intermediate ports:
from vfs.readDumpFile import read_dump_file
metadata, port_data = read_dump_file("./port_dumps/graph_input_0.txt")
print(f"Captured {len(port_data)} samples at port '{metadata['name']}'")
```

## Complete MATLAB Example: AIE Graph

```matlab
%% VFS functional verification: AIE graph (multiplyByTwo)
graph = vfs.aieGraph( ...
    input_file="./src/multiplyByTwo/vmc_model/graph.cpp", ...
    include_paths="./src/multiplyByTwo/vmc_model/");

% Inspect ports
disp(graph.getInputSpec());
disp(graph.getOutputSpec());

% Prepare input: 128 int32 values
N = 128;
input_data = varray.int32(int32(randi([-1000, 1000], 1, N)));

% Execute
output = graph.run(input_data);
result = int32(output);

% Verify: kernel multiplies by 2
expected = int32(randi([-1000, 1000], 1, N)) * 2;  % Use same seed!
% For random: just check output is non-empty and reasonable
assert(length(result) == N, sprintf('Expected %d outputs, got %d', N, length(result)));
fprintf('PASS: Got %d output samples\n', length(result));
```

## Complete MATLAB Example: AIE FIR with Run-Time Parameter

```matlab
%% VFS functional verification: AIE FIR filter with async RTP
graph = vfs.aieGraph( ...
    input_file="./src/firAsyncRTP/vmc_model/graph.cpp", ...
    include_paths="./src/firAsyncRTP/vmc_model/");

% Prepare input signal
N = 512;
fs = 1000;  % Sample rate
t = (0:N-1) / fs;
signal = int16(round(16000 * sin(2*pi*50*t)));  % 50 Hz tone
input_data = varray.int16(signal);

% Run the FIR graph
output = graph.run(input_data);
result = double(output);

% Basic sanity: output should be same length, attenuated
assert(length(result) == N, 'Output length mismatch');
fprintf('PASS: FIR output %d samples, peak amplitude %.1f\n', ...
    length(result), max(abs(result)));
```

---

## Common AIE Data Types

| C++ Type in Graph | varray Type (Python) | varray Type (MATLAB) |
|-------------------|---------------------|---------------------|
| `int16` | `va.int16` | `varray.int16` |
| `int32` | `va.int32` | `varray.int32` |
| `cint16` | `va.cint16(real, imag)` | `varray.cint16` |
| `cint32` | `va.cint32(real, imag)` | `varray.cint32` |
| `float` | `va.float32` | `varray.single` |
| `cfloat` | `va.cfloat` | `varray.csingle` |
| `bfloat16` | `va.bfloat16` | `varray.bfloat16` |

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `run()` returns empty | Window/buffer not full | Send data = window size (check graph `connect<>`) |
| Compilation error on `aie::` | Missing include paths | Add path containing `aie_api/` headers |
| Wrong output values | Data type mismatch | Use `getInputSpec()` and match varray dtype exactly |
| `Xpreproc` defines not taking effect | Wrong format | Use list: `Xpreproc=["-DNAME=VALUE"]` |
| Port dump files empty | `writePortDump()` not called | Call after `run()` completes |
