---
name: optimize-aie-split-accumulator
description: >-
  Optimizes AI Engine kernel inner loops that are limited by accumulator feedback
  recurrence. Splits a single accumulator into N independent accumulators with an
  Nx-unrolled loop body, reducing effective initiation interval (II) by hiding the
  MAC-to-accumulator feedback latency. Use when: extract-aie-loop-ii shows the
  critical cycle is the accumulator recurrence (e.g., 4-cycle fpmac on AIE1),
  inner loop II exceeds the resource minimum, or the user wants to improve kernel
  throughput by breaking dependency chains.
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
# Optimize AIE: Split Accumulator

Break accumulator feedback recurrence in inner loops to reduce effective II.

---

## When to Apply

This optimization applies when **all** of the following are true:

1. The inner loop contains a MAC operation writing back to its own accumulator:
   ```cpp
   acc = aie::mac(acc, ...);   // feedback recurrence
   ```
2. The **critical cycle** (from `extract-aie-loop-ii`) matches or exceeds the MAC feedback latency:
   - AIE (1st gen): 4 cycles for `fpmac` (float), 2 cycles for `int16` MAC
   - AIE-ML: 4 cycles for `fpmac`, 2 cycles for `int8/int16` MAC
   - AIE-ML v2: 2 cycles for `fpmac` (fp32 vector MAC), 2 cycles for integer MAC
3. The **resource minimum** is lower than the achieved II — indicating the loop is
   dependency-limited, not resource-limited.
4. The loop trip count is divisible by the desired unroll factor (or can be made so).

**Do NOT apply when**:
- The loop is already resource-limited (resource min == achieved II)
- The accumulator is read mid-loop (not a simple running sum)
- The trip count is very small (< 8), where unrolling overhead dominates

---

## Background: MAC Feedback Latency

On AI Engine, a floating-point MAC (`fpmac`) has a 4-cycle result latency. When the
accumulator feeds back to itself, the scheduler cannot start the next iteration until
the previous MAC completes:

```
Cycle 0:  acc = mac(acc, a0, b0)   ← writes acc at cycle 3
Cycle 4:  acc = mac(acc, a1, b1)   ← must wait for acc to be ready
```

This creates a critical cycle of length 4, forcing II ≥ 4 even though the hardware
resources (load units, compute units) could sustain II = 2.

---

## Solution: Split Accumulators

By splitting into N accumulators and unrolling the loop Nx, each accumulator only
updates every N iterations, giving it N × II cycles to complete before its next use:

```
Cycle 0:  acc0 = mac(acc0, a0, b0)   ← acc0 ready at cycle 3
Cycle 3:  acc1 = mac(acc1, a1, b1)   ← acc1 ready at cycle 6
Cycle 6:  acc0 = mac(acc0, a2, b2)   ← acc0 was ready at cycle 3 ✓
```

With N=2 accumulators, the effective II per original iteration = achieved_II / 2.

---

## Workflow

### Step 1: Identify the Bottleneck

Run `extract-aie-loop-ii` and examine the inner loop report:

```
HW do-loop at line XX (inner loop):
  Critical cycle:     4          ← MAC feedback latency
  Resource minimum:   2          ← hardware could do II=2
  Achieved II:        4          ← limited by dependency
```

If critical_cycle > resource_min and the recurrence is the accumulator, proceed.

### Step 2: Choose Unroll Factor

The unroll factor N should satisfy:

```
N = ceil(MAC_latency / resource_min)
```

For typical cases:
- AIE float: MAC_latency=4, resource_min=2 → N=2
- AIE int16: MAC_latency=2, resource_min=1 → N=2
- AIE-ML v2 float: MAC_latency=2, resource_min=1 → N=2

**Constraint**: The loop trip count must be divisible by N. If the original trip count is
not divisible, either:
- Pad the reduction dimension to make it divisible (preferred)
- Add a remainder loop after the main unrolled loop

### Step 3: Apply the Transformation

**Before** (single accumulator, II=4):
```cpp
aie::accum<accfloat, LANES> acc;
acc = aie::zeros<accfloat, LANES>();

for (unsigned k = 0; k < N; k++)
    chess_prepare_for_pipelining
{
    float a_val = *pA_scalar++;
    auto b_vec = *pB;
    pB += stride;
    acc = aie::mac(acc, aie::broadcast<float, LANES>(a_val), b_vec);
}

*pC++ = acc.to_vector<float>();
```

