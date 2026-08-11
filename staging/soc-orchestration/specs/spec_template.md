<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Design Specification

> Fill in each section below to define your AMD Adaptive SoC design.
> The orchestrator uses this spec to partition workloads across PS / PL / AIE / NoC,
> run the T0–T4 estimation pipeline, generate interface contracts, and drive
> implementation through to closure.
>
> **Sections are ordered by QoR impact.** Each section is tagged with a priority
> tier that reflects how frequently it is needed and how severely QoR suffers
> when it is missing or wrong:
>
> | Priority | Meaning | Frequency | Missing = |
> |----------|---------|-----------|-----------|
> | **P1 — Must Have** | Incorrect or absent → design will not close | ~100% of designs | Build failure or repartition loop |
> | **P2 — Critical** | Absent → high risk of wasted builds or poor results | ~70–90% | Degraded QoR, extra iterations |
> | **P3 — Important** | Improves results meaningfully when present | ~40–70% | Suboptimal but potentially functional |
> | **P4 — Helpful** | Nice to have; marginal QoR improvement | ~20–50% | Defaults work adequately |
> | **P5 — Situational** | Only relevant for specific design styles | ~5–30% | No impact unless applicable |

---

## 1. Target Hardware — P1

The single most foundational spec field. Every T0–T4 estimate, every resource
budget, every timing constraint, and every power calculation depends on the
exact part. A wrong speed grade alone can mean 20–30% Fmax difference.

| Field                  | Value                          |
|------------------------|--------------------------------|
| **Device Family** (required) | _One of: `versal_ai_core`, `versal_ai_edge`, `versal_ai_edge_gen2`, `versal_premium`, `zynq_ultrascale_plus`, `zynq_7000`_ |
| **Part Number** (required) | _e.g., `xcvc1902-vsva2197-2MP-e-S`_ |
| **Board** (if applicable) | _e.g., VCK190, ZCU106, VHK158, VP1902_ |
| **Speed Grade** (required) | _e.g., `-2MP`, `-1`, `-2L` — directly sets achievable Fmax_ |

### Device Selection Guidance

| Family | PS | PL | AIE | NoC | Typical Use Cases |
|--------|----|----|-----|-----|-------------------|
| Versal AI Core | Cortex-A72 + R5F | Full | AIE (1st gen) | Yes | High-throughput DSP, radar, 5G |
| Versal AI Edge | Cortex-A72 + R5F | Full | AIE-ML | Yes | Edge AI inference, sensor fusion |
| Versal AI Edge Gen2 | Cortex-A78AE + R52 | Full | AIE-ML v2 | Yes | Next-gen edge AI, automotive |
| Versal Premium | Cortex-A72 + R5F | Full | None | Yes | Networking, data center, HBM |
| Zynq UltraScale+ | Cortex-A53 + R5F | Full | None | None | Embedded, motor control, video |
| Zynq-7000 | Cortex-A9 | Full | None | None | Legacy embedded |

> **QoR rationale:** The part number determines the device resource budget
> (LUTs, DSPs, BRAMs, AIE tiles), the speed-grade timing limits, and the
> available compute domains. Picking the wrong part invalidates every
> subsequent estimation tier.

---

## 2. Clock Domains — P1

The #1 driver of timing QoR. Every nanosecond of clock period directly
determines whether WNS closes. Multiple clock domains introduce CDC paths
that are a top source of methodology violations.

| Clock Name | Target Frequency (MHz) | Domain | Notes |
|------------|----------------------|--------|-------|
| _pl_clk0_  | _300_                | PL     | _Primary PL fabric clock_ |
| _pl_clk1_  | _500_                | PL     | _High-speed datapath_ |
| _aie_clk_  | _1000_               | AIE    | _AIE array clock_ |
| _ddr_clk_  | _3200_               | NoC/DDR| _DDR4 interface rate (data rate, not clock)_ |

> **QoR rationale:** Clock frequencies set the fundamental timing
> constraints. An aggressive clock (e.g., 500 MHz PL) forces the
> orchestrator into pipelining, retiming, and potentially repartitioning
> to AIE. Missing clocks = missing constraints = unconstrained paths = false
> timing closure that fails on hardware.

---

## 3. Workload Modules — P1

The design decomposition. Each module is independently estimated and assigned
to a compute domain. Getting the workload type and parameters right is what
makes T0 estimation useful (filtering bad partitionings in <1 second).

### Module Entry Format

Repeat the subsection below for every module.

---

### Module: _[name]_

