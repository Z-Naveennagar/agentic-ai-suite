---
name: soc-orchestration
description: Top-level orchestration skill for AMD SoC AI-assisted design — coordinates partitioning, estimation, implementation, and timing closure across PS/PL/AIE domains.
metadata:
  category: amd-soc-design
  tier: tutorial
  tags:
    - orchestration
    - soc
    - partitioning
    - estimation
    - timing-closure
    - versal
    - zynq
  complexity: advanced
  estimated_duration: 30-180 minutes
  prerequisites_skills:
    - soc-orchestration/partitioning
    - soc-orchestration/estimation
  related_skills:
    - hls-optimization
    - hls-timing-closure
    - hls-area-opt
    - qor-classification
    - timing-methodology-checks
    - congestion-analysis
    - opt-design-analysis
    - phys-opt-design-analysis
    - device-floorplan
    - rtl-lint
    - rtl-elaboration-analysis
    - versal-rtl-design-advisories
    - vivado-revision-control
    - noc-debug
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# SKILL: AMD SoC Design Orchestration

## Overview

This skill orchestrates end-to-end AMD SoC design from a high-level specification to a
closed, implementable design. It coordinates multi-domain partitioning (PS / PL / AIE),
progressive estimation (T0–T3), full implementation (T4), and timing closure by composing
specialized sub-skills and MCP servers.

**You are the reasoning engine.** Do not look for coded orchestration logic. Read the
design spec, reason about trade-offs, invoke tools, and iterate.

## Prerequisites

- **MCP servers available:**
  - `vivado` — Vivado TCL session (vivado_start, vivado_execute, vivado_status, etc.)
  - `vivado-doc-search` — AMD/Xilinx documentation search
  - `model-composer` — Vitis Model Composer via MATLAB (evaluate_matlab_code, list_skills, get_skill)
- **Agent Skills available** (invoke by reading their SKILL.md):
  - `soc-orchestration/partitioning` — multi-domain partitioning
  - `soc-orchestration/estimation` — progressive T0–T3 estimation
  - `soc-orchestration/ps-software` — PS firmware generation and compile-test
  - `soc-orchestration/vitis-platform` — Vitis extensible platform creation (PFM properties, VDU, NoC expansion, XSA export)
  - `soc-orchestration/vitis-acceleration` — v++ kernel integration (DPUCVDX8G, HLS, AIE graph compilation, xclbin generation)
  - `hls-optimization` — Vitis HLS kernel workflow (csim → synth → cosim → ooc → optimize)
  - `hls-timing-closure` — isolate-and-close the limiting HLS structure in a microbenchmark
  - `hls-area-opt` — rebalance HLS area across BRAM/URAM/LUTRAM/DSP to fit
  - `ipi-block-design` — IP Integrator block design construction (PS8/CIPS + PL IPs)
  - `qor-classification` — First-Step timing-closure bottleneck classifier (RQA/RQS/congestion/util/WNS-progression → one class + confidence + FullFlow dashboard)
  - `timing-methodology-checks` — 55+ UG906 timing methodology checks (post-synthesis)
  - `congestion-analysis` — placement/routing congestion analysis with HTML dashboard (post-impl)
  - `opt-design-analysis` — opt_design log analysis and directive recommendations
  - `phys-opt-design-analysis` — phys_opt_design replication/retiming/hold-fix analysis
  - `device-floorplan` — SLR/pblock floorplanning for multi-SLR partition fixes
  - `rtl-lint` — RTL linter (pre-synthesis design checks)
  - `rtl-elaboration-analysis` — synthesis elaboration error/warning analysis with RTL fixes
  - `versal-rtl-design-advisories` — Versal RTL design advisory checks (DSP58, URAM/BRAM, FSM, US+→Versal migration)
  - **Timing closure** is orchestrated inline in **Phase 5** (classify → localize → dispatch →
    rebuild → re-check), composing the skills above. There is no monolithic methodology skill.
  - `noc-debug` — NoC error diagnosis (Versal)
  - `vivado-revision-control` — project build scripts and version control
  - **CDC / clock-interaction analysis** and a consolidated **QoR-score umbrella** are NOT in the
    vivado-agentic-ai-skills repo. Use the external/global `baselining` skill if you need those.
