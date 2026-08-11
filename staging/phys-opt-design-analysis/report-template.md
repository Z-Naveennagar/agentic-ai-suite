<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# phys_opt_design Report Templates & Reference

Read this file when generating report_data.json and REPORT.md in Step 5.

## Output Files

```
vivado_agentic_ai_reports/phys-opt-design-analysis/
├── report_data.json          ← Structured optimization metrics
├── REPORT.md                 ← Markdown summary with recommendations
└── dashboard.html            ← Interactive HTML dashboard (loads report_data.json)
```

## report_data.json Schema

```json
{
  "metadata": {
    "design": "<design_name>",
    "device": "<part_number>",
    "date": "<ISO 8601 timestamp>",
    "command": "phys_opt_design <options>",
    "directive": "<directive or Default>",
    "runtime": "<HH:MM:SS>",
    "iterations": 1,
    "log_file": "<path>"
  },
  "timing_trend": [
    {
      "iteration": 0,
      "label": "Initial",
      "wns": -0.500,
      "tns": -12.345,
      "whs": 0.020,
      "ths": 0.0
    },
    {
      "iteration": 1,
      "label": "Post phys_opt",
      "wns": -0.200,
      "tns": -5.678,
      "whs": 0.015,
      "ths": 0.0
    }
  ],
  "optimization_stats": {
    "replication": {
      "nets_optimized": 0,
      "instances_created": 0,
      "instances_replaced": 0
    },
    "retiming": {
      "forward_candidates": 0,
      "backward_candidates": 0,
      "registers_retimed": 0,
      "path_groups_improved": 0
    },
    "rewiring": {
      "nets_rewired": 0,
      "pins_swapped": 0
    },
    "dsp_reg": {
      "candidates": 0,
      "registers_pushed": 0
    },
    "bram_reg": {
      "candidates": 0,
      "registers_pushed": 0
    },
    "uram_reg": {
      "candidates": 0,
      "registers_pushed": 0
    },
    "srl": {
      "candidates": 0,
      "optimized": 0
    },
    "hold_fix": {
      "candidates": 0,
      "lut1_inserted": 0,
      "zhold_delays": 0
    },
    "lut_opt": {
      "candidates": 0,
      "luts_replaced": 0
    },
    "interconnect_retime": {
      "candidates": 0,
      "optimized": 0
    },
    "equivalent_driver": {
      "candidates": 0,
      "groups_optimized": 0
    },
    "critical_cell": {
      "candidates": 0,
      "cells_optimized": 0
    },
    "control_set": {
      "flops_optimized": 0
    },
    "fanout": {
      "candidates": 0,
      "nets_replicated": 0
    },
    "end_pass": {
      "cells_created": 0,
      "cells_deleted": 0,
      "cells_moved": 0
    }
  },
  "skipped_optimizations": [
    {
      "optimization": "<name>",
      "reason": "<message text>",
      "message_id": "32-NNN"
    }
  ],
  "blocking_properties": {
    "dont_touch_cells": 0,
    "mark_debug_nets": 0,
    "non_replicable": 0,
    "phys_opt_skipped": 0,
    "critical_blocked": [
      {
        "cell": "<cell_path>",
        "property": "DONT_TOUCH|MARK_DEBUG|IS_REPLICABLE",
        "slack": -0.123
      }
    ]
  },
  "errors_warnings": [
    {
      "id": "32-NNN",
      "severity": "ERROR|CRIT_WARN|WARNING",
      "message": "<message text>",
      "fix_type": "RTL|XDC",
      "agent_action": "<Tcl command executed or diagnostic performed>",
      "count": 1
    }
  ],
  "recommendations": [
    {
      "priority": 1,
      "severity": "CRITICAL|HIGH|MEDIUM|INFO",
      "category": "directive|rerun|constraint|rtl|stop",
      "finding": "<actual values, no placeholders>",
      "action": "<one-line description of what to do>",
      "tcl_commands": ["<copy-pasteable Tcl command 1>", "<command 2 if needed>"],
      "expected_impact": "<description>"
    }
  ],
  "assessment": {
    "optimization_score": 5,
    "timing_improvement_pct": 0.0,
    "overall_status": "GREEN|YELLOW|RED",
    "notes": null
  }
}
```

