---
name: extract-aie-throughput
description: Provides user a utility to measure AI Engine design simulated throughput.
author: Faisal El-Shabani
---

# Extracting AIE Throughput Metrics from Simulated Designs

This guide demonstrates how to extract AI Engine throughput metrics from AIE simulation results by analyzing timestamped output data with TLAST markers.

## IMPORTANT: Design Must Be Simulated First

**This skill requires that the AIE design has already been successfully compiled and simulated.** The extraction utility reads simulation output files and does not perform simulation itself.

**Before using this skill, verify the design has been simulated by checking for:**
- `aiesimulator_output/` directory exists in the design directory
- `aiesimulator_output/data/` directory exists with `*.txt` output files
- `AIESimulator.log` exists (shows "[INFO] : Simulation Finished")
- `libadf.a` file exists (design must be compiled first)

If these files do not exist, the design must be compiled and simulated first following the instructions below.

## Prerequisites

Before simulating and extracting throughput, verify that the Vitis environment is properly configured:

```bash
# Verify aiesimulator is available
which aiesimulator
# Should output: /path/to/Vitis/aietools/bin/aiesimulator

# Verify environment variables  
echo $XILINX_VITIS
# Should output: /path/to/Vitis/version
```

If `aiesimulator` is not found after setup, consult your system administrator for Vitis installation paths.

## Overview

AIE throughput characterization measures the rate at which the design processes data. Key metrics include:

- **Update Rate (KHz)**: Number of graph iterations per second
- **Throughput (Msps)**: Million samples processed per second
- **Samples per Iteration**: Total samples output in one graph iteration

The extraction utility supports both simple designs (1 TLAST marker per graph iteration) and multi-TLAST designs (multiple TLAST markers per iteration, such as multi-channel channelizers or multi-stream designs). The appropriate calculation method is automatically detected based on the TLAST pattern in the output files.

## Compilation

### Compile for Hardware Target

Throughput extraction requires compilation with hardware target to generate timestamped outputs:

```bash
cd <design_directory>
make compile
# Or: v++ -c --mode aie --target hw --part <part_number> graph.cpp -o libadf.a
```

**Key flags:**
- `--mode aie`: AIE-only compilation
- `--target hw`: Hardware target (generates timestamped output)

## Simulation

### Quick Simulation

For small designs (1-4 tiles), standard synchronous simulation works well:

```bash
cd <design_directory>
make aiesim
# Or: aiesimulator --pkg-dir=./Work
```

### Background Simulation with Monitoring

For large multi-tile designs (20+ tiles), simulation can take 5-15+ minutes. Use background execution with status monitoring:

```bash
# Check for Makefile with aiesimulator target
if [ -f Makefile ] && grep -q "aiesim" Makefile; then
    # Use Makefile target
    make aiesim > aiesim.log 2>&1 &
else
    # Use direct command
    aiesimulator --pkg-dir=./Work > aiesim.log 2>&1 &
fi

# Monitor for completion (up to 30 minutes)
MAX_WAIT=1800  # 30 minutes
ELAPSED=0

while [ ! -f AIESimulator.log ] || ! grep -q "Simulation Finished" AIESimulator.log 2>/dev/null; do
    # Check if aiesimulator process is still running
    if ! pgrep -f "aiesimulator" > /dev/null 2>&1; then
        echo "Simulation process finished at ${ELAPSED}s"
        break
    fi
    
    echo "[$(date +%H:%M:%S)] Simulating... (${ELAPSED}s elapsed)"
    tail -1 aiesim.log 2>/dev/null || echo "Starting..."
    sleep 10
    ELAPSED=$((ELAPSED + 10))
done

# Check result
if [ -f AIESimulator.log ] && grep -q "Simulation Finished" AIESimulator.log; then
    echo "✓ Simulation successful (took ${ELAPSED} seconds)"
    ls -lh aiesimulator_output/data/*.txt | wc -l
    echo "output files created"
else
    echo "✗ Simulation failed - check aiesim.log for errors"
    tail -50 aiesim.log
fi
```

**Expected Simulation Times:**
- Small designs (1-4 tiles): 10-60 seconds
- Medium designs (8-20 tiles): 1-5 minutes  
- Large designs (40+ tiles): 5-15 minutes

