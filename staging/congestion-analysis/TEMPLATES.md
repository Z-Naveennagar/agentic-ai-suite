<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Congestion Analysis — Output Templates

## report_data.json Structure

The `report_data.json` file is the single source of truth for the dashboard. All fields should be populated from parsed Vivado reports. Fields that cannot be determined should be set to `null`.

```json
{
  "metadata": {
    "design": "top_module_name",
    "device": "xcvp1802-lsvc4072-2MP-e-S",
    "device_family": "Versal Premium",
    "num_slrs": 4,
    "clock_region_grid": {"cols": 4, "rows": 5, "labels_x": ["X0","X1","X2","X3"], "labels_y": ["Y0","Y1","Y2","Y3","Y4"]},
    "analysis_date": "2026-03-28T14:30:00Z",
    "reports_analyzed": [
      "design_analysis.rpt",
      "utilization.rpt",
      "route_status.rpt",
      "timing_summary.rpt",
      "clock_util.rpt"
    ],
    "analysis_phase": "post-route",
    "vivado_version": "2025.2 (Build 6262816)",
    "output_dir": "vivado_agentic_ai_reports/congestion-analysis"
  },

  "assessment": {
    "placement_score": 3,
    "routing_score": 2,
    "overall_score": 2,
    "overall_status": "RED",
    "summary": "Severe congestion in East/West directions with 47 unrouted nets"
  },

  "placement_congestion": {
    "global_congestion": {
      "north": 1,
      "south": 2,
      "east": 5,
      "west": 4,
      "max_direction": "East",
      "max_value": 5
    },
    "congestion_windows": [
      {
        "direction": "East",
        "type": "Short",
        "level": 5,
        "congestion_pct": 89,
        "window": "(CLEL_R_X10Y164,CLE_M_X26Y195)",
        "affected_clock_regions": ["X0Y2", "X0Y3", "X1Y2", "X1Y3"],
        "combined_luts_pct": 4,
        "avg_lut_inputs": 3.753,
        "resource_breakdown": {
          "lut_pct": 72, "lutram_pct": 11, "flop_pct": 59, "muxf_pct": 0,
          "bram_pct": 100, "uram_pct": null, "dsp_pct": 91, "carry_pct": 6, "srl_pct": 25
        },
        "top_cells": [
          {"name": "inst_a/inst_b", "short_name": "inst_b", "module": "mod_A",
           "parent_module": "mod_top", "pct": 21,
           "resources": {"lut": 6234, "ff": 8304, "bram_tiles": 17, "dsp": 116, "srl": 1137},
           "placed_in_crs": ["X0Y2", "X1Y2"]},
          {"name": "inst_a/inst_c", "short_name": "inst_c", "module": "mod_B",
           "parent_module": "mod_top", "pct": 20,
           "resources": {"lut": 6190, "ff": 8350, "bram_tiles": 17, "dsp": 116, "srl": 1137},
           "placed_in_crs": ["X0Y2", "X0Y3"]}
        ]
      }
    ],
    "congestion_type_summary": {
      "short": {"count": 2, "max_level": 5, "max_pct": 89, "directions": ["East", "West"]},
      "long": {"count": 0, "max_level": null, "max_pct": null, "directions": []},
      "note": "Only Short congestion detected — no Long congestion windows at Level 5 or above."
    },
    "module_hierarchy": [
      {
        "instance": "top_module", "module": "(top)", "lut": 209723, "ff": 257285,
        "bram36": 500, "bram18": 168, "dsp": 916,
        "children": [
          {"instance": "inst_a", "module": "mod_top", "lut": 208000, "ff": 256532,
           "bram36": 500, "bram18": 160, "dsp": 916,
           "congestion_role": "Contains all congestion-contributing cells",
           "children": [
             {"instance": "inst_b", "module": "mod_A", "lut": 6234, "ff": 8304,
              "bram36": 10, "bram18": 14, "dsp": 116,
              "congestion_window": "East", "congestion_pct": 21}
           ]}
        ]
      }
    ],
    "router_initial_congestion": "No effective congestion windows found above level 5",
    "rent_exponent": 0.68,
    "rent_note": null,
    "avg_fanout": 3.42,
    "logic_levels": {
      "avg": 6.8,
      "max": 22
    },
    "global_utilization": {
      "lut_used": 539079,
      "lut_available": 3360960,
      "lut_pct": 16.04,
      "ff_used": 963525,
      "ff_available": 6721920,
      "ff_pct": 14.34,
      "bram_used": 1619.5,
      "bram_available": 2688,
      "bram_pct": 60.25,
      "dsp_used": 24,
      "dsp_available": 9216,
      "dsp_pct": 0.26,
      "clb_used": null,
      "clb_available": null,
      "clb_pct": null,
      "uram_used": 64,
      "uram_available": 960,
      "uram_pct": 6.67
    },
    "per_clock_region": [
      {
        "region": "X0Y0",
        "ff_used": 18200,
        "ff_avail": 92160,
        "ff_pct": 19.7,
        "lutram_used": 500,
        "lutram_avail": 5760,
        "lutram_pct": 8.68,
        "bram_used": 32,
        "bram_avail": 72,
        "bram_pct": 44.44,
        "dsp_used": 10,
        "dsp_avail": 96,
        "dsp_pct": 10.42
      }
    ],
    "per_clock_region_routing": [
      {
        "region": "X0Y0",
        "hroute_pct": 12.50,
        "hdistr_pct": 33.33,
        "vroute_pct": 4.17,
        "vdistr_pct": 8.33
      }
    ],
    "per_slr": [
      {
        "slr": "SLR0",
        "lut_pct": 18.2,
        "ff_pct": 15.1,
        "bram_pct": 55.0,
        "dsp_pct": 0.5,
        "congestion_max": 3,
        "worst_direction": "East"
      }
    ],
    "hot_regions_count": 2,
    "utilization_imbalance_pct": 65.1
  },

  "routing_pressure": {
    "muxf7_count": 3200,
    "muxf8_count": 850,
    "carry_count": 12500,
    "hlutnm_count": 45000,
    "primary_clock": "clk300m (3.333 ns / 300 MHz)",
    "primary_clock_loads": 153983
  },

  "routing_congestion": {
    "route_status": {
      "nets_routed": 485230,
      "nets_unrouted": 47,
      "nets_partial": 3,
      "nets_conflicts": 0,
      "nets_antennas": 0,
      "route_completion_pct": 99.99
    },
    "timing": {
      "wns": -0.342,
      "whs": 0.010,
      "tns": -85.6,
      "ths": 0.0,
      "failing_endpoints_setup": 312,
      "failing_endpoints_hold": 0
    },
    "timing_degradation": {
      "wns_pre_route": -0.150,
      "wns_post_route": -0.342,
      "degradation_ns": 0.192,
      "degradation_pct": 128.0
    },
    "unrouted_net_details": [
      {
        "net": "core_0/data_path/result_bus[15]",
        "driver_region": "X2Y3",
        "load_count": 12,
        "probable_cause": "congestion"
      }
    ]
  },

  "recommendations": [
    {
      "priority": 1,
      "severity": "CRITICAL",
      "category": "placement",
      "finding": "Clock region X2Y3 at 92.2% LUT utilization with congestion level 5",
      "action": "Re-place with: place_design -directive SpreadLogic_high",
      "expected_impact": "Distribute logic to neighboring regions, target < 80% peak LUT utilization"
    },
    {
      "priority": 2,
      "severity": "HIGH",
      "category": "placement",
      "finding": "Rent exponent 0.68 indicates inherent routing complexity",
      "action": "Use: place_design -directive AltSpreadLogic_high",
      "expected_impact": "Spread logic to reduce local routing demand in complex regions"
    },
    {
      "priority": 3,
      "severity": "CRITICAL",
      "category": "routing",
      "finding": "47 unrouted nets concentrated in X2Y2-X2Y3",
      "action": "Fix placement congestion first (recommendation 1), then re-route: route_design",
      "expected_impact": "Unrouted nets likely resolve when placement congestion is alleviated"
    },
    {
      "priority": 4,
      "severity": "MEDIUM",
      "category": "routing",
      "finding": "Post-route WNS degraded 0.192 ns from pre-route",
      "action": "After re-route: phys_opt_design -directive AggressiveExplore",
      "expected_impact": "Recover 0.1-0.2 ns through post-route physical optimization"
    }
  ],

  "thresholds": {
    "lut_per_cr_green": 70,
    "lut_per_cr_yellow": 80,
    "rent_green": 0.55,
    "rent_yellow": 0.65,
    "congestion_green": 2,
    "congestion_yellow": 3,
    "degradation_green_ns": 0.1,
    "degradation_yellow_ns": 0.5
  }
}
```

