#!/usr/bin/env python3
#
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Author: Faisal El-Shabani
#
# Extract throughput metrics from AIE simulation output files
# Usage: python3 extract_throughput.py <example_dir> <datatype> <plio_width>
#   datatype: float, cfloat, cint16, etc.
#   plio_width: 32, 64, 128 (PLIO width in bits)

import sys
import os
import csv
import re
import glob
from pathlib import Path

def verify_simulation_artifacts(example_dir):
    """
    Verify that all required simulation artifacts exist.
    
    Returns:
        tuple: (success: bool, missing_items: list, base_dir: str)
    """
    # Define paths - handle current directory
    if example_dir == '.':
        base_dir = os.getcwd()
        sim_output_dir = "aiesimulator_output"
        data_dir = "aiesimulator_output/data"
        sim_log = "AIESimulator.log"
    else:
        base_dir = os.path.abspath(example_dir)
        sim_output_dir = f"{example_dir}/aiesimulator_output"
        data_dir = f"{example_dir}/aiesimulator_output/data"
        sim_log = f"{example_dir}/AIESimulator.log"
    
    missing = []
    
    # Check critical directories and files
    if not os.path.exists(sim_output_dir):
        missing.append(f"aiesimulator_output/ directory (expected in {base_dir})")
        # If aiesimulator_output doesn't exist, no point checking subdirectories
        return False, missing, base_dir
    
    if not os.path.exists(data_dir):
        missing.append(f"aiesimulator_output/data/ directory")
    
    # Check for output data files
    if os.path.exists(data_dir):
        txt_files = glob.glob(f"{data_dir}/*.txt")
        if not txt_files:
            missing.append(f"Output data files (*.txt) in aiesimulator_output/data/")
    
    # Check for simulation log (optional but helpful)
    if not os.path.exists(sim_log):
        missing.append(f"AIESimulator.log (optional, indicates simulation was run)")
    
    success = len(missing) == 0
    return success, missing, base_dir


def find_graph_iterations(base_dir):
    """
    Find the graph iteration count by parsing the top-level .cpp file.
    Looks for patterns like: graph.run(N) or mygraph.run(N)
    
    Args:
        base_dir: Path to design directory
        
    Returns:
        int: Number of graph iterations, or None if not found
    """
    # Search for .cpp files in common locations
    cpp_patterns = [
        os.path.join(base_dir, "graph.cpp"),
        os.path.join(base_dir, "main.cpp"),
        os.path.join(base_dir, "*.cpp"),
        os.path.join(base_dir, "../graph.cpp"),
        os.path.join(base_dir, "../main.cpp"),
    ]
    
    cpp_files = []
    for pattern in cpp_patterns:
        matches = glob.glob(pattern)
        cpp_files.extend(matches)
    
    # Remove duplicates
    cpp_files = list(set(cpp_files))
    
    if not cpp_files:
        return None
    
    # Parse each .cpp file looking for .run(N) pattern
    run_pattern = re.compile(r'\.run\s*\(\s*(\d+)\s*\)')
    
    for cpp_file in cpp_files:
        try:
            with open(cpp_file, 'r') as f:
                content = f.read()
                matches = run_pattern.findall(content)
                if matches:
                    # Return the first match (should be the graph.run() call)
                    return int(matches[0])
        except Exception as e:
            continue
    
    return None


def get_samples_per_line(datatype, plio_width):
    """
    Calculate how many samples are represented per line in PLIO output.
    
    Args:
        datatype: Data type (float, cfloat, cint16, etc.)
        plio_width: PLIO width in bits (32, 64, 128)
    
    Returns:
        Number of samples per line
    """
    # Define bit widths for different data types
    datatype_bits = {
        'float': 32,
        'cfloat': 64,  # complex float = 2 x 32-bit
        'int32': 32,
        'cint32': 64,  # complex int32 = 2 x 32-bit
        'int16': 16,
        'cint16': 32,  # complex int16 = 2 x 16-bit
    }
    
    if datatype not in datatype_bits:
        print(f"WARNING: Unknown datatype '{datatype}', assuming 32 bits")
        bits_per_sample = 32
    else:
        bits_per_sample = datatype_bits[datatype]
    
    samples_per_line = plio_width // bits_per_sample
    
    if samples_per_line < 1:
        samples_per_line = 1
        print(f"WARNING: PLIO width ({plio_width}) < sample width ({bits_per_sample}), assuming 1 sample per line")
    
    return samples_per_line