| Field | QoR Priority | Value |
|-------|-------------|-------|
| **Workload Type** | P1 | _One of: `fft`, `fir_filter`, `beamformer`, `hls_kernel`, `ps_software`, `ai_inference`, `custom_rtl`, `vision_pipeline`, `comms_chain`, `motor_control`, `power_converter`_ |
| **Workload Parameters** | P1 | _(see type-specific table below)_ |
| **Data Representation** | P1 | _One of: `fixed_point`, `floating_point`, `native_float_hdl`, `mixed`_ |
| **Word Length** (bits) | P1 | _e.g., 16 — total bit width for fixed-point_ |
| **Fraction Length** (bits) | P2 | _e.g., 14 — fractional bits_ |
| **Signed** | P2 | _yes / no_ |
| **Source Type** | P2 | _One of: `rtl_verilog`, `rtl_vhdl`, `rtl_systemverilog`, `hls_cpp`, `matlab_hdl`, `simulink_hdl`, `aie_kernel`, `aie_graph`, `deep_learning`, `ps_c_cpp`, `ps_python`, `existing_ip`_ |
| **Preferred Domain** | P2 | _(optional) `ps`, `pl`, `aie`, or blank for auto_ |
| **Source Path** | P3 | _relative path to source — enables T2/T3 estimation_ |
| **Safety Margin** (%) | P4 | _e.g., 0 — headroom on dynamic range_ |

> **QoR rationale — workload type + params (P1):** These feed the T0 parametric
> model. An FFT with 4096 points at 1 GSPS needs ~4x the resources of 1024 points
> at 100 MSPS. Wrong parameters → wrong T0 estimate → bad partitioning → wasted
> T4 builds.
>
> **QoR rationale — data type + word length (P1):** A 32-bit fixed-point FIR uses
> ~4x the DSPs and LUTs of a 16-bit version. Native floating-point HDL can cost
> 5–10x more area than fixed-point. This field has a **multiplicative** effect on
> every resource and timing estimate.
>
> **QoR rationale — source type (P2):** Determines the tool flow (HLS csynth vs
> Vivado OOC vs AIE mapper). If the orchestrator misidentifies the source type, T2
> estimation runs the wrong tool entirely.

**Workload Parameters** (type-specific — include all that apply):

| Workload Type | Key Parameters |
|---------------|----------------|
| FFT | `points`, `channels`, `rate_msps`, `use_aie` |
| FIR Filter | `taps`, `channels`, `rate_msps`, `use_aie` |
| Beamformer | `inputs` (antenna channels), `beams`, `rate_msps` |
| HLS Kernel | `lut_estimate`, `dsp_estimate`, `bram_estimate`, `clock_mhz`, `initiation_interval` |
| PS Software | `cpu_pct`, `mem_mb`, `os` (`linux` / `freertos` / `baremetal`) |
| AI Inference | `model_name`, `input_shape`, `precision` (`int8` / `bfloat16` / `fp32`), `throughput_fps` |
| Custom RTL | `lut_estimate`, `ff_estimate`, `dsp_estimate`, `bram_estimate`, `uram_estimate` |
| Vision Pipeline | `resolution`, `frame_rate_fps`, `pixel_depth`, `algorithm` |
| Comms Chain | `modulation`, `symbol_rate_msps`, `coding` |
| Motor Control | `pwm_freq_khz`, `control_loop`, `adc_channels`, `update_rate_khz` |
| Power Converter | `topology`, `switching_freq_khz`, `model_type` |

| Parameter | Value |
|-----------|-------|
| _e.g., points_ | _1024_ |
| _e.g., channels_ | _4_ |
| _e.g., rate_msps_ | _500_ |

---

**HDL Optimization Directives — P2** (per module):

| Directive | QoR Impact | Value |
|-----------|-----------|-------|
| **Distributed Pipelining** | _Highest — #1 optimization for timing closure_ | _yes / no_ |
| **Input Pipelining** (stages) | _High — reduces critical path at module boundary_ | _e.g., 1_ |
| **Output Pipelining** (stages) | _High_ | _e.g., 1_ |
| **Resource Sharing** | _High — #1 optimization for area closure_ | _e.g., share multipliers_ |
| **RAM Mapping** | _Medium — BRAM vs distributed affects routing congestion_ | _e.g., map delay lines to BRAM_ |
| **Loop Unroll Factor** | _Medium — for HLS kernels, trades area for throughput_ | _e.g., 4_ |
| **HLS Pragmas** | _Medium — fine-grained HLS control_ | _e.g., `#pragma HLS PIPELINE II=1`_ |

