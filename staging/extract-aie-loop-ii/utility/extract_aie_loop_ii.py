#!/usr/bin/env python3
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
"""
extract_aie_loop_ii.py
Extract loop initiation interval (II) metrics from AIE compiler backend logs.

Parses mist1/mist2 output in per-tile .log files under Work/aie/<tile>/<tile>.log
to report:
  - HW do-loop: critical cycle, resource minimum, achieved II, folding
  - Non-leaf loops: selected pipelining solution and cycle count

Usage:
    python3 extract_aie_loop_ii.py <design_path>

Output:
    - Console summary table
    - <design_path>/Work/loop_ii_summary.csv

Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
"""

import os
import re
import csv
import sys
from pathlib import Path


def find_tile_logs(design_path):
    """Find all per-tile compiler logs under Work/aie/."""
    work_aie = Path(design_path) / "Work" / "aie"
    if not work_aie.is_dir():
        return []
    logs = []
    for tile_dir in sorted(work_aie.iterdir()):
        if tile_dir.is_dir():
            log_file = tile_dir / f"{tile_dir.name}.log"
            if log_file.is_file():
                logs.append((tile_dir.name, log_file))
    return logs


def parse_tile_log(log_path):
    """Parse a single tile log file for loop scheduling info."""
    content = log_path.read_text(errors="replace")

    hw_loops = []
    non_leaf_loops = []

    # --- Parse HW do-loops (mist2 section) ---
    # Pattern: HW do-loop #<id> in "<file>", line <line>: (loop #<n>) :
    #          critical cycle of length <N> : ...
    #          minimum length due to resources: <N>
    #          scheduling HW do-loop #<id>
    #          (modulo)    -> # cycles: <N> ...
    #          (resume algo)  -> after folding: <N>  (folded over <M> iterations)
    hw_pattern = re.compile(
        r'HW do-loop #(\d+) in "([^"]+)", line (\d+):.*?'
        r'critical cycle of length (\d+).*?'
        r'minimum length due to resources:\s*(\d+).*?'
        r'scheduling HW do-loop #\1\s*\n'
        r'(?:\(algo[^)]*\)\s*->\s*#\s*cycles:\s*\d+\s*\n)?'
        r'\(modulo\)\s*->\s*#\s*cycles:\s*(\d+).*?\n'
        r'(?:\(resume algo\)\s*->\s*after folding:\s*(\d+)\s*\(folded over (\d+) iterations?\))?',
        re.DOTALL
    )

    for m in hw_pattern.finditer(content):
        loop_id = m.group(1)
        source_file = os.path.basename(m.group(2))
        line_num = m.group(3)
        critical_cycle = int(m.group(4))
        resource_min = int(m.group(5))
        achieved_ii = int(m.group(6))
        after_folding = int(m.group(7)) if m.group(7) else achieved_ii
        fold_iterations = int(m.group(8)) if m.group(8) else 0

        efficiency = critical_cycle / after_folding if after_folding > 0 else 0.0

        hw_loops.append({
            "loop_id": loop_id,
            "source_file": source_file,
            "line": line_num,
            "critical_cycle": critical_cycle,
            "resource_min": resource_min,
            "achieved_ii": achieved_ii,
            "after_folding": after_folding,
            "fold_iterations": fold_iterations,
            "efficiency": efficiency,
        })

    # --- Parse non-leaf loops ---
    # Pattern: Software pipelining non-leaf loop in "<file>", line <line>:
    #          ...
    #          ==> Selected [<N>] (# cycles=<C>, max fi=<F>)
    nl_pattern = re.compile(
        r'Software pipelining non-leaf loop in "([^"]+)", line (\d+):.*?'
        r'==> Selected \[(\d+)\] \(# cycles=(\d+), max fi=(\d+)\)',
        re.DOTALL
    )

    for m in nl_pattern.finditer(content):
        source_file = os.path.basename(m.group(1))
        line_num = m.group(2)
        solution = int(m.group(3))
        cycles = int(m.group(4))
        max_fi = int(m.group(5))

        non_leaf_loops.append({
            "source_file": source_file,
            "line": line_num,
            "solution": solution,
            "cycles": cycles,
            "max_fi": max_fi,
        })

    # --- Parse total kernel cycles from mist1 ---
    total_match = re.search(r'Total number of cycles\s*=\s*(\d+)', content)
    total_cycles = int(total_match.group(1)) if total_match else None

    return hw_loops, non_leaf_loops, total_cycles