- **Structured types** defined in `contracts/types.py`:
  - `DesignSpec`, `PartitionPlan`, `QoRMetrics`, `ClosureReport`

## Architecture: LLM-First

```
User Spec (JSON / natural language)
        │
        ▼
┌─────────────────────────────────────────────┐
│  LLM Orchestrator (this skill)              │
│  • Reads spec → reasons about partitioning  │
│  • Invokes sub-skills and MCP tools         │
│  • Iterates on estimation failures          │
│  • Drives implementation and closure        │
└──────┬──────────┬──────────┬────────────────┘
       │          │          │
  ┌────▼───┐ ┌───▼────┐ ┌───▼──────────────┐
  │ Vivado │ │ Model  │ │ Agent Skills     │
  │  MCP   │ │Composer│ │ (HLS Optim.,     │
  │        │ │  MCP   │ │  Baselining,     │
  │        │ │        │ │  RTL Assistant,  │
  │        │ │        │ │  Timing Closure, │
  │        │ │        │ │  NoC Debug, etc.)│
  └────────┘ └────────┘ └──────────────────┘
```

## Task: Full Design Flow

### Phase 0 — Load & Validate Spec

1. Read the design spec (JSON file matching `DesignSpec` schema, or natural language).
2. Validate the target device exists using the Vivado MCP:
   ```tcl
   # Simplest validation (proven to work)
   puts [get_parts <target_device>]
   # Returns the part name if valid, empty if not found
   ```
3. Enumerate functional blocks and their `workload_type` values.
4. **Determine the project type** based on the partition:
   - PL-only → simple RTL project
   - PS+PL → block design with Zynq PS8 (UltraScale+) or CIPS (Versal)
   - PS+PL+AIE → block design with CIPS + NoC + AIE graph compilation

### Phase 1 — Partition

Invoke the **partitioning sub-skill** (`soc-orchestration/partitioning/SKILL.md`).

Inputs: `DesignSpec` (blocks, target device, constraints)
Outputs: `PartitionPlan` (domain assignments, cross-domain interfaces, rationale)

The partitioning skill uses `workload_type.natural_domain` as a starting point, then
adjusts based on device resources, latency constraints, and power budget.

### Phase 2 — Progressive Estimation (T0 → T3)

Invoke the **estimation sub-skill** (`soc-orchestration/estimation/SKILL.md`).

For each assigned block, progressively estimate fidelity:

| Tier | Method | Duration | Failure action |
|------|--------|----------|----------------|
| T0 | Parametric model (LLM reasoning over device specs) | <1s | Re-partition |
| T1 | XPE power estimation via Vivado MCP | 5-30s | Re-partition |
| T2 | HLS C-synthesis / AIE mapping (`hls-optimization/csim` + `synth`) | 10-60s | Re-partition |
| T3 | Vivado OOC synthesis (`hls-optimization/ooc` or Vivado MCP) | 2-10min | Re-partition |

**Important:** If any tier fails, return to Phase 1 with failure context and re-partition.
Track repartition count — escalate to user after 3 attempts.

### Phase 2b — Combined Resource Budget (DPU + Custom PL)

**MANDATORY when the design includes BOTH custom PL blocks AND a DPU (`ml_inference`
workload_type).** This check prevents the most common failure mode: building the PL
pipeline and DPU separately, each fitting individually, but overflowing the device
when combined.

Before proceeding to Phase 3, check combined resource usage:

1. Sum ALL PL blocks from the T0 estimation (custom pipeline + interconnects + resets)
2. Add the DPU resource profile from the PG338/PG389 tables in `estimation/SKILL.md`
3. Add ~10% overhead for platform infrastructure (AXI interconnect, clock buffers)
4. Compare total against device resource limits at 85% threshold