> **QoR rationale:** Distributed pipelining is the single most impactful
> optimization for meeting timing on PL. Resource sharing is the single most
> impactful optimization for fitting within area budgets. These two directives
> together determine whether ~50% of marginal designs close or fail.

---

**Module Constraints — P3:**

| Constraint | Value |
|------------|-------|
| Max latency | _e.g., 10 us_ |
| Min throughput | _e.g., 1 GSPS_ |
| Resource ceiling | _e.g., max 50% DSP utilization_ |

---

_Copy the module block above for each additional module._

---

## 4. Optimization Priority — P1

The global speed/area/power tradeoff. This fundamentally changes what the
orchestrator does when estimation tiers fail.

| Field | Value |
|-------|-------|
| **Optimization Priority** (required) | _One of: `speed` (maximize Fmax), `area` (minimize resources), `power` (minimize dynamic power), `balanced` (default)_ |

> **QoR rationale:** When T2 shows a module doesn't meet Fmax:
> - **speed** → add pipelining, repartition to AIE, increase parallelism
> - **area** → add resource sharing, reduce unroll factor, accept lower Fmax
> - **power** → move compute from PL to AIE (lower power per MAC), reduce clock
>
> Getting this wrong means the orchestrator optimizes in exactly the opposite
> direction from what the designer needs.

---

## 5. Power and Thermal Budget — P2

| Field | Value |
|-------|-------|
| **Power Budget** (watts) | _e.g., 35_ |
| **Ambient Temperature** (°C) | _default: 25_ |
| **Thermal Solution** | _e.g., active heatsink, passive, fan-cooled enclosure_ |
| **Airflow** (LFM) | _e.g., 200_ |

> **QoR rationale:** Gates the T1 (PDM) estimation tier. Without a power
> budget, the orchestrator cannot filter thermally infeasible partitionings.
> Designs that pass T0–T3 but exceed the thermal envelope at T4 waste hours
> of build time. A tight power budget also forces PL→AIE migration, which
> changes the entire partitioning landscape.

---

## 6. Cross-Domain Interfaces — P2

Interface widths and clock domains between modules directly affect timing
(CDC crossings), resource usage (FIFOs, clock converters), and throughput.

### Cross-Domain Interfaces

| Source Module | Source Domain | Sink Module | Sink Domain | Interface Type | Data Width (bits) | Clock (MHz) | Notes |
|---------------|---------------|-------------|-------------|---------------|-------------------|-------------|-------|
| _fft_engine_  | _aie_         | _detector_  | _pl_        | `axi4_stream` | _128_             | _300_       |       |
| _controller_  | _ps_          | _fft_engine_| _aie_       | `plio`        | _64_              | _312.5_     |       |

**Interface types**: `axi4_mm`, `axi4_stream`, `plio`, `noc_nmu_nsu`, `gpio`

> **QoR rationale:** Wrong PLIO widths can bottleneck AIE throughput by 2–4x.
> Wrong AXI widths waste BRAM on unnecessarily wide FIFOs. Cross-clock-domain
> interfaces that aren't properly constrained cause CDC methodology violations
> — the #1 source of report_methodology failures in real designs.

### Memory Interfaces — P2

| Interface | Type | Data Rate | Capacity | Controller | Notes |
|-----------|------|-----------|----------|------------|-------|
| _ddr0_    | _DDR4_ | _3200 MT/s_ | _4 GB_ | _NoC DDRMC_ | _Primary system memory_ |
| _hbm_     | _HBM2e_ | _460 GB/s_ | _8 GB_ | _NoC HBM_ | _High-bandwidth path_ |

> **QoR rationale:** DDR controller configuration directly affects NoC routing,
> power consumption, and system bandwidth. Memory bottlenecks are the #1
> performance limiter in data-intensive designs.

### External I/O — P3

| Port Name | Standard | Direction | Width | Package Pin | Bank | Notes |
|-----------|----------|-----------|-------|-------------|------|-------|
| _adc_data_ | _LVDS_  | _input_   | _16_  |             |      | _ADC differential pairs_ |
| _dac_out_  | _LVCMOS18_ | _output_ | _8_ |             |      |       |

### High-Speed Serial — P3

| Interface | Protocol | Line Rate | Lanes | Transceiver | Notes |
|-----------|----------|-----------|-------|-------------|-------|
| _aurora0_ | _Aurora 64B/66B_ | _25.78 Gbps_ | _4_ | _GTY_ | _Inter-FPGA link_ |
| _pcie0_   | _PCIe Gen4_ | _16 GT/s_ | _8_ | _GTY/GTYP_ | _Host interface_ |

