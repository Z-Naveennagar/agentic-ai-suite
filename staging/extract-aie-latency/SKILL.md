---
name: extract-aie-latency
description: Provides user a utility to measure AI Engine design simulated latency.
author: Faisal El-Shabani
---

# Extracting AIE Latency Metrics from Simulated Designs

This guide demonstrates how to extract AI Engine latency metrics from AIE simulation results using automated scripts and the Vitis Python API.

## IMPORTANT: Design Must Be Simulated With Profiling First

**This skill requires that the AIE design has already been successfully compiled and simulated WITH PROFILING FLAGS.** The extraction utility reads profiling data from simulation and does not perform simulation itself.

**Before using this skill, verify the design has been simulated with profiling by checking for:**
- `aiesimulator_output/` directory exists in the design directory
- `aiesimulator_output/default.aierun_summary` exists
- `aiesimulator_output/profile_*.txt` or `profile_*.xml` files exist (indicates profiling was enabled)
- `AIESimulator.log` exists (shows "[INFO] : Simulation Finished")

If these files do not exist, or if `profile_*.txt` files are missing, the design must be simulated with profiling flags first following the instructions below.

## Overview

AIE simulation with profiling enabled generates detailed latency measurements showing the time from when data enters the graph to when it exits. Key metrics include:

- **First Latency**: Time for the first output sample
- **Average Latency**: Mean latency across all iterations
- **Last Latency**: Latency for the final iteration (steady-state)

## Prerequisites

### Environment Setup

Before simulating and extracting latency, verify that the Vitis environment is properly configured:

```bash
# Verify vitis and aiesimulator are available
which vitis
which aiesimulator
# Should output: /path/to/Vitis/bin/vitis and /path/to/Vitis/aietools/bin/aiesimulator

# Verify environment variables  
echo $XILINX_VITIS
# Should output: /path/to/Vitis/version
```

If `vitis` or `aiesimulator` is not found after setup, consult your system administrator for Vitis installation paths.

### Profiling Simulation Required

Latency extraction requires running AIE simulation with profiling enabled. Use these flags:

```bash
aiesimulator --profile --online -wdb -text
```

**Flag Descriptions:**
- `--profile`: Enable performance profiling
- `--online`: Real-time profiling data collection
- `-wdb`: Generate waveform database
- `-text`: Generate text-based output files

### Makefile Integration

```makefile
profile:
	@echo "Running AIE simulation with profiling..."
	aiesimulator --profile --online -wdb -text 2>&1 | tee -a log
```

**Note:** Some designs have profiling flags in the default `sim` target. Check your Makefile's `sim` target to see if it already includes `--profile --online -wdb -text`.

## Compilation

Before simulation, the design must be compiled:

```bash
cd <design_directory>
make compile
# Or: v++ -c --mode aie --target hw --part <part_number> graph.cpp -o libadf.a
```

**Key flags:**
- `--mode aie`: AIE-only compilation
- `--target hw`: Hardware target (required for accurate profiling)

## Simulation With Profiling

### Quick Simulation

For small designs (1-4 tiles), standard synchronous simulation with profiling works well:

```bash
cd <design_directory>
make profile
# Or if 'sim' target has profiling flags: make sim
# Or manually: aiesimulator --profile --online -wdb -text --pkg-dir=./Work
```

### Background Simulation with Monitoring

For large multi-tile designs (20+ tiles), simulation with profiling can take 5-30+ minutes. Use background execution with status monitoring:

```bash
# Check for Makefile with profiling target
if [ -f Makefile ] && grep -q "profile" Makefile; then
    # Use Makefile profile target
    make profile > aiesim.log 2>&1 &
elif [ -f Makefile ] && grep -q "\-\-profile" Makefile; then
    # Use sim target if it has profiling flags
    make sim > aiesim.log 2>&1 &
else
    # Use direct command with profiling flags
    aiesimulator --profile --online -wdb -text --pkg-dir=./Work > aiesim.log 2>&1 &
fi

# Monitor for completion (up to 45 minutes for large designs with profiling)
MAX_WAIT=2700  # 45 minutes
ELAPSED=0

while [ ! -f AIESimulator.log ] || ! grep -q "Simulation Finished" AIESimulator.log 2>/dev/null; do
    # Check if aiesimulator process is still running
    if ! pgrep -f "aiesimulator" > /dev/null 2>&1; then
        echo "Simulation process finished at ${ELAPSED}s"
        break
    fi
    
    echo "[$(date +%H:%M:%S)] Simulating with profiling... (${ELAPSED}s elapsed)"
    tail -1 aiesim.log 2>/dev/null || echo "Starting..."
    sleep 10
    ELAPSED=$((ELAPSED + 10))
done

# Check result
if [ -f AIESimulator.log ] && grep -q "Simulation Finished" AIESimulator.log; then
    echo "✓ Simulation successful (took ${ELAPSED} seconds)"
    ls -lh aiesimulator_output/profile_*.txt 2>/dev/null | wc -l
    echo "profile files created"
else
    echo "✗ Simulation failed - check aiesim.log for errors"
    tail -50 aiesim.log
fi
```