**After** (split into 2 accumulators, effective II=3):
```cpp
aie::accum<accfloat, LANES> acc0;
aie::accum<accfloat, LANES> acc1;
acc0 = aie::zeros<accfloat, LANES>();
acc1 = aie::zeros<accfloat, LANES>();

for (unsigned k = 0; k < N; k += 2)
    chess_prepare_for_pipelining
{
    // Even iteration -> acc0
    float a_val0 = *((float*)in_A.data() + i * N + k);
    auto b_vec0 = *pB;
    pB += stride;
    acc0 = aie::mac(acc0, aie::broadcast<float, LANES>(a_val0), b_vec0);

    // Odd iteration -> acc1
    float a_val1 = *((float*)in_A.data() + i * N + k + 1);
    auto b_vec1 = *pB;
    pB += stride;
    acc1 = aie::mac(acc1, aie::broadcast<float, LANES>(a_val1), b_vec1);
}

// Combine partial accumulators
auto result = aie::add(acc0.to_vector<float>(), acc1.to_vector<float>());
*pC++ = result;
```

### Step 4: Use Restrict Iterators

When splitting accumulators, also ensure all buffer iterators use
`aie::begin_restrict_vector<LANES>()` instead of `aie::begin_vector<LANES>()`.
This tells the compiler there is no pointer aliasing between different buffer accesses,
enabling better instruction scheduling within each unrolled iteration.

```cpp
auto pB = aie::begin_restrict_vector<LANES>(in_B);  // restrict: no aliasing
auto pC = aie::begin_restrict_vector<LANES>(out_C);
```

### Step 5: Verify Improvement

1. Recompile with `--target=hw` and `verbose=1` in `aie.cfg`
2. Run `extract-aie-loop-ii` on the new build
3. Verify the effective II improved:
   - New achieved II / unroll_factor < old achieved II
   - Example: II=6 (folded over 2) = effective 3 cycles/iteration, improved from II=4

### Step 6: Verify Functional Correctness

Run x86sim to verify the split-accumulator version produces identical results.
Floating-point addition is not perfectly associative, but for typical AIE kernels
the reordering is acceptable (same precision, different accumulation order).

---

## Generalization to N=4 Accumulators

> **WARNING**: On AIE1 with floating-point broadcast-scalar × vector MAC (GEMM pattern),
> N=4 is empirically **worse** than N=2. The 4x-unrolled loop body becomes too large
> for effective modulo scheduling — the resource minimum increases dramatically (e.g.,
> from 4 to 13) due to register spilling, and the critical cycle explodes (e.g., from
> 6 to 26). Only use N=4 when the loop body per iteration is very simple (e.g., a
> single vector-vector MAC with no scalar broadcast or pointer arithmetic).

For cases where N=2 is insufficient AND the loop body is simple enough (e.g., pure
vector-vector MAC with sequential iterators), extend to 4 accumulators:

```cpp
aie::accum<accfloat, LANES> acc0, acc1, acc2, acc3;
// ... zero-initialize all ...

for (unsigned k = 0; k < N; k += 4)
    chess_prepare_for_pipelining
{
    // Iteration k+0 -> acc0
    // Iteration k+1 -> acc1
    // Iteration k+2 -> acc2
    // Iteration k+3 -> acc3
}

// Combine: result = (acc0 + acc1) + (acc2 + acc3)
auto partial01 = aie::add(acc0.to_vector<float>(), acc1.to_vector<float>());
auto partial23 = aie::add(acc2.to_vector<float>(), acc3.to_vector<float>());
auto result = aie::add(partial01, partial23);
*pC++ = result;
```

---

## Key Constraints

- **Trip count divisibility**: Loop trip count must be divisible by unroll factor N
- **Register pressure**: Each additional accumulator consumes LANES × sizeof(acc) of
  register file. AIE1 has limited accumulator registers — N=2 is usually safe, N=4
  may cause register spilling on complex kernels
- **Code size**: Unrolled body increases program memory usage. AIE tiles have 16 KB
  program memory — check that the unrolled kernel still fits
- **Combine overhead**: The final `aie::add()` to merge accumulators adds 1 cycle
  per output vector — negligible for large trip counts

---

## Expected Results

| Architecture | MAC Type | Before | After (N=2) | Improvement |
|---|---|---|---|---|
| AIE (1st gen) | fpmac (float) | II=4 | II=6/2=3 effective | 25% |
| AIE (1st gen) | int16 MAC | II=2 | II=2/2=1 effective | 50% |
| AIE-ML | fpmac (float) | II=4 | II=6/2=3 effective | 25% |
| AIE-ML v2 | fpmac (fp32) | II=2 | II=2/2=1 effective | 50% |

**Empirical N=4 results (AIE1 float GEMM — broadcast-scalar × vector pattern)**:

| Unroll | Critical Cycle | Resource Min | Modulo II | Fold | Effective II/iter |
|---|---|---|---|---|---|
| 1x (baseline) | 4 | 2 | 4 | 3 | 4.0 |
| 2x (recommended) | 6 | 4 | 6 | 2 | 3.0 |
| 4x (not recommended) | 26 | 13 | 26 | 1 | 6.5 |

**Recommendation**: Always start with N=2. Only try N=4 if the per-iteration loop body
is trivial (1 vector load + 1 vector MAC, no scalar loads or broadcast). For GEMM-style
broadcast-scalar patterns, N=2 is optimal.
