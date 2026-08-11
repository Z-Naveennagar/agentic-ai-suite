---
name: extract-aie-resources
description: Provides user a utility to extract AI Engine design resource count.
author: Faisal El-Shabani
---

# Extracting AIE Resource Utilization from Compiled Designs

This guide demonstrates how to extract AI Engine resource metrics from compiled AIE designs using automated scripts and manual inspection.

## IMPORTANT: Design Must Be Compiled First

**This skill requires that the AIE design has already been successfully compiled.** The extraction utility reads compilation artifacts and does not perform compilation itself.

**Before using this skill, verify the design has been compiled by checking for:**
- `libadf.a` file exists in the design directory
- `Work/` directory exists with subdirectories: `aie/`, `reports/`, `temp/`
- `Work/aie/active_cores.json` exists
- `Work/reports/*_mapping_analysis_report.txt` exists

If these files do not exist, the design must be compiled first following the compilation instructions below.

## Prerequisites

Before compiling and extracting resources, verify that the Vitis environment is properly configured:

```bash
# Verify v++ compiler is available
which v++
# Should output: /path/to/Vitis/bin/v++

# Verify environment variables
echo $XILINX_VITIS
# Should output: /path/to/Vitis/version
```

If `v++` is not found after setup, consult your system administrator for Vitis installation paths.

## Overview

After compiling an AIE design with `v++ -c --mode aie`, the compiler generates detailed reports about resource utilization. Key metrics include:

- **Compute Tiles**: Number of AIE tiles performing computation (running kernels)
- **Total AIE Tiles**: All AIE tiles used (compute + memory/buffer tiles)
- **Memory Tiles**: Number of memory tiles used for buffering (AIE-ML/AIE-MLv2 only)
- **I/O Interfaces**: Designs use either PLIOs or GMIOs (not both)
  - **PLIOs** (Programmable Logic I/O): Streaming interfaces for data transfer
  - **GMIOs** (Global Memory I/O): Direct memory access interfaces

## Compilation

### Quick Compilation

For small designs (1-4 tiles), standard synchronous compilation works well:

```bash
cd <design_directory>
make compile
```

### Background Compilation with Monitoring

For large multi-tile designs (20+ tiles), compilation can take 10-30+ minutes. Use background execution with status monitoring:

```bash
# Start compilation in background
make compile &

# Monitor for libadf.a creation OR process completion (up to 30 minutes)
MAX_WAIT=3600  # 60 minutes
ELAPSED=0

while [ ! -f libadf.a ] && [ $ELAPSED -lt $MAX_WAIT ]; do
    # Check if any AIE compilation processes are still running
    if ! pgrep -f "aiecompiler|v\+\+" > /dev/null 2>&1; then
        echo "Compilation processes finished at ${ELAPSED}s"
        break
    fi
    
    echo "[$(date +%H:%M:%S)] Compiling... (${ELAPSED}s elapsed)"
    tail -1 AIECompiler.log 2>/dev/null || echo "Starting..."
    sleep 30
    ELAPSED=$((ELAPSED + 30))
done

# Check result
if [ -f libadf.a ]; then
    echo "✓ Compilation successful (took ${ELAPSED} seconds)"
    ls -lh libadf.a
else
    echo "✗ Compilation failed - check AIECompiler.log for errors"
    tail -50 AIECompiler.log
fi
```

**Expected Compilation Times:**
- Small designs (1-4 tiles): 2-5 minutes
- Medium designs (8-20 tiles): 5-15 minutes
- Large designs (40+ tiles): 15-30 minutes

**Verification:**
- **libadf.a exists**: Compilation produced output archive
- **AIECompiler.log**: Check end of log for success/error messages
- **Work directory created**: Contains aie/, reports/, temp/ subdirectories

## Automated Extraction

### Using extract_aie_resources.py

The [extract_aie_resources.py](./utility/extract_aie_resources.py) utility automates resource extraction from compilation artifacts.

**Usage:**
```bash
cd <design_directory>
python3 <path_to_utility>/extract_aie_resources.py .
```

**Parameters:**
- `<design_path>`: Path to design directory (use `.` for current directory)

**Example:**
```bash
cd <your_design_directory>
make compile                    # Compile the design first
python3 <path_to_utility>/extract_aie_resources.py .
```

**Output:** `Work/aie_resources.csv`

**For AIE designs with PLIOs:**
```csv
Metric,Value
Compute Tiles,1
Total AIE Tiles,2
Input PLIOs,1
Output PLIOs,1
```

**For AIE-ML/AIE-MLv2 designs with PLIOs and memory tiles:**
```csv
Metric,Value
Compute Tiles,48
Total AIE Tiles,48
Memory Tiles,7
Input PLIOs,18
Output PLIOs,20
```

**For AIE-MLv2 designs with GMIOs:**
```csv
Metric,Value
Compute Tiles,1
Total AIE Tiles,2
Input GMIOs,1
Output GMIOs,1
```

