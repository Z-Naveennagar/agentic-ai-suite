<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# /hls-optimize — Iterative Pragma & Structural Tuning

Iteratively modify a Vitis HLS kernel to meet an optimization criterion — minimize latency, reduce DSP/LUT, maximize throughput (minimize II) — applying and measuring one change at a time so cause and effect stay clean.

| Field | Value |
|-------|-------|
| **Argument hint** | `<optimization-criteria>` |
| **Bundle path** | `vitis-hls-ai-assistant-skills/hls-optimize/SKILL.md` |

## Example Criteria

```
/hls-optimize minimize latency
/hls-optimize minimize DSP usage while meeting timing
/hls-optimize maximize throughput (minimize II)
/hls-optimize reduce LUT count below 5000
/hls-optimize Reduce true-latency by 2x while using no more than 1.5x the resources
```

## Five Principles

| Principle | Meaning |
|-----------|---------|
| **One idea at a time** | Each attempt changes exactly one thing — one pragma, one transformation, one loop restructure. Never combine independent changes. |
| **Investigate before moving on** | Read the schedule, loop detail, II achieved vs target, warnings in synth log. Understand *why* a metric moved. |
| **Use all available tools** | BC file, QoR JSON, inferred directives, schedule. Verify the change had the expected effect in IR/schedule, not just the report. |
| **Experimental changes are valid** | A change that tests a hypothesis is worth running even if you don't expect a metric win. Document expectation vs reality. |
| **csim+csynth is the inner loop** | Only run cosim when csynth shows >= 10% cycle change or a structural change (II reduction). Only run impl when cosim confirms. |

## Six-Step Process

1. **Init component + git** — Configure git, tag a `baseline` commit. Never improvise this — always invoke the reference doc.
2. **Establish baseline** — Run csim + csynth, capture latency, II, resources, schedule. Saved as iteration 0 in `perf_outcomes.md`.
3. **Identify dominant bottleneck** — Choose from:
    - Memory port contention → `ARRAY_PARTITION` / `BIND_STORAGE`
    - Carried dependence → `DEPENDENCE` overrides / restructuring
    - Resource over budget → `ALLOCATION`, sharing, precision change
    - Bandwidth-limited interface → `INTERFACE` mode change or finer `DATAFLOW` decomposition
4. **Apply one change** — Commit, re-synthesize, compare against baseline + previous iteration
5. **Decide** — Target met → escalate to cosim → impl. Improved → continue. Regressed → revert. Requires algorithmic change → escalate to user.
6. **Record** — Each iteration logged in `perf_outcomes.md` (change, expected effect, actual effect, decision)

## Guardrails

- Always shows a diff before applying a pragma or `hls_config.cfg` change
- Will not modify functional C code without explicit user authorization
- Logs every iteration so any prior state can be restored from git
- Will not run cosim / impl prematurely

## Outputs

- Final pragma / `hls_config.cfg` diff vs architect baseline
- `perf_outcomes.md` iteration log
- Final summary: latency, II, resources, post-route timing (if impl ran)

## Example

```
cd examples/globaltonemapping
/hls-optimize xf_gtm_accel.cpp Reduce true-latency by 2x while using no more than 1.5x the resources
```

<p class="sphinxhide" align="center"><sub>Copyright © 2026 Advanced Micro Devices, Inc</sub></p>
<p class="sphinxhide" align="center"><sup><a href="https://www.amd.com/en/corporate/copyright">Terms and Conditions</a></sup></p>