```
combined = sum(all_PL_T0_estimates) + DPU_table_lookup + 10%_platform_overhead

if combined.URAM > 0.85 * device.URAM:
  → Reduce DPU arch (B4096 → B2304 → B1024 → B512)
  → Re-estimate with smaller arch before building
if combined.BRAM > 0.85 * device.BRAM:
  → Same downgrade path
if combined.LUT > 0.85 * device.LUT:
  → Consider removing non-essential PL blocks or using SW alternatives
```

**If DPU arch must be reduced:** Update the spec and re-run T0 to confirm the smaller
DPU + full PL pipeline fits. Document the trade-off (reduced inference throughput vs.
design fit) in the ClosureReport.

**Consult `reference/device-resource-limits.md`** for device resource tables, DPU
architecture ceilings per device, PG338/PG389 IP-only vs system-total resource
explanation, and split architecture fallback guidance. The agent MUST read this file
during Phase 2b.

### Phase 3 — Interface Generation

Based on the partition plan's `cross_domain_interfaces`:

1. For PS↔PL: Generate AXI4 / AXI-Stream interface constraints.
2. For PL↔AIE: Generate PLIO / GMIO interface definitions.
3. For PS↔AIE: Route through PL or NoC as appropriate.
4. Use `vivado_execute` to validate interface clock domain compatibility.

### Phase 4 — Full Implementation (T4)

Execute the full build using Vivado MCP tools. The flow depends on partition type:

**PL-only designs:**
```tcl
create_project <name> <path> -part <device> -force
add_files <rtl_sources>
add_files -fileset constrs_1 <constraint_files>
set_property top <module> [current_fileset]
launch_runs synth_1; wait_on_run synth_1
launch_runs impl_1; wait_on_run impl_1
```

**PS+PL designs (Zynq UltraScale+):**
Read the `ipi-block-design` skill (`ipi-block-design/SKILL.md`) for the complete
IPI construction flow. Key steps:
1. `create_bd_design` → `create_bd_cell` (PS8) → `apply_bd_automation`
2. Set `pl_clk0` frequency explicitly (default is ~97 MHz, not 100!)
3. Enable HP ports before adding DMA/VDMA masters
4. Wire control plane with automation, data plane manually if automation fails
5. `assign_bd_address` for any manually-wired HP segments
6. `validate_bd_design` → `save_bd_design` → `make_wrapper`
7. Add wrapper via explicit path, not `get_files` filter
8. `launch_runs synth_1/impl_1`

**AIE blocks**: Shell access — `aiecompiler` / `v++` invocations
   (use `vivado_doc_search` to look up exact CLI syntax if needed)
**PS software**: Shell access — Vitis / Petalinux build commands
**Model Composer blocks**: Use `model-composer` MCP — `evaluate_matlab_code`

**Consult `reference/build-timing-benchmarks.md`** for expected synth/impl/link
durations by design type. Use these to set `block_until_ms` timeouts and user
expectations.

**Post-implementation checks:**
```tcl
open_run impl_1
report_timing_summary -no_header -no_detailed_paths
report_utilization -no_primitives
```
For VDMA designs, also run `report_bus_skew` (VDMA generates bus skew constraints).

### Phase 4b — PS Software Generation

**First, consult the Software Build Flow Selection decision tree** (see Decision Trees
section) to determine the correct flow based on the partition plan.

**Traditional Embedded Flow** — If the partition plan includes PS blocks with
`workload_type: "bare_metal_firmware"` or `"linux_app"` and the design has **no AIE
graphs or HLS acceleration kernels**, invoke the **ps-software sub-skill**
(`soc-orchestration/ps-software/SKILL.md`).

**v++ Flow** — If the design includes AIE graphs or Vitis-kernel-flow HLS blocks,
the PS software must be built against the fixed XSA produced by `v++ --link` (or from
Vivado after VMA import). Use the `v++` CLI for kernel compilation and system linking
first, then generate the BSP from the resulting fixed XSA.

