---
name: soc-orchestration/estimation
description: Progressive estimation sub-skill — validates partition assignments through T0-T3 tiers of increasing fidelity using Vivado MCP and shell tools.
metadata:
  category: amd-soc-design
  tier: domain
  tags:
    - estimation
    - soc
    - hls
    - synthesis
    - power
    - qor
    - progressive-validation
  complexity: intermediate
  estimated_duration: 10-60 minutes
  prerequisites_skills:
    - soc-orchestration/partitioning
  related_skills:
    - soc-orchestration
    - hls-optimization
    - timing-methodology-checks
    - congestion-analysis
    - rtl-lint
    - rtl-elaboration-analysis
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# SKILL: Progressive Estimation (T0–T3)

## Overview

This skill validates partition assignments by running progressively more expensive
estimation tiers. Each tier provides higher fidelity results but takes longer. If a
tier fails (resource overflow, timing violation, power exceeded), the orchestrator
should repartition and retry.

**You drive each tier.** Construct the appropriate tool commands, parse the results,
and decide whether to proceed or escalate.

## Prerequisites

- **MCP servers available:**
  - `vivado` — Vivado TCL session for synthesis and power estimation
  - `vivado-doc-search` — CLI syntax lookup for Vitis tools
- **Shell access** — for HLS, AIE compiler, v++ invocations
- **Structured types** from `contracts/types.py`:
  - Input: `PartitionPlan` + `DesignSpec`
  - Output: `QoRMetrics` (one per block per tier)

## Task: Run Progressive Estimation

### Tier 0 — Parametric Model (< 1 second)

**Method:** Pure LLM reasoning. No tool calls needed.

For each block, estimate resource usage analytically:

**PL blocks:**
- **Counters/adders**: Primarily use CARRY8 chains on UltraScale+, consuming
  very few LUTs (a 32-bit counter uses ~1 LUT + 4 CARRY8 + 32 FFs)
- **Multipliers**: Map to DSP48E2 slices. Each DSP does 27×18 multiply-accumulate.
  Count MAC operations explicitly.
- **FFs** ≈ registered_signals × data_width (pipeline stages multiply this)
- **LUTs** ≈ combinational_logic_complexity × data_width × 0.3
  (random logic averages ~0.3 LUTs per function per bit)
- **BRAMs** = memory_depth × width / 36Kb (RAMB36E2) or / 18Kb (RAMB18E2)
  Note: Small lookup tables (≤4Kb, e.g., 256×16-bit sin/cos ROM) are implemented
  as distributed LUT ROM by the synthesizer — do NOT count these as BRAMs.
  Only count memories >4Kb as BRAM candidates.
- **URAMs** = memory_depth × width / 288Kb (for large memories >36Kb)

Note: T0 estimates should be conservative but not wildly pessimistic. A factor of
2-3x is acceptable; 10x overestimate suggests the estimation model is wrong. After
T3 actuals, update your mental model for similar designs.

**AIE blocks:**
- Cores = data_rate / (clock × vector_width)
- Memory = buffer_count × buffer_size

**PS blocks:**
- CPU utilization = MIPS_required / MIPS_available
- Memory = stack + heap + DMA buffers

**DPU / Pre-built IP blocks (ml_inference workload_type):**

When the design includes a DPU or other pre-built acceleration IP with known resource
profiles, T0 MUST look up the actual resource numbers from the product guide rather
than estimating from first principles. DPU resource usage is well-documented and
device-specific — guessing leads to builds that fail on URAM/BRAM overflow.

**DPUCZDX8G resource table (PG338 — Zynq UltraScale+ PL-only DPU):**

**PG338 numbers cover the DPU IP core only — not the full system.** The table below
shows PG338 IP-only estimates alongside measured totals from complete v++ linked builds
(DPU + platform interconnect + clock infrastructure + memory subsystem). Use the
"System Total" columns for T0 estimation. The difference is platform overhead: AXI
SmartConnect instances, clock domain crossing FIFOs, protocol converters, and control
logic that v++ adds during system linking.