def parse_output_file(filepath, samples_per_line):
    """
    Parse AIE output file to extract TLAST timestamps and sample counts.
    
    Args:
        filepath: Path to output file
        samples_per_line: Number of samples per data line (based on datatype and PLIO width)
    
    Returns:
        dict with keys: 'tlast_timestamps', 'samples_between_tlast', 'first_timestamp', 'total_samples'
    """
    tlast_timestamps = []
    first_timestamp = None
    samples_between = []
    current_samples = 0
    total_samples = 0
    
    with open(filepath, 'r') as f:
        lines = f.readlines()
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Check for data lines (non-timestamp, non-TLAST lines)
        if line and line[0] != 'T' and 'TLAST' not in line:
            # This is a data line, count samples
            current_samples += samples_per_line
            total_samples += samples_per_line
        
        # Check for timestamp lines (format: "T 13678400 ps" or "T 13680 ns")
        elif line and line[0] == 'T':
            tokens = line.split()
            if len(tokens) >= 3:
                time_value = float(tokens[1])
                time_unit = tokens[2]
                
                # Convert to picoseconds
                if time_unit == 'ns':
                    time_ps = time_value * 1000
                elif time_unit == 'ps':
                    time_ps = time_value
                elif time_unit == 'us':
                    time_ps = time_value * 1e6
                else:
                    time_ps = time_value  # Assume ps
                
                # Record first timestamp
                if first_timestamp is None:
                    first_timestamp = time_ps
                
                # Check if next line contains TLAST
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if 'TLAST' in next_line:
                        tlast_timestamps.append(time_ps)
                        if len(tlast_timestamps) > 1:
                            samples_between.append(current_samples)
                        current_samples = 0
        
        i += 1
    
    return {
        'tlast_timestamps': tlast_timestamps,
        'samples_between_tlast': samples_between,
        'first_timestamp': first_timestamp,
        'total_samples': total_samples
    }

def calculate_throughput(parsed_data, graph_iterations):
    """
    Calculate update rate and throughput from parsed data.
    Uses steady-state measurement (last 2 TLASTs) when possible.
    
    Args:
        parsed_data: Dictionary with tlast_timestamps, samples_between_tlast, total_samples
        graph_iterations: Number of graph iterations from graph.run(N)
    
    Returns:
        dict with keys: 'update_rate_khz', 'throughput_msps', 'samples_per_iteration'
    """
def calculate_throughput(parsed_data, graph_iterations):
    """
    Calculate update rate and throughput from parsed data.
    
    Args:
        parsed_data: Dictionary with total_samples, first_timestamp, last_timestamp
        graph_iterations: Number of graph iterations from graph.run(N)
    
    Returns:
        dict with keys: 'update_rate_khz', 'throughput_msps', 'samples_per_iteration'
    """
