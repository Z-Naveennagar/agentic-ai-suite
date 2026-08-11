<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# TEMPLATES.md — Report & Iteration Templates

Templates for `versal-timing-closure` outputs. Fill every `[actual_*]` marker
with real values extracted from the Vivado reports — no generic placeholders.

## Table of Contents
- [iteration_log.csv](#iteration_logcsv)
- [TIMING_CLOSURE_REPORT.md](#timing_closure_reportmd)

---

## iteration_log.csv

One row per implementation attempt. Append after each stage that produces timing.

```csv
attempt,stage,place_dir,physopt_dir,route_dir,extra,WNS_ns,TNS_ns,WHS_ns,THS_ns,cong_level,qor_score,notes
1,postroute,Default,Explore,Default,,-0.412,-18.30,0.021,0.000,5,3,baseline
2,postroute,Explore,AggressiveExplore,Explore,net_delay_weight=high,-0.118,-2.10,0.015,0.000,5,4,congestion reduced
3,final,Explore,AggressiveExplore,AggressiveExplore,pr_physopt,0.004,0.000,0.011,0.000,4,5,closed
```

Columns: `cong_level` = worst interconnect congestion level (4–7+ or `-` if none);
`qor_score` = `report_qor_assessment` Overall Score (1–5).

---

## TIMING_CLOSURE_REPORT.md

```markdown
# Versal Timing Closure Report — [actual_design_name]

**Device:** [actual_part]  |  **SLRs:** [actual_n_slr] ([SSI|monolithic])
**Vivado:** [actual_version]  |  **Methodology:** UG1788
**Final status:** [✅ Closed | ⚠️ Not closed — N paths remain]

## 1. Summary
| Metric | Baseline | Final | Target |
|---|---|---|---|
| WNS (ns) | [actual] | [actual] | ≥ 0 |
| TNS (ns) | [actual] | [actual] | 0 |
| WHS (ns) | [actual] | [actual] | ≥ 0 |
| THS (ns) | [actual] | [actual] | 0 |
| Worst congestion level | [actual] | [actual] | ≤ 4 |
| QoR Assessment score | [actual] | [actual] | 5 |
| Fully routed | [Y/N] | [Y/N] | Y |

## 2. Dominant Limiter(s)
Per UG1788 path-characteristic analysis (logic delay / net delay / clock skew /
clock uncertainty / hold). For the worst path(s):

- **Worst setup path:** [actual_startpoint] → [actual_endpoint]
  - Logic delay: [x] ns ([n] levels) | Net delay: [x] ns | Skew: [x] ns | Uncertainty: [x] ns
  - **Primary limiter:** [LOGIC|NET/CONGESTION|SKEW|UNCERTAINTY|HOLD]
- **Worst hold path:** [actual_startpoint] → [actual_endpoint] (WHS [x] ns)

## 3. Iteration Log
See `iteration_log.csv`. Highlights:
| Attempt | Change | WNS | WHS | Outcome |
|---|---|---|---|---|
| 1 | baseline ([dirs]) | [x] | [x] | [...] |
| 2 | [change] | [x] | [x] | [...] |
| N | [change] | [x] | [x] | closed/plateaued |

## 4. Applied Fixes
For each fix actually applied (constraints/properties/directives):

### [LIMITER] — [short description]
📋 **Copy-Paste Fix**
```tcl
[exact Tcl/XDC with ACTUAL names, e.g.:]
set_property CLOCK_BUFFER_TYPE BUFG_FABRIC [get_nets fpga1/ctrl/rst_n_net]
# Verify: report_timing_summary ; confirm WNS improved
```

## 5. Recommended RTL/Constraint Changes (need user action)
Changes that require source edits or re-synthesis (not auto-applied):
- [ ] **[path/module]** — [recommendation, e.g. add pipeline stage around DSP
  cascade `fpga1/dp_core/mac_*`]. Reference: UG1788 [section].
- [ ] **[control signal]** — set `(* extract_enable = "no" *)` on
  `[actual_signal]` in RTL.

## 6. Delegated Analysis
| Stage | Skill | Key finding | Report |
|---|---|---|---|
| opt_design | opt-design-analysis | [summary] | [path] |
| post-place | congestion-analysis | [summary] | [path] |
| post-place/route | timing-methodology-checks | [summary] | [path] |
| phys_opt_design | phys-opt-design-analysis | [summary] | [path] |

## 7. Remaining Violations (if not closed)
| Path | Slack | Limiter | Recommended next step |
|---|---|---|---|
| [actual] | [x] ns | [type] | [directive/strategy/RTL] |

## 8. Reproduce
Final flow that produced the best result:
```tcl
open_checkpoint [actual_start_dcp]
opt_design
place_design -directive [actual_place_dir]
phys_opt_design -directive [actual_physopt_dir]
route_design -directive [actual_route_dir]
phys_opt_design          ;# post-route, if used
report_timing_summary -file final_timing_summary.rpt
```

## References
- UG1788 (Timing Closure Quick Reference), UG1388, UG906, UG904, UG901.
```