#### Traditional Embedded Flow (hsi::generate_bsp)

This path builds firmware end-to-end through the Vitis toolchain:
1. Export `.xsa` from Vivado: `write_hw_platform -fixed -force <path>.xsa`
2. Extract address map from `.hwh` using `scripts/extract_addr_map.py`
3. Generate `platform_config.h` and `main.c` using driver API patterns
4. Build via `scripts/vitis_build.tcl` — generates real BSP, compiles, and **links to .elf**

```bash
xsct scripts/vitis_build.tcl <design>.xsa <firmware_dir> /scratch/<build_dir> \
    -os standalone -proc psu_cortexa53_0 -app-name <app>
```

The build script uses `hsi::generate_bsp` (works on headless servers without Eclipse)
to create the BSP with real `xparameters.h` and `libxil.a`, then compiles and links
against it. Build takes ~16 seconds per design.

**Success criteria:** `vitis_build.tcl` exits 0, producing a valid AArch64 ELF binary.

**Skip this phase** for PL-only designs (no PS block).

#### v++ Flow (AIE/acceleration designs)

When the design includes AIE or Vitis-kernel-flow HLS blocks, invoke two sub-skills
in sequence:

1. **Select or create extensible platform:**
   - **Preferred:** Use an AMD-provided base platform (e.g., `xilinx_vck190_base_202520_1`)
     that has correct PS-NoC dedicated clock routing and pre-validated DDR access ports.
     See "Versal Platform Pitfalls" section for why custom platforms can fail.
   - **Alternative:** If a custom platform is required, invoke `soc-orchestration/vitis-platform/SKILL.md`
     to tag PFM.CLOCK, PFM.AXI_PORT, PFM.IRQ on the block design and export extensible
     XSA. Ensure the platform was built with board automation, not manual Tcl NoC wiring.

2. **Integrate kernels** — invoke `soc-orchestration/vitis-acceleration/SKILL.md`:
   - Compile AIE graph: `v++ --mode aie --config aie.cfg --part <device>`
   - Compile HLS kernels: `v++ --mode hls --config hls.cfg --part <device>`
   - Link system: `v++ --link --platform <extensible.xsa> --config system.cfg <kernel.xo> <libadf.a> -t hw -o fixed.xsa`
   - Package: `v++ --package --platform fixed.xsa -t hw --package.boot_mode sd`

3. **Build PS software** from the fixed XSA:
   - For baremetal/FreeRTOS: `hsi::generate_bsp` from `vitis_build.tcl`
   - For Linux XRT apps: compile with `aarch64-linux-gnu-gcc` against XRT headers

Output artifacts:
- `tests/<spec_name>/firmware/` — source code, .xsa, addr_map.json
- `/scratch/.../build/` — BSP, objects, linked `.elf`

### Phase 5 — Timing Closure (inline orchestrator)

Phase 5 **is** the timing-closure orchestrator. It does not delegate to a monolithic
methodology skill; instead it runs a **classify → localize → dispatch → rebuild → re-check**
loop, composing the granular analysis skills already in this repo. Two reference files drive
the loop:
- `reference/device-profiles.md` — what the target device implies (SLR count, knobs, thresholds)
- `reference/closure-pattern-library.md` — ordered, cheapest-first remedy per bottleneck class

**Entry condition:** Phase 4 produced a placed/routed checkpoint. Read `WNS@Route` (and
`WHS@Route`). If both ≥ 0, skip to Phase 6 with `status: met`.

#### Step 5.1 — Classify the bottleneck (First-Step)
Invoke the **`qor-classification`** leaf skill on the routed (preferred) checkpoint. It fuses
`report_qor_assessment` (RQA 1–5), `report_qor_suggestions` (RQS), congestion level,
utilization, the WNS Place→PhysOpt→Route progression, and the logic/route split into **one
class** — `Partition | Congestion | Clocking | Utilization | Timing` — with a HIGH/MEDIUM/LOW
confidence and a sub-class. Pass the per-design output dir so artifacts land under
`vivado_agentic_ai_reports/qor-classification/<design>/`.