---

## 7. Design Goals and Success Criteria — P2

The acceptance criteria the orchestrator uses at every gate from T0 through T4.
Without explicit targets, the orchestrator uses defaults that may be too
aggressive (causing unnecessary repartitioning) or too lenient (passing designs
that fail on hardware).

| Metric | Target | Hard Limit | QoR Priority |
|--------|--------|------------|-------------|
| **WNS** (Worst Negative Slack) | _>= 0.0 ns_ | _>= -0.5 ns before repartition_ | P1 |
| **WHS** (Worst Hold Slack) | _>= 0.0 ns_ | | P2 |
| **Total Power** | _< 35 W_ | _< 40 W_ | P2 |
| **PL Utilization (LUTs)** | _< 70%_ | _< 85%_ | P1 |
| **DSP Utilization** | _< 80%_ | _< 95%_ | P2 |
| **BRAM/URAM Utilization** | _< 80%_ | _< 95%_ | P2 |
| **AIE Tile Utilization** | _< 85%_ | _< 95%_ | P2 |
| **Congestion Level** | _none / low_ | _medium (triggers restructuring)_ | P2 |
| **QoR Score** | _>= 3 (out of 5)_ | _>= 2_ | P3 |

> **QoR rationale:** LUT utilization targets and WNS hard limits are the two
> most frequently hit gates during the estimation pipeline. Designs that target
> >85% LUT utilization almost always hit congestion, and designs with WNS < -0.5ns
> at T3 almost never recover at T4.

---

## 8. Synthesis and Optimization Strategy — P2

Global Vivado strategy selection and HDL generation settings. Choosing the
right synthesis and implementation strategies can be the difference between
closing at an aggressive clock and failing.

| Field | QoR Priority | Value |
|-------|-------------|-------|
| **Synthesis Strategy** | P2 | _e.g., `Flow_PerfOptimized_high`, `Flow_AreaOptimized_high`, or default_ |
| **Implementation Strategy** | P2 | _e.g., `Performance_ExploreWithRemap`, `Area_ExploreSequential`, or default_ |
| **HDL Language** | P4 | _`verilog`, `systemverilog`, or `vhdl`_ |
| **Target Workflow** | P3 | _One of: `generic_fpga`, `ip_core_generation`, `fpga_in_the_loop`, `asic`_ |
| **Max Build Cores** | P4 | _number of CPU cores for parallel synthesis/implementation_ |
| **IP Caching** | P4 | _yes / no — cache OOC-synthesized IP to speed subsequent builds_ |

> **QoR rationale:** `Flow_PerfOptimized_high` enables retiming and advanced
> optimizations that can recover 10–20% Fmax over default strategies.
> `Performance_ExploreWithRemap` at implementation can close designs that
> fail with default placement. These are the first levers the orchestrator
> pulls when T3 shows marginal timing.

---

## 9. Constraint Files — P2

Pre-existing constraints that the orchestrator must honor. User-provided
timing constraints override auto-generated ones and prevent constraint
conflicts that cause false timing closure.

| File Path | Type | Scope | Notes |
|-----------|------|-------|-------|
| _constraints/timing.xdc_ | `timing` | _all modules_ | _Primary clock definitions_ |
| _constraints/pins.xdc_ | `physical` | _top-level_ | _Package pin assignments and I/O standards_ |
| _constraints/floorplan.xdc_ | `physical` | _per-module_ | _Pblock assignments_ |
| _constraints/dfx_pblock.xdc_ | `dfx` | _DFX partitions_ | _RP pblock definitions_ |
| _constraints/timing.sdc_ | `sdc` | _ASIC flow_ | _For Cadence Genus / ASIC targets_ |

**Constraint types**: `timing`, `physical`, `dfx`, `sdc`, `bitstream`, `power`, `debug`

> **QoR rationale:** Missing timing constraints cause unconstrained paths —
> Vivado doesn't optimize what it doesn't know about. Conflicting constraints
> (e.g., two different create_clock on the same net) cause methodology
> violations. User-provided constraints take precedence to avoid these issues.

---

## 10. NoC Configuration — P3 (Versal only)