**Notes:**
- Memory Tiles are only reported for AIE-ML and AIE-MLv2 designs that use them
- PLIOs and GMIOs are mutually exclusive - designs use one or the other
- Only the I/O interface type actually used by the design is reported (PLIOs or GMIOs, not both)

**Integration with Makefile:**
```makefile
extract-resources:
	python3 <path_to_utility_scripts>/extract_aie_resources.py .
```

## Manual Extraction Methods

### 1. Extract Compute Tiles and Total AIE Tiles

**Source File:** `Work/aie/active_cores.json`

**Method:**
```python
import json

with open('Work/aie/active_cores.json', 'r') as f:
    data = json.load(f)

# Extract compute tiles from ActiveCores field
# This is a list of column indices for tiles running compute kernels
num_compute = len(data.get('ActiveCores', []))

# Extract total tiles from ActiveMemory field
# Each entry is in format "column_row"
tiles = set(data.get('ActiveMemory', []))
num_total_tiles = len(tiles)

print(f"Compute Tiles: {num_compute}")
print(f"Total AIE Tiles: {num_total_tiles}")
```

**Example active_cores.json:**
```json
{
  "ActiveCores": [24],
  "ActiveMemory": ["24_0", "24_1"]
}
```

**Expected Output:**
```
Compute Tiles: 1
Total AIE Tiles: 2
```

**Alternative (bash):**
```bash
# Extract compute tiles count
python3 -c "import json; print(len(json.load(open('Work/aie/active_cores.json'))['ActiveCores']))"

# Extract total tiles count
python3 -c "import json; print(len(set(json.load(open('Work/aie/active_cores.json'))['ActiveMemory'])))"
```

### 2. Extract PLIO Counts

**Source File:** `Work/reports/*_mapping_analysis_report.txt`

**Note:** The report filename includes the graph name (e.g., `farrow_app_mapping_analysis_report.txt`). Use a glob pattern or find the file:

```bash
# Find the mapping report
REPORT=$(ls Work/reports/*_mapping_analysis_report.txt)

# Parse Block Mapping Report section for PLIO entries
grep ':PLIO' "$REPORT" | wc -l
```

**Method:**
```bash
# Count input PLIOs (look for variable names with "_i" pattern)
grep ':PLIO' Work/reports/*_mapping_analysis_report.txt | grep -E '(sig_i|in\[)' | wc -l

# Count output PLIOs (look for variable names with "_o" pattern) 
grep ':PLIO' Work/reports/*_mapping_analysis_report.txt | grep -E '(sig_o|out\[)' | wc -l
```

### 3. Extract GMIO Counts

**Source File:** `Work/reports/*_mapping_analysis_report.txt`

**Note:** GMIOs (Global Memory I/O) provide direct memory access and are an alternative to PLIOs. Designs use either PLIOs or GMIOs, not both.

**Method:**
```bash
# Find the mapping report
REPORT=$(ls Work/reports/*_mapping_analysis_report.txt)

# Parse Block Mapping Report section for GMIO entries
grep ':GMIO' "$REPORT" | wc -l
```

**Categorize by direction:**
```bash
# Count input GMIOs (look for variable names with "_i" or "data_i" pattern)
grep ':GMIO' Work/reports/*_mapping_analysis_report.txt | grep -E '(data_i|_i\[|_in)' | wc -l

# Count output GMIOs (look for variable names with "_o" or "data_o" pattern)
grep ':GMIO' Work/reports/*_mapping_analysis_report.txt | grep -E '(data_o|_o\[|_out)' | wc -l
```

**Example output:**
```
Input GMIOs: 1
Output GMIOs: 1
```

### 4. Extract Memory Tiles

**Source File:** `Work/reports/*_mapping_analysis_report.txt`

**Note:** Memory tiles are only present in AIE-ML and AIE-MLv2 architectures. AIE designs will not have memory tiles.

**Method:**
```bash
# Find the mapping report
REPORT=$(ls Work/reports/*_mapping_analysis_report.txt)

# Count unique memory tiles from Shared Buffer Mapping Report
# Memory tiles are identified as MT(x,y):b where x,y are coordinates
grep -oP 'MT\(\d+,\d+\)' "$REPORT" | sort -u | wc -l
```

**Alternative (Python):**
```python
import re

with open('Work/reports/*_mapping_analysis_report.txt', 'r') as f:
    text = f.read()

# Find Shared Buffer Mapping Report section
buffer_section = text.split('Shared Buffer Mapping Report:')[-1]

# Extract unique memory tile coordinates MT(x,y)
memory_tiles = set()
for match in re.finditer(r'MT\((\d+),(\d+)\):\d+', buffer_section):
    x, y = match.groups()
    memory_tiles.add(f"MT({x},{y})")

print(f"Memory Tiles: {len(memory_tiles)}")
```

