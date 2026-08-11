#!/usr/bin/env python3
#
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Author: Faisal El-Shabani
#
# Extract AIE simulation latency metrics using Vitis Python API
# Usage: vitis -s extract_latency.py <example_path>

import vitis
import sys
import os
import csv
import glob
from pathlib import Path

def verify_profiling_artifacts(example_dir):
    """
    Verify that AIE simulation was run with profiling enabled.
    
    Args:
        example_dir: Path to the design directory
        
    Returns:
        tuple: (success: bool, missing_items: list, base_dir: str)
    """
    missing_items = []
    base_dir = os.path.abspath(example_dir)
    
    # Check for aiesimulator_output directory
    aiesim_output_dir = os.path.join(base_dir, "aiesimulator_output")
    if not os.path.exists(aiesim_output_dir):
        missing_items.append("aiesimulator_output/ directory")
        return False, missing_items, base_dir
    
    # Check for default.aierun_summary
    summary_file = os.path.join(aiesim_output_dir, "default.aierun_summary")
    if not os.path.exists(summary_file):
        missing_items.append("aiesimulator_output/default.aierun_summary")
        return False, missing_items, base_dir
    
    # Check for AIESimulator.log
    log_file = os.path.join(base_dir, "AIESimulator.log")
    if not os.path.exists(log_file):
        missing_items.append("AIESimulator.log")
    
    # Check for profiling artifacts (profile_*.txt or profile_*.xml files)
    profile_files = glob.glob(os.path.join(aiesim_output_dir, "profile_*.txt"))
    profile_files.extend(glob.glob(os.path.join(aiesim_output_dir, "profile_*.xml")))
    
    if len(profile_files) == 0:
        missing_items.append("profile_*.txt or profile_*.xml files (profiling not enabled)")
        return False, missing_items, base_dir
    
    return len(missing_items) == 0, missing_items, base_dir

# Get the example path from command line argument
if len(sys.argv) < 2:
    print("ERROR: Please specify path to example directory")
    print("Usage: vitis -s extract_latency.py <example_path>")
    sys.exit(1)

example_path = sys.argv[1]

# Verify profiling artifacts exist
success, missing_items, base_dir = verify_profiling_artifacts(example_path)

if not success:
    print("ERROR: AIE simulation with profiling has not been run. Missing required files:")
    for item in missing_items:
        print(f"  ✗ {item}")
    print("\n" + "="*70)
    print("REQUIRED ACTION: Run AIE simulation with profiling flags")
    print("="*70)
    print(f"\nThe design must be simulated with profiling enabled before extracting latency.")
    print(f"\nTo simulate with profiling, run from directory: {base_dir}")
    print("")
    print("Option 1 - Use Makefile (if available with profiling target):")
    print("  make profile")
    print("  # Or check if 'sim' target has profiling flags")
    print("  make sim")
    print("")
    print("Option 2 - Run aiesimulator directly with profiling:")
    print("  aiesimulator --profile --online -wdb -text --pkg-dir=./Work")
    print("")
    print("Required profiling flags:")
    print("  --profile  : Enable performance profiling")
    print("  --online   : Real-time profiling data collection")
    print("  -wdb       : Generate waveform database")
    print("  -text      : Generate text-based output files")
    print("")
    print("Expected simulation time with profiling:")
    print("  - Small designs (1-4 tiles): 1-2 minutes")
    print("  - Medium designs (8-20 tiles): 2-10 minutes")
    print("  - Large designs (40+ tiles): 10-30 minutes")
    print("")
    print("Simulation completion indicator:")
    print("  - Check AIESimulator.log for '[INFO] : Simulation Finished'")
    print("  - aiesimulator_output/ contains profile_*.txt files")
    print("")
    print("After simulation completes successfully, re-run this script.")
    print("")
    print("For agents: Prompt user whether to run profiling simulation now.")
    print("  If Makefile has 'profile' or 'sim' target with profiling flags, use it.")
    print("  Otherwise, guide user to run aiesimulator with profiling flags directly.")
    sys.exit(1)

# Get the aierun_summary file path
summary_file = os.path.join(example_path, "aiesimulator_output", "default.aierun_summary")

# Create Vitis client
client = vitis.create_client()

# Initialize vitis_analyzer summary object
try:
    summary = client.get_vitis_analyzer(summary_file)
    
    # Export latency table to temporary CSV file
    import tempfile
    temp_csv = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv')
    temp_csv.close()
    
    summary.export_aiesim_latency(temp_csv.name, overwrite=True)
    
    # Process the CSV to create a summary with key metrics
    summary_csv = os.path.join(example_path, "aiesimulator_output", "latency_summary.csv")
    
    # Read the CSV and filter for PLIO ports
    key_metrics = []
    with open(temp_csv.name, 'r') as f:
        # Read CSV with proper handling of whitespace
        content = f.read()
        # Remove spaces after commas in the header line
        lines = content.split('\n')
        if lines:
            lines[0] = lines[0].replace(', ', ',')
        content = '\n'.join(lines)
        
        # Parse the cleaned CSV
        import io
        reader = csv.DictReader(io.StringIO(content))
        for row in reader:
            output_port = row['Output']
            input_port = row['Input']
            
            # Skip rows with empty or invalid latency values
            try:
                first_latency_ps = float(row['First Latency (ps)'].strip())
                last_latency_ps = float(row['Last Latency (ps)'].strip())
                avg_latency_ps = float(row['Average Latency (ps)'].strip())
            except (ValueError, AttributeError):
                # Skip rows with empty or invalid latency data
                continue
            
            # Only keep PLIO or mat* ports (top-level ports)
            if 'PLIO' in output_port or 'mat' in output_port:
                # Convert ps to microseconds
                first_latency_us = first_latency_ps / 1e6
                avg_latency_us = avg_latency_ps / 1e6
                last_latency_us = last_latency_ps / 1e6
                key_metrics.append({
                    'Output Port': output_port,
                    'Input Port': input_port,
                    'First Latency (us)': f"{first_latency_us:.2f}",
                    'Average Latency (us)': f"{avg_latency_us:.2f}",
                    'Last Latency (us)': f"{last_latency_us:.2f}"
                })
    
    # Write summary CSV
    with open(summary_csv, 'w', newline='') as f:
        if key_metrics:
            fieldnames = ['Output Port', 'Input Port', 'First Latency (us)', 'Average Latency (us)', 'Last Latency (us)']
            writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
            writer.writeheader()
            writer.writerows(key_metrics)
            print(f"SUCCESS: Latency summary written to {summary_csv}")
            print(f"  Found {len(key_metrics)} PLIO latency metrics")
        else:
            # Write empty file with header
            fieldnames = ['Output Port', 'Input Port', 'First Latency (us)', 'Average Latency (us)', 'Last Latency (us)']
            writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
            writer.writeheader()
            print("\nWARNING: No PLIO latency metrics found")
            print("")
            print("This typically means simulation was run WITHOUT profiling flags.")
            print("Re-run simulation with: aiesimulator --profile --online -wdb -text")
            print("")
            print("For agents: The simulation needs to be re-run with profiling enabled.")
            print("  Suggest updating Makefile 'sim' target to include profiling flags.")
    
    # Clean up temporary file
    os.unlink(temp_csv.name)
    
except Exception as e:
    print(f"ERROR: Failed to extract latency: {e}")
    sys.exit(1)
finally:
    # Close the client connection and terminate the vitis server
    vitis.dispose()
