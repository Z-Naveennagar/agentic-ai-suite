#!/usr/bin/env python3
#
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Author: Faisal El-Shabani
#
# Extract AIE resource utilization metrics from compilation results
# Usage: python extract_aie_resources.py <example_dir>

import json
import csv
import sys
import os
import re
import glob

def extract_compute_and_total_tiles(active_cores_path):
    """
    Extract number of compute tiles and total tiles from active_cores.json
    
    Returns:
        tuple: (num_compute, num_total)
            num_compute: Number of compute tiles (from ActiveCores field)
            num_total: Total number of AIE tiles (from ActiveMemory field)
    """
    num_compute = 0
    num_total = 0
    
    try:
        with open(active_cores_path, 'r') as f:
            data = json.load(f)
        
        # Extract compute tiles from ActiveCores field
        # Can be either a list of dictionaries or a simple list
        if 'ActiveCores' in data and data['ActiveCores']:
            if isinstance(data['ActiveCores'], list):
                if isinstance(data['ActiveCores'][0], dict):
                    # Format: [{"24_0": "/path/..."}, {"25_0": "/path/..."}]
                    num_compute = len(data['ActiveCores'])
                else:
                    # Format: [24, 25, 26]
                    num_compute = len(data['ActiveCores'])
        
        # Extract total tiles from ActiveMemory field
        # Each entry is in format "column_row"
        if 'ActiveMemory' in data and data['ActiveMemory']:
            unique_tiles = set()
            
            for mem_tile in data['ActiveMemory']:
                # Extract column and row
                parts = mem_tile.split('_')
                if len(parts) == 2:
                    tile_key = f"{parts[0]}_{parts[1]}"
                    unique_tiles.add(tile_key)
            
            num_total = len(unique_tiles)
    except Exception as e:
        print(f"Warning: Could not parse active_cores.json: {e}")
    
    return num_compute, num_total


def extract_plio_counts(mapping_report_path):
    """
    Extract number of input and output PLIOs from *_mapping_analysis_report.txt
    
    Parses the Block Mapping Report section for PLIO entries and categorizes them
    as input or output based on their variable names.
    
    Returns:
        tuple: (num_input_plios, num_output_plios)
    """
    num_input = 0
    num_output = 0
    
    try:
        with open(mapping_report_path, 'r') as f:
            text = f.read()
        
        # Extract the Block Mapping Report section
        # This section lists all blocks including PLIO instances
        block_start = text.find('Block Mapping Report:')
        port_start = text.find('Port Mapping Report:')
        
        if block_start == -1:
            print("Warning: Block Mapping Report section not found")
            return 0, 0
        
        # Extract section between Block Mapping Report and Port Mapping Report
        if port_start != -1:
            block_section = text[block_start:port_start]
        else:
            # If Port Mapping Report not found, take rest of file
            block_section = text[block_start:]
        
        # Parse PLIO entries from Block Mapping Report
        # Format: "i##:PLIO  IO(##)  variable_name  graph_name"
        # Example: "i78:PLIO  IO(30)  sig_i[0]  aie_dut"
        input_plios = set()
        output_plios = set()
        
        for line in block_section.split('\n'):
            # Look for lines with PLIO blocks
            if ':PLIO' not in line:
                continue
            
            # Skip header and separator lines
            if line.strip().startswith('Block:') or '=' in line or '-' * 5 in line:
                continue
            
            # Split line into columns
            parts = line.split()
            if len(parts) < 4:
                continue
            
            # Extract variable name (typically 3rd or 4th column)
            # Format: Block:Function  CR/IO  Schedule  Utilization  VariableName  GraphName
            # Or:     Block:Function  CR/IO  VariableName  GraphName
            variable_name = None
            for i, part in enumerate(parts):
                # Look for typical PLIO variable patterns after IO(##)
                if i > 0 and parts[i-1].startswith('IO(') and parts[i-1].endswith(')'):
                    # Next non-numeric field is likely the variable name
                    # Skip Schedule/Utilization if present (float numbers)
                    for j in range(i, len(parts)):
                        try:
                            float(parts[j])
                            continue
                        except ValueError:
                            variable_name = parts[j]
                            break
                    break
            
            if not variable_name:
                continue
            
            # Categorize based on variable naming patterns
            # Input PLIOs typically contain: _i, _in, input
            # Output PLIOs typically contain: _o, _out, output
            var_lower = variable_name.lower()
            
            # Check for input patterns
            if (var_lower.endswith('_i') or '_i[' in var_lower or 
                var_lower.endswith('_in') or '_in[' in var_lower or
                'input' in var_lower or var_lower.startswith('in_') or
                var_lower.startswith('sig_i') or var_lower.startswith('front_i') or
                var_lower.startswith('back_i')):
                input_plios.add(variable_name)
            # Check for output patterns
            elif (var_lower.endswith('_o') or '_o[' in var_lower or
                  var_lower.endswith('_out') or '_out[' in var_lower or
                  'output' in var_lower or var_lower.startswith('out_') or
                  var_lower.startswith('sig_o') or var_lower.startswith('front_o') or
                  var_lower.startswith('back_o')):
                output_plios.add(variable_name)
            else:
                # Default heuristic: if name ends with 'i' or contains 'in', assume input
                if var_lower.endswith('i') or 'in' in var_lower:
                    input_plios.add(variable_name)
                else:
                    output_plios.add(variable_name)
        
        num_input = len(input_plios)
        num_output = len(output_plios)
        
    except Exception as e:
        print(f"Warning: Could not extract PLIO counts: {e}")
    
    return num_input, num_output