> Anchor on metrics, not RQS presence. RQS suggestions appear for almost every failing design,
> so they corroborate but never decide the class. Honor the single-SLR rule from
> `device-profiles.md` (no `Partition` on single-SLR parts).

#### Step 5.2 — Localize the worst path to its owning block
Before any fix, map the worst path back to the block that owns it (the hls-timing-closure
"isolate-and-close" pattern): `report_timing -max_paths 10 -nworst 1` → resolve the
startpoint/endpoint cell to a BD instance / RTL module / HLS kernel. Fix in the **smallest**
owning scope, not the whole design.

#### Step 5.2b — Gate the automated backend attempt on confidence
Only launch a multi-hour automated re-implementation (re-place/route with directives,
phys_opt, retiming) when the classifier is **HIGH confidence** on a backend-fixable class
(`Congestion`, `Clocking`, `Utilization`, or `Timing/Retiming_Opportunity`). At MEDIUM/LOW
confidence, first gather cheap evidence (per-phase WNS via the physopt DCP, `congestion-analysis`)
to raise confidence, or skip straight to Step 5.6 (source review) — do not burn a long build on
a guess. Record the gate decision in the `QoRMetrics.notes`.

#### Step 5.3 — Dispatch to the right fix skill (UltraFast priority)
Fix **structure before paths**. Apply the first untried remedy for the class from
`closure-pattern-library.md`:

| Class | Primary fix skill(s) | Typical action |
|---|---|---|
| **Clocking** | `timing-methodology-checks` | fix/relax clock constraints, CDC groups, uncertainty |
| **Utilization** | `hls-area-opt`, `partitioning` | rebalance area / re-partition to fit |
| **Congestion** | `congestion-analysis` | spread-logic placement + aggressive phys_opt directives |
| **Partition** *(multi-SLR)* | `device-floorplan` | SLR pblocks, register crossings, NoC for long data |
| **Timing** | `opt-design-analysis`, `phys-opt-design-analysis`, `hls-timing-closure` | retiming (`RQS_NETLIST-10`), pipelining, net-delay fixes |

For RTL-rooted issues, also use `rtl-lint`, `rtl-elaboration-analysis`, and (Versal)
`versal-rtl-design-advisories`. Apply RQS via `write_qor_suggestions` then
`read_qor_suggestions` before re-synth/place so RTL-level suggestions take effect.

#### Step 5.4 — Rebuild the affected scope and re-check
Re-run only the necessary stage (re-place/route for placement remedies; re-synth for RTL/RQS
remedies). Capture the new `WNS@Route`. Track the per-iteration QoR as `QoRMetrics`
(`wns_place`, `wns_popt`, `wns_route`, `rqa_score`, `classification`, `confidence`, `rqs_ids`).

#### Step 5.5 — Loop or escalate
- `WNS@Route ≥ 0 and WHS ≥ 0` → **closed**, go to Phase 6 (`status: met`).
- Improved but still failing, and iteration budget remains → re-classify (Step 5.1) and apply
  the next remedy. The class often *changes* as you fix structure (e.g. Congestion → Timing).
- No improvement after exhausting a class's remedies, or budget exhausted → **escalate**
  (Step 5.6).

#### Step 5.6 — Escalate to source-code remediation (backend cannot close)
When the Vivado backend cannot meet timing, the violations are rooted in the RTL/HLS source.
Generate a **source-code remediation report** with `qor-classification/scripts/source_remediation.py`:
it maps each worst failing path to its owning HLS/RTL construct (function, source line, storage),
locates it in the source tree, and emits `SOURCE_REMEDIATION.md` with concrete, signature-driven
edits (register the memory read + window shift-register for BRAM→MUXF stalls, pipeline DSP/carry
paths, insert pipeline stages for deep logic, reduce fanout/unroll for net-delay/congestion).
Then route the specific fix back to the owning flow:
  - Partition-level (wrong domain) → return to **Phase 1**.
  - Constraint-level (missing/wrong constraints) → fix and re-run **Phase 4**.
  - HLS kernel-level (latency/II/area, or a source fix from the remediation report) → invoke
    `hls-optimization/optimize` or `hls-timing-closure` to isolate-and-close the construct in a
    microbench, then re-package and re-implement.
  - Emit `status: partial` with the best achieved WNS, the blocking class, and the path to
    `SOURCE_REMEDIATION.md`.

