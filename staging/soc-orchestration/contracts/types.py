# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
"""Structured types for LLM-first AMD SoC design orchestration.

These Pydantic models define the contracts between the LLM orchestrator,
MCP servers (Vivado, Model Composer), and Agent Skills. They are used as
structured output schemas -- the LLM reasons through design decisions and
emits these types; downstream tools consume them.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Compute domain taxonomy
# ---------------------------------------------------------------------------

class ComputeDomain(str, Enum):
    """Where a functional block executes on an AMD SoC."""

    PS = "PS"            # Processing System (Arm Cortex-A/R)
    PL = "PL"            # Programmable Logic (FPGA fabric)
    AIE = "AIE"          # AI Engine array (Versal)
    AIE_ML = "AIE_ML"    # AI Engine ML variant
    DPU = "DPU"          # Deep Learning Processing Unit (soft IP on PL)
    NOC = "NoC"          # Network on Chip (interconnect / config)


class WorkloadType(str, Enum):
    """Categorizes functional blocks for initial domain mapping.

    The `natural_domain` property provides a starting-point assignment
    that the LLM can override based on device resources and constraints.
    """

    # Archetypes with clear domain affinity
    CONTROL_LOGIC = "control_logic"
    OS_APPLICATION = "os_application"
    BARE_METAL_FIRMWARE = "bare_metal_firmware"
    STREAM_DSP = "stream_dsp"
    VECTOR_COMPUTE = "vector_compute"
    ML_INFERENCE = "ml_inference"
    PACKET_PROCESSING = "packet_processing"
    VIDEO_PIPELINE = "video_pipeline"
    SENSOR_INTERFACE = "sensor_interface"
    MEMORY_CONTROLLER = "memory_controller"
    CRYPTO_ACCELERATOR = "crypto_accelerator"
    MOTOR_CONTROL = "motor_control"
    PROTOCOL_BRIDGE = "protocol_bridge"
    COMPRESSION = "compression"
    SIGNAL_CHAIN = "signal_chain"
    CUSTOM_PL = "custom_pl"
    CUSTOM_AIE = "custom_aie"
    CUSTOM_PS = "custom_ps"

    @property
    def natural_domain(self) -> ComputeDomain:
        """Default compute domain for this workload type."""
        ps = {
            self.CONTROL_LOGIC, self.OS_APPLICATION,
            self.BARE_METAL_FIRMWARE, self.MOTOR_CONTROL,
            self.CUSTOM_PS,
        }
        aie = {
            self.STREAM_DSP, self.VECTOR_COMPUTE,
            self.SIGNAL_CHAIN, self.CUSTOM_AIE,
        }
        aie_ml = {self.ML_INFERENCE}
        if self in ps:
            return ComputeDomain.PS
        if self in aie:
            return ComputeDomain.AIE
        if self in aie_ml:
            return ComputeDomain.AIE_ML
        return ComputeDomain.PL


# ---------------------------------------------------------------------------
# Estimation tiers
# ---------------------------------------------------------------------------

class EstimationTier(str, Enum):
    """Progressive estimation levels with increasing fidelity and cost."""

    T0_PARAMETRIC = "T0"   # Analytical model (<1s)
    T1_POWER = "T1"        # XPE / power estimation (5-30s)
    T2_HLS = "T2"          # HLS C-synthesis / AIE mapping (10-60s)
    T3_SYNTHESIS = "T3"    # Vivado OOC synthesis (2-10min)
    T4_FULL_BUILD = "T4"   # Full implementation


# ---------------------------------------------------------------------------
# Design specification (LLM input / output)
# ---------------------------------------------------------------------------

class InterfaceSpec(BaseModel):
    """A single interface on a functional block."""

    name: str
    protocol: str = Field(description="AXI4, AXI-Stream, PLIO, GPIO, etc.")
    width_bits: int | None = None
    clock_mhz: float | None = None
    direction: str = Field(default="bidirectional", description="in | out | bidirectional")


class FunctionalBlock(BaseModel):
    """One logical block in the design."""

    name: str
    description: str = ""
    workload_type: WorkloadType
    interfaces: list[InterfaceSpec] = Field(default_factory=list)
    source_path: str | None = Field(default=None, description="Path to RTL/HLS/AIE source")
    constraints: dict[str, Any] = Field(default_factory=dict, description="Latency, throughput, etc.")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Block-specific config")


class DesignSpec(BaseModel):
    """Top-level design specification consumed by the orchestrator skill."""

    name: str
    description: str = ""
    target_device: str = Field(description="e.g. xcvc1902-vsva2197-2MP-e-S")
    blocks: list[FunctionalBlock]
    global_constraints: dict[str, Any] = Field(default_factory=dict)
    clock_domains: list[dict[str, Any]] = Field(default_factory=list)
    power_budget_watts: float | None = None


# ---------------------------------------------------------------------------
# Partition assignment (LLM output)
# ---------------------------------------------------------------------------

class PartitionAssignment(BaseModel):
    """Maps a functional block to a compute domain."""

    block_name: str
    domain: ComputeDomain
    rationale: str = Field(description="LLM reasoning for this assignment")
    estimated_resources: dict[str, Any] = Field(default_factory=dict)


class PartitionPlan(BaseModel):
    """Complete partitioning result."""

    assignments: list[PartitionAssignment]
    cross_domain_interfaces: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Timing-closure bottleneck classification (qor-classification skill output)
# ---------------------------------------------------------------------------

class BottleneckClass(str, Enum):
    """First-Step bottleneck class emitted by the qor-classification skill.

    Aligns with Vivado's report_qor_suggestions categories (Clocking, Congestion,
    Utilization, Timing) plus a derived multi-SLR PARTITION class. The orchestrator
    (soc-orchestration Phase 5) dispatches fixes in the documented UltraFast priority
    order: CLOCKING -> UTILIZATION -> CONGESTION -> TIMING.
    """

    PARTITION = "Partition"        # multi-SLR scatter / missing SLR pblocks (derived)
    CONGESTION = "Congestion"      # routing resources locally exhausted
    CLOCKING = "Clocking"          # skew / CEW / clock topology / missing constraints
    UTILIZATION = "Utilization"    # device over-utilized
    TIMING = "Timing"              # logic/routing delay on critical paths


# ---------------------------------------------------------------------------
# QoR metrics (Vivado / tool output, parsed by LLM)
# ---------------------------------------------------------------------------

class QoRMetrics(BaseModel):
    """Quality of Results snapshot from any estimation tier."""

    tier: EstimationTier
    block_name: str | None = None
    wns_ns: float | None = Field(default=None, description="Worst negative slack (final/route)")
    whs_ns: float | None = Field(default=None, description="Worst hold slack")
    tns_ns: float | None = Field(default=None, description="Total negative slack (sum of setup violations)")
    utilization_pct: dict[str, float] = Field(default_factory=dict, description="LUT, FF, BRAM, DSP, etc.")
    power_watts: float | None = None
    frequency_mhz: float | None = None
    logic_levels: int | None = None
    qor_score: float | None = Field(default=None, description="Vivado QoR score if available")
    # --- timing-closure (qor-classification) extensions ---
    rqa_score: int | None = Field(default=None, description="report_qor_assessment score 1-5 (5=meets easily)")
    max_congestion: int | None = Field(default=None, description="Max effective router congestion level 0-9")
    route_iters: int | None = Field(default=None, description="Global routing iterations")
    wns_place: float | None = Field(default=None, description="WNS immediately after place_design")
    wns_popt: float | None = Field(default=None, description="WNS after post-place phys_opt_design")
    wns_route: float | None = Field(default=None, description="WNS after route_design (authoritative)")
    closed_at_popt: bool | None = Field(default=None, description="WNS>=0 after phys_opt but design analysed pre-route")
    classification: BottleneckClass | None = Field(default=None, description="First-Step bottleneck class")
    confidence: str | None = Field(default=None, description="HIGH | MEDIUM | LOW (score separation)")
    sub_class: str | None = Field(default=None, description="e.g. Retiming_Opportunity, Net_Delay_Dominated, Clock_Constraint")
    rqs_ids: list[str] = Field(default_factory=list, description="RQS suggestion IDs generated by Vivado")
    passed: bool = True
    notes: str = ""


# ---------------------------------------------------------------------------
# Closure report (final output)
# ---------------------------------------------------------------------------

class ClosureReport(BaseModel):
    """Final timing closure report."""

    design_name: str
    status: str = Field(description="met | not_met | partial")
    partition_plan: PartitionPlan
    qor_history: list[QoRMetrics] = Field(default_factory=list)
    final_wns_ns: float | None = None
    final_whs_ns: float | None = None
    final_tns_ns: float | None = None
    classification: BottleneckClass | None = Field(default=None, description="Dominant bottleneck class at closure")
    confidence: str | None = Field(default=None, description="HIGH | MEDIUM | LOW")
    rqs_suggestions: list[str] = Field(default_factory=list, description="RQS suggestion IDs applied/considered")
    total_power_watts: float | None = None
    build_artifacts: dict[str, str] = Field(default_factory=dict, description="Paths to bitstream, PDI, reports")
    recommendations: list[str] = Field(default_factory=list)