| Field | Value |
|-------|-------|
| **NoC Flow** | _IPI (IP Integrator) or RTL (Modular NoC)_ |
| **Traffic Class** | _best_effort, low_latency, isochronous_ |
| **Read Bandwidth** | _e.g., 12.8 GB/s_ |
| **Write Bandwidth** | _e.g., 6.4 GB/s_ |
| **Exclusive Routing** | _yes / no — for deterministic latency paths_ |
| **Address Remap** | _describe if non-default address mapping needed_ |

> **QoR rationale:** NoC QoS class directly affects achievable bandwidth and
> latency. Isochronous traffic requires reserved bandwidth that constrains NoC
> routing. Wrong traffic class = missed real-time deadlines. Affects ~50% of
> Versal designs.

---

## 11. Floorplan and Physical Constraints — P3

| Constraint Type | Details |
|-----------------|---------|
| **Pblock Assignments** | _Module-to-region mappings for critical modules_ |
| **SLR Strategy** | _Per-SLR allocation for multi-die devices (LAGUNA column reservations)_ |
| **Congestion Avoidance** | _Utilization ceilings per region_ |
| **Clock Region Sharing** | _Modules sharing clock regions (relevant for DFX)_ |

> **QoR rationale:** Floorplanning is critical for designs >70% utilization
> or multi-SLR devices. Poor placement causes routing congestion — the #1
> non-timing QoR problem in large designs. However, for small-to-medium
> designs Vivado's placer handles this well without user guidance.

---

## 12. Application Domain — P3

| Field | Value |
|-------|-------|
| **Primary Domain** | _One of: `dsp_signal_processing`, `communications`, `radar_electronic_warfare`, `vision_image_processing`, `ai_ml_inference`, `motor_control`, `power_electronics`, `networking`, `data_center`, `automotive`, `aerospace_defense`, `medical`, `test_measurement`, `general_purpose`_ |
| **Secondary Domain** | _(optional) for multi-domain designs_ |
| **Industry Standard** | _(optional) e.g., DO-254 (avionics), IEC 61508 (industrial), ISO 26262 (automotive)_ |
| **Reference Design** | _(optional) name of an existing AMD reference design to build upon_ |

> **QoR rationale:** Domain informs partitioning heuristics (e.g., DSP → AIE,
> motor control → low-latency PL). The orchestrator can infer this from the
> module list, so this field accelerates partitioning rather than enabling it.
> Industry standards affect coding style and verification but not synthesis QoR.

---

## 13. Design Identity — P4

| Field         | Value                          |
|---------------|--------------------------------|
| **Name** (required) | _e.g., Radar Signal Processing Chain_ |
| **Description**     | _1–3 sentence summary of system function and performance goals_ |
| **Author**          | _team or individual_           |
| **Date**            |                                |
| **Revision**        | _spec version, e.g., 0.1_     |

> **QoR rationale:** Zero direct QoR impact. Important for tracking and
> reproducibility, but the orchestrator produces identical results whether
> this is filled in or left empty.

---

## 14. Verification and Software — P4

Verification does not directly change synthesis/implementation QoR, but CDC
analysis (P2 within this section) catches cross-clock-domain issues that
cause real hardware failures.

### Simulation — P4

| Field | Value |
|-------|-------|
| **Simulation Required** | _yes / no_ |
| **Simulation Tool** | _Vivado XSIM, QuestaSim/ModelSim, VCS, Riviera-PRO_ |
| **Testbench Language** | _SystemVerilog, VHDL, MATLAB, Simulink_ |
| **Cosimulation** | _yes / no — HDL cosim with MATLAB/Simulink via HDL Verifier_ |
| **FPGA-in-the-Loop** | _yes / no — verify on real FPGA hardware during development_ |
| **FIL Connection** | _Ethernet, JTAG, PCI Express, USB Ethernet_ |

### RTL Quality Checks — P3 (CDC is P2)

| Field | QoR Priority | Value |
|-------|-------------|-------|
| **CDC Analysis** | P2 | _yes / no — clock domain crossing verification_ |
| **RTL Lint** | P3 | _yes / no — static analysis of generated HDL_ |
| **Lint Tool** | P4 | _SpyGlass, Ascent Lint, or Vivado built-in_ |
| **Code Coverage** | P4 | _yes / no — statement, branch, toggle, FSM_ |
| **Compliance Standard** | P4 | _e.g., DO-254, IEC 61508, ISO 26262, none_ |

### Software and Deployment — P4