### Assessment Scoring

- **5 (GREEN):** WNS met or improved >20%, no errors, all optimizations effective
- **4 (GREEN):** WNS improved 10-20%, minor warnings only
- **3 (YELLOW):** WNS improved <10%, some optimizations skipped or blocked
- **2 (YELLOW):** WNS stagnant or oscillating, critical warnings present
- **1 (RED):** WNS degraded, errors present, or timing gap too large for phys_opt

---

## REPORT.md Template

Use this exact template structure. Replace bracketed values with actual data from the design.

```markdown
# phys_opt_design Analysis Report

**Design:** [design_name]
**Device:** [part_number]
**Date:** [timestamp]
**Command:** `phys_opt_design <options>`
**Directive:** [directive]
**Runtime:** [HH:MM:SS]

## Executive Summary

| Metric | Value | Status |
|--------|-------|--------|
| Overall Score | X/5 | 🟢/🟡/🔴 |
| WNS Before | -X.XXX ns | ❌ |
| WNS After | -X.XXX ns | ✅ / ❌ |
| WNS Improvement | XX.X% | ✅ / ⚠️ |
| TNS Before | -X.XXX ns | ❌ |
| TNS After | -X.XXX ns | ✅ / ❌ |
| WHS After | X.XXX ns | ✅ / ❌ |
| Errors | N | ✅ / ❌ |
| Critical Warnings | N | ✅ / ⚠️ |
| Cells Created | N | — |
| Cells Moved | N | — |

## Timing Trend

| Iteration | WNS (ns) | TNS (ns) | WHS (ns) | THS (ns) |
|-----------|----------|----------|----------|----------|
| Initial | -X.XXX | -X.XXX | X.XXX | X.XXX |
| Post phys_opt | -X.XXX | -X.XXX | X.XXX | X.XXX |

## Optimization Statistics

| Category | Candidates | Optimized | Cells Created |
|----------|------------|-----------|---------------|
| Replication | N | N | N |
| Retiming | N | N | N |
| Rewiring | N | N | — |
| DSP Register | N | N | — |
| BRAM Register | N | N | — |
| URAM Register | N | N | — |
| SRL | N | N | — |
| Hold Fix | N | N | N (LUT1) |
| LUT Opt | N | N | — |
| Interconnect Retime | N | N | — |
| Equivalent Driver | N | N | — |
| Critical Cell | N | N | — |
| Fanout | N | N | N |

## Skipped Optimizations

| Optimization | Reason | Message ID |
|-------------|--------|------------|
| [name] | [reason] | 32-NNN |

## Errors & Warnings

| ID | Severity | Count | Fix | Message | Agent Action |
|----|----------|-------|-----|--------|---------------|
| 32-NNN | ERROR | N | RTL/XDC | [summary] | [Tcl command or diagnostic performed] |

## Blocking Properties

[DONT_TOUCH/MARK_DEBUG/IS_REPLICABLE inventory — cells on critical paths with slack values]

## Recommendations

### Immediate Fixes

**[Finding]:** [DONT_TOUCH on N cells blocking replication/retiming on critical paths with worst slack -X.XXX ns]

```tcl
reset_property DONT_TOUCH [get_cells {cell_a cell_b}]
```

**Expected Impact:** [Unblocks replication/retiming on N critical-path cells]

---

**[Finding]:** [Optimization improved timing — save replay script for retrofit]

```tcl
write_iphys_opt_tcl iphys_opt_replay.tcl
```

**Expected Impact:** [Replay script enables retrofit of successful optimizations in future runs]

---

### Findings & Diagnosis

**[Finding]:** [WNS improved X% — optimization was effective/stagnant/oscillating]

**Assessment:** [Trend analysis based on per-iteration WNS/TNS from log]

---

**[Finding]:** [WNS gap too large for phys_opt (> -2.0 ns) — must fix at RTL/architecture level]

```tcl
report_timing -max_paths 10 -sort_by group -input_pins
report_design_analysis -logic_level_distribution
```

**Rationale:** [Beyond phys_opt scope — user must reduce logic depth in RTL]

---

**[Finding]:** [Hold fix degraded setup timing — WNS went from -X.XXX to -Y.YYY ns]

**Assessment:** [Separating setup and hold optimization may help]

---

### Next-Run Suggestions

**[Finding]:** [WNS improved >20% — another pass likely beneficial]

```tcl
phys_opt_design -directive AggressiveExplore
```

**Rationale:** [Per AMD docs (UG904), iterative phys_opt is supported; each pass targets top failing paths]

---

**[Finding]:** [Replication helped but WNS still negative on specific nets]

```tcl
phys_opt_design -force_replication_on_nets [get_nets {net_a net_b}]
```

**Rationale:** [Target specific nets identified from timing analysis]

---

### Accept / Waive

**[Finding]:** [MARK_DEBUG on N nets blocking optimization — expected for debug]

**Rationale:** [Acceptable if debug probes are intentional; remove MARK_DEBUG after debug is complete]

---

**[Finding]:** [Replication blocked on N cells with IS_REPLICABLE=FALSE]

**Rationale:** [Verify cells are intentionally non-replicable (e.g., single-instance state machines)]
```

