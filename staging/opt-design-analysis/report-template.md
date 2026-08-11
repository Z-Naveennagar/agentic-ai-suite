<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# opt_design Report Templates & Reference

Read this file when generating report_data.json and REPORT.md in Step 5.

## Output Files

```
vivado_agentic_ai_reports/opt-design-analysis/
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
    "command": "opt_design <options>",
    "directive": "<directive or Default>",
    "switches": ["-control_set_merge", "-remap"],
    "analysis_mode": "open_design | dcp | log_only",
    "runtime": "<HH:MM:SS>",
    "log_file": "<path>"
  },
  "context": {
    "impl_wns": null,
    "impl_tns": null,
    "failing_clock": null,
    "user_goal": null,
    "_note": "Orchestrator-provided, read-only. opt_design does not compute or improve timing."
  },
  "switch_reconciliation": [
    {
      "optimization": "<phase or switch name>",
      "expected_from": "directive | switch | default",
      "observed": "ran_effective | ran_no_effect | expected_but_absent | blocked",
      "cells_changed": 0,
      "note": "<e.g. -control_set_merge requested but 0 merges>"
    }
  ],
  "blocked_ledger": [
    {
      "optimization": "<name>",
      "blocked_by": "DONT_TOUCH | MARK_DEBUG | constraint | architecture | feedback_loop | no_candidate",
      "object": "<cell/net path>",
      "message_id": "31-NNN",
      "recoverable": true,
      "suggested_fix": "<XDC/RTL action>"
    }
  ],
  "utilization": {
    "_note": "Populated only in open_design/dcp mode. null in log_only mode.",
    "post_synth": { "lut": null, "ff": null, "carry": null, "muxf": null, "bram": null, "uram": null, "dsp": null, "srl": null },
    "post_opt":   { "lut": null, "ff": null, "carry": null, "muxf": null, "bram": null, "uram": null, "dsp": null, "srl": null },
    "delta_pct":  { "lut": null, "ff": null, "carry": null, "muxf": null },
    "significant_changes": []
  },
  "control_sets": {
    "_note": "Populated only in open_design/dcp mode.",
    "post_opt_count": null,
    "post_synth_count": null,
    "delta_pct": null,
    "exceeds_threshold": false
  },
  "resource_increase_attribution": {
    "net_cell_change": 0,
    "sources": [
      { "source": "bufg_insertion | hfn_split_load | lut_decomposition | remap | muxf", "cells": 0, "adds_logic_level": false }
    ]
  },
  "optimization_stats": {
    "phases": [
      {
        "name": "<phase_name>",
        "cells_created": 0,
        "cells_removed": 0,
        "constrained_objects": 0
      }
    ],
    "total_cells_created": 0,
    "total_cells_removed": 0,
    "total_constrained_objects": 0,
    "net_cell_change": 0
  },
  "phase_details": {
    "retarget_count": 0,
    "sweep_removed": 0,
    "propconst_removed": 0,
    "bufg_inserted": 0,
    "bufg_loads": [],
    "inverter_pushed": 0,
    "inverter_pulled": 0,
    "carry_transforms": 0,
    "carry_removed": 0,
    "muxf_created": 0,
    "muxf_removed": 0,
    "srl_remap_count": 0,
    "lut_decomposition_count": 0,
    "resynth_remap_count": 0,
    "bram_power_opt_count": 0
  },
  "blocking_properties": {
    "dont_touch_cells": 0,
    "dont_touch_nets": 0,
    "mark_debug_nets": 0,
    "dont_touch_hierarchical": 0,
    "critical_blocked": [
      {
        "cell": "<cell_path>",
        "property": "DONT_TOUCH|MARK_DEBUG",
        "slack": -0.123
      }
    ]
  },
  "errors_warnings": [
    {
      "id": "31-NNN",
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
      "category": "constraint|directive|rerun|rtl",
      "finding": "<actual values, no placeholders>",
      "action": "<one-line description of what to do>",
      "tcl_commands": ["<copy-pasteable Tcl command 1>", "<command 2 if needed>"],
      "expected_impact": "<description>"
    }
  ],
  "assessment": {
    "optimization_score": 5,
    "overall_status": "GREEN|YELLOW|RED",
    "notes": null
  }
}
```

### Assessment Scoring

- **5 (GREEN):** No errors/critical warnings, all phases completed, DONT_TOUCH not blocking critical paths
- **4 (GREEN):** Minor warnings only, all phases completed
- **3 (YELLOW):** Some optimizations skipped or DONT_TOUCH blocking non-critical paths
- **2 (YELLOW):** Critical warnings present, significant optimizations blocked
- **1 (RED):** Errors present, design connectivity issues, or critical paths blocked

---

## REPORT.md Template

Use this exact template structure. Replace bracketed values with actual data from the design.