def extract_gmio_counts(mapping_report_path):
    """
    Extract number of input and output GMIOs from *_mapping_analysis_report.txt
    
    Parses the Block Mapping Report section for GMIO entries and categorizes them
    as input or output based on their variable names.
    
    GMIOs (Global Memory I/O) provide direct memory access instead of streaming PLIOs.
    
    Returns:
        tuple: (num_input_gmios, num_output_gmios)
    """
    num_input = 0
    num_output = 0
    
    try:
        with open(mapping_report_path, 'r') as f:
            text = f.read()
        
        # Extract the Block Mapping Report section
        block_start = text.find('Block Mapping Report:')
        port_start = text.find('Port Mapping Report:')
        
        if block_start == -1:
            return 0, 0
        
        # Extract section between Block Mapping Report and Port Mapping Report
        if port_start != -1:
            block_section = text[block_start:port_start]
        else:
            block_section = text[block_start:]
        
        # Parse GMIO entries from Block Mapping Report
        # Format: "i##:GMIO  IO(##)  variable_name  graph_name"
        # Example: "i1:GMIO  IO(17)  data_i  aie_dut"
        input_gmios = set()
        output_gmios = set()
        
        for line in block_section.split('\n'):
            # Look for lines with GMIO blocks
            if ':GMIO' not in line:
                continue
            
            # Skip header and separator lines
            if line.strip().startswith('Block:') or '=' in line or '-' * 5 in line:
                continue
            
            # Split line into columns
            parts = line.split()
            if len(parts) < 3:
                continue
            
            # Extract variable name (typically 3rd or 4th column after IO(##))
            variable_name = None
            for i, part in enumerate(parts):
                # Look for IO(##) pattern, variable name follows
                if part.startswith('IO(') and part.endswith(')'):
                    # Next non-empty field is the variable name
                    if i + 1 < len(parts):
                        variable_name = parts[i + 1]
                    break
            
            if not variable_name:
                continue
            
            # Categorize based on variable naming patterns
            # Input GMIOs typically contain: _i, _in, input, data_i
            # Output GMIOs typically contain: _o, _out, output, data_o
            var_lower = variable_name.lower()
            
            # Check for input patterns
            if (var_lower.endswith('_i') or '_i[' in var_lower or
                var_lower.endswith('_in') or '_in[' in var_lower or
                'input' in var_lower or var_lower.startswith('in_') or
                var_lower.startswith('data_i') or var_lower == 'data_i'):
                input_gmios.add(variable_name)
            # Check for output patterns
            elif (var_lower.endswith('_o') or '_o[' in var_lower or
                  var_lower.endswith('_out') or '_out[' in var_lower or
                  'output' in var_lower or var_lower.startswith('out_') or
                  var_lower.startswith('data_o') or var_lower == 'data_o'):
                output_gmios.add(variable_name)
            else:
                # Default heuristic: if name ends with 'i' or contains 'in', assume input
                if var_lower.endswith('i') or 'in' in var_lower:
                    input_gmios.add(variable_name)
                else:
                    output_gmios.add(variable_name)
        
        num_input = len(input_gmios)
        num_output = len(output_gmios)
        
    except Exception as e:
        print(f"Warning: Could not extract GMIO counts: {e}")
    
    return num_input, num_output