| Field | Value |
|-------|-------|
| **PS Software Flow** | _PetaLinux, Vitis Embedded (baremetal/FreeRTOS), none_ |
| **XSA Export** | _yes / no_ |
| **Boot Mode** | _JTAG, QSPI, eMMC, OSPI, SD, USB_ |
| **Programming Method** | _JTAG, SD card download, flash programming_ |
| **Debug Insertion** | _none, ILA, VIO, FPGA data capture_ |
| **Debug Connection** | _JTAG, PL Ethernet, PS Ethernet_ |

---

## 15. IP Core Packaging — P4

Fill only if the design should be packaged as a reusable IP core.

| Field | Value |
|-------|-------|
| **IP Core Name** | _e.g., my_fft_core_ |
| **IP Core Version** | _e.g., 1.0_ |
| **IP Repository Path** | _(optional) path to store the packaged IP_ |
| **AXI Interface** | _One of: `axi4_lite`, `axi4`, `axi4_stream`, `none`_ |
| **Register Map** | _list of control/status registers with addresses and widths_ |
| **Clock Domain Crossing** | _yes / no — enable CDC on AXI-Lite registers_ |
| **Generate IP Documentation** | _yes / no_ |

> **QoR rationale:** Affects integration quality in the T4 full build but
> not individual module resource or timing results. The AXI interface type
> does affect routing and area marginally.

---

## 16. Estimation Strategy — P4

Override the default estimation pipeline behavior if needed.

| Field | Value |
|-------|-------|
| **Skip Tiers** | _e.g., skip T1 if no power budget specified_ |
| **T3 Modules** | _list specific modules for OOC synthesis, or "all PL modules"_ |
| **Parallel OOC Jobs** | _number of concurrent T3 synthesis runs (default: 4)_ |
| **Max Repartition Iterations** | _default: 3_ |
| **Estimation Timeout** | _max minutes for the T0–T3 pipeline (default: 30)_ |

> **QoR rationale:** Defaults work well for most designs. Tuning these helps
> wall-clock time but doesn't change the final QoR. The exception is
> increasing max repartition iterations for very constrained designs.

---

## 17. DFX / Partial Reconfiguration — P5

Fill only if the design uses Dynamic Function eXchange (~5–10% of designs).

| Field | Value |
|-------|-------|
| **Number of Reconfigurable Partitions** | _e.g., 2_ |
| **DFX Flow** | _IPI BDC (Block Design Container) or RTL-based_ |
| **Abstract Shell** | _yes / no — for per-SLR parallel compilation_ |
| **Decoupling Strategy** | _DFX Decoupler, AXI Shutdown Manager, or manual_ |

### Reconfigurable Partition Table

| RP Name | Pblock Region | Modules (RMs) | Static Interface | Notes |
|---------|---------------|---------------|------------------|-------|
| _rp_slr0_ | _SLR0 pblock_ | _rm_algo_v1, rm_algo_v2_ | _AXI4-MM_ | |

### DFX Constraints

- Separate constraint sets for parent vs. child implementations
- PACKAGE_PIN / IOSTANDARD reapplication for embedded IOBs in RPs
- USER_SLL_REG for SLR crossing registers (UltraScale+ multi-die)
- CLOCK_DEDICATED_ROUTE for cross-SLR clocking in RMs

> **QoR rationale:** Critical when applicable — DFX adds significant
> constraints on placement, routing, and timing. But the vast majority
> of designs don't use DFX, making this P5 by frequency despite being
> P1-level impact when present.

---

## 18. Methodology and Reference Documents — P5

| Document | ID | Relevance |
|----------|----|-----------|
| _Vivado Synthesis_ | _UG901_ | _Synthesis attributes and coding style_ |
| _Timing Closure (UltraScale)_ | _UG949_ | _Timing methodology and QoR baseline_ |
| _Timing Closure (Versal)_ | _UG1788_ | _Versal-specific timing closure_ |
| _Partial Reconfiguration_ | _UG947_ | _DFX tutorial and constraints_ |
| _NoC / DDRMC_ | _PG313_ | _NoC IP configuration_ |
| _Power Analysis_ | _UG907_ | _Power estimation methodology_ |
| _Methodology Report_ | _UG906_ | _Timing and CDC checks_ |

> **QoR rationale:** The orchestrator already encodes methodology knowledge
> from these documents. Listing them helps human reviewers but has zero
> impact on automated QoR.

---

## QoR Priority Summary

