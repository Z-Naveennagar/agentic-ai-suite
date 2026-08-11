<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
# hls-intro-matmul_gen — hls-architect skill evaluation (C++ → HLS acceleration)

Take a naive triple-nested float matrix-multiply kernel and accelerate it into
an optimized HLS design that reaches **≥ 8× the baseline C-synthesis
throughput** (top-function Interval/II reduced ≥ 8×) while staying functionally
correct against a frozen self-checking testbench.

Sourced from `examples/hls-intro-matmul/`. Self-contained C++ — **no MATLAB,
no OpenCV**; only Vitis HLS is required.

| | |
|---|---|
| **Skill under test** | `hls-architect` |
| **Downstream skills used** | `hls-optimize`, `hls-run-flow` |
| **Goal** | ≥ 8× baseline **throughput**  |

---

## Run configuration & host requirements

| Setting | Value |
|---|---|
| 
| Max tokens per run | 500000 |
| Vitis (HLS / `v++`) | **required** (C synthesis) |
| Memory / disk | ≥ 5 GB / ≥ 5 GB |
| Est. duration | ~30 min |



---



## Input files

Staged into the agent's workspace (flat at the workspace root, beside the
agent's `outputs/` directory):

| File | Role |
|---|---|
| `kernel.cpp` | baseline kernel — naive triple-nested `C = A × B` (float) |
| `kernel.hpp` | `extern "C" kernel(float C[], const float A[], const float B[], int M, int N, int K)` signature, `MAX_SIZE=4096` |
| `main.cpp` | **frozen testbench / oracle** — random matrices (seed 42), ULP-compares (≤ 8 ULP) against a reference matmul, prints `PASS` / `FAIL` |

The kernel signature in `kernel.hpp` is fixed; the final kernel must keep it so
the frozen testbench can call it directly.

---

## Prompt to Agent

> `kernel.cpp` is a baseline float matrix-multiply kernel (C = A × B); its
> signature is in `kernel.hpp` and `main.cpp` is a self-checking testbench
> (prints PASS/FAIL).
>
> Accelerate this kernel on an FPGA to at least **8× higher C-synthesis
> throughput** than the baseline — i.e. reduce the top function's **Interval
> (II)** by ≥ 8× (throughput = 1 / Interval) — while `main.cpp` still prints
> PASS. Targets: part `xczu9eg-ffvb1156-2-e`, clock 3.3 ns, matrix 64×64×64.
>
> Non-interactive run: never wait for confirmation; use any auto-confirm option
> and sensible defaults.
>
> Then report the baseline vs optimized Interval (II), the throughput speedup,
> and how correctness was confirmed.

The request is deliberately phrased as a plain engineering task — it names no
skill, tier, or internal tool. The agent is expected to discover and apply the
right skills on its own.

---

## Verification Steps

The case exercises a full C++→HLS acceleration workflow and judges **each
stage's own job**, not just the final speed:
1. **Correctness** — Compile `kernel_final.cpp` against the frozen `main.cpp` 
   and run it at 64×64×64. It builds its own golden reference, so a plain 
   `PASS` (no `FAIL`) means the kernel is functionally correct. Double-check 
   the pinned `csim.log` also shows `PASS`.

2. **Architecture stage holds up too** — `architect_kernel_hls.cpp` should 
   pass that same golden check on its own. It should just be a clean 
   load → compute → store `DATAFLOW` split, with no `PIPELINE`/`UNROLL`/
   `ARRAY_PARTITION` pragmas yet — those come later.

3. **Actually 8× faster** — Pull the Interval (II) from `baseline_synth.rpt` 
   and `final_synth.rpt` and check `baseline_II / optimized_II ≥ 8`. If either 
   report shows `?` for Interval, the trip count wasn't fixed and the number 
   doesn't count.

4. **Optimization stage did real work** — `kernel_final.cpp` shouldn't be 
   identical to the architecture version, and it should carry the 
   fine-grained pragmas the earlier stage wasn't allowed to have.

Optional: cosim (and impl) to confirm the real RTL cycle count, since the 
Interval from step 3 is just a synthesis estimate. Not required to pass — 
just flag it as "estimated" if skipped

---

## Design targets (fixed for this eval)

| Parameter | Value | Source |
|---|---|---|
| Throughput target | **≥ 8× baseline** (Interval/II reduced ≥ 8×; throughput = 1/II) | example README ("8× baseline") |
| Matrix size | 64 × 64 × 64 | example README |
| FPGA part | `xczu9eg-ffvb1156-2-e` | **chosen for this eval** (example README specifies none; a part is required to synthesize) |
| Clock period | 3.3 ns | **chosen for this eval** (same reason) |

To change the part/clock, edit them **here** and regenerate/reinstall the suite.

---


## Output contract

Two things must come out of a run: the **core output** (the result you should
get) and the **behaviour output** (how the skill should have gone about getting
it). Both are described in plain terms — the framework decides what files and
reports to capture as evidence.

### Core output — what the result should be

- The kernel runs at least **8× faster** than the original — its C-synthesis
  throughput (1 / Interval) is ≥ 8× the baseline's, at the fixed 64×64×64 size,
  the given FPGA part, and the 3.3 ns clock.
- The optimized kernel is **still correct** — it produces the same result as the
  original within the testbench's tolerance, and the self-checking testbench
  still passes.
- The speedup is a **real, measured number**, backed by C synthesis of both the
  original and the optimized kernel (not just a claim).

### Behaviour output — how the skill should have behaved

- It first **restructures** the kernel into a clean streaming architecture
  (read inputs → compute → write outputs) *before* doing any fine-grained
  performance tuning — this structural version should already be correct.
- It then **optimizes** that structure, applying the performance techniques and
  measuring the effect, so the final kernel is meaningfully different from the
  structural version (real optimization work, not a no-op).
- It **actually runs the HLS flow** (C simulation for correctness, C synthesis
  for the speed numbers) rather than estimating or asserting results.
- It works **iteratively and keeps a record** — each optimization attempt is
  tracked (what was tried, what happened) so the path from baseline to final is
  auditable.