**Stop conditions (always honor):** closed; iteration budget reached; or the same class
recurs with no WNS improvement across two consecutive iterations (avoid thrashing) — report
and escalate rather than loop further.

### Phase 6 — Report

Emit a `ClosureReport` (structured JSON matching the Pydantic model):

```json
{
  "design_name": "...",
  "status": "met | not_met | partial",
  "partition_plan": { "assignments": [...], ... },
  "qor_history": [...],
  "final_wns_ns": ...,
  "final_whs_ns": ...,
  "final_tns_ns": ...,
  "classification": "Timing | Congestion | Clocking | Utilization | Partition",
  "confidence": "HIGH | MEDIUM | LOW",
  "rqs_suggestions": ["RQS_NETLIST-10", "..."],
  "total_power_watts": ...,
  "build_artifacts": { "pdi": "...", "bitstream": "...", ... },
  "ps_software": {
    "generated": true,
    "os": "baremetal | freertos | linux",
    "firmware_dir": "tests/<spec>/firmware/",
    "compile_status": "pass | fail",
    "elf_path": "/scratch/.../build/<app>.elf",
    "bsp_path": "/scratch/.../build/bsp/psu_cortexa53_0/lib/libxil.a"
  },
  "recommendations": [...]
}
```

## Decision Trees

### Software Build Flow Selection (per AMD 2025.2 — UG1701, UG1273, UG1387)

AMD defines three distinct software/integration flows. The choice depends on the
partition plan's domain assignments and workload types. Evaluate **after Phase 1**
(partitioning) to determine which Phase 4b path to follow.

```
Partition plan ready
  │
  ├─ Design includes AIE graphs?
  │     YES ──► v++ Flow (Integrated or Export-to-Vivado)
  │                │
  │                ├─ Need fine-grained Vivado implementation control?
  │                │     YES ──► Vitis Export to Vivado Flow (v++ --export_archive → VMA)
  │                │     NO  ──► Vitis Integrated Flow (v++ --link → automated impl)
  │                │
  │                └─ PS software: BSP from v++ linker output (standalone/FreeRTOS)
  │                   or XRT host app (Linux)
  │
  ├─ Design includes HLS acceleration kernels (.xo via v++ --mode hls)?
  │     YES ──► v++ Flow (same decision as above)
  │
  └─ PS+PL only (no AIE, no HLS kernels)?
        │
        └─ PS is control processor with register-mapped I/O to PL peripherals
              ──► Traditional Embedded Flow (hsi::generate_bsp)
```

#### Flow comparison

| Criteria | Traditional Embedded (`hsi`) | Vitis Integrated (`v++`) | Export to Vivado (`v++ --export_archive`) |
|----------|------------------------------|--------------------------|------------------------------------------|
| **When to use** | PS controls PL peripherals via AXI register I/O | AIE graphs, HLS acceleration kernels, XRT-based host | Same as Integrated, but need Vivado impl control |
| **XSA type** | Fixed (from `write_hw_platform -fixed`) | Extensible → Fixed (via `v++ --link`) | Extensible → VMA → Vivado impl → Fixed |
| **AIE support** | No (UG1273: "AI Engine programming not supported") | Yes — primary flow for AIE | Yes — Versal only |
| **PL integration** | Manual IPI block design in Vivado | Automated by `v++` linker | `v++` assembles, Vivado implements |
| **BSP generation** | `hsi::generate_bsp` (pure TCL, headless) | From `v++` linker output or fixed XSA | From fixed XSA after Vivado impl |
| **PS app model** | Bare-metal/FreeRTOS register I/O (`xgpio.h`, etc.) | XRT host API (Linux) or bare-metal BSP | Same as Integrated |
| **Impl control** | Full (Vivado project) | Limited (`--vivado` options, `--to_step`) | Full (Vivado project after VMA import) |
| **Headless/batch** | Yes (`xsct`, `hsi` are pure TCL) | Yes (`v++` is pure CLI) | Yes (`v++` CLI + Vivado TCL) |
| **Device support** | Zynq US+, Versal (all) | Versal, Zynq US+ (with platform) | Versal only |
| **Skill/script** | `ps-software/SKILL.md` + `vitis_build.tcl` | `vitis-acceleration/SKILL.md` | Future: `vitis-export/SKILL.md` |