| Priority | Sections | Key Fields | Why |
|----------|----------|------------|-----|
| **P1** | 1, 2, 3, 4 | Part number, speed grade, clock frequencies, workload type + params, word length, optimization priority | Wrong → design cannot close. These determine resource budget, timing targets, and partitioning strategy. |
| **P2** | 3, 5, 6, 7, 8, 9 | Data precision details, source type, preferred domain, optimization directives, power budget, cross-domain interfaces, memory interfaces, success criteria, synthesis strategy, constraint files, CDC analysis | Missing → high risk of wasted builds. These refine estimation accuracy and catch infeasible designs earlier in the T0–T3 pipeline. |
| **P3** | 3, 6, 7, 10, 11, 12, 14 | Module constraints, external I/O, serial links, NoC config, floorplan, application domain, RTL lint | Missing → suboptimal but potentially functional. These improve results for specific design styles. |
| **P4** | 3, 8, 13, 14, 15, 16 | Safety margin, HDL language, build cores, IP caching, design identity, simulation, deployment, IP packaging, estimation tuning | Missing → defaults work adequately. These improve process efficiency more than QoR. |
| **P5** | 17, 18 | DFX, methodology references | Only relevant for specific design styles (DFX) or humans (doc references). |

---

## JSON Equivalent

The sections above map to the following JSON structure consumed by the
`amd-soc-orchestrator` CLI. You may author your spec in either format.

```json
{
  "name": "Radar Signal Processing Chain",
  "description": "4-channel pulsed radar with FFT, CFAR detection, and track management",
  "application_domain": "radar_electronic_warfare",
  "target_device": "xcvc1902-vsva2197-2MP-e-S",
  "device_family": "versal_ai_core",
  "modules": [
    {
      "name": "fft_engine",
      "workload_type": "fft",
      "source_type": "aie_graph",
      "params": {
        "points": 1024,
        "channels": 4,
        "rate_msps": 500,
        "use_aie": true
      },
      "data_type": {
        "representation": "fixed_point",
        "word_length": 16,
        "fraction_length": 14,
        "signed": true
      },
      "source_path": "src/aie/fft_graph.cpp"
    },
    {
      "name": "cfar_detector",
      "workload_type": "custom_rtl",
      "source_type": "rtl_systemverilog",
      "params": {
        "lut_estimate": 12000,
        "ff_estimate": 8000,
        "dsp_estimate": 32,
        "bram_estimate": 16
      },
      "data_type": {
        "representation": "fixed_point",
        "word_length": 18,
        "fraction_length": 16,
        "signed": true
      },
      "optimization": {
        "distributed_pipelining": true,
        "ram_mapping": "bram"
      },
      "source_path": "src/rtl/cfar_detector.sv"
    },
    {
      "name": "track_manager",
      "workload_type": "ps_software",
      "source_type": "ps_c_cpp",
      "params": {
        "cpu_pct": 30,
        "mem_mb": 256,
        "os": "linux"
      }
    }
  ],
  "clock_targets_mhz": {
    "pl_clk0": 300,
    "pl_clk1": 500,
    "aie_clk": 1000
  },
  "power_budget_watts": 35,
  "ambient_temp_c": 25,
  "optimization_priority": "speed",
  "hdl_language": "systemverilog",
  "constraint_files": [
    "constraints/timing.xdc",
    "constraints/pins.xdc"
  ]
}
```

---

## Appendix A: Workload Type Reference

| Workload Type | Domain Affinity | Key Parameters | Estimation Models Available |
|--------------|----------------|----------------|----------------------------|
| `fft` | AIE (primary), PL | points, channels, rate_msps | T0 analytic, T2 AIE map / HLS csynth |
| `fir_filter` | AIE (primary), PL | taps, channels, rate_msps | T0 analytic, T2 AIE map / HLS csynth |
| `beamformer` | AIE | inputs, beams, rate_msps | T0 analytic, T2 AIE map |
| `hls_kernel` | PL | lut/dsp/bram estimates, clock_mhz, II | T0 analytic, T2 HLS csynth, T3 OOC synth |
| `ps_software` | PS | cpu_pct, mem_mb, os | T0 analytic, T1 PDM power |
| `ai_inference` | AIE (primary), PL | model, precision, throughput | T0 analytic, T2 AIE map |
| `custom_rtl` | PL | resource estimates | T0 analytic, T3 OOC synth |
| `vision_pipeline` | PL (primary), AIE | resolution, frame_rate, pixel_depth, algorithm | T0 analytic, T2 HLS csynth |
| `comms_chain` | PL + AIE | modulation, symbol_rate, coding | T0 analytic, T2 HLS/AIE |
| `motor_control` | PL (low-latency) | pwm_freq, control_loop, adc_channels | T0 analytic, T2 HLS csynth |
| `power_converter` | PL (HIL simulation) | topology, switching_freq, model_type | T0 analytic, T2 HLS csynth |