| Arch  | PG338 LUTs (IP only) | System Total LUTs | PG338 BRAMs (IP only) | System Total BRAM tiles | PG338 URAMs (IP only) | System Total URAMs | DSPs | MACs/cycle |
|-------|---------------------|-------------------|----------------------|------------------------|----------------------|-------------------|------|------------|
| B512  | ~14K                | ~26K              | 34                   | ~12                    | 11                   | ~15               | 118  | 512        |
| B800  | ~18K                | ~32K (est)        | 50                   | ~50 (est)              | 17                   | ~25 (est)         | ~160 | 800        |
| B1024 | ~22K                | ~53K              | 56                   | ~82                    | 17                   | ~46               | 710  | 1024       |
| B1152 | ~24K                | ~58K (est)        | 60                   | ~90 (est)              | 21                   | ~50 (est)         | ~780 | 1152       |
| B1600 | ~29K                | ~68K (est)        | 72                   | ~108 (est)             | 27                   | ~55 (est)         | ~900 | 1600       |
| B2304 | ~38K                | ~85K (est)        | 92                   | ~130 (est)             | 37                   | ~58 (est)         | ~1050| 2304       |
| B3136 | ~46K                | ~100K (est)       | 122                  | N/A                    | 43                   | N/A               | ~1200| 3136       |
| B4096 | ~56K                | ~115K (est)       | 162                  | N/A                    | 56                   | N/A               | ~1400| 4096       |

"System Total" values marked (est) are interpolated from B512 and B1024 measured data.
B512 and B1024 system totals are from verified v++ link builds on xck26 (KV260) and
include the v++ platform overhead (SmartConnect, clock infrastructure, protocol converters).
PG338 "IP only" numbers are correct for the DPU core itself — the difference is platform
infrastructure that v++ adds during linking. BRAM "tiles" count RAMB36E2 + RAMB18E2/2.
The xck26 has 144 BRAM tiles.

**DPUCVDX8G resource table (PG389 — Versal AI Core, PL portion only):**

| Arch  | LUTs  | FFs   | DSPs | BRAMs | URAMs | AIE Tiles |
|-------|-------|-------|------|-------|-------|-----------|
| B512  | ~15K  | ~13K  | 20   | 20    | 5     | 4         |
| B1024 | ~25K  | ~20K  | 35   | 35    | 10    | 8         |
| B2048 | ~45K  | ~35K  | 60   | 60    | 18    | 16        |
| B4096 | ~80K  | ~65K  | 110  | 110   | 32    | 32        |

**Combined resource check (CRITICAL):** When a design has BOTH custom PL blocks (video
pipeline, peripherals, etc.) AND a DPU, T0 MUST sum the resources of ALL blocks and
check the total against device limits. This is the most common source of build failures
— the DPU and custom PL are estimated separately and each fits individually, but
together they exceed device capacity (especially URAM and BRAM on smaller devices).

**IMPORTANT: Use "System Total" (not PG338 IP-only) numbers for resource budgeting.**
PG338 reports the DPU IP core resources correctly, but a real v++ linked system includes
additional platform infrastructure (~15-25 BRAM tiles for AXI SmartConnect instances,
clock domain crossing FIFOs, and protocol converters). This platform overhead is not
part of the DPU IP — it is added by `v++ --link` during system integration and only
appears in post-synthesis utilization reports.

```
For each resource type R in {LUT, FF, DSP, BRAM, URAM}:
  total_R = sum(custom_PL_blocks_R) + DPU_actual_R + vpp_interconnect_overhead_R + platform_overhead_R
  if total_R > 0.80 * device_available_R:
    WARNING — tight fit, may fail after v++ link adds interconnect
  if total_R > 0.85 * device_available_R:
    FAIL — recommend smaller DPU arch or remove PL blocks
  if total_R > 0.90 * device_available_R:
    CRITICAL FAIL — design will not fit
```

