<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# phys_opt_design Message Reference

> Actionable `[Physopt 32-*]` messages that require **user intervention** — RTL code changes or XDC constraint modifications.
> Internal tool errors, informational messages, prerequisite errors, timing degradation (agent re-run), and rewire skip reasons are excluded.
>
> **Legend:** `🔧 Tcl` = execute via vivado_execute | `📋 Report` = report to user for RTL/XDC change | **Fix:** `RTL` or `XDC`

---

## 1. AUTOPIPELINE Errors

| ID | Severity | Message Summary | Fix | Agent Action |
|---|---|---|---|---|
| `32-909` | CRIT_WARN | Non-constant input on SRL pin | RTL | 📋 Report — user must fix RTL so autopipeline SRL input is constant. |
| `32-1122` | CRIT_WARN | AUTOPIPELINE_GROUP inconsistent depth | RTL | 📋 Report inconsistent nets — user must equalize pipeline depth in RTL. |
| `32-1124` | CRIT_WARN | AUTOPIPELINE without AUTOPIPELINE_GROUP | XDC | 🔧 `set_property AUTOPIPELINE_GROUP <group_name> [get_cells <cell>]`. |
| `32-1125`/`32-1126` | CRIT_WARN | AUTOPIPELINE_INCLUDE references invalid group | RTL | 📋 Report — user must fix or create the referenced group. |
| `32-1127` | CRIT_WARN | Inconsistent AUTOPIPELINE_LIMIT | XDC | 🔧 Unify: `set_property AUTOPIPELINE_LIMIT <value>` on all group nets. |
| `32-1128` | CRIT_WARN | Fanout exceeds AUTOPIPELINE limit | RTL | 📋 Report — user should reduce fanout in RTL, or increase `AUTOPIPELINE_LIMIT`. |
| `32-1129` | CRIT_WARN | Net not driven by register | RTL | 📋 Report — user must ensure register drives the autopipeline net. |
| `32-1500` | CRIT_WARN | AUTOPIPELINE net doesn't drive storage | RTL | 📋 Report — user must add register at net endpoint. |
| `32-1501` | CRIT_WARN | AUTOPIPELINE on HD net — skipped | RTL | 📋 Report — HD nets cannot be autopipelined. User must restructure design. |

---

## 2. SLR / Laguna Issues

| ID | Severity | Message Summary | Fix | Agent Action |
|---|---|---|---|---|
| `32-769` | ERROR | Flop in Laguna site but not TX/RX | XDC | 📋 Report — only TX/RX registers belong in Laguna sites. User must adjust placement constraints. |
| `32-944` | CRIT_WARN | Address net conflict across SLR | XDC | 🔧 `report_timing -through [get_pins -of [get_cells <cell>]] -max_paths 3`. 📋 Report cross-SLR conflict. |
| `32-954` | CRIT_WARN | Skip hold fix on Laguna TX→RX paths | RTL | 📋 Report clocking topology issue — user should adjust clock tree or add pipeline stages. |
| `32-957` | CRIT_WARN | Cannot fix hold — different SLRs, no room | RTL | 📋 Report — user should add Laguna pipeline stages or adjust clock skew. |
| `32-1019` | CRIT_WARN | DONT_TOUCH preventing SLR pipeline insertion | XDC | 🔧 `reset_property DONT_TOUCH [get_nets <net>]`. |

---

## 3. Clock Constraint

| ID | Severity | Message Summary | Fix | Agent Action |
|---|---|---|---|---|
| `32-1304` | WARNING | CLOCK_EXPANSION_WINDOW match failed | XDC | 📋 Report constraint value — user may need to adjust `CLOCK_EXPANSION_WINDOW` in XDC. |

---

## 4. ASYNC_REG Blocking

| ID | Severity | Message Summary | Fix | Agent Action |
|---|---|---|---|---|
| `32-723` | CRIT_WARN | Replication blocked by ASYNC_REG | XDC | 🔧 Check criticality: `report_timing -through [get_pins -of [get_cells <cell>]] -max_paths 3`. If synchronizer not needed: `reset_property ASYNC_REG [get_cells <cell>]`. If synchronizer IS needed: `set_property DONT_TOUCH true [get_cells <cell>]`. |