def calculate_throughput(parsed_data, graph_iterations):
    """
    Calculate update rate and throughput from parsed data.
    Uses steady-state measurement (last 2 TLASTs) when possible.
    
    Args:
        parsed_data: Dictionary with tlast_timestamps, samples_between_tlast, total_samples
        graph_iterations: Number of graph iterations from graph.run(N)
    
    Returns:
        dict with keys: 'update_rate_khz', 'throughput_msps', 'samples_per_iteration'
    """
    tlast_timestamps = parsed_data['tlast_timestamps']
    samples_between = parsed_data['samples_between_tlast']
    total_samples = parsed_data['total_samples']
    
    if not tlast_timestamps or graph_iterations is None or graph_iterations == 0:
        return None
    
    total_tlasts = len(tlast_timestamps)
    
    # Calculate TLASTs per graph iteration
    tlasts_per_iteration = total_tlasts / graph_iterations
    
    # Determine which TLASTs mark actual graph iteration boundaries
    if abs(tlasts_per_iteration - 1.0) < 0.1:
        # Simple case: 1 TLAST per iteration
        # Use last two TLASTs for steady-state measurement
        if len(tlast_timestamps) >= 2:
            time_diff_ps = tlast_timestamps[-1] - tlast_timestamps[-2]
            samples_per_iteration = samples_between[-1] if samples_between else 0
        else:
            return None
            
    elif tlasts_per_iteration > 1:
        # Packet-switched case: Multiple TLASTs per iteration
        # Use every Nth TLAST where N = tlasts_per_iteration
        tlast_stride = int(round(tlasts_per_iteration))
        
        # Get the last two "iteration-ending" TLASTs
        iteration_tlasts = [tlast_timestamps[i] for i in range(len(tlast_timestamps)) if (i + 1) % tlast_stride == 0]
        
        if len(iteration_tlasts) >= 2:
            time_diff_ps = iteration_tlasts[-1] - iteration_tlasts[-2]
            
            # Sum samples between the last two iteration boundaries
            # This is the sum of tlast_stride consecutive sample counts
            last_iter_end_idx = len(samples_between) - 1
            first_iter_end_idx = last_iter_end_idx - tlast_stride
            
            if first_iter_end_idx >= 0:
                samples_per_iteration = sum(samples_between[first_iter_end_idx:last_iter_end_idx])
            else:
                # Fallback: use average
                samples_per_iteration = total_samples / graph_iterations
        else:
            # Not enough iteration-ending TLASTs, use average
            time_diff_ps = (tlast_timestamps[-1] - tlast_timestamps[0]) / (total_tlasts - 1) * tlast_stride
            samples_per_iteration = total_samples / graph_iterations
    else:
        # Unexpected case: fewer TLASTs than iterations
        return None
    
    if time_diff_ps <= 0:
        return None
    
    # Convert to seconds
    time_diff_s = time_diff_ps * 1e-12
    
    # Calculate update rate (iterations per second)
    update_rate_hz = 1.0 / time_diff_s
    update_rate_khz = update_rate_hz / 1e3
    
    # Calculate throughput (samples per second)
    if samples_per_iteration > 0:
        throughput_sps = update_rate_hz * samples_per_iteration
        throughput_msps = throughput_sps / 1e6
    else:
        throughput_msps = 0.0
    
    return {
        'update_rate_khz': update_rate_khz,
        'throughput_msps': throughput_msps,
        'samples_per_iteration': int(samples_per_iteration)
    }