def extract_memory_tiles(mapping_report_path):
    """
    Extract number of memory tiles from *_mapping_analysis_report.txt
    
    Parses the Shared Buffer Mapping Report section for memory tile entries.
    Memory tiles are identified by MT(x,y):b format where x,y are coordinates
    and b is bank number (not relevant for counting unique tiles).
    
    Returns:
        int: Number of unique memory tiles
    """
    num_memory_tiles = 0
    
    try:
        with open(mapping_report_path, 'r') as f:
            text = f.read()
        
        # Extract the Shared Buffer Mapping Report section
        buffer_start = text.find('Shared Buffer Mapping Report:')
        
        if buffer_start == -1:
            # Memory tiles may not be present in all designs
            return 0
        
        # Extract section (take rest of file or until next major section)
        buffer_section = text[buffer_start:]
        
        # Parse memory tile entries
        # Format: "i## MT(x,y):b Addr Size VariableName GraphName"
        # Example: "i62   MT(29,0):0  61440  4096  memTileFrontOut[0]  aie_dut"
        memory_tiles = set()
        
        for line in buffer_section.split('\n'):
            # Look for lines with MT( pattern
            match = re.search(r'MT\((\d+),(\d+)\):\d+', line)
            if match:
                x_coord = match.group(1)
                y_coord = match.group(2)
                # Store unique tile coordinates (ignore bank number)
                tile_id = f"MT({x_coord},{y_coord})"
                memory_tiles.add(tile_id)
        
        num_memory_tiles = len(memory_tiles)
        
    except Exception as e:
        print(f"Warning: Could not extract memory tile count: {e}")
    
    return num_memory_tiles


def verify_compilation_artifacts(example_dir):
    """
    Verify that all required compilation artifacts exist.
    
    Returns:
        tuple: (success: bool, missing_items: list, base_dir: str)
    """
    # Define file paths - handle current directory
    if example_dir == '.':
        base_dir = os.getcwd()
        work_dir = "Work"
        libadf_file = "libadf.a"
        reports_dir = "Work/reports"
        aie_dir = "Work/aie"
        active_cores_file = "Work/aie/active_cores.json"
    else:
        base_dir = os.path.abspath(example_dir)
        work_dir = f"{example_dir}/Work"
        libadf_file = f"{example_dir}/libadf.a"
        reports_dir = f"{example_dir}/Work/reports"
        aie_dir = f"{example_dir}/Work/aie"
        active_cores_file = f"{example_dir}/Work/aie/active_cores.json"
    
    missing = []
    
    # Check critical files and directories
    if not os.path.exists(libadf_file):
        missing.append(f"libadf.a (expected in {base_dir})")
    
    if not os.path.exists(work_dir):
        missing.append(f"Work/ directory (expected in {base_dir})")
        # If Work/ doesn't exist, no point checking subdirectories
        return False, missing, base_dir
    
    if not os.path.exists(aie_dir):
        missing.append(f"Work/aie/ directory")
    
    if not os.path.exists(reports_dir):
        missing.append(f"Work/reports/ directory")
    
    if not os.path.exists(active_cores_file):
        missing.append(f"Work/aie/active_cores.json")
    
    # Check for mapping analysis report
    mapping_report_pattern = f"{reports_dir}/*_mapping_analysis_report.txt"
    mapping_report_matches = glob.glob(mapping_report_pattern)
    if not mapping_report_matches:
        missing.append(f"Work/reports/*_mapping_analysis_report.txt")
    
    success = len(missing) == 0
    return success, missing, base_dir