**v++ interconnect overhead estimate** (from measured KV260 builds):
- BRAM: +15-25 tiles (for SmartConnect, AXI protocol converters, CDC FIFOs)
- LUT: +5-10K (AXI interconnect fabric, address decoders)
- FF: +3-5K (pipeline registers in interconnects)
This overhead scales with the number of DPU AXI ports and PFM-tagged platform ports.

**Platform overhead** accounts for AXI interconnects, clock infrastructure, reset blocks,
and PS8/CIPS support logic (~5-10% of LUT/FF on typical designs).

**DPU arch selection guidance (KV260 — xck26: 117K LUT, 64 URAM, 144 BRAM tiles):**

Using System Total resource numbers with a moderate video pipeline (4K MIPI + VPSS +
FBW/FBR + IIC + GPIO ≈ 15K LUT, 10 BRAM tiles, 10 URAM):

| Arch  | Combined BRAM          | Combined URAM        | Verdict                     |
|-------|------------------------|----------------------|-----------------------------|
| B4096 | N/A (system total > 144)| ~56+10+5 = 71 > 64  | IMPOSSIBLE on xck26         |
| B2304 | ~130+10+20 = 160 > 144 | ~58+10+5 = 73 > 64  | DOES NOT FIT                |
| B1024 | ~82+10+20 = 112 / 144  | ~46+10+5 = 61 / 64  | DOES NOT FIT (BRAM 78%, URAM 95%) |
| B512  | ~12+10+20 = 42 / 144   | ~15+10+5 = 30 / 64  | FITS (BRAM 29%, URAM 47%)   |

**Key learning: B512 is the practical ceiling for KV260 combined designs with a
video pipeline.** B1024 appeared feasible from PG338 IP-only numbers alone, but the
full v++ linked system (DPU + platform interconnect + video pipeline) exceeded
available BRAM (required 318 BRAM tiles, only 288 available).

For larger devices (ZCU104: 504 BRAM, 96 URAM), B1024 fits comfortably. For VCK190
(Versal, 967 BRAM, 463 URAM), B4096 fits with room to spare.

Emit a `QoRMetrics` with `tier: "T0"`, `passed: true/false`, and estimated values.

**Failure criteria:** Any domain exceeds 90% of available resources.

### Tier 1 — Power Estimation (5–30 seconds)

**Method:** Xilinx Power Estimator (XPE) via Vivado.

```tcl
# Run via vivado_execute after opening/creating a project
# Set activity rates based on design spec
set_switching_activity -toggle_rate 25 -static_probability 0.5 [get_nets *]
report_power -file power_t1.rpt
```

Parse the power report and check against `power_budget_watts`.

Alternatively, for early estimation without a project:
- Use `vivado_doc_search` to find the XPE spreadsheet approach
- Or use `report_power -advisory` after elaboration

Emit `QoRMetrics` with `tier: "T1"`, `power_watts`, `passed`.

**Failure criteria:** Total power > `power_budget_watts` or any domain > 80% of its thermal budget.

### Tier 2 — HLS C-Synthesis / AIE Mapping (10–60 seconds)

**Method:** Run actual tool compilation on individual blocks.

**For PL blocks with HLS source (Vitis HLS `hls.cfg` project):**

Invoke the `hls-optimization` skill sub-steps:

1. **`hls-optimization/csim`** — run `make csim` to verify kernel correctness and
   collect loop trip count profiles. If csim fails, the kernel logic is broken —
   fix before proceeding.

2. **`hls-optimization/synth`** — run `make csynth` to compile to RTL and get
   resource/latency/timing estimates. Parse the csynth report using:
   ```bash
   python3 .claude/skills/hls-optimization/synth/scripts/report_summary.py \
       hls/hls/syn/report/kernel_csynth.rpt
   ```