---

## 5. DONT_TOUCH / Constraint Blocking (XDC Fix)

| ID | Severity | Message Summary | Agent Action |
|---|---|---|---|
| `32-558` | WARNING | XDC constraint preventing register opt | 📋 Report constraint and timing paths — user can remove constraint in XDC if optimization is preferred. |
| `32-559` | WARNING | No XDC constraints — forced replication skipped | 📋 Report — user must add constraints (`create_clock`, `set_max_delay`) to XDC to enable phys_opt. |

---

## 6. MARK_DEBUG Warning (XDC Fix)

| ID | Severity | Message Summary | Agent Action |
|---|---|---|---|
| `32-722` | WARNING | MARK_DEBUG net optimized | 🔧 `set_property DONT_TOUCH true [get_nets <net>]`. |

---

## 7. DSP / BRAM / URAM Issues

| ID | Severity | Message Summary | Fix | Agent Action |
|---|---|---|---|---|
| `32-744` | WARNING | DSP flop packing not feasible — multi-load | RTL | 📋 Report — user should reduce fanout on DSP input net in RTL. |
| `32-848` | ERROR | URAM chain length mismatch | RTL | 📋 Report chain/pipeline mismatch — user must fix CASCADE_ORDER in RTL. |

---

## 8. Hold Fix Issues

| ID | Severity | Message Summary | Fix | Agent Action |
|---|---|---|---|---|
| `32-1021` | WARNING | >50 candidates for SLL hold fix | RTL | 📋 Report hold violation count on SLR crossings — user should add pipeline stages or adjust clocking. |
| `32-1495` | WARNING | Skip post-route hold fix (too many violations) | RTL | 📋 Report violation count — must be addressed at architecture level (clock tree, pipelining). |

---

## 9. Retiming Warnings

| ID | Severity | Message Summary | Fix | Agent Action |
|---|---|---|---|---|
| `32-1139` | WARNING | Conflicting retiming properties | XDC | 🔧 Remove conflicting: `reset_property RETIMING_BACKWARD [get_cells <cell>]` (or `reset_property PHYSOPT_RETIMING_BACKWARD`). |
| `32-1137` | WARNING | SRL/register control set mismatch | RTL | 📋 Report mismatch — user must fix control sets in RTL. |

---

## 10. Clock Polarity

| ID | Severity | Message Summary | Fix | Agent Action |
|---|---|---|---|---|
| `32-1045` | CRIT_WARN | Clock pin invertness mismatch | RTL | 📋 Report — cells in equivalent-driver group must share clock polarity. User must unify in RTL. |

---

## 11. Placement Conflicts (XDC Fix)

| ID | Severity | Message Summary | Agent Action |
|---|---|---|---|
| `32-738` | WARNING | Cannot place cell at location | 📋 Report — site may be occupied or incompatible. User should adjust LOC/PBLOCK in XDC. |
| `32-892` | WARNING | Could not move cell | 🔧 If LOC not essential: `reset_property LOC [get_cells <cell>]`. Otherwise 📋 report blocking constraint. |
| `32-894` | WARNING | `-through` constraint prevents optimization | 📋 Report — user should review if `-through` is necessary in timing constraint XDC. |

---

## Grep Patterns

```bash
# RTL-fix messages (AUTOPIPELINE, DSP/URAM, hold, retiming, clock polarity)
sed -n '/Command: phys_opt_design/,/phys_opt_design.*Time/p' <logfile> | grep -E "\[Physopt 32-(744|848|909|954|957|1021|1045|1122|1125|1126|1128|1129|1137|1495|1500|1501)\]"

# XDC-fix messages (DONT_TOUCH, placement, MARK_DEBUG, SLR, ASYNC_REG, retiming)
sed -n '/Command: phys_opt_design/,/phys_opt_design.*Time/p' <logfile> | grep -E "\[Physopt 32-(558|559|722|723|738|769|892|894|944|1019|1124|1127|1139|1304)\]"
```
