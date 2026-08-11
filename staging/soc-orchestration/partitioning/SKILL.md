---
name: soc-orchestration/partitioning
description: Multi-domain partitioning sub-skill — assigns functional blocks to PS, PL, AIE, or AIE-ML based on workload type, device resources, and design constraints.
metadata:
  category: amd-soc-design
  tier: domain
  tags:
    - partitioning
    - soc
    - ps
    - pl
    - aie
    - domain-mapping
    - versal
    - zynq
  complexity: intermediate
  estimated_duration: 5-15 minutes
  related_skills:
    - soc-orchestration
    - soc-orchestration/estimation
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# SKILL: Multi-Domain Partitioning

## Overview

This skill assigns each functional block in a design specification to a compute domain
(PS, PL, AIE, AIE-ML, DPU) on an AMD SoC. It uses `WorkloadType.natural_domain` as a
starting point, then refines assignments based on device resource availability, latency
requirements, power budget, and inter-block communication patterns.

**You are making the partitioning decisions.** Use the structured types, device data from
Vivado, and your reasoning to produce a `PartitionPlan`.

## Prerequisites

- **MCP servers available:**
  - `vivado` — for device resource queries (`vivado_execute`)
  - `vivado-doc-search` — for device family documentation
- **Structured types** from `contracts/types.py`:
  - Input: `DesignSpec` (blocks with `workload_type`, constraints, target device)
  - Output: `PartitionPlan` (assignments with domain + rationale)

## Task: Partition a Design

### Step 1 — Query Device Resources

First, confirm the device part exists. Then query its resources.

```tcl
# Validate device exists (run via vivado_execute)
puts [get_parts <target_device>]
# e.g., get_parts xck26-sfvc784-2LV-c → returns the part or empty

# For Zynq UltraScale+ (xck26, xck24, etc.), key resources from DS987/DS985:
# - K26: 256K logic cells, 117K LUTs, 234K FFs, 1248 DSPs, 144 BRAMs, 64 URAMs
# - K24: 154K logic cells, 67K LUTs, 134K FFs, 360 DSPs, 48 BRAMs, 0 URAMs
#
# For Versal AI Core (xcvc1902 on VCK190):
# - 899K LUTs, 1.8M FFs, 1968 DSPs, 967 BRAMs, 463 URAMs, 400 AIE cores
#
# Use vivado_doc_search to look up exact numbers for unfamiliar devices.
```

For PS+PL designs (Zynq family), check whether the device has a PS8 (UltraScale+)
or CIPS (Versal) hard block — this determines the block design flow.

Parse the output to build a resource budget.

### Step 2 — Initial Assignment via natural_domain

For each `FunctionalBlock` in the spec, start with the `workload_type.natural_domain`:

| WorkloadType | natural_domain | Rationale |
|-------------|---------------|-----------|
| `control_logic` | PS | Low-latency control best on Arm cores |
| `os_application` | PS | Needs Linux/OS stack |
| `bare_metal_firmware` | PS | Runs on Arm R-class |
| `stream_dsp` | AIE | High-throughput streaming DSP |
| `vector_compute` | AIE | VLIW vector operations |
| `ml_inference` | AIE_ML | INT8/INT4 MAC arrays |
| `signal_chain` | AIE | Multi-stage signal processing |
| `video_pipeline` | PL | Frame-buffer / pixel-parallel |
| `packet_processing` | PL | Wire-speed packet inspection |
| `sensor_interface` | PL | Direct I/O pad connection |
| `memory_controller` | PL | Custom memory timing |
| `crypto_accelerator` | PL | Constant-time HW implementation |
| `compression` | PL | Bit-manipulation heavy |
| `protocol_bridge` | PL | Protocol conversion logic |
| `motor_control` | PL | Inner current loop needs sub-µs latency; only PL can guarantee this |
| `custom_pl` | PL | User-specified PL |
| `custom_aie` | AIE | User-specified AIE |
| `custom_ps` | PS | User-specified PS |

### Step 3 — Resource Feasibility Check

For each domain, sum the estimated resource requirements of all assigned blocks:

**PL domain:**
- Total LUTs vs. device LUT_COUNT (target < 70% for routability)
- Total BRAMs vs. BLOCKRAM_TILE_COUNT
- Total DSPs vs. DSP_SLICE_COUNT
- **Total I/O pins vs. device available IOBs** — this is critical for SOM devices:
  - K24 (xck24): only 81 I/O pins total
  - K26 (xck26): ~240 I/O pins
  - VCK190 (xcvc1902): ~500+ I/O pins
  - Count all top-level ports: clocks, resets, data buses, control signals
  - For PL-only designs: every RTL port maps to a physical pin
  - For PS+PL designs: parameters/control come via AXI (no pins needed for those)

**AIE domain:**
- Total AIE kernels vs. AIE_CORE_COUNT
- Total memory vs. AIE local memory budget

**PS domain:**
- Number of concurrent threads vs. core count
- Memory bandwidth requirements