For csynth report structure and interpretation, see `hls-optimization/synth/SKILL.md`.

**For PL blocks without `hls.cfg` (legacy Vivado HLS flow):**

```bash
vitis_hls -f run_hls.tcl
# Or construct inline:
# open_project <name>; set_top <fn>; add_files <src>; open_solution <sol>;
# set_part <device>; csynth_design; exit
```

Parse the csynth report for: latency, interval, LUT/FF/DSP/BRAM usage.

**For AIE blocks:**

```bash
# vivado_doc_search: "aiecompiler" for syntax
aiecompiler --target=hw --platform=<xpfm> -graph=<graph> <source>.cpp
```

Parse the AIE compiler output for core mapping and memory usage.

**For Model Composer blocks:**

Use the Model Composer MCP server:
```
evaluate_matlab_code: "xmcExportForSynthesis('<model>', '<output_dir>')"
```

Emit `QoRMetrics` with `tier: "T2"`, resource utilization, latency, `passed`.

**Failure criteria:** Resource usage > 80% of allocated budget, or latency exceeds constraint.

### Tier 3 — Out-of-Context Place & Route (2–10 minutes)

**Method:** Full synthesis + P&R in OOC mode for each PL block.

**For HLS kernels with `hls.cfg` project:** invoke `hls-optimization/ooc` — run
`make impl` to get the true post-route clock period. See `hls-optimization/ooc/SKILL.md`
for report interpretation.

**For standalone RTL blocks:** use Vivado OOC synthesis as described below.

**IMPORTANT: When to use OOC vs normal synthesis:**
- **Use OOC** for standalone RTL blocks that will be integrated into a PS+PL block
  design. OOC skips I/O placement, which fails on pin-limited SOM devices (K24 has
  only 81 pins — a motor controller with 141 ports will fail place_design).
- **Use normal synthesis** for PL-only designs with few ports that fit device I/O,
  or for PS+PL block designs where the BD wrapper is the top level.

```tcl
# Run via vivado_execute — OOC mode for PL blocks targeting BD integration
create_project ooc_<block> <output_path> -part <device> -force
add_files <source_files>
add_files -fileset constrs_1 <constraint_files>
set_property top <top_module> [current_fileset]
# OOC mode: skips I/O placement — essential for port-heavy blocks on SOMs
set_property -name {STEPS.SYNTH_DESIGN.ARGS.MORE OPTIONS} -value {-mode out_of_context} -objects [get_runs synth_1]
launch_runs synth_1
wait_on_run synth_1
# Collect results after synthesis
open_run synth_1
report_utilization -return_string
report_timing_summary -return_string -max_paths 3
```

For PS+PL block designs, don't use OOC mode — instead run full synthesis which
includes IP OOC synthesis of sub-blocks automatically:
```tcl
# PS+PL designs: full project synthesis handles IP generation
launch_runs synth_1
wait_on_run synth_1
# IP OOC synthesis happens automatically; expect ~2 min total for simple designs
```

**Known pitfall (from actual runs):** If you run normal synthesis+implementation on
standalone RTL with many ports on a K24 (81 pins), placement will fail with:
`ERROR: [Place 30-58] IO placement is infeasible. Number of unplaced IO Ports (N) > available pins (81)`
Recovery: `reset_runs impl_1; reset_runs synth_1`, set OOC mode, re-launch.

After synthesis completes, invoke the **timing-methodology-checks** skill (and
`congestion-analysis` / `opt-design-analysis` post-implementation) to get:
- Timing methodology check results (UG906)
- Congestion and optimization-phase analysis
- Utilization summary
- Clock network quality

NOTE: a consolidated QoR-score and CDC analysis are not in the vivado-agentic-ai-skills
repo; use the external/global `baselining` skill if you need them.

```tcl
# Key reports (these analysis skills run them comprehensively)
report_utilization -file util_t3.rpt
report_timing_summary -file timing_t3.rpt
report_qor_assessment -file qor_t3.rpt
```