### Field Notes

| Field | Required | Description |
|-------|----------|-------------|
| `metadata.*` | Yes | Design info and analysis context |
| `metadata.clock_region_grid` | Yes | Grid dimensions for heatmap rendering: `{cols, rows, labels_x, labels_y}` |
| `metadata.vivado_version` | Recommended | Vivado version used for analysis |
| `assessment.*` | Yes | Overall health scores |
| `placement_congestion.global_congestion` | Yes (if congestion report available) | Direction-level congestion (integer levels 0-5, null if no window above 5) |
| `placement_congestion.congestion_windows` | Yes (if congestion report available) | Array of window objects with resource breakdown, top cells, affected CRs, and module correlation |
| `placement_congestion.congestion_windows[].affected_clock_regions` | Yes (if DCP available) | CRs covered by the window, from `get_clock_regions -of_objects [get_tiles ...]` |
| `placement_congestion.congestion_windows[].top_cells[].short_name` | Recommended | Last segment of the hierarchical cell name for display |
| `placement_congestion.congestion_windows[].top_cells[].module` | Yes (if DCP available) | Module name from `get_property REF_NAME` |
| `placement_congestion.congestion_windows[].top_cells[].parent_module` | Yes (if DCP available) | Parent module REF_NAME |
| `placement_congestion.congestion_windows[].top_cells[].resources` | Yes (if DCP available) | `{lut, ff, bram_tiles, dsp, srl}` from `report_utilization -cells` |
| `placement_congestion.congestion_windows[].top_cells[].placed_in_crs` | Yes (if DCP available) | CRs where leaf cells are placed |
| `placement_congestion.congestion_type_summary` | Yes | Short vs Long breakdown: `{short: {count, max_level, max_pct, directions}, long: {...}, note}` |
| `placement_congestion.module_hierarchy` | Yes (if DCP available) | Hierarchical tree with per-module LUT/FF/BRAM/DSP counts and congestion tags |
| `placement_congestion.router_initial_congestion` | Yes | String description or null |
| `placement_congestion.rent_exponent` | Conditional | May be `null` — set `rent_note` to explain why |
| `placement_congestion.rent_note` | If rent is null | Explanation string |
| `placement_congestion.per_clock_region` | Yes (from clock_util or utilization report) | Array with FF/LUTRAM/BRAM/DSP per region |
| `placement_congestion.per_clock_region_routing` | Yes (from clock_util) | Clock routing resource utilization per CR |
| `placement_congestion.per_slr` | Only for multi-SLR | Empty array `[]` for single-SLR |
| `placement_congestion.global_utilization.clb_*` | Recommended | CLB tile utilization (separate from LUT) |
| `routing_pressure.hlutnm_count` | Conditional | Requires Tcl query if Vivado active; null otherwise |
| `routing_pressure.primary_clock` | Recommended | Clock name and frequency from clock_util |
| `routing_pressure.primary_clock_loads` | Recommended | Load count for primary clock |
| `routing_congestion` | Only if routing done | `null` if design is only placed |
| `routing_congestion.timing_degradation` | Only if pre+post-route timing available | `null` otherwise |
| `routing_congestion.unrouted_net_details` | Only if unrouted nets exist | Empty array `[]` if all routed |
| `recommendations` | Yes | Always generate at least one |
| `thresholds` | Yes | Fixed reference thresholds, includes BRAM/clock routing thresholds |

### `assessment.overall_status` Values

| Status | Score Range | Meaning |
|--------|------------|---------|
| `GREEN` | 4-5 | Congestion is well-managed |
| `YELLOW` | 3 | Moderate congestion, may impact timing |
| `RED` | 1-2 | Severe congestion, likely routing failures |