---

## Optimization Phase Reference

The following phys_opt_design optimization phases should be recognized during log analysis:

| Phase | Description | Key Message IDs |
|---|---|---|
| Max fanout opt | Replicate drivers to reduce fanout | `[Physopt 32-76]`, `[Physopt 32-65]`, `[Physopt 32-1353]` |
| HD net replication | Replicate high-driver nets across clock regions | `[Physopt 32-232]`, `[Physopt 32-571]` |
| Retiming | Forward/backward register retiming through LUTs | `[Physopt 32-942]`, `[Physopt 32-943]`, `[Physopt 32-952]`, `[Physopt 32-953]` |
| Timing-based retime | Retiming driven by post-place/route timing | `[Physopt 32-735]`, `[Physopt 32-952]` |
| Interconnect retime | Retime through interconnect routing resources | `[Physopt 32-1306]`, `[Physopt 32-1307]`, `[Physopt 32-1324]` |
| Rewiring/critical-pin opt | Rewire nets and swap pins for timing | `[Physopt 32-601]`, `[Physopt 32-606]` to `[Physopt 32-608]`, `[Physopt 32-69]` |
| LUT optimization | Restructure LUT logic for shorter paths | `[Physopt 32-1332]` to `[Physopt 32-1338]` |
| Cascade opt | Cascade LUT optimization for depth reduction | `[Physopt 32-1331]` |
| DSP register opt | Push/pull registers into/out of DSP48 primitives | `[Physopt 32-456]`, `[Physopt 32-457]`, `[Physopt 32-665]`, `[Physopt 32-666]` |
| BRAM register opt | Push/pull registers into/out of BRAM primitives | `[Physopt 32-526]`, `[Physopt 32-527]` |
| URAM register opt | Push/pull registers into/out of URAM primitives | `[Physopt 32-846]` |
| Memory rewire | Rewire BRAM/URAM address/data pins for timing | `[Physopt 32-1395]` to `[Physopt 32-1398]` |
| Shift register opt | Decompose/restructure SRLs for timing | `[Physopt 32-677]`, `[Physopt 32-1123]`, `[Physopt 32-1401]`, `[Physopt 32-1402]` |
| Equivalent driver rewiring | Rewire equivalent net drivers for shorter paths | `[Physopt 32-670]`, `[Physopt 32-1030]`, `[Physopt 32-1487]` to `[Physopt 32-1489]` |
| Critical cell group opt | Optimize a group of critical cells together | `[Physopt 32-1305]`, `[Physopt 32-1308]`, `[Physopt 32-1323]` |
| Control set opt | Reduce control sets for packing improvement | `[Physopt 32-1359]`, `[Physopt 32-1360]` |
| Hold fix | Insert LUT1/ZHOLD_DELAY buffers for hold violations | `[Physopt 32-45]`, `[Physopt 32-234]`, `[Physopt 32-960]` |
| SLR crossing opt | Optimize inter-SLR crossing paths | `[Physopt 32-1411]`, `[Physopt 32-1492]` |
| Per-SLR replication | Replicate logic per SLR for multi-die designs | `[Physopt 32-1411]` |
| BUFG fabric phys opt | Optimize BUFG_FABRIC net placement | `[Physopt 32-1300]` |
| AUTOPIPELINE | Automatic pipeline register insertion | `[Physopt 32-909]`, `[Physopt 32-1122]` to `[Physopt 32-1129]`, `[Physopt 32-1500]`, `[Physopt 32-1501]` |
| Default opt | Combined optimization pass with default directives | `[Vivado_Tcl 4-137]` |