#### Workload type → flow mapping

| `workload_type` | Natural domain | Software flow |
|-----------------|---------------|---------------|
| `bare_metal_firmware` | PS | Traditional Embedded (`hsi`) |
| `linux_app` | PS | Traditional Embedded (`hsi`) |
| `rtl_logic` | PL | No PS software needed |
| `hls_kernel` | PL | Traditional if Vivado IP flow; `v++` if Vitis kernel flow |
| `stream_dsp` | AIE | **v++ required** (AIE graph compilation) |
| `vector_compute` | AIE | **v++ required** |
| `ml_inference` | AIE_ML | **v++ required** |
| `signal_chain` | AIE | **v++ required** |
| `custom_aie` | AIE | **v++ required** |

#### v++ CLI quick reference (batch/headless)

```bash
# HLS kernel compilation → .xo
v++ --mode hls --config hls_config.cfg --part <device>

# AIE graph compilation → libadf.a
v++ --mode aie --config aie_config.cfg --part <device>

# System linking (Integrated Flow) → fixed .xsa
v++ --link --platform <extensible.xsa> --config system.cfg \
    <kernel.xo> <libadf.a> -t hw -o <output.xsa>

# System linking (Export to Vivado) → .vma
v++ --link --platform <extensible.xsa> --config system.cfg \
    <kernel.xo> <libadf.a> --export_archive -o <output.vma>

# Packaging → SD card / boot image
v++ --package --platform <fixed.xsa> -t hw \
    --package.boot_mode sd -o <output>
```

**References:** UG1701 (Embedded Design Development), UG1700 (Data Center Acceleration),
UG1273 (Versal Design Guide), UG1387 (Versal HW/IP/Platform Methodology), UG1702 (Vitis Reference)

### When to re-partition vs. optimize

```
Estimation/Closure failure
  ├── Resource overflow (>95% LUT/BRAM/DSP)
  │     └── RE-PARTITION: move block to different domain
  ├── Timing violation (WNS < -0.5ns after optimization)
  │     ├── High logic levels (>15)
  │     │     └── RE-PARTITION: offload to AIE or split block
  │     └── Clock domain issue
  │           └── INVOKE: CDC analysis from external/global baselining skill (not in repo)
  ├── Power exceeded budget
  │     └── RE-PARTITION: move compute-heavy blocks to AIE (lower power/op)
  └── Functional failure
        └── ESCALATE to user with diagnostic context
```

### When to use which MCP server

| Task | Tool |
|------|------|
| RTL synthesis, implementation, timing | Vivado MCP (`vivado_execute`) |
| AMD documentation lookup | `vivado_doc_search` |
| Simulink model creation/modification | Model Composer MCP (`evaluate_matlab_code`) |
| HLS kernel dev (csim/synth/cosim/impl) | `hls-optimization` skill (Shell: `make csim/csynth/cosim/impl`) |
| HLS kernel optimization | `hls-optimization/optimize` skill |
| AIE compilation | Shell (`aiecompiler` CLI) |
| System linking | Shell (`v++` CLI) |
| Boot image | Shell (`bootgen` CLI) |

## Platform Pitfalls