### Source Type Reference

| Source Type | Description | Tool Flow | Estimation Path |
|-------------|-------------|-----------|-----------------|
| `rtl_verilog` | Hand-written Verilog | Vivado synthesis | T3 OOC synth |
| `rtl_vhdl` | Hand-written VHDL | Vivado synthesis | T3 OOC synth |
| `rtl_systemverilog` | Hand-written SystemVerilog | Vivado synthesis | T3 OOC synth |
| `hls_cpp` | C/C++ for Vitis HLS | HLS csynth → Vivado | T2 HLS csynth, T3 OOC |
| `matlab_hdl` | MATLAB function (HDL Coder) | HDL Coder → Vivado | T2 via generated RTL |
| `simulink_hdl` | Simulink model (HDL Coder) | HDL Coder → Vivado | T2 via generated RTL |
| `aie_kernel` | AIE C++ kernel | AIE compiler | T2 AIE map |
| `aie_graph` | AIE graph (adaptive dataflow) | AIE compiler + linker | T2 AIE map |
| `deep_learning` | DNN model (MATLAB Deep Learning) | HDL Coder DL → Vivado | T2 HLS csynth |
| `ps_c_cpp` | PS application (C/C++) | Vitis / PetaLinux | T0 only |
| `ps_python` | PS application (Python) | PetaLinux | T0 only |
| `existing_ip` | Pre-packaged IP (XCI/XCIX) | Vivado IP flow | T3 OOC synth |

## Appendix B: Interface Type Reference

| Interface Kind | Cross-Domain Use | Typical Data Width | Notes |
|---------------|------------------|-------------------|-------|
| `axi4_mm` | PS-PL, PL-NoC | 32/64/128 bits | Memory-mapped, burst-capable |
| `axi4_stream` | PL-PL, PL-AIE | 32/64/128/256 bits | Streaming datapath |
| `plio` | PL-AIE | 32/64/128 bits | Physical-level I/O to AIE array |
| `noc_nmu_nsu` | Any-NoC | 128 bits | NoC master/slave units |
| `gpio` | PS-PL | 1–32 bits | Control/status registers |

## Appendix C: Design Patterns from Tutorials

| Pattern | Source | QoR Priority | Spec Sections |
|---------|--------|-------------|---------------|
| Fixed-point conversion and HDL code gen | HDL Coder | P1 | 3 (data types) |
| Clock domain definitions and constraints | Vivado tutorials | P1 | 2, 9 |
| HDL optimization (pipeline, sharing, RAM) | HDL Coder Design Patterns | P2 | 3 (directives), 8 |
| IPI block design with CIPS + NoC + DDRMC | Versal / IP_Integrator | P2 | 1, 6, 10 |
| Modular NoC with exclusive routing | Versal / Memory_and_NoC / RTL | P3 | 10 |
| HBM via BLI/VNOC endpoints | Versal / Memory_and_NoC / NoC_HBM | P3 | 6, 10 |
| Abstract shell per-SLR compilation | UltraScalePlus / DFX | P3 | 11, 17 |
| Aurora / GT Subsystem serial links | Versal / High_Speed_Serial | P3 | 6 |
| Advanced I/O Wizard (LVDS) | Versal / IO_Design | P3 | 6 |
| PCIe migration to Transceivers Wizard | Versal / PCI_Express | P3 | 6 |
| IP core generation with AXI interface | HDL Coder IP Core workflow | P4 | 15 |
| Cosimulation and FPGA-in-the-loop | HDL Coder + HDL Verifier | P4 | 14 |
| Vision HDL (Sobel, median, HDR) | Vision HDL Toolbox | P4 | 3 (vision_pipeline) |
| Wireless HDL (OFDM, Viterbi) | Wireless HDL Toolbox | P4 | 3 (comms_chain) |
| Motor control (FOC, PID on FPGA) | HDL Coder Motor Control | P4 | 3 (motor_control) |
| Power electronics HIL | Simscape-to-HDL | P4 | 3 (power_converter) |
| DFX with BDC and per-RP constraints | General/Versal DFX | P5 | 17 |
| Debug insertion (ILA, VIO) | Versal / HW_Debug | P5 | 14 |
| Boot mode and PDI delivery | Versal / Boot_and_Config | P5 | 14 |
| Revision control and build scripts | General / Revision_Control | P5 | (infrastructure) |