**Verification:**
- **AIESimulator.log exists**: Check for "[INFO] : Simulation Finished"
- **aiesimulator_output/data/ created**: Contains *.txt output files
- **Output files have TLAST markers**: Required for throughput calculation

## Automated Extraction

### Using extract_throughput.py

The [extract_throughput.py](./utility/extract_aie_throughput.py) utility analyzes timestamped output data to calculate throughput metrics.

**Usage:**
```bash
python3 <path_to_utility_scripts>/extract_throughput.py <design_path> <datatype> <plio_width>
```

**Parameters:**
- `<design_path>`: Path to design directory (use `.` for current)
- `<datatype>`: Data type used in design (`float`, `cfloat`, `cint16`, etc.) - **REQUIRED**
- `<plio_width>`: PLIO width in bits (typically `64`) - **REQUIRED**

### Agent Guidance: Required Parameters

**When a user requests throughput extraction, agents must prompt for missing parameters:**

1. **Datatype (REQUIRED):** The utility cannot auto-detect datatype from the design. If the user doesn't specify, prompt them to provide the datatype used in their AIE graph.
   - Common options: `cint16` (most DSP designs), `cfloat`, `float`, `cint32`, `int16`, `int32`
   - Example prompt: *"What datatype does your AIE design use? Common options are cint16 (for DSP), cfloat, or float."*

2. **PLIO Width (REQUIRED):** The utility cannot auto-detect PLIO width. If not specified, prompt the user.
   - Most common: `64` bits (use as suggested default)
   - Other options: `128` (wide PLIO), `32` (narrow PLIO)
   - Example prompt: *"What PLIO width does your design use? Typical value is 64 bits."*

3. **Simulation Status:** If simulation artifacts don't exist, prompt the user to run simulation first.
   - Example prompt: *"The design hasn't been simulated yet. Would you like me to run the simulation now? (Estimated time: 1-5 minutes for typical designs)"*

**The utility will provide detailed error messages with these prompts if parameters are missing, but agents should proactively ask for them when extracting throughput.**

**Examples:**
```bash
# For float (32-bit) design with 64-bit PLIO
cd <your_design_directory>
python3 <path_to_utility_scripts>/extract_throughput.py . float 64

# For cfloat (64-bit complex) design with 64-bit PLIO
python3 <path_to_utility_scripts>/extract_throughput.py . cfloat 64

# For cint16 (32-bit complex) design with 64-bit PLIO
python3 <path_to_utility_scripts>/extract_throughput.py . cint16 64
```

**Input:** `aiesimulator_output/data/*.txt` (timestamped PLIO output files)  
**Output:** `aiesimulator_output/throughput_summary.csv`

**CSV Format:**
```csv
"Metric","Value","Unit"
"Update Rate","81.23","KHz"
"Throughput","2.60","Msps"
"Samples per Iteration","32","samples"
```

**Makefile Integration:**
```makefile
# For float-based design
extract-throughput:
	@echo "Extracting throughput metrics..."
	python3 <path_to_utility_scripts>/extract_throughput.py . float 64

# For cfloat-based design
extract-throughput:
	@echo "Extracting throughput metrics..."
	python3 <path_to_utility_scripts>/extract_throughput.py . cfloat 64
```

## Understanding Throughput Calculation

### Datatype Bit Widths

The script automatically maps datatypes to bit widths:

| Datatype | Bits | Description |
|----------|------|-------------|
| `float` | 32 | Single-precision floating-point |
| `cfloat` | 64 | Complex float (2×32 bits) |
| `int32` | 32 | 32-bit integer |
| `cint32` | 64 | Complex 32-bit integer |
| `int16` | 16 | 16-bit integer |
| `cint16` | 32 | Complex 16-bit integer |

### Samples per PLIO Line

```
samples_per_line = plio_width / datatype_bits
```

**Examples:**
- `float` with 64-bit PLIO: 64/32 = 2 samples per line
- `cfloat` with 64-bit PLIO: 64/64 = 1 sample per line
- `cint16` with 64-bit PLIO: 64/32 = 2 samples per line

### Throughput Metrics

**1. Graph Time (ps):**
- Time between last two iteration boundaries (steady-state measurement)
- For simple designs (1 TLAST/iteration): Time between last 2 TLASTs
- For multi-TLAST designs (N TLASTs/iteration): Time between last 2 iteration boundary TLASTs
- Extracted from timestamped output files
- Example: `1644800 ps` between iterations