Emit `QoRMetrics` with `tier: "T3"`, full utilization, WNS, WHS, QoR score, `passed`.

**Failure criteria:** WNS < -0.5ns, utilization > 85%, QoR score < 2 (needs attention).

## Decision Logic

```
For each block in partition_plan.assignments:
  run T0 →  if failed: SIGNAL repartition needed
  run T1 →  if failed: SIGNAL repartition needed
  run T2 →  if failed and source available: SIGNAL repartition needed
             if no source: SKIP (warn user)
  run T3 →  if failed: try rtl-lint / rtl-elaboration-analysis for quick fixes
             if still failed: SIGNAL repartition needed
  all passed → block is VALIDATED
```

**Early termination:** If T0 fails catastrophically (>200% resource usage), skip higher
tiers for that block — the partition is clearly wrong.

**Parallel execution:** Independent blocks at the same tier can be estimated in parallel
using separate Vivado sessions (different `session_id` values).

## Output Format

For each block, produce a `QoRMetrics` JSON:

```json
{
  "tier": "T2",
  "block_name": "fft_engine",
  "utilization_pct": {"LUT": 12.3, "FF": 8.1, "DSP": 45.0, "BRAM": 15.2},
  "frequency_mhz": 300.0,
  "power_watts": 1.2,
  "logic_levels": 8,
  "passed": true,
  "notes": "HLS csynth completed; latency 256 cycles at 300MHz meets 1us target"
}
```

Collect all `QoRMetrics` into the `ClosureReport.qor_history` list.

## Versal-Specific Notes

### Implementation Directive Compatibility

When configuring Vivado directives for Versal T3 synthesis or post-T3 implementation:
- `EarlyBlockPlacement` is **NOT valid** for Versal `PLACE_DESIGN` — use `Explore`
- `Performance_ExploreWithRemap` may not be supported in all Versal contexts
- Always verify directive validity with `vivado_doc_search` or UG904 before applying

### v++ Flow Estimation

For AIE + HLS kernel designs targeting v++, T3 estimation should account for the full
`v++ --link` build time (which includes VPL synthesis + implementation internally).
From actual measurements:
- AIE graph compilation: ~180s for a 50-column DSP Library design
- HLS kernel compilation: ~60s for 3 simple kernels (CFAR + mm2s + s2mm)
- `v++ --link` on VCK190 base: ~867s (system_link 10s + VPL 857s)
- Final PL utilization for a 4-ch radar processor: 2.1% LUT, 7.6% DSP, 2.3% BRAM

When estimating v++ builds, use AMD base platforms rather than custom platforms to
avoid PS-NoC clock routing failures (see `vitis-platform/SKILL.md`).

## Troubleshooting

### HLS csynth takes too long
Set a timeout. If csynth exceeds 5 minutes for a single block, it may indicate
the design is too large for OOC synthesis — consider splitting.

### AIE compiler fails with memory error
The block may need more AIE tiles than assigned. Check the partition and increase
allocation or split the kernel across tiles.

### No source_path for a block
Skip T2/T3 for that block. T0/T1 can still provide estimates.
Warn the user that higher-fidelity validation requires source code.

## Related Skills

- `soc-orchestration`: Parent orchestration flow
- `soc-orchestration/partitioning`: Produces the partition plan this skill validates
- `hls-optimization`: Vitis HLS workflow (csim → synth → cosim → ooc) used in T2/T3
- `hls-optimization/optimize`: Iterative HLS optimization when T2/T3 targets not met
- `timing-methodology-checks`: Post-synthesis timing methodology checks (used in T3)
- `congestion-analysis` / `opt-design-analysis`: Post-implementation QoR/congestion analysis
- `rtl-lint` / `rtl-elaboration-analysis` / `versal-rtl-design-advisories`: Suggest RTL fixes when T3 fails