def main():
    # Get the example directory from command line argument (single_tile or multi_tile)
    if len(sys.argv) < 2:
        print("ERROR: Please specify example directory (single_tile or multi_tile)")
        print("Usage: python extract_aie_resources.py <example_dir>")
        sys.exit(1)
    
    example_dir = sys.argv[1]
    
    # Verify compilation artifacts exist
    success, missing_items, base_dir = verify_compilation_artifacts(example_dir)
    
    if not success:
        print("ERROR: Design has not been compiled. Missing required files:")
        for item in missing_items:
            print(f"  ✗ {item}")
        print("\n" + "="*70)
        print("REQUIRED ACTION: Compile the design first")
        print("="*70)
        print("\nThe design must be compiled before extracting resources.")
        print(f"\nTo compile, run from directory: {base_dir}")
        print("  make compile")
        print("\nFor large designs (20+ tiles), use background compilation:")
        print("  make compile > compile.log 2>&1 &")
        print("\nExpected compilation time:")
        print("  - Small designs (1-4 tiles): 2-5 minutes")
        print("  - Medium designs (8-20 tiles): 5-15 minutes")
        print("  - Large designs (40+ tiles): 15-30 minutes")
        print("\nAfter compilation completes successfully, re-run this script.")
        print("\nFor agents: Prompt user whether to compile the design now.")
        sys.exit(1)
    
    # Define file paths - handle current directory
    if example_dir == '.':
        reports_dir = "Work/reports"
        active_cores_file = "Work/aie/active_cores.json"
        output_csv = "Work/aie_resources.csv"
    else:
        reports_dir = f"{example_dir}/Work/reports"
        active_cores_file = f"{example_dir}/Work/aie/active_cores.json"
        output_csv = f"{example_dir}/Work/aie_resources.csv"
    
    # Search for mapping analysis report (graph name may vary)
    mapping_report_pattern = f"{reports_dir}/*_mapping_analysis_report.txt"
    mapping_report_matches = glob.glob(mapping_report_pattern)
    
    if len(mapping_report_matches) > 1:
        print(f"WARNING: Multiple mapping reports found: {mapping_report_matches}")
        print(f"Using first match: {mapping_report_matches[0]}")
    
    mapping_report = mapping_report_matches[0]
    
    # Extract resource metrics
    num_compute, num_total = extract_compute_and_total_tiles(active_cores_file)
    num_input_plios, num_output_plios = extract_plio_counts(mapping_report)
    num_input_gmios, num_output_gmios = extract_gmio_counts(mapping_report)
    num_memory_tiles = extract_memory_tiles(mapping_report)
    
    # Write results to CSV
    # Note: Only report I/O interfaces that are actually used (PLIOs or GMIOs)
    # Note: Memory Tiles are only reported for AIE-ML and AIE-MLv2 designs
    try:
        with open(output_csv, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Metric', 'Value'])
            writer.writerow(['Compute Tiles', num_compute])
            writer.writerow(['Total AIE Tiles', num_total])
            
            # Only report Memory Tiles if they exist (AIE-ML/AIE-MLv2 only)
            if num_memory_tiles > 0:
                writer.writerow(['Memory Tiles', num_memory_tiles])
            
            # Report PLIOs only if the design uses them
            if num_input_plios > 0 or num_output_plios > 0:
                writer.writerow(['Input PLIOs', num_input_plios])
                writer.writerow(['Output PLIOs', num_output_plios])
            
            # Report GMIOs only if the design uses them
            if num_input_gmios > 0 or num_output_gmios > 0:
                writer.writerow(['Input GMIOs', num_input_gmios])
                writer.writerow(['Output GMIOs', num_output_gmios])
        
        print(f"SUCCESS: AIE resource metrics written to {output_csv}")
        print(f"  Compute tiles: {num_compute}")
        print(f"  Total AIE tiles: {num_total}")
        
        # Only report memory tiles if present
        if num_memory_tiles > 0:
            print(f"  Memory tiles: {num_memory_tiles}")
        
        # Only report PLIOs if present
        if num_input_plios > 0 or num_output_plios > 0:
            print(f"  Input PLIOs: {num_input_plios}")
            print(f"  Output PLIOs: {num_output_plios}")
        
        # Only report GMIOs if present
        if num_input_gmios > 0 or num_output_gmios > 0:
            print(f"  Input GMIOs: {num_input_gmios}")
            print(f"  Output GMIOs: {num_output_gmios}")
    except Exception as e:
        print(f"ERROR: Failed to write CSV file: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