**2. Update Rate (KHz):**
```
update_rate_hz = 1e12 / graph_time_ps
update_rate_khz = update_rate_hz / 1000
```

**3. Samples per Iteration:**
- Count all data lines (non-timestamp, non-TLAST) between consecutive TLAST markers
- Each data line contains `samples_per_line` samples
- Total samples = data_lines × samples_per_line

**4. Throughput (Msps):**
```
throughput_sps = update_rate_hz × samples_per_iteration
throughput_msps = throughput_sps / 1e6
```

## Manual Extraction Methods

### Using Python Script

```python
import re
import os

def extract_throughput_manual(output_file, datatype, plio_width):
    """Extract throughput from timestamped output file."""
    
    # Datatype bit widths
    datatype_bits = {
        'float': 32, 'cfloat': 64,
        'int32': 32, 'cint32': 64,
        'int16': 16, 'cint16': 32
    }
    
    # Calculate samples per line
    bits = datatype_bits.get(datatype, 32)
    samples_per_line = plio_width // bits
    
    # Read timestamped output
    timestamps = []
    line_counts = []
    current_lines = 0
    
    with open(output_file, 'r') as f:
        for line in f:
            # Match timestamp lines: T(12345678) TLAST(0 or 1) data...
            match = re.match(r'T\((\d+)\)\s+TLAST\((\d)\)', line)
            if match:
                timestamp_ps = int(match.group(1))
                tlast = int(match.group(2))
                current_lines += 1
                
                if tlast == 1:  # End of iteration
                    timestamps.append(timestamp_ps)
                    line_counts.append(current_lines)
                    current_lines = 0
    
    # Use last two iterations for steady-state measurement
    if len(timestamps) >= 2:
        graph_time_ps = timestamps[-1] - timestamps[-2]
        graph_time_us = graph_time_ps / 1e6
        samples_per_iteration = line_counts[-1] * samples_per_line
        
        update_rate_khz = 1000.0 / graph_time_us
        throughput_msps = (samples_per_iteration * update_rate_khz) / 1000.0
        
        print(f"Graph Time: {graph_time_us:.2f} µs")
        print(f"Update Rate: {update_rate_khz:.2f} KHz")
        print(f"Samples/Iteration: {samples_per_iteration}")
        print(f"Throughput: {throughput_msps:.2f} Msps")
        
        return update_rate_khz, throughput_msps, samples_per_iteration
    else:
        print("ERROR: Insufficient TLAST markers found")
        return None, None, None

# Usage
output_file = 'aiesimulator_output/data/output.txt'
update_rate, throughput, samples = extract_throughput_manual(output_file, 'float', 64)
```

### Using Bash/Grep

```bash
# Extract timestamps with TLAST=1 (end of iteration markers)
grep -E 'T\([0-9]+\).*TLAST\(1\)' aiesimulator_output/data/output.txt | \
    sed -E 's/T\(([0-9]+)\).*/\1/' > tlast_timestamps.txt

# Get last two timestamps
timestamps=($(tail -2 tlast_timestamps.txt))
last_ts=${timestamps[1]}
prev_ts=${timestamps[0]}

# Calculate graph time (picoseconds to microseconds)
graph_time_ps=$((last_ts - prev_ts))
graph_time_us=$(echo "scale=2; $graph_time_ps / 1000000" | bc)

# Calculate update rate (KHz)
update_rate=$(echo "scale=2; 1000 / $graph_time_us" | bc)

echo "Graph Time: $graph_time_us µs"
echo "Update Rate: $update_rate KHz"
```

## Multi-Output Designs

For designs with multiple output PLIOs, analyze each output separately:

```bash
# Extract throughput for all output ports
python3 extract_throughput.py . float 64

# The script automatically processes all .txt files in aiesimulator_output/data/
# Each output file will be analyzed and results combined in the summary
```

The automated script handles multiple outputs by finding all `*.txt` files in the data directory and calculating throughput for each output file.

## Reading Results in MATLAB

Read the extracted throughput metrics in MATLAB:

```matlab
% Read throughput metrics CSV file
throughput_csv = 'aiesimulator_output/throughput_summary.csv';

if exist(throughput_csv, 'file')
    % Load CSV with preserved variable names
    warning('off', 'MATLAB:table:ModifiedAndSavedVarnames');
    throughput_table = readtable(throughput_csv, 'VariableNamingRule', 'preserve');
    warning('on', 'MATLAB:table:ModifiedAndSavedVarnames');
    
    % Display throughput metrics
    fprintf('\n=== AIE Performance Metrics ===\n\n');
    fprintf('%-30s: %10s %s\n', 'Metric', 'Value', 'Unit');
    fprintf('%s\n', repmat('-', 1, 50));
    
    for i = 1:height(throughput_table)
        fprintf('%-30s: %10.2f %s\n', ...
            char(throughput_table{i, 'Metric'}), ...
            throughput_table{i, 'Value'}, ...
            char(throughput_table{i, 'Unit'}));
    end
else
    error('Throughput metrics file not found. Run AIE simulation and extraction script first.');
end
```

**Expected Output:**
```
=== AIE Performance Metrics ===

Metric                        :      Value Unit
--------------------------------------------------
Update Rate                   :      81.23 KHz
Throughput                    :       2.60 Msps
Samples per Iteration         :      32.00 samples
```

## Understanding TLAST Markers

### TLAST Signal Purpose

TLAST (Transaction Last) marks the end of a data packet or transaction. Depending on the design architecture, TLAST markers may appear once per graph iteration (simple designs) or multiple times per iteration (packet-switched designs).

### Timestamped Output Format

```
T 3910400 ps
5.610785961e+00 -1.314172626e+00 
T 3912 ns
-2.808101848e-02 -5.683001876e-01 
T 4113600 ps
TLAST                           <- End of packet/iteration marker
0.000000000e+00 5.829967976e+00 
T 10668800 ps
```

**Format details:**
- `T <timestamp> <unit>`: Timestamp line (ps or ns)
- Next line: Data values (format depends on datatype - float, cfloat, etc.)
- `TLAST`: Marks end of packet or iteration (appears on separate line)
- Data continues on next line after TLAST marker

### TLAST Patterns in Different Design Architectures

**Simple Designs (1 TLAST per iteration):**
- Most basic AIE designs output one transaction per graph iteration
- Each graph.run(N) iteration produces exactly 1 TLAST marker
- Example: FIR filters, FFTs outputting single result per iteration
- TLAST ratio = 1.0

**Multi-TLAST Designs (Multiple TLASTs per iteration):**
- Each graph iteration produces multiple output transactions
- Multiple TLAST markers appear per graph.run(1) iteration
- Example: 8-channel channelizer produces 8 TLASTs per graph.run(1) iteration
- TLAST ratio = 8.0 (or other multiples)
- Can occur in: Channelizers, filterbanks, multi-stream processing, designs with multiple independent output streams
- Reasons for multiple TLASTs: Multiple output channels, interleaved data streams, burst transactions, or various architectural choices

### Hybrid Throughput Calculation

The extraction utility automatically detects the TLAST pattern and adapts the calculation method:

**Step 1: Detect TLAST Ratio**
```
tlast_ratio = total_tlasts_in_file / graph_iterations_from_source
```
- `graph_iterations_from_source`: Parsed from graph.run(N) in .cpp files
- `total_tlasts_in_file`: Count of all TLAST markers in output

**Step 2: Apply Appropriate Calculation Method**

**For Simple Designs (ratio ≈ 1.0):**
- Use last 2 TLAST timestamps directly
- Measures steady-state time between last two iterations
- `time_diff_ps = tlast_timestamps[-1] - tlast_timestamps[-2]`

**For Multi-TLAST Designs (ratio > 1):**
- Extract every Nth TLAST where N = int(ratio)
- These mark graph iteration boundaries
- Use last 2 iteration boundaries for steady-state measurement
- Example: ratio=8 → use TLASTs at positions 8, 16, 24, 32...
- `time_diff_ps = iteration_boundary[-1] - iteration_boundary[-2]`

**Why This Matters:**
- Simple approach: Ensures steady-state measurement (avoids startup transients)
- Multi-TLAST approach: Correctly identifies iteration boundaries while maintaining steady-state accuracy
- Automatic detection: No user configuration needed

### Graph Iteration Count