**Example Output:**
```
Memory Tiles: 7
```

This indicates 7 unique memory tile locations are used (e.g., MT(26,0), MT(26,1), MT(27,1), etc.)

## Understanding the Metrics

### Compute Tiles vs Total Tiles

- **Compute Tiles (NUM_COMPUTE)**: Tiles running computation kernels
- **Total Tiles (NUM_TOTAL)**: Includes compute + memory/buffer tiles

**Example:**
```
NUM_COMPUTE = 1    ← One kernel instance
NUM_TOTAL = 2      ← One compute tile + one memory tile
```

The difference indicates memory tiles used for buffering/storage.

### Multi-Tile Designs

For multi-tile designs, metrics scale with parallelism:

**Example 1 - Triangular Tiling Pattern:**
```
NUM_COMPUTE = 3    ← 3 compute kernels in triangular pattern
NUM_TOTAL = 6      ← 3 compute + 3 memory tiles
```

**Example 2 - Cascade Architecture:**
```
NUM_COMPUTE = 8    ← 8 cascade kernels
NUM_TOTAL = 17     ← 8 compute + 9 memory tiles
```

## Reading Results in MATLAB

You can read the extracted resource metrics in MATLAB using `readtable`:

```matlab
% Read the resource metrics CSV file
resources_csv = 'Work/aie_resources.csv';

if exist(resources_csv, 'file')
    % Load CSV into table
    resources = readtable(resources_csv);
    
    % Extract individual metrics
    num_compute = resources.Value(strcmp(resources.Metric, 'Compute Tiles'));
    num_total = resources.Value(strcmp(resources.Metric, 'Total AIE Tiles'));
    num_input_plios = resources.Value(strcmp(resources.Metric, 'Input PLIOs'));
    num_output_plios = resources.Value(strcmp(resources.Metric, 'Output PLIOs'));
    
    % Display results
    fprintf('=== AIE Resource Utilization ===\n');
    fprintf('Compute tiles:   %d\n', num_compute);
    fprintf('Total AIE tiles: %d\n', num_total);
    fprintf('Input PLIOs:     %d\n', num_input_plios);
    fprintf('Output PLIOs:    %d\n', num_output_plios);
else
    error('Resource metrics file not found. Run extraction script first.');
end
```

**Expected Output:**
```
=== AIE Resource Utilization ===
Compute tiles:   1
Total AIE tiles: 2
Input PLIOs:     1
Output PLIOs:    1
```

## Troubleshooting

**Problem:** `v++` command not found  
**Solution:** Source Vitis environment setup script or load environment module. Run `which v++` to verify.

**Problem:** Compilation takes too long / appears hung  
**Solution:** Large designs (40+ tiles) can take 15-30 minutes. Use background compilation with monitoring pattern above. Check `AIECompiler.log` for progress.

**Problem:** `*_mapping_analysis_report.txt` not found  
**Solution:** Run `make compile` first to generate compilation reports. The filename includes your graph name.

**Problem:** `active_cores.json` not found  
**Solution:** Ensure compilation completed successfully; check for `libadf.a` and review `AIECompiler.log` for errors.

**Problem:** `libadf.a` not created after compilation  
**Solution:** Compilation failed. Check `AIECompiler.log` for error messages. Common issues:
- Missing dependencies (DSPLIB_ROOT not set)
- Syntax errors in graph code
- Resource constraints (too many tiles requested)

**Problem:** Zero or incorrect PLIO counts  
**Solution:** The utility parses the Block Mapping Report section. Verify PLIOs are defined in your graph and mapped to IO ports.

**Problem:** Utility script fails to find reports  
**Solution:** Ensure you run the script from the design directory with `python3 <path>/extract_aie_resources.py .` (note the `.` for current directory)

## Complete Workflow Example

```bash
# 1. Compile the design
cd <your_design_directory>
make compile

# 2. Extract resources
python3 <path_to_utility_scripts>/extract_aie_resources.py .

# 3. View results
cat Work/aie_resources.csv

# 4. Verify results (if verification script available)
make verify-aie
```

## Architecture Support

This utility supports all AIE architectures:
- **AIE** (Versal AI Core series)
- **AIE-ML** (Versal AI Edge series)
- **AIE-MLv2** (Versal AI Edge Series Gen 2)

Resource extraction works identically across all architectures, though AIE-ML and AIE-MLv2 may have additional memory tile resources not captured by this utility.

## References

- **Compilation Reports**: `Work/reports/*_mapping_analysis_report.txt`
- **Active Cores JSON**: `Work/aie/active_cores.json`
- **Compiler Output**: `libadf.a` (compiled library)
- **Compiler Log**: `AIECompiler.log`
- **AIE Compiler Guide**: UG1076 (AI Engine Tools and Flows User Guide)

---

**Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.**  
**SPDX-License-Identifier: MIT**