**I/O pin overflow resolution:**
If the standalone RTL requires more pins than the device provides, the design MUST be
wrapped in a PS+PL block design where PS delivers control/parameters via AXI-Lite registers
instead of dedicated pins. This is a very common scenario on SOM devices (K24/K26).
Alternatively, use OOC synthesis mode for T3 validation (no pin placement required).

If any domain exceeds its budget, proceed to Step 4.

### Step 4 — Reassignment Heuristics

When a domain is over-budget, apply these rules in order:

1. **Spill PL → AIE**: If PL DSP usage > 80% and target has AIE cores, move
   `stream_dsp` or `signal_chain` blocks to AIE.

2. **Spill AIE → PL**: If AIE core count exceeded, move least-streaming blocks
   (e.g., simple filters) to PL HLS implementation.

3. **Spill PS → PL**: If PS compute budget exceeded, offload
   `motor_control` or `control_logic` to PL soft-processor or FSM.

4. **Split large blocks**: If a single block dominates a domain, recommend splitting
   it into pipelined stages across domains.

For each reassignment, record the rationale in the `PartitionAssignment.rationale` field.

### Step 5 — Cross-Domain Interface Analysis

For every pair of blocks in different domains, determine the interface:

| Source → Dest | Interface Type | Notes |
|--------------|---------------|-------|
| PS → PL | AXI4 / AXI-Lite | Memory-mapped or register access |
| PL → PS | AXI4 / interrupt | DMA or interrupt-driven |
| PL → AIE | PLIO / GMIO | Streaming or memory-mapped |
| AIE → PL | PLIO | Streaming output |
| PS → AIE | GMIO (via NoC) | Memory-mapped through NoC |
| AIE → PS | GMIO (via NoC) | Results back to PS |

Record each cross-domain interface in `PartitionPlan.cross_domain_interfaces`.

### Step 6 — Emit PartitionPlan

Produce a JSON object matching the `PartitionPlan` schema:

```json
{
  "assignments": [
    {
      "block_name": "fft_engine",
      "domain": "AIE",
      "rationale": "512-pt streaming FFT maps efficiently to AIE vector cores; device has 400 AIE cores available",
      "estimated_resources": {"aie_cores": 4, "memory_kb": 128}
    }
  ],
  "cross_domain_interfaces": [
    {
      "source": "data_ingress",
      "dest": "fft_engine",
      "type": "PLIO",
      "width_bits": 128,
      "clock_mhz": 312.5
    }
  ],
  "warnings": []
}
```

## Validation

After generating the partition plan, verify:

1. Every block in the spec has exactly one assignment.
2. No domain exceeds 80% of available resources (with estimates).
3. All cross-domain interfaces have compatible clock domains.
4. Power estimate (sum of domain budgets) is within `power_budget_watts`.

## Common Patterns

- **Versal designs** typically use PS for control, AIE for DSP/ML, PL for I/O and glue.
- **Zynq UltraScale+** has no AIE — all compute splits between PS and PL.
- **If the device has no AIE cores**, all AIE-natural workloads must go to PL (HLS).
- **DPU blocks** are soft IP instantiated in PL — count them against PL resources.
- **Motor control**: Inner current loop (Clarke/Park/SVM) goes to PL for deterministic
  sub-µs latency; outer speed/position loops can run on PS under FreeRTOS.

### AIE DSP Library Throughput (from actual builds)

When partitioning streaming DSP chains (FFT, FIR, etc.) to AIE using the AMD DSP
Library (`dsplib::fft::dit_1ch`, `dsplib::fir::sr_sym`):
- **PLIO at 128-bit / 312.5 MHz** provides ~5 GB/s per interface — sufficient for
  4-channel parallel processing of cint16 data
- A 4-channel radar chain (demux → 4×(1024-pt FFT → 64-tap FIR) → mux) uses ~50 AIE
  columns on xcvc1902 (400 AIE cores available)
- DSP Library graphs compile with `v++ --mode aie` and integrate seamlessly with HLS
  kernels via PLIO `stream_connect` directives in `system.cfg`

### Data Movement Pattern for v++ Flows

For AIE+HLS designs using `v++ --link`, prefer **custom HLS data movers** (mm2s/s2mm)
over platform-embedded `axi_dma` IP:
- HLS data movers are v++ kernels (`.xo`), instantiated via `nk=` and connected via
  `stream_connect=` and `sp=` directives
- This avoids polluting the platform BD with DMA IP, interrupt routing, and fixed
  AXI interconnects that conflict with v++ linker automation
- 128-bit AXI-Stream width naturally matches AIE PLIO width

## Software Build Flow Implications

The partition directly determines the downstream software build flow (per AMD UG1701,
UG1273). Record this in the `PartitionPlan` so Phase 4b selects the correct path:

| Partition result | Software build flow | Reason |
|-----------------|--------------------|---------| 
| **PS+PL only** (no AIE, no Vitis-kernel HLS) | Traditional Embedded (`hsi::generate_bsp`) | Fixed XSA, register-mapped I/O |
| **Any block in AIE domain** | v++ Flow (`v++ --link`) | AIE graph requires v++ compilation (UG1273: "AI Engine programming is not supported" in traditional flow) |
| **HLS blocks via Vitis kernel flow** | v++ Flow (`v++ --mode hls` → `.xo` → `v++ --link`) | Vitis kernel .xo files need v++ linker for platform integration |
| **HLS blocks via Vivado IP flow** | Traditional Embedded | HLS IP packaged into Vivado IPI, no v++ needed |

When an HLS block is assigned to PL, decide the HLS flow target:
- **Vivado IP flow**: More flexible interfaces, integrates manually in IPI. Use when the
  HLS block is part of a hand-stitched block design with specific AXI connectivity.
- **Vitis kernel flow**: Correct-by-construction XRT integration. Use when the HLS block
  will be dynamically loaded or managed via XRT host APIs. AMD recommends Vitis kernel
  flow for platform-based designs (UG1387 Table 1).

See the **Software Build Flow Selection** decision tree in `soc-orchestration/SKILL.md`
for the full flow comparison and `v++` CLI reference.

## Implementation Flow by Design Type

The partition determines the Vivado project structure:

**PL-only design** (no PS blocks): Simple RTL project.
```tcl
create_project <name> <path> -part <device> -force
add_files <rtl_sources>
add_files -fileset constrs_1 <xdc_files>
set_property top <top_module> [current_fileset]
launch_runs synth_1; wait_on_run synth_1
launch_runs impl_1; wait_on_run impl_1
```

**PS+PL design** (Zynq UltraScale+): Requires block design with PS8 IP.
```tcl
create_project <name> <path> -part <device> -force
create_bd_design "<bd_name>"
# Add PS and configure clocks
create_bd_cell -type ip -vlnv xilinx.com:ip:zynq_ultra_ps_e:3.5 zynq_ps
apply_bd_automation -rule xilinx.com:bd_rule:zynq_ultra_ps_e -config {apply_board_preset 0} [get_bd_cells zynq_ps]
# IMPORTANT: Set exact PL clock frequency (default is ~96.97 MHz, NOT 100 MHz)
set_property CONFIG.PSU__CRL_APB__PL0_REF_CTRL__FREQMHZ {100} [get_bd_cells zynq_ps]

# Enable HP slave ports if DMA/VDMA masters need memory access
# HP0 = S_AXI_GP2, HP1 = S_AXI_GP3, HP2 = S_AXI_GP4, HP3 = S_AXI_GP5
set_property -dict [list CONFIG.PSU__USE__S_AXI_GP2 {1} CONFIG.PSU__SAXIGP2__DATA_WIDTH {128}] [get_bd_cells zynq_ps]

# Add PL IP (e.g., AXI GPIO for control)
create_bd_cell -type ip -vlnv xilinx.com:ip:axi_gpio:2.0 axi_gpio_0
# Wire control plane via AXI-Lite automation (usually works reliably)
apply_bd_automation -rule xilinx.com:bd_rule:axi4 -config {Master {/zynq_ps/M_AXI_HPM0_LPD} Slave {/axi_gpio_0/S_AXI}} [get_bd_intf_pins axi_gpio_0/S_AXI]

# For data plane (DMA/VDMA masters → PS HP slave):
# apply_bd_automation may fail — use manual interconnect as fallback:
# create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect:2.1 axi_ic_hp0
# set_property CONFIG.NUM_SI {N} CONFIG.NUM_MI {1} [get_bd_cells axi_ic_hp0]
# connect_bd_intf_net [get_bd_intf_pins <master>/M_AXI] [get_bd_intf_pins axi_ic_hp0/S00_AXI]
# connect_bd_intf_net [get_bd_intf_pins axi_ic_hp0/M00_AXI] [get_bd_intf_pins zynq_ps/S_AXI_HP0_FPD]
# Then wire clocks, resets, and assign_bd_address for the HP segments

# Validate, generate wrapper
validate_bd_design; save_bd_design
make_wrapper -files [get_files <bd_name>.bd] -top
# Add wrapper and set as top
add_files -norecurse <path_to_wrapper>
set_property top <bd_name>_wrapper [current_fileset]
```

**PS+PL+AIE design** (Versal): Requires CIPS + NoC + AIE graph.
```tcl
# Similar to above but uses:
# xilinx.com:ip:versal_cips for processing system
# xilinx.com:ip:axi_noc for NoC connections
# Plus AIE graph compilation via aiecompiler (shell)
```

## Troubleshooting

### Device part not found
Use `vivado_doc_search` to find the correct part string. Common format:
`xc<family><size>-<package>-<speed>-<temp>` (e.g., `xcvc1902-vsva2197-2MP-e-S`).

### AIE core count returns 0
The target device may not have an AIE array (e.g., Zynq, non-Versal).
Remap all AIE-natural workloads to PL with HLS.

## Related Skills

- `soc-orchestration`: Parent orchestration flow
- `soc-orchestration/estimation`: Validates partition with progressive estimation
- `timing-methodology-checks`: Post-synthesis timing check (use `congestion-analysis` / `opt-design-analysis` for resource/congestion QoR)