def print_summary(tile_name, hw_loops, non_leaf_loops, total_cycles):
    """Print human-readable summary for one tile."""
    # Determine source file from loops
    source_files = set()
    for loop in hw_loops:
        source_files.add(loop["source_file"])
    for loop in non_leaf_loops:
        source_files.add(loop["source_file"])
    src_label = ", ".join(sorted(source_files)) if source_files else "unknown"

    print(f"\nTile {tile_name} ({src_label}):")

    if not hw_loops and not non_leaf_loops:
        print("  No pipelined loops found in this tile.")
        return

    for loop in hw_loops:
        limit_type = "critical-cycle limited" if loop["critical_cycle"] >= loop["resource_min"] else "resource limited"
        print(f"  HW do-loop at line {loop['line']} (inner loop):")
        print(f"    Critical cycle:     {loop['critical_cycle']}")
        print(f"    Resource minimum:   {loop['resource_min']}")
        print(f"    Achieved II:        {loop['achieved_ii']} (modulo)")
        if loop["fold_iterations"] > 0:
            print(f"    After folding:      {loop['after_folding']} (folded over {loop['fold_iterations']} iterations)")
        print(f"    Efficiency:         {loop['efficiency']:.2f} ({limit_type})")
        print()

    for loop in non_leaf_loops:
        solution_names = {
            0: "no folding",
            1: "no folding to next iteration",
            2: "allow postamble",
            3: "no folding to prev iteration",
            4: "unrestricted folding",
        }
        sol_name = solution_names.get(loop["solution"], f"solution {loop['solution']}")
        print(f"  Non-leaf loop at line {loop['line']}:")
        print(f"    Selected solution:  [{loop['solution']}] {sol_name}")
        print(f"    Cycles:             {loop['cycles']} (max fi={loop['max_fi']})")
        print()

    if total_cycles is not None:
        print(f"  Total kernel cycles (mist1): {total_cycles}")


def write_csv(design_path, all_results):
    """Write CSV summary file."""
    csv_path = Path(design_path) / "Work" / "loop_ii_summary.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow([
            "Tile", "Loop Type", "Source File", "Line",
            "Critical Cycle", "Resource Min", "Achieved II",
            "After Folding", "Fold Iterations", "Efficiency"
        ])
        for tile_name, hw_loops, non_leaf_loops, total_cycles in all_results:
            for loop in hw_loops:
                writer.writerow([
                    tile_name, "HW do-loop", loop["source_file"], loop["line"],
                    loop["critical_cycle"], loop["resource_min"],
                    loop["achieved_ii"], loop["after_folding"],
                    loop["fold_iterations"], f"{loop['efficiency']:.2f}"
                ])
            for loop in non_leaf_loops:
                writer.writerow([
                    tile_name, "non-leaf", loop["source_file"], loop["line"],
                    "", "", "", loop["cycles"], loop["max_fi"], ""
                ])

    return csv_path


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 extract_aie_loop_ii.py <design_path>")
        print("  <design_path>: Path to design directory containing Work/ folder")
        sys.exit(1)

    design_path = sys.argv[1]

    if not os.path.isdir(design_path):
        print(f"ERROR: Design path not found: {design_path}")
        sys.exit(1)

    work_dir = os.path.join(design_path, "Work", "aie")
    if not os.path.isdir(work_dir):
        print(f"ERROR: Work/aie/ directory not found in {design_path}")
        print("The design must be compiled with --target=hw first.")
        print("x86sim target does not produce Chess backend scheduling logs.")
        sys.exit(1)

    tile_logs = find_tile_logs(design_path)
    if not tile_logs:
        print(f"ERROR: No tile log files found under {work_dir}/")
        sys.exit(1)

    print("=== AIE Loop II Summary ===")

    all_results = []
    for tile_name, log_path in tile_logs:
        hw_loops, non_leaf_loops, total_cycles = parse_tile_log(log_path)
        if hw_loops or non_leaf_loops:
            all_results.append((tile_name, hw_loops, non_leaf_loops, total_cycles))
            print_summary(tile_name, hw_loops, non_leaf_loops, total_cycles)

    if not all_results:
        print("\nNo pipelined loops found in any tile logs.")
        print("Ensure the design was compiled with --target=hw (not x86sim).")
        sys.exit(1)

    csv_path = write_csv(design_path, all_results)
    print(f"\nCSV written to: {csv_path}")


if __name__ == "__main__":
    main()
