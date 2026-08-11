---
name: vhls-opt
description: "Vitis HLS command execution and code optimization. Use when: (1) running Vitis HLS commands (csim, csynth, cosim, pack, impl) from shorthand like 'run csynth config.cfg workdir', or (2) analyzing HLS C/C++ code for optimization (throughput, latency, II, fmax, resources). Trigger on mentions of 'vhls', 'hls run', 'run csynth/csim/cosim/pack/impl', 'hls optimize', 'baseline', or HLS performance analysis requests."
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
# vhls-opt — Vitis HLS Command Runner & Optimizer

This skill has two modes: **Run** (command execution) and **Opt** (code optimization analysis).

---

## Mode 1: Run — HLS Command Execution

Convert shorthand into Vitis HLS commands and **execute them**.

### Environment Detection

Before the first execution in a conversation, verify the environment is set up:

1. Use the Bash tool to run: `which vitis 2>/dev/null && vitis --version 2>&1 | head -5`
2. If `vitis` is NOT found, ask the user to set up their Vitis environment first (e.g., `source <Vitis_install_path>/settings64.sh`) and retry.
3. If `vitis` IS found, proceed directly.

Cache the result: skip this check on subsequent invocations in the same conversation.

### Shorthand Grammar

```
run <ACTION> <CONFIG_FILE> <WORK_DIR>
```

- `<ACTION>` : `csim | csynth | cosim | pack | impl`
- `<CONFIG_FILE>` : required, must end with `.cfg`
- `<WORK_DIR>` : required
- Both paths are relative to the current working directory unless absolute.

### Command Templates

| Action | Command |
|--------|---------|
| csynth | `v++ -c --mode hls --config <CFG> --work_dir <DIR>` |
| csim   | `vitis-run --mode hls --csim --config <CFG> --work_dir <DIR>` |
| cosim  | `vitis-run --mode hls --cosim --config <CFG> --work_dir <DIR>` |
| pack   | `vitis-run --mode hls --package --config <CFG> --work_dir <DIR>` |
| impl   | `vitis-run --mode hls --impl --config <CFG> --work_dir <DIR>` |

### Execution Rules

1. **All arguments present and validated**:
   - Verify `<CONFIG_FILE>` exists using the Read tool or Bash `test -f`. If missing, stop and tell the user.
   - Verify `<WORK_DIR>` exists (or can be created). If it does not exist, create it with `mkdir -p`.
   - Show the user the exact command that will be executed.
   - Execute it using the Bash tool. For long-running actions (`csynth`, `cosim`, `impl`), set `timeout` to 600000 (10 minutes).
   - After execution, report the result:
     - **Success**: Print "Completed successfully." and show the last 20 lines of output.
     - **Failure**: Print the full stderr/stdout and highlight the error. If a log file exists in `<WORK_DIR>`, read the tail of the log for additional context.
   - For `csynth`: after success, automatically read and display key metrics from `<WORK_DIR>/<component>/syn/report/csynth.rpt` (or the first `csynth.rpt` found under `<WORK_DIR>`) — specifically the Performance Estimates and Utilization Estimates sections.

2. **Missing `<CONFIG_FILE>`**: State it is required, explain that the HLS config file (`.cfg`) contains the component source files, top function, clock period, and device target. Ask the user to provide it.

3. **Missing `<WORK_DIR>` only**: Ask the user for it.

4. **Multiple actions**: The user may chain actions (e.g., `run csim csynth cosim config.cfg workdir`). Execute them sequentially in the given order, stopping on the first failure.

### Post-Run Reporting

After any successful action, check for and report:
- Warnings count from the output
- For `csynth`: latency, II, clock period, and resource utilization from `csynth.rpt`
- For `cosim`: pass/fail status from cosim output
- For `impl`: timing (WNS/TNS) and utilization from implementation reports

---

## Mode 2: Opt — HLS Code Optimization Analysis

Analyze HLS code and provide optimization directions with feasibility assessment. Optimizations are applied **iteratively** — one group at a time — with cosim verification after each round.

### Required Inputs

- Optimization goals (throughput / latency / II / fmax / resources)
- Current constraints (target device / memory / interfaces) or `.cfg` file
- `<CONFIG_FILE>` and `<WORK_DIR>` — needed to run csynth/cosim during iterations
- Code (snippet or file)