See [message-reference.md](message-reference.md) for the full categorized message catalog with resolutions for all `[Physopt 32-*]` messages.

### Common Issues After phys_opt_design

| Symptom | Root Cause | Recommendation |
|---|---|---|
| phys_opt did not run (WNS > threshold) | WNS threshold check — phys_opt skips if WNS exceeds limit | Expected behavior — no action needed for met timing |
| URAM register opt expected but did not occur | URAM register optimization requires specific register patterns adjacent to URAM | Check if URAM-adjacent registers have correct enable/reset patterns for absorption |
| Retime did not occur | No register satisfies retiming conditions (timing, connectivity, properties) | Verify retiming is not blocked by DONT_TOUCH, MARK_DEBUG, or async reset on candidate registers |
| PHYS_OPT_MODIFIED not set on expected cell | Cell was not touched by phys_opt despite being a candidate | Check if the cell is marked IS_REPLICABLE=FALSE or has DONT_TOUCH |
| Equivalent driver rewiring did not occur | No equivalent drivers found, or no setup violation on candidate nets | Check for setup margin — rewiring only triggers when WNS < 0 on the candidate path |
| Crash during post-route phys_opt | Routing engine error during post-route phys_opt | File a support case; try different directive or skip post-route phys_opt |
| DRC NSTD-2 (UNDEFINED I/O standard) | Missing IOSTANDARD on ports — blocks implementation validation | Set IOSTANDARD on all ports before running phys_opt |
| Unexpected SRL decomposition | SRL decomposition occurred when not intended | Check if `-shift_register_opt` was inadvertently enabled |
| DRC REQPXA-321 (OPMODEREG tied low) | DSP OPMODE register control pin improperly constrained | Fix DSP48 OPMODEREG configuration before phys_opt |
| Fanout replication not performed | Fanout threshold not met, or net has DONT_TOUCH | Lower `-force_replication_on_nets` threshold or remove DONT_TOUCH |
| Per-SLR replication occurred unexpectedly | Replication triggered on a net not expected to cross SLRs | Check SLR assignment — net may be incorrectly assigned across SLR boundaries |

---

## Directives Reference

| Directive | Focus |
|---|---|
| `Default` | Balanced optimization |
| `Explore` | Try multiple approaches, pick best |
| `AggressiveExplore` | Maximum effort — all optimization techniques |
| `AggressiveFanoutOpt` | Focus on high fanout net reduction |
| `AlternateReplication` | Different replication heuristic |
| `ExploreWithHoldFix` | Explore with hold fixing enabled |

### Key phys_opt Options

| Option | Purpose |
|---|---|
| `-force_replication_on_nets` | Force replicate specific net drivers |
| `-hold_fix` | Fix hold violations |
| `-aggressive_hold_fix` | More aggressive hold fixing |
| `-insert_negative_edge_ffs` | Use negative-edge FFs for hold fix |
| `-slr_crossing_opt` | Optimize inter-SLR paths |
| `-lut_opt` | LUT restructuring optimization (2023.1+) |
| `-interconnect_retime` | Retime through interconnect (2022.1+) |
| `-critical_cell_opt` | Optimize groups of critical cells |
| `-dsp_register_opt` | Push/pull DSP registers |
| `-bram_register_opt` | Push/pull BRAM registers |
| `-uram_register_opt` | Push/pull URAM registers |
| `-shift_register_opt` | SRL decomposition/restructuring |
| `-rewire` | Net rewiring for shorter paths |
| `-critical_pin_opt` | Pin swapping for timing |
| `-placement_opt` | Re-place cells for timing |
| `-retime` | Register retiming |
