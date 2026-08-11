<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Vitis Python API (vitis.analysis) — Embedded/Project-Relevant Commands

This document extracts the commands from the provided **`vitis.analysis`** specification that are relevant to **embedded software development** (performance analysis, simulation KPIs, trace-derived metrics) and **project management** (exporting results to artifacts such as CSV files).

> Scope note: The excerpt only contains Analysis-related APIs (AIE simulation latency/throughput). No explicit build, workspace, repo, CI, or planning APIs were present in the provided text.

## Module: `vitis.analysis`

### Class: `vitis.analysis.AnalysisService(server)`
Client class for the Vitis Analysis service.

| API | Kind | Purpose (embedded/project relevance) | Key inputs | Outputs | Notes/Defaults |
|---|---|---|---|---|---|
| `get_vitis_analyzer(path) -> VitisAnalyzer` | Factory / accessor | Opens an analysis-summary file for post-run performance analysis and reporting | `path`: path to analysis summary file | `VitisAnalyzer` instance | Used to obtain an analyzer object for subsequent exports/queries |

---

### Class: `vitis.analysis.VitisAnalyzer(analysis_service, path)`
Client class for the **Analysis Summary file** API.

## AIE Simulation Metrics (Latency / Throughput)

### Export APIs (project artifact generation)
These commands **write CSV files**, which is typically useful for project management (reporting, regression tracking, CI artifact collection) and embedded performance engineering.

| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Typical embedded use |
|---|---|---|---|---|---|---|
| `export_aiesim_continuous_latency(io_or_kernel_port_dest_name, io_or_kernel_port_input_name, interval, output_csv_file, overwrite=False, is_cycle_interval=True) -> Tuple[bool, str]` | Export / Latency | Exports **continuous latency** values between an output and input I/O pair **or** kernel dest/input port pair to CSV | `io_or_kernel_port_dest_name`: output I/O or hierarchical kernel port (e.g., `g1.g2.k1/out`); `io_or_kernel_port_input_name`: input I/O or hierarchical kernel port (e.g., `g1.g2.k1/in`); `interval`: cycle interval or total intervals; `output_csv_file`: CSV path | `overwrite` (spec text says default False but also states “Default is True” in description — treat as **as-signature**); `is_cycle_interval=True` | `(success: bool, message: str)` | Track per-interval or per-iteration latency drift; generate CSV for dashboards/regressions |
| `export_aiesim_continuous_throughput(io_or_kernel_port_name, interval, output_csv_file, overwrite=False, is_cycle_interval=True, is_equal_time_interval=False, is_graph_iteration=False) -> Tuple[bool, str]` | Export / Throughput | Exports **continuous throughput** for a given I/O or kernel port to CSV | `io_or_kernel_port_name`: I/O or hierarchical kernel port; `interval`: cycle time per interval **or** number of equal-time intervals **or** number of graph iterations; `output_csv_file`: CSV path | `overwrite` (as-signature); `is_cycle_interval=True`; `is_equal_time_interval=False`; `is_graph_iteration=False` | `(success: bool, message: str)` | Throughput trending across time/iterations; compare builds, kernels, or graph configs |
| `export_aiesim_latency(output_csv_file, overwrite=False, is_io=True, is_kernel_ports=True) -> Tuple[bool, str]` | Export / Latency | Exports latency summary table (**First/Last/Average**) to CSV | `output_csv_file`: CSV path | `overwrite=False`; `is_io=True` (include I/O); `is_kernel_ports=True` (include kernel ports) | `(success: bool, message: str)` | Create a single KPI snapshot per run for release notes, PR validation, or nightly benchmarks |
| `export_aiesim_throughput(output_csv_file, overwrite=False, is_io=True, is_kernel_ports=True) -> Tuple[bool, str]` | Export / Throughput | Exports throughput column (**MB/s**) from I/O and ports tables to CSV | `output_csv_file`: CSV path | `overwrite=False`; `is_io=True`; `is_kernel_ports=True` | `(success: bool, message: str)` | Produce standardized throughput report artifacts for CI or performance signoff |

### Query APIs (in-memory data extraction)
These commands populate user-provided lists with tuples, enabling embedded performance automation without writing files.

| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Data shape / Notes |
|---|---|---|---|---|---|---|
| `get_aiesim_continuous_latency(io_or_kernel_port_dest_name, io_or_kernel_port_input_name, interval, latencies, is_cycle_interval=True) -> Tuple[bool, str]` | Query / Latency | Retrieves continuous latency values between an output and input I/O pair (or kernel ports) and fills `latencies` | `io_or_kernel_port_dest_name`: output I/O or hierarchical kernel port; `io_or_kernel_port_input_name`: input I/O or hierarchical kernel port; `interval`: cycle interval or total intervals; `latencies`: list to fill | `is_cycle_interval=True` | `(filled: bool, message: str)` | `latencies` is filled with tuples: `((start_ps, end_ps, latency_ps), ...)` |
| `get_aiesim_continuous_throughput(adf_io_name, interval, throughput, is_cycle_interval=True, is_equal_time_interval=False, is_graph_iteration=False) -> Tuple[bool, str]` | Query / Throughput | Retrieves continuous throughput values for a given ADF I/O and fills `throughput` | `adf_io_name`: I/O as specified in ADF; `interval`: cycle interval or total intervals; `throughput`: list to fill | `is_cycle_interval=True`; `is_equal_time_interval=False`; `is_graph_iteration=False` | `(filled: bool, message: str)` | `throughput` is filled with tuples: `((start_ps, end_ps, mbytes), ...)` |

---

## Practical Notes (from the provided spec)

- **Hierarchical kernel port naming**: for kernel ports, specify the full hierarchical name, e.g. `g1.g2.k1/in` or `g1.g2.k1/out`.
- **Interval interpretation** depends on flags:
  - `is_cycle_interval=True`: `interval` is a cycle count per interval.
  - `is_cycle_interval=False`: `interval` is the total number of intervals.
  - `is_equal_time_interval=True`: `interval` is the number of equal time intervals.
  - `is_graph_iteration=True`: `interval` is the number of graph iterations.
- **Return contract**: All functions return `Tuple[bool, str]` where the boolean indicates success (file written or list filled) and the string carries an error message or informational success message.
- **Exceptions**: The spec notes possible internal errors during gRPC calls.