**Consult `reference/platform-pitfalls.md`** before Phase 4 for device-family-specific
issues including Zynq UltraScale+ DPU pitfalls (encrypted RTL, IP cache, PFM control
master, PS8 clock accuracy) and Versal pitfalls (PS-NoC clock routing, implementation
directives, HLS data movers vs DMA IP).

## Troubleshooting

### Vivado session not responding
Use `vivado_status` to check session health. If `is_command_running` is stuck, use
`vivado_status` with `action="health"` to diagnose.

### Model Composer environment not initialized
Use `evaluate_matlab_code` with `xmcStart` to initialize. Check with `detect_matlab_toolboxes`
that Model Composer is available.

### Estimation tier keeps failing at T2
Check if HLS source is synthesizable. Use the `rtl-lint` skill on the source
first to catch common issues before running csynth.

## Field Learnings

**Consult `reference/field-learnings.md`** for hard-won operational lessons from actual
deployments, including ONNX model inspection practices, HLS memory architecture planning,
incremental hardware validation sequences, and dfx-mgr persistence risks on Kria boards.
These are NOT covered by `vivado_doc_search`.

## Related Skills

- `soc-orchestration/partitioning`: Multi-domain partitioning logic
- `soc-orchestration/estimation`: Progressive estimation T0–T3
- `soc-orchestration/ps-software`: PS firmware generation and compile-test
- `soc-orchestration/vitis-platform`: Vitis extensible platform creation (PFM properties, VDU, NoC, XSA export)
- `soc-orchestration/vitis-acceleration`: v++ kernel integration (DPU, HLS, AIE, xclbin generation)
- `hls-optimization`: Vitis HLS kernel workflow (csim → synth → cosim → ooc → optimize)
- `hls-timing-closure` / `hls-area-opt`: isolate-and-close HLS timing / rebalance HLS area
- `qor-classification`: First-Step timing-closure bottleneck classifier + FullFlow dashboard
- `timing-methodology-checks`: 55+ UG906 timing methodology checks (post-synthesis)
- `congestion-analysis`: Placement/routing congestion analysis with HTML dashboard
- `opt-design-analysis` / `phys-opt-design-analysis`: Optimization-phase log analysis
- `rtl-lint`: RTL linter (pre-synthesis)
- `rtl-elaboration-analysis`: Synthesis elaboration error/warning analysis with RTL fixes
- `versal-rtl-design-advisories`: Versal RTL design advisory checks
- Timing closure: orchestrated inline in **Phase 5** (no monolithic methodology skill); see
  `reference/closure-pattern-library.md` and `reference/device-profiles.md`
- `noc-debug`: Versal NoC error diagnosis
- `vivado-revision-control`: Project build scripts and version control
- Hardware bring-up debug (live device): `ila-vio-debug`, `noc-perfmon`, `sysmon-health-check`, `ddrmc-debug`, `ibert-link-scan`, `pcie-link-debug`
- Segmented Configuration (Versal): `segcfg-overview`, `segcfg-project-setup`, `segcfg-design-check`, `segcfg-build-images`, `segcfg-programming`, `segcfg-pl-reload`, `segcfg-firmware-build`, `segcfg-debug-guide`
- Visualization: `device-floorplan`; Skill authoring: `vivado-skill-creator`

## References

- UG1788 — Versal Adaptive SoC Design Methodology (Timing Closure)
- UG949 — UltraScale Architecture Design Methodology
- UG906 — Design Analysis and Closure Techniques
- UG1393 — Vitis Application Acceleration Development (Platform Creation, v++ Flow)
- UG1387 — Versal HW/IP/Platform Methodology
- UG1076 — Vitis AI User Guide
- PG389 — DPUCVDX8G Product Guide (Versal AI Core DPU)
- PG414 — VDU H.264/H.265 Video Decode Unit
- UG1483 — Vitis Model Composer User Guide
- `contracts/types.py` — Structured type definitions
- `specs/spec_template.md` — Design specification template