def main():
    # Check command line arguments
    if len(sys.argv) < 2:
        print("ERROR: Please specify design directory")
        print("Usage: python3 extract_aie_throughput.py <design_dir> <datatype> <plio_width>")
        print("")
        print("Arguments:")
        print("  <design_dir>  : Path to design directory (use '.' for current)")
        print("  <datatype>    : Data type (float, cfloat, cint16, cint32, int16, int32)")
        print("  <plio_width>  : PLIO width in bits (typically 64, 128, or 32)")
        print("")
        print("Example:")
        print("  python3 extract_aie_throughput.py . cint16 64")
        sys.exit(1)
    
    example_dir = sys.argv[1]
    
    # Verify simulation artifacts exist
    success, missing_items, base_dir = verify_simulation_artifacts(example_dir)
    
    if not success:
        print("ERROR: AIE simulation has not been run. Missing required files:")
        for item in missing_items:
            print(f"  ✗ {item}")
        print("\n" + "="*70)
        print("REQUIRED ACTION: Run AIE simulation first")
        print("="*70)
        print(f"\nThe design must be simulated before extracting throughput.")
        print(f"\nTo simulate, run from directory: {base_dir}")
        print("")
        print("Option 1 - Use Makefile (if available):")
        print("  make aiesim")
        print("")
        print("Option 2 - Run aiesimulator directly:")
        print("  aiesimulator --pkg-dir=./Work")
        print("")
        print("Expected simulation time:")
        print("  - Small designs (1-4 tiles): 10-60 seconds")
        print("  - Medium designs (8-20 tiles): 1-5 minutes")
        print("  - Large designs (40+ tiles): 5-15 minutes")
        print("")
        print("Simulation completion indicator:")
        print("  - Check AIESimulator.log for '[INFO] : Simulation Finished'")
        print("  - aiesimulator_output/data/ directory contains *.txt files")
        print("")
        print("After simulation completes successfully, re-run this script.")
        print("")
        print("For agents: Prompt user whether to run simulation now.")
        sys.exit(1)
    
    # Check for required datatype parameter
    if len(sys.argv) < 3:
        print("ERROR: Datatype parameter is required but not provided")
        print("")
        print("="*70)
        print("REQUIRED ACTION: Specify the datatype")
        print("="*70)
        print("")
        print("Usage: python3 extract_aie_throughput.py <design_dir> <datatype> <plio_width>")
        print("")
        print("Common datatypes:")
        print("  cint16  - Complex 16-bit integer (most common for DSP)")
        print("  cfloat  - Complex float (64-bit)")
        print("  float   - Single-precision float (32-bit)")
        print("  cint32  - Complex 32-bit integer")
        print("  int16   - 16-bit integer")
        print("  int32   - 32-bit integer")
        print("")
        print("For agents: Prompt user to specify the datatype used in their AIE design.")
        sys.exit(1)
    
    datatype = sys.argv[2]
    
    # Check for PLIO width parameter
    if len(sys.argv) < 4:
        print("ERROR: PLIO width parameter is required but not provided")
        print("")
        print("Usage: python3 extract_aie_throughput.py <design_dir> <datatype> <plio_width>")
        print("")
        print("Common PLIO widths:")
        print("  64  - Most common (default)")
        print("  128 - Wide PLIO")
        print("  32  - Narrow PLIO")
        print("")
        print("For agents: Prompt user to specify PLIO width (default: 64).")
        sys.exit(1)
    
    try:
        plio_width = int(sys.argv[3])
    except ValueError:
        print(f"ERROR: Invalid PLIO width '{sys.argv[3]}' - must be an integer")
        sys.exit(1)
    
    # Calculate samples per line based on datatype and PLIO width
    samples_per_line = get_samples_per_line(datatype, plio_width)
    print(f"Configuration: datatype={datatype}, plio_width={plio_width} bits, samples_per_line={samples_per_line}")
    example_dir = sys.argv[1]
    
    # Find graph iteration count from source code
    graph_iterations = find_graph_iterations(base_dir)
    
    if graph_iterations is None:
        print("\nWARNING: Could not find graph.run(N) in source files")
        print("Searched for .cpp files in: " + base_dir)
        print("Will attempt to extract throughput, but results may be inaccurate for packet-switched designs.")
        print("For agents: Ask user for the number of graph iterations run in simulation.")
        # Set to 1 as fallback to avoid division by zero
        graph_iterations = 1
    else:
        print(f"Found graph iterations: {graph_iterations}")
    
    # Path to aiesimulator output data directory
    # Handle both relative path (when called from utility_scripts) and direct path
    if example_dir == '.':
        data_dir = Path("aiesimulator_output/data")
    else:
        data_dir = Path(f"{example_dir}/aiesimulator_output/data")
        if not data_dir.exists():
            data_dir = Path(f"../{example_dir}/aiesimulator_output/data")
    
    if not data_dir.exists():
        print(f"ERROR: Data directory not found: {data_dir}")
        sys.exit(1)
    
    # Find all .txt files in the data directory
    output_files = sorted(data_dir.glob("*.txt"))
    
    if not output_files:
        print(f"ERROR: No .txt files found in {data_dir}")
        sys.exit(1)
    
    # Process each output file
    results = []
    for output_file in output_files:
        print(f"Processing: {output_file.name}")
        
        parsed_data = parse_output_file(output_file, samples_per_line)
        metrics = calculate_throughput(parsed_data, graph_iterations)
        
        if metrics:
            results.append({
                'Output File': output_file.name,
                'Samples per Iteration': metrics['samples_per_iteration'],
                'Update Rate (KHz)': f"{metrics['update_rate_khz']:.2f}",
                'Throughput (Msps)': f"{metrics['throughput_msps']:.2f}"
            })
            print(f"  Update Rate: {metrics['update_rate_khz']:.2f} KHz")
            print(f"  Throughput: {metrics['throughput_msps']:.2f} Msps")
        else:
            print(f"  WARNING: Could not calculate throughput")
    
    # Write to CSV
    if example_dir == '.':
        csv_file = Path("aiesimulator_output/throughput_summary.csv")
    else:
        csv_file = Path(f"{example_dir}/aiesimulator_output/throughput_summary.csv")
        if not csv_file.parent.exists():
            csv_file = Path(f"../{example_dir}/aiesimulator_output/throughput_summary.csv")
    
    if results:
        with open(csv_file, 'w', newline='') as f:
            fieldnames = ['Output File', 'Samples per Iteration', 'Update Rate (KHz)', 'Throughput (Msps)']
            writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
            writer.writeheader()
            writer.writerows(results)
        
        print(f"\nSUCCESS: Throughput summary written to {csv_file}")
        print(f"  Processed {len(results)} output file(s)")
    else:
        print(f"\nERROR: No valid throughput data to write")
        sys.exit(1)

if __name__ == "__main__":
    main()