If the user provides a `<WORK_DIR>`, automatically read:
- The `.cfg` file for constraints (clock, part, top function)
- Source files referenced in the `.cfg`
- `<WORK_DIR>/<component>/syn/report/csynth.rpt` for current metrics

### Step 0: Baseline (run when user asks for baseline, or before first optimization)

Before any optimization, establish a baseline:

1. Run `csynth` using the command template from Mode 1.
2. Find and read the synthesis report: use Glob `<WORK_DIR>/**/csynth.rpt` to locate it.
3. Extract and display a **Baseline Report** with:
   - Target clock period and estimated clock (fmax)
   - Latency (min/max, in cycles and absolute time)
   - Initiation Interval (II)
   - Resource utilization (BRAM, DSP, FF, LUT) — counts and percentages
   - Any timing or resource warnings
4. Save these numbers internally as the baseline for comparison in later iterations.

If the user asks for "baseline" or "baseline performance", run this step and stop — do not proceed to optimization unless asked.

### Workflow

1. **Restate** goals and constraints.
2. **Retrieve baseline metrics** (run Step 0 if no baseline exists yet).
3. **Analyze** the code for:
   - Correctness risks
   - Performance bottlenecks (loop II, memory bandwidth, dependencies, interfaces)
   - Pragma opportunities (pipeline, dataflow, array_partition, stream, etc.)
4. **Group improvements** into logical categories. Typical groups:
   - **Loop optimization**: pipeline, unroll, loop_flatten, loop_merge
   - **Memory optimization**: array_partition, array_reshape, bind_storage
   - **Dataflow / streaming**: dataflow, stream depth, FIFO sizing
   - **Interface optimization**: m_axi burst, interface pragma, port widths
   - **Algorithmic restructuring**: code refactoring, function inlining, data type changes
   - Groups may vary based on the specific code and goals.
5. **Present all groups** with rationale, expected impact, and trade-offs for each. Ask the user which group to apply first, or recommend a starting order.

### Iterative Optimization Loop

Apply optimizations **one group at a time**. For each iteration:

1. **Apply** the changes for the current group using the Edit tool on the source files.
2. **Run csynth** to get updated metrics.
3. **Run cosim** to verify functional correctness.
4. **Report iteration results**:
   - cosim pass/fail status — if FAIL, immediately revert the changes (using Edit to restore the original code) and report the failure. Do not proceed to the next group.
   - Updated metrics vs. baseline and vs. previous iteration:
     - Latency delta
     - II delta
     - fmax delta
     - Resource utilization delta (BRAM, DSP, FF, LUT)
   - Summary: whether this group improved, regressed, or was neutral for each metric.
5. **Proceed or stop**:
   - If cosim passed and metrics improved, confirm with the user before moving to the next group.
   - If cosim passed but metrics regressed, ask the user whether to keep or revert.
   - If cosim failed, revert and ask the user how to proceed.

Repeat until all groups are applied or the user is satisfied.

### Output Format (per iteration)

```
Iteration N: <Group Name>
─────────────────────────
A) Changes Applied
   - List of edits with rationale

B) csynth Results
   - Latency: <new> (baseline: <old>, delta: <+/->)
   - II:      <new> (baseline: <old>, delta: <+/->)
   - fmax:    <new> (baseline: <old>, delta: <+/->)
   - BRAM:    <new> (baseline: <old>, delta: <+/->)
   - DSP:     <new> (baseline: <old>, delta: <+/->)
   - FF:      <new> (baseline: <old>, delta: <+/->)
   - LUT:     <new> (baseline: <old>, delta: <+/->)

C) cosim Result: PASS / FAIL

D) Recommendation: Keep / Revert / User decision needed
```

### Final Summary

After all iterations, present a cumulative summary:

```
Optimization Summary
════════════════════
Baseline → Final

| Metric  | Baseline | Final  | Delta  |
|---------|----------|--------|--------|
| Latency | ...      | ...    | ...    |
| II      | ...      | ...    | ...    |
| fmax    | ...      | ...    | ...    |
| BRAM    | ...      | ...    | ...    |
| DSP     | ...      | ...    | ...    |
| FF      | ...      | ...    | ...    |
| LUT     | ...      | ...    | ...    |

Groups applied: ...
Groups reverted: ...
cosim: all PASS / N failures
```