**Expected Simulation Times (with profiling):**
- Small designs (1-4 tiles): 1-2 minutes
- Medium designs (8-20 tiles): 2-10 minutes  
- Large designs (40+ tiles): 10-30 minutes

**Note:** Profiling adds overhead to simulation time (typically 1.5-2x slower than non-profiling simulation).

**Verification:**
- **AIESimulator.log exists**: Check for "[INFO] : Simulation Finished"
- **aiesimulator_output/profile_*.txt created**: Profiling artifacts confirm profiling was enabled
- **default.aierun_summary has latency data**: Required for extraction

## Automated Extraction

### Using extract_latency.py

The [extract_latency.py](./utility/extract_aie_latency.py) utility uses the Vitis Python API to extract latency metrics from simulation results.

**Usage:**
```bash
cd <design_directory>
vitis -s <path_to_utility_scripts>/extract_latency.py .
```

**Parameters:**
- `<design_path>`: Path to design directory (use `.` for current directory)

### Agent Guidance: Required Profiling

**When a user requests latency extraction, agents must verify profiling was enabled:**

1. **Check for Profiling Artifacts (REQUIRED):** The utility requires `profile_*.txt` files in `aiesimulator_output/`. If missing, simulation was run without profiling flags.
   - Required files: `aiesimulator_output/profile_*.txt` or `profile_*.xml`
   - Example check: `ls aiesimulator_output/profile_*.txt`

2. **Profiling Status:** If profiling artifacts don't exist, prompt the user to run simulation with profiling flags.
   - Example prompt: *"The design hasn't been simulated with profiling enabled. Latency metrics require profiling. Would you like me to run the simulation with profiling now? (Estimated time: 2-10 minutes for typical designs)"*

3. **Makefile Detection:** Check if Makefile has `profile` target or if `sim` target includes profiling flags (`--profile --online -wdb -text`).
   - If yes: Suggest `make profile` or `make sim`
   - If no: Guide user to run `aiesimulator --profile --online -wdb -text --pkg-dir=./Work`

4. **Time Expectations:** Inform user that profiling simulation takes longer than standard simulation (typically 1.5-2x overhead).

**The utility will provide detailed error messages if profiling wasn't enabled, but agents should proactively check for profiling artifacts before attempting extraction.**

**Examples:**
```bash
cd <your_design_directory>
make profile                    # Run profiling simulation first
vitis -s <path_to_utility_scripts>/extract_latency.py .
```

**Input:** `aiesimulator_output/default.aierun_summary`  
**Output:** `aiesimulator_output/latency_summary.csv`

**CSV Format:**
```csv
"Output Port","Input Port","First Latency (us)","Average Latency (us)","Last Latency (us)"
"PLIO_out","PLIO_in","12.50","12.35","12.30"
```

**Makefile Integration:**
```makefile
extract-latency:
	@echo "Extracting latency metrics..."
	vitis -s <path_to_utility_scripts>/extract_latency.py .
```

## Manual Extraction Methods

### Using Vitis Python API

The Vitis Analyzer provides a Python API to extract latency data programmatically.

**Method:**
```python
import vitis

# Create Vitis client
client = vitis.create_client()

# Load the simulation summary
summary_file = 'aiesimulator_output/default.aierun_summary'
summary = client.get_vitis_analyzer(summary_file)

# Export latency data to CSV
summary.export_aiesim_latency('latency_raw.csv', overwrite=True)

# Close the client
vitis.dispose()

print("Latency data exported to latency_raw.csv")
```

**Run the script:**
```bash
vitis -s extract_latency_custom.py
```

### Processing Raw Latency Data

The exported CSV contains latency for all internal connections. Filter for PLIO ports (top-level I/O):

```python
import csv
import io

with open('latency_raw.csv', 'r') as f:
    content = f.read()
    # Clean header (remove spaces after commas)
    lines = content.split('\n')
    if lines:
        lines[0] = lines[0].replace(', ', ',')
    content = '\n'.join(lines)
    
    reader = csv.DictReader(io.StringIO(content))
    for row in reader:
        output_port = row['Output']
        input_port = row['Input']
        
        # Filter for PLIO ports only
        if 'PLIO' in output_port:
            first_latency_ps = float(row['First Latency (ps)'])
            avg_latency_ps = float(row['Average Latency (ps)'])
            last_latency_ps = float(row['Last Latency (ps)'])
            
            # Convert picoseconds to microseconds
            first_us = first_latency_ps / 1e6
            avg_us = avg_latency_ps / 1e6
            last_us = last_latency_ps / 1e6
            
            print(f"{output_port} <- {input_port}")
            print(f"  First: {first_us:.2f} µs")
            print(f"  Avg:   {avg_us:.2f} µs")
            print(f"  Last:  {last_us:.2f} µs")
```

## Understanding Latency Metrics

### First, Average, and Last Latency

- **First Latency**: Initial output latency (may include pipeline fill time)
- **Average Latency**: Mean across all graph iterations
- **Last Latency**: Steady-state latency (most representative of sustained performance)