For reliable steady-state throughput measurement:
- **Minimum**: 4 graph iterations
- **Recommended**: 8+ iterations for stable measurements
- **For multi-TLAST designs**: Ensure enough iterations to capture multiple complete TLAST cycles
- Use time between **last two iterations** to avoid startup effects

## Troubleshooting

**Problem:** `output.txt` not found or empty  
**Solution:** Ensure design was compiled with `--target hw` and simulated with `aiesimulator`

**Problem:** No TLAST markers in output  
**Solution:** Verify graph.run() is called with iteration count > 1; check PLIO TLAST configuration

**Problem:** Incorrect throughput calculation  
**Solution:** Verify datatype matches actual design (float vs cfloat); check PLIO width setting

**Problem:** "Insufficient TLAST markers" error  
**Solution:** Increase graph iteration count in graph.cpp (e.g., `graph.run(8)`)

**Problem:** Throughput values seem too low/high  
**Solution:** Check AIE clock frequency in compilation flags; verify samples_per_line calculation

**Problem:** Multiple TLAST markers per iteration (multi-TLAST design)  
**Solution:** The utility automatically detects and handles this pattern. Verify graph.run(N) count in source code matches expected iteration count. For multi-channel or multi-stream designs, multiple TLASTs per iteration is normal and expected.

**Problem:** "Unexpected TLAST ratio" warning or incorrect throughput  
**Solution:** Check that graph.run(N) in source code matches actual simulation; verify all output files have consistent TLAST patterns; for multi-stream designs, ensure TLAST appears at expected transaction boundaries

## Best Practices

1. **Use last two iterations** for steady-state throughput measurement (automatically handled)
2. **Run ≥4 iterations** to ensure stable measurements (avoid startup transients)
3. **Match datatype parameter** to actual design implementation
4. **Verify PLIO width** matches your graph configuration (typically 64 bits)
5. **Check TLAST configuration** in PLIO setup to ensure proper transaction/iteration marking
6. **Document compilation flags** when reporting throughput (especially AIE clock frequency)
7. **For multi-TLAST designs**: The utility automatically detects multiple TLASTs per iteration - no special configuration needed
8. **Verify graph.run(N)**: Ensure source code has correct iteration count for accurate TLAST ratio detection

## Complete Workflow Example

```bash
# 1. Verify environment
which aiesimulator
echo $XILINX_VITIS

# 2. Compile the design (hardware target for timestamped outputs)
cd <your_design_directory>
make compile
# Or: v++ -c --mode aie --target hw --part <part> graph.cpp -o libadf.a

# 3. Run AIE simulation
make aiesim
# Or: aiesimulator --pkg-dir=./Work

# 4. Verify simulation completed
ls aiesimulator_output/data/*.txt
grep "Simulation Finished" AIESimulator.log

# 5. Extract throughput metrics (specify your datatype and PLIO width)
python3 <path_to_utility_scripts>/extract_aie_throughput.py . cint16 64

# 6. View results
cat aiesimulator_output/throughput_summary.csv

# 7. Analyze in MATLAB (if applicable)
matlab -batch "verify_results('aie')"
```

## Datatype Reference

### Common AIE Datatypes

**Real-valued:**
- `float` (32-bit): 2 samples/line @ 64-bit PLIO
- `int32` (32-bit): 2 samples/line @ 64-bit PLIO
- `int16` (16-bit): 4 samples/line @ 64-bit PLIO

**Complex-valued:**
- `cfloat` (64-bit): 1 sample/line @ 64-bit PLIO
- `cint32` (64-bit): 1 sample/line @ 64-bit PLIO
- `cint16` (32-bit): 2 samples/line @ 64-bit PLIO

### Custom PLIO Widths

For non-64-bit PLIO configurations:

```bash
# 128-bit PLIO with float (4 samples/line)
python3 extract_throughput.py . float 128

# 32-bit PLIO with int16 (2 samples/line)
python3 extract_throughput.py . int16 32
```

## References

- **AIE Simulation Output**: `aiesimulator_output/data/output*.txt`
- **TLAST Documentation**: UG1076 (AI Engine Tools and Flows User Guide)
- **PLIO Configuration**: Vitis Libraries DSPLib documentation
- **v++ Compilation**: UG1076 Chapter on AIE Compilation

---

**Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.**  
**SPDX-License-Identifier: MIT**
