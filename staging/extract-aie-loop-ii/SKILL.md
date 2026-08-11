---
name: extract-aie-loop-ii
description: Extracts AI Engine kernel loop initiation interval (II) metrics from compiler logs. Reports critical cycle (dependency bound), resource-limited minimum, achieved modulo-scheduled II, and folding details for each HW do-loop and software-pipelined non-leaf loop per kernel tile. Use when analyzing kernel scheduling efficiency, identifying II bottlenecks, or comparing achieved vs. theoretical loop performance.
author: Mark Rollins
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
# Extracting AIE Loop Initiation Interval (II) from Compiler Logs

This skill extracts loop scheduling metrics from the AIE compiler backend (mist1/mist2) logs to assess kernel vectorization efficiency.

## IMPORTANT: Design Must Be Compiled First

**This skill requires that the AIE design has already been successfully compiled.** The extraction utility reads per-tile compiler logs from the `Work/` directory and does not perform compilation itself.

**Before using this skill, verify the design has been compiled by checking for:**
- `Work/` directory exists in the design directory
- `Work/aie/` directory contains per-tile subdirectories (e.g., `24_0/`, `25_0/`)
- Per-tile `.log` files exist (e.g., `Work/aie/24_0/24_0.log`)

If these files do not exist, compile the design first:
```bash
make          # or: v++ --compile --config aie.cfg --mode aie --target=hw --part=<part> graph.cpp --include=.
```

## Overview

The AIE compiler backend (Chess/mist2) performs modulo scheduling on innermost loops (HW do-loops) and software pipelining on non-leaf loops. The key metrics extracted are:

### HW Do-Loop Metrics (Innermost Loops)

| Metric | Description | Source Line Pattern |
|--------|-------------|---------------------|
| **Critical Cycle** | Length of the longest dependency chain through the loop body. This is the absolute lower bound on II dictated by data dependencies. | `critical cycle of length <N>` |
| **Resource Minimum** | Minimum II limited by hardware resource conflicts (e.g., only 1 load port per bank). | `minimum length due to resources: <N>` |
| **Achieved II** | The initiation interval achieved by the modulo scheduler. | `(modulo) -> # cycles: <N>` |
| **After Folding** | Final II after instruction folding optimization, with fold factor. | `after folding: <N> (folded over <M> iterations)` |
| **Source Location** | File and line number of the loop in kernel source. | `HW do-loop #<id> in "<file>", line <L>` |

### Non-Leaf Loop Metrics (Outer Loops)

| Metric | Description | Source Line Pattern |
|--------|-------------|---------------------|
| **Selected Solution** | The folding strategy selected (0=no folding, 4=unrestricted). | `==> Selected [<N>] (# cycles=<C>, max fi=<F>)` |
| **Cycles per Solution** | Cycles for each folding strategy attempted. | `scheduling macro #<id> -> # cycles: <N>` |
| **Source Location** | File and line number. | `Software pipelining non-leaf loop in "<file>", line <L>` |

## Efficiency Analysis

### Interpreting Results

- **Achieved II = Critical Cycle**: Optimal — the scheduler matched the theoretical dependency-limited lower bound.
- **Achieved II > Critical Cycle**: The scheduler could not reach the dependency bound due to resource conflicts, register pressure, or scheduling constraints.
- **Achieved II > Resource Minimum**: Indicates the scheduler struggled with the loop structure — consider restructuring the kernel code.
- **Folded over N iterations**: The scheduler overlaps N consecutive iterations to fill pipeline slots. Higher N means better utilization but longer prologue/epilogue.

### Efficiency Ratio

```
Efficiency = Critical Cycle / Achieved II
```

- `1.0` = Perfect scheduling (ideal)
- `0.5` = 2× overhead from scheduling inefficiency
- `< 0.5` = Significant scheduling issues — kernel may need restructuring

## Automated Extraction

### Using extract_aie_loop_ii.py

The [extract_aie_loop_ii.py](./utility/extract_aie_loop_ii.py) utility parses all per-tile compiler logs and produces a summary.

**Usage:**
```bash
python3 <path_to_utility>/extract_aie_loop_ii.py <design_path>
```

**Parameters:**
- `<design_path>`: Path to design directory containing the `Work/` folder (use `.` for current directory)

**Output:** Prints a per-kernel summary table and writes `Work/loop_ii_summary.csv`.

**Example output:**
```
=== AIE Loop II Summary ===

Tile 24_0 (gemm_kernel.cpp):
  HW do-loop at line 50 (inner loop):
    Critical cycle:     4
    Resource minimum:   2
    Achieved II:        4 (modulo)
    After folding:      4 (folded over 3 iterations)
    Efficiency:         1.00 (critical-cycle limited)

  Non-leaf loop at line 38 (middle loop):
    Selected solution:  [4] unrestricted folding
    Cycles:             16 (max fi=2)

  Non-leaf loop at line 35 (outer loop):
    Selected solution:  [4] unrestricted folding
    Cycles:             16 (max fi=2)

Total kernel cycles (mist1): 174
```

**CSV Format:**
```csv
"Tile","Loop Type","Source File","Line","Critical Cycle","Resource Min","Achieved II","After Folding","Fold Iterations","Efficiency"
"24_0","HW do-loop","gemm_kernel.cpp","50","4","2","4","4","3","1.00"
"24_0","non-leaf","gemm_kernel.cpp","38","","","","16","2",""
"24_0","non-leaf","gemm_kernel.cpp","35","","","","16","2",""
```

### Makefile Integration

```makefile
extract-loop-ii:
	@echo "Extracting loop II metrics..."
	python3 <path_to_utility>/extract_aie_loop_ii.py .
```

## Common Patterns and Recommendations

| Symptom | Likely Cause | Recommendation |
|---------|-------------|----------------|
| Achieved II >> Critical Cycle | Register pressure or load/store conflicts | Reduce live variables; restructure to avoid pointer aliasing |
| Resource minimum > Critical cycle | Too many loads/stores per iteration | Increase vector width; batch data accesses |
| No folding achieved | Loop body too complex or trip count too small | Simplify inner loop; ensure `chess_prepare_for_pipelining` is present |
| Multiple "folded negative edges" | Complex cross-iteration dependencies | Acceptable — indicates aggressive overlap scheduling |

## Prerequisites

- Python 3.6+
- Design compiled with `v++ --compile --mode aie` (either `--target=hw` or `--target=x86sim` — but only `hw` target produces mist2 scheduling reports)
- The `--target=hw` compilation is **required** for loop II extraction (x86sim does not invoke the Chess backend)