**Typical Pattern:**
```
First:   15.50 µs  ← Higher due to pipeline startup
Average: 12.80 µs  ← Average across iterations
Last:    12.30 µs  ← Steady-state (use for performance characterization)
```

### PLIO vs Internal Ports

The raw latency data includes measurements for all internal connections. For system-level characterization:

- **Use PLIO ports**: Top-level input/output interfaces
- **Ignore internal ports**: Intermediate connections between kernels

### Multiple Outputs

Designs with multiple output ports will have separate latency measurements for each path:

```
Output Port: PLIO_out_q  | Input Port: PLIO_in_a  | Last Latency: 11.90 µs
Output Port: PLIO_out_r  | Input Port: PLIO_in_a  | Last Latency: 12.00 µs
```

## Reading Results in MATLAB

Read the extracted latency metrics in MATLAB:

```matlab
% Read latency metrics CSV file
latency_csv = 'aiesimulator_output/latency_summary.csv';

if exist(latency_csv, 'file')
    % Load CSV with preserved variable names (handles spaces in column names)
    warning('off', 'MATLAB:table:ModifiedAndSavedVarnames');
    latency_table = readtable(latency_csv, 'VariableNamingRule', 'preserve');
    warning('on', 'MATLAB:table:ModifiedAndSavedVarnames');
    
    % Display latency table
    fprintf('=== AIE Latency Metrics ===\n\n');
    fprintf('%-40s | %-40s | %-15s\n', 'Output Port', 'Input Port', 'Last Latency (us)');
    fprintf('%s\n', repmat('-', 1, 100));
    
    for i = 1:height(latency_table)
        fprintf('%-40s | %-40s | %15.2f\n', ...
            char(latency_table{i, 'Output Port'}), ...
            char(latency_table{i, 'Input Port'}), ...
            latency_table{i, 'Last Latency (us)'});
    end
else
    error('Latency metrics file not found. Run profiling simulation and extraction script first.');
end
```

**Expected Output:**
```
=== AIE Latency Metrics ===

Output Port                              | Input Port                               | Last Latency (us)
----------------------------------------------------------------------------------------------------
PLIO_out                                 | PLIO_in                                  |           12.30
```

## Troubleshooting

**Problem:** `default.aierun_summary` not found  
**Solution:** Run simulation with profiling flags: `aiesimulator --profile --online -wdb -text`

**Problem:** `profile_*.txt` files not found  
**Solution:** Simulation was run WITHOUT profiling flags. Re-run with: `aiesimulator --profile --online -wdb -text --pkg-dir=./Work`

**Problem:** "WARNING: No PLIO latency metrics found"  
**Solution:** This indicates simulation ran without profiling. Check for `profile_*.txt` files in `aiesimulator_output/`. If missing, re-run simulation with profiling flags.

**Problem:** Vitis command not found  
**Solution:** Source Vitis tools: `source /path/to/Vitis/settings64.sh`

**Problem:** Empty or no PLIO latency entries (but profiling files exist)  
**Solution:** Check that your graph has PLIO connections; internal-only connections won't appear in filtered results

**Problem:** Latency values seem incorrect (too low/high)  
**Solution:** Verify AIE clock frequency setting in compilation flags (e.g., `--aie.pl-freq=625.0` for 625 MHz)

**Problem:** Simulation with profiling takes too long  
**Solution:** Profiling adds 1.5-2x overhead. For large designs, use background execution with monitoring as shown in the Simulation section above.

## Complete Workflow Example

```bash
# 1. Verify environment
which vitis
which aiesimulator
echo $XILINX_VITIS

# 2. Compile the design
cd <your_design_directory>
make compile
# Or: v++ -c --mode aie --target hw --part <part> graph.cpp -o libadf.a

# 3. Run profiling simulation
make profile
# Or if sim has profiling: make sim
# Or manually: aiesimulator --profile --online -wdb -text --pkg-dir=./Work

# 4. Verify profiling completed
ls aiesimulator_output/profile_*.txt
grep "Simulation Finished" AIESimulator.log

# 5. Extract latency metrics
vitis -s <path_to_utility_scripts>/extract_latency.py .

# 6. View results
cat aiesimulator_output/latency_summary.csv

# 7. Analyze in MATLAB (if applicable)
matlab -batch "verify_results('aie')"
```

## Best Practices

1. **Always enable profiling flags** when running simulation for latency extraction
2. **Use Last Latency** for performance characterization (represents steady-state)
3. **Run multiple iterations** (≥4) to get stable Last Latency measurements
4. **Check AIE clock frequency** to ensure latency is calculated with correct timing
5. **Filter for PLIO ports** when reporting system-level latency
6. **Document simulation flags** used when reporting latency metrics
7. **Budget extra time** for profiling simulation (1.5-2x overhead vs. standard simulation)
8. **Use background monitoring** for large designs to avoid blocking workflow

## References

- **Vitis Analyzer Summary**: `aiesimulator_output/default.aierun_summary`
- **Vitis Python API**: Vitis unified IDE documentation
- **AIE Profiling Guide**: UG1076 (AI Engine Tools and Flows User Guide)

---

**Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.**  
**SPDX-License-Identifier: MIT**