```markdown
# opt_design Analysis Report

**Design:** [design_name]
**Device:** [part_number]
**Date:** [timestamp]
**Command:** `opt_design <options>`
**Directive:** [directive or Default] · **Switches:** [list]
**Analysis Mode:** [open_design | dcp | log_only]
**Runtime:** [HH:MM:SS]

> _Timing context (if provided by orchestrator):_ Implementation WNS = [impl_wns] ns,
> TNS = [impl_tns] ns. opt_design is a logic/area step and does not optimize timing — the
> recommendations below target area, logic levels, and control sets only.

## Executive Summary

| Metric | Value | Status |
|--------|-------|--------|
| Overall Score | X/5 | 🟢/🟡/🔴 |
| Errors | N | ✅ / ❌ |
| Critical Warnings | N | ✅ / ⚠️ |
| Cells Created | N | — |
| Cells Removed | N | — |
| Net Cell Change | +N / -N | — |
| Constrained Objects | N | ✅ / ⚠️ |
| Blocked Optimizations | N | ✅ / ⚠️ |
| Control Sets | N | ✅ / ⚠️ |
| DONT_TOUCH Cells | N | ✅ / ⚠️ |
| MARK_DEBUG Nets | N | ✅ / ⚠️ |

## Switches & Directive

| Item | Value |
|------|-------|
| Directive | [directive] |
| Explicit switches | [list] |
| Optimizations enabled | [expanded list] |

## Switch / Phase Reconciliation

| Optimization | Expected From | Observed | Cells Changed | Note |
|--------------|---------------|----------|---------------|------|
| [name] | directive/switch/default | ran_effective / ran_no_effect / expected_but_absent / blocked | N | [e.g. switch did nothing] |

## Change Summary

| Phase | Cells Created | Cells Removed | Constrained |
|-------|---------------|---------------|-------------|
| Retarget | N | N | N |
| Constant propagation | N | N | N |
| Sweep | N | N | N |
| BUFG insertion | N | N | N |
| Shift register | N | N | N |
| Remap | N | N | N |
| **Total** | **N** | **N** | **N** |

## Phase Details

[Per-phase key actions: inverter push/pull counts, carry transforms, BUFG insertions with load counts, MUXF stats, BRAM power opt, resynth/remap, LUT decomposition]

## Utilization & Control-Set QoR

> _Populated in open_design / dcp mode only. In log_only mode write: "Not captured — log-only analysis."_

| Resource | Post-Synth | Post-Opt | Δ% | Flag |
|----------|-----------|----------|-----|------|
| LUT | N | N | ±X% | ✅/⚠️ |
| FF | N | N | ±X% | ✅/⚠️ |
| CARRY | N | N | ±X% | ✅/⚠️ |
| MUXF | N | N | ±X% | ✅/⚠️ |
| Control Sets | N | N | ±X% | ✅/⚠️ |

**Significant changes:** [list any metric crossing the 5% / 5000 / utilization-band thresholds, or "none"]

## Resource-Increase Root-Cause

> _Only when net cell change > 0._

| Source | Cells Added | Adds Logic Level? |
|--------|-------------|-------------------|
| [bufg_insertion / hfn_split_load / lut_decomposition / remap / muxf] | N | yes/no |

[If a logic-level-adding source is present and impl WNS<0, call it out as the likely opt_design→timing link.]

## Blocked / Skipped Optimizations

| Optimization | Blocked By | Object | Msg ID | Recoverable | Suggested Fix |
|--------------|-----------|--------|--------|-------------|---------------|
| [name] | DONT_TOUCH/MARK_DEBUG/constraint/architecture/feedback_loop/no_candidate | [path] | 31-NNN | yes/no | [action] |

## Errors & Warnings

| ID | Severity | Count | Fix | Message | Agent Action |
|----|----------|-------|-----|--------|---------------|
| 31-NNN | ERROR | N | RTL/XDC | [summary] | [Tcl command or diagnostic performed] |

## Blocking Properties

[DONT_TOUCH/MARK_DEBUG inventory — cells on critical paths with slack values]

## Recommendations

### Immediate Fixes

**[Finding]:** [DONT_TOUCH on N cells blocking critical paths with worst slack -X.XXX ns]

```tcl
reset_property DONT_TOUCH [get_cells {cell_a cell_b}]
```

**Expected Impact:** [Unblocks optimization on N critical-path cells]

---

### Findings & Diagnosis

**[Finding]:** [Sweep removed <1% of cells — design already clean]

**Assessment:** [Per-phase breakdown of optimization effectiveness]

---

### Next-Run Suggestions

**[Finding]:** [N control sets — high packing pressure]

```tcl
opt_design -control_set_merge
```

**Rationale:** [Reduces packing pressure in next implementation iteration]

---

### Accept / Waive

**[Finding]:** [MARK_DEBUG on N nets — expected for debug, blocking optimization]

**Rationale:** [Acceptable if debug probes are intentional; remove MARK_DEBUG after debug complete]
```

---

## Optimization Phase Reference

The following opt_design phases and sub-commands should be recognized during log analysis:

| Phase/Sub-Command | Description | Key Message IDs |
|---|---|---|
| MBUFG sweep | Sweep/optimize MBUFGCE/MBUFG_GT buffers — remove unused, merge equivalent | `[Opt 31-389]` |
| MUXF optimization | Optimize MUX primitives (MUXF7/F8/F9) — create/remove based on timing | `[Opt 31-1005]`, `[Opt 31-1384]`–`[Opt 31-1389]` |
| Multi-level optimization (MLO) | Tieoff optimization, buffer removal, OBUF/IBUF insertion, BUFG_GT_SYNC | `[Opt 31-288]`, `[Opt 31-289]` |
| Push inverter | Push inverters through LUTs, IOB primitives (IDDR/ODDR), carry chains | `[Opt 31-1566]`, `[Opt 31-1561]`, `[Opt 31-138]` |
| BRAM memory opt | BRAM port optimization, power mode conversion, cascade detection | `[Opt 31-2042]` |
| SRL remap | Remap shift registers between SRL16/SRLC32 and flip-flops | `[Opt 31-389]` |
| BUFG GT sweep | Sweep/remove unused BUFG_GT instances | `[Opt 31-441]`, `[Opt 31-662]` |
| HFN BUFG insertion | Insert BUFGs for high-fanout nets at hierarchy boundaries | `[Opt 31-194]`, `[Opt 31-1077]` |
| HFN split load | Split high-fanout net loads across replicated buffers | `[Opt 31-389]` |
| LUT decomposition | Decompose wide LUTs (LUT6→LUT5+LUT5) for timing | `[Opt 31-2244]` |
| Lookahead8 remap | Remap carry-lookahead logic | `[Opt 31-1834]`, `[Opt 31-519]` |
| Split load | Replicate high-fanout drivers without BUFG insertion | `[Opt 31-389]` |
| Time-driven BUFG | Insert BUFGs based on timing analysis | `[Opt 31-194]` |
| SRL retarget | Retarget SRLs between fixed/variable-length modes | `[Opt 31-49]` |
| Resynth/remap | Re-synthesize and remap logic for QoR | `[Opt 31-2117]`–`[Opt 31-2118]` |
| LUT remap | Remap LUT equations for better packing | `[Opt 31-389]` |
| Aggressive LUT remap | More aggressive LUT remapping with area tradeoff | `[Opt 31-389]` |
| Property optimization | Optimize based on INIT values, constant propagation through properties | `[Opt 31-389]` |
| SLR optimization | SSI/SLR-aware optimizations for multi-die devices | `[Opt 31-422]` |
| Constant propagation | Propagate constant values through logic | `[Opt 31-389]` |
| BUFG insertion (Versal) | Versal-specific BUFG insertion (MMCM/DPLL/XPLL output buffering) | `[Opt 31-194]` |
| Set logic | Apply set_logic_one/set_logic_zero constraints | `[Opt 31-81]` |

### Common Issues After opt_design

| Symptom | Root Cause | Recommendation |
|---|---|---|
| VCC↔GND tieoff cell changes after sweep | Sweep or MLO merged/replaced constant sources differently | Verify tieoff connectivity; if functionally incorrect, constrain the tieoff net with DONT_TOUCH |
| IOB BEL assignment changed (e.g., HDIOLOGIC↔XPIOLOGIC) | Push-inverter through IOB changed BEL assignment due to architecture mapping | Expected on 7-series — verify functional correctness; no action usually needed |
| DRC REQP-2090 after MBUFG_GT sweep (CLR/CLRB_LEAF) | MBUFG_GT sweep left CLR/CLRB_LEAF pin in invalid state | Check AR73639 for CLR pin sequencing requirements; may need to constrain MBUFG_GT with DONT_TOUCH |
| `[Opt 31-81]` CRITICAL WARNING on set_logic | `set_logic_one`/`set_logic_zero` applied to an already-driven pin — constraint ignored | Remove the redundant constraint or fix the netlist so the pin is not driven |
| `[Opt 31-83]` series input buffers | Chained IBUF→IBUF or OBUF→OBUF in the RTL/netlist | Fix RTL to eliminate cascaded I/O buffers |
| Unexpected cell count after high-fanout-net (HFN) split | Driver replication created more cells than expected | Review `-hier_fanout_limit` threshold; lower value = more replication |
| `[Netlist 29-356]` non-native primitives remain | MUXCY/XORCY not fully remapped to CARRY8 during optimization | Run `opt_design -retarget` or re-synthesize the affected hierarchy |

---

## Directives Reference

| Directive | Purpose |
|---|---|
| `Explore` | Run all optimizations, pick best |
| `ExploreArea` | Optimize for area reduction |
| `ExploreWithRemap` | Include LUT remap pass |
| `NoBramPowerOpt` | Skip BRAM power optimization |
| `-merge_equivalent_drivers` | Merge replicated logic |
| `-control_set_merge` | Combine compatible control sets |
| `-hier_fanout_limit <N>` | Replicate high fanout drivers (min 512) |
| `-debug_log` | Log which constrained objects block optimization |
| `-resynth_seq_area` | Re-synthesize sequential logic for area |
| `-propconst` | Run only constant propagation |
| `-sweep` | Run only sweep (remove unconnected) |
| `-retarget` | Run only retarget (carry chain, inverter push) |
| `-muxf_remap` | Run only MUXF optimization |
| `-shift_register_opt` | Run only SRL optimization |
| `-aggressive_remap` | Aggressive LUT remapping |
