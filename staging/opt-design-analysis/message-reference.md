<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# opt_design Message Reference

> Actionable `[Opt 31-*]` messages that require **user intervention** — RTL code changes or XDC constraint modifications.
> Internal tool errors, informational messages, and agent-only re-runs are excluded.
>
> **Legend:** `🔧 Tcl` = execute via vivado_execute | `📋 Report` = report to user for RTL/XDC change | **Fix:** `RTL` or `XDC`

---

## 1. Connectivity Errors

| ID | Severity | Message Summary | Fix | Agent Action |
|---|---|---|---|---|
| `31-1` | ERROR | Pin not connected to top-level port | RTL | 🔧 `report_drc -check {NSTD-1} -file drc_conn.rpt`. 📋 Report unconnected pin path — user must connect in RTL. |
| `31-2` | ERROR | Pin missing a connection (no driver) | RTL | 🔧 `get_pins -of [get_cells <cell>] -filter {DIRECTION==IN && IS_CONNECTED==FALSE}`. 📋 Report undriven input pins. |
| `31-7` | ERROR | Missing LUT input connection | RTL | 🔧 `get_property INIT [get_cells <cell>]` and `get_pins -of [get_cells <cell>] -filter {IS_CONNECTED==FALSE}`. 📋 Report. |
| `31-67` | ERROR | Cell missing required input after trimming | RTL | 🔧 `get_pins -of [get_cells <cell>] -filter {DIRECTION==IN && IS_CONNECTED==FALSE}`. 📋 Report — input was trimmed/left unconnected; user must restore connectivity in RTL. |
| `31-30`/`31-31` | ERROR | Blackbox module not implemented | RTL | 🔧 `get_cells -hier -filter {IS_BLACKBOX==TRUE}`. 📋 Report — user must implement missing modules. |
| `31-66` | ERROR | Driverless net — load cell won't work | RTL | 🔧 `get_pins -of [get_nets <net>] -filter {DIRECTION==OUT}`. 📋 Report net path and loads. |
| `31-236` | ERROR | Primitives driven by blackboxes | RTL | 🔧 `get_cells -hier -filter {IS_BLACKBOX==TRUE}`. 📋 Report affected connections — user must implement modules. |
| `31-290` | ERROR | Multi-driver net | RTL | 🔧 `get_pins -of [get_nets <net>] -filter {DIRECTION==OUT}`. 📋 Report — user must fix multi-driver in RTL. |
| `31-304`/`31-305` | ERROR | Invalid connectivity — multiple sources | RTL | 🔧 `get_pins -of [get_nets <net>] -filter {DIRECTION==OUT}`. 📋 Report. |
| `31-349` | ERROR | Pin without terminal or driver | RTL | 🔧 `get_pins <pin> -filter {IS_CONNECTED==FALSE}`. 📋 Report dangling pin. |

---

## 2. Device / Architecture Errors

| ID | Severity | Message Summary | Fix | Agent Action |
|---|---|---|---|---|
| `31-14` | ERROR | Device doesn't support feature | RTL | 🔧 `get_property ARCHITECTURE [current_design]`. 📋 Report — user must remove unsupported primitives from RTL. |
| `31-132` | ERROR | Cannot process cell type | RTL | 🔧 `get_property REF_NAME [get_cells <cell>]`. 📋 Report — user may need different primitive for target device. |
| `31-1078` | ERROR | Too many cells of type for Versal | RTL | 🔧 `report_utilization -file util_overuse.rpt`. 📋 Report — user must reduce resource usage in RTL. |
| `31-1079` | ERROR | Attribute not supported in Versal | XDC | 🔧 `report_property [get_cells <cell>]`. 🔧 `reset_property <attr> [get_cells <cell>]`. |
| `31-1080` | ERROR | Pin not supported in Versal | RTL | 📋 Report — primitive must be replaced for Versal migration. |
| `31-350`/`31-351` | CRIT_WARN | Cell not supported but has constraints | XDC | 🔧 `report_property [get_cells <cell>]`. 🔧 If LOC: `reset_property LOC [get_cells <cell>]`. |
| `31-1012` | CRIT_WARN | CLOCK_BUFFER_TYPE not supported | XDC | 🔧 `set_property CLOCK_BUFFER_TYPE BUFG [get_nets <net>]`. |

---

## 3. DONT_TOUCH / Constraint Blocking (XDC Fix)

| ID | Severity | Message Summary | Agent Action |
|---|---|---|---|
| `31-111` | CRIT_WARN | DONT_TOUCH blocking ZHOLD_DELAY | 🔧 `report_timing -through [get_nets <net>] -max_paths 1`. If not critical: `reset_property DONT_TOUCH [get_nets <net>]`. |
| `31-257`–`31-261` | ERROR | DONT_TOUCH preventing optimization | 🔧 `reset_property DONT_TOUCH [get_cells <cell>]` or `reset_property DONT_TOUCH [get_nets <net>]`. |
| `31-444`–`31-447` | ERROR | BUFMR retarget blocked by DONT_TOUCH | 🔧 `reset_property DONT_TOUCH [get_cells <bufmr>]` and/or `reset_property DONT_TOUCH` on connected nets. |
| `31-448` | ERROR | BUFMR inversion on I pin | 📋 Report — user must remove inversion in **RTL** (Fix: RTL). |
| `31-449`–`31-455` | ERROR | BUFMRCE/BUFR load constraints | 🔧 `reset_property DONT_TOUCH` on blocking cells/nets. |
| `31-456`–`31-463` | ERROR | BUFR retarget blocked | 🔧 `reset_property DONT_TOUCH` on flagged nets. For inversions: 📋 report for **RTL** fix. |

---

## 4. BUFG / Clock Buffer Errors

| ID | Severity | Message Summary | Fix | Agent Action |
|---|---|---|---|---|
| `31-137` | ERROR | Loads don't share CE/CLR | RTL | 🔧 `foreach c {<cell1> <cell2>} {puts "$c CE=[get_nets -of [get_pins $c/CE]] CLR=[get_nets -of [get_pins $c/CLR]]"}`. 📋 Report — user must unify CE/CLR in RTL. |
| `31-214` | ERROR | BUFG_GT CE net mismatch | RTL | 🔧 `foreach bg [get_cells -hier -filter {REF_NAME=~BUFG_GT*}] {puts "$bg CE=[get_nets -of [get_pins $bg/CE]]"}`. 📋 Report — RTL must unify CE signals. |
| `31-215` | ERROR | BUFG_GT CLR net mismatch | RTL | Same as 31-214, check CLR pin. |
| `31-317` | CRIT_WARN | BUFG insertion failed — DONT_TOUCH | XDC | 🔧 `reset_property DONT_TOUCH [get_nets <net>]`. |
| `31-1091` | ERROR | MBUFG conversion blocked | XDC | 🔧 Remove DONT_TOUCH on MBUFG_GROUP cells. |

---

## 5. Design Rule Checks

| ID | Severity | Message Summary | Fix | Agent Action |
|---|---|---|---|---|
| `31-40` | CRIT_WARN | Conflicting IOB constraints blocking ZHOLD | XDC | 🔧 `reset_property IOB [get_cells <cell>]` on non-essential one. |
| `31-42` | ERROR | Multiple CAPTURE elements | RTL | 🔧 `get_cells -hier -filter {REF_NAME=~CAPTURE*}`. 📋 Report — user must remove duplicate. |
| `31-43` | ERROR | Multiple STARTUP elements | RTL | 🔧 `get_cells -hier -filter {REF_NAME=~STARTUP*}`. 📋 Report — user must remove duplicate. |
| `31-78` | CRIT_WARN | S and R both active on cell | RTL | 🔧 `get_nets -of [get_pins <cell>/S]` and `get_nets -of [get_pins <cell>/R]`. 📋 Report — user must disconnect one in RTL. |
| `31-168` | CRIT_WARN | LOCK_PINS lost | XDC | 🔧 Re-apply: `set_property LOCK_PINS {I0:A1 I1:A2} [get_cells <cell>]`. |
| `31-198` | ERROR | CARRY4 CI+CYINIT both active | RTL | 🔧 `get_nets -of [get_pins <cell>/CI]` and `get_nets -of [get_pins <cell>/CYINIT]`. 📋 Report — user must use only one. |
| `31-377` | ERROR | CLOCK_DOMAINS=COMMON but different sources | XDC | 🔧 `set_property CLOCK_DOMAINS INDEPENDENT [get_cells <cell>]`. |
| `31-430` | CRIT_WARN | Data pin undriven | RTL | 🔧 `get_pins -of [get_cells <cell>] -filter {DIRECTION==IN && IS_CONNECTED==FALSE}`. 📋 Report — user must connect driver. |
| `31-443` | CRIT_WARN | Feedback loop in constant propagation | RTL | 🔧 `report_timing -from [get_cells <cell>] -to [get_cells <cell>] -max_paths 1`. 📋 Report — user must break combinational loop. |

---

## 6. I/O Buffer Warnings

| ID | Severity | Message Summary | Fix | Agent Action |
|---|---|---|---|---|
| `31-32`/`31-33` | WARNING | Redundant IBUF/OBUF removed | RTL | 📋 Report redundant buffer names — user should remove from RTL. |
| `31-35`/`31-36` | WARNING | Redundant IBUF/OBUF on port path | RTL | 📋 Report cascaded buffers — user should remove from RTL. |
| `31-110` | ERROR | Output buffers in series | RTL | 🔧 `get_cells -of [get_pins -leaf -of [get_nets -of [get_pins <cell>/O]]]`. 📋 Report buffer chain — user must fix RTL. |

---

## 7. Driverless Net / Multi-Driver Warnings

| ID | Severity | Message Summary | Fix | Agent Action |
|---|---|---|---|---|
| `31-6`/`31-8` | WARNING | Driverless net | RTL | 🔧 `get_pins -of [get_nets <net>] -filter {DIRECTION==OUT}`. 📋 Report — user must add driver in RTL. |
| `31-80` | WARNING | Multi-driver net | RTL | 🔧 `get_pins -of [get_nets <net>] -filter {DIRECTION==OUT}`. 📋 Report — user must fix multiple assignments in RTL. |

---

## 8. MARK_DEBUG / Property Warnings (XDC Fix)

| ID | Severity | Message Summary | Agent Action |
|---|---|---|---|
| `31-79` | WARNING | DONT_TOUCH cell removed (no loads) | To prevent: `set_property DONT_TOUCH true [get_nets -of [get_cells <cell>]]` (protect the *net*). |
| `31-139` | WARNING | User constraint disobeyed | To preserve: `set_property DONT_TOUCH true [get_cells <cell>]`. |
| `31-232`/`31-233` | WARNING | MARK_DEBUG net optimized | `set_property DONT_TOUCH true [get_nets <net>]`. |

---

## 9. Buffer Insertion / Clock Separation (XDC Fix)

| ID | Severity | Message Summary | Agent Action |
|---|---|---|---|
| `31-143`/`31-145` | WARNING | Auto BUFG on high-fanout net — risk | 📋 Report fanout count — user should manually insert BUFG in RTL (Fix: RTL). |
| `31-278` | WARNING | Cascaded clock buffer opt failed | 🔧 `reset_property DONT_TOUCH [get_cells <cell>]`. |
| `31-295`/`31-1075` | WARNING | Clock load separation failed | 🔧 `reset_property DONT_TOUCH` on blocking clock nets. |
| `31-313` | WARNING | CLOCK_BUFFER_TYPE=NONE blocking insertion | 🔧 `set_property CLOCK_BUFFER_TYPE BUFG [get_nets <net>]`. |
| `31-1556` | WARNING | BUFGCE→BUFG_FABRIC blocked by timing | 📋 Report — timing constraint may need relaxation in XDC. |

---

## 10. Carry Remap Issues (XDC Fix)

| ID | Severity | Message Summary | Agent Action |
|---|---|---|---|
| `31-512` | WARNING | Carry remap blocked by constraints | 🔧 `reset_property DONT_TOUCH [get_cells <cell>]`. |
| `31-513`/`31-514`/`31-1126`/`31-1127` | WARNING | Inconsistent CARRY_REMAP values | 🔧 Unify: `set_property CARRY_REMAP <value> [get_cells {<chain_cells>}]`. |
| `31-516` | WARNING | Cannot remap reg chain to SRL | 🔧 `reset_property DONT_TOUCH [get_cells <cell>]`. |
| `31-520` | WARNING | Carry remap skipped — threshold/constraint not met | 🔧 Review `CARRY_REMAP` property and `-carry_remap` threshold; `reset_property DONT_TOUCH [get_cells <cell>]` if a blocking constraint applies, else accept. |

---

## 11. Control Set Reduction

| ID | Severity | Message Summary | Fix | Agent Action |
|---|---|---|---|---|
| `31-1557` | WARNING | Async flop — control set reduction unsupported | RTL | 📋 Report — user should convert async resets to sync in RTL. |
| `31-1842` | WARNING | Cell cannot be removed (DONT_TOUCH) | XDC | 🔧 `reset_property DONT_TOUCH [get_cells <cell>]`. |
| `31-1843` | WARNING | Physical constraint on cell | XDC | 🔧 If non-essential: `reset_property LOC [get_cells <cell>]`. |
| `31-1844` | WARNING | Control set reduction blocked — incompatible CE/CLR | RTL | 📋 Report — loads do not share a compatible control set; user should unify CE/CLR in RTL. |
| `31-1845` | WARNING | Control set reduction skipped — no benefit / no candidate | — | 📋 Informational — no mergeable control sets found; no action required. |

---

## 12. BUFG / MBUFG Warnings (XDC Fix)

| ID | Severity | Message Summary | Agent Action |
|---|---|---|---|
| `31-1090` | WARNING | MMCM INTERNAL comp with external feedback | 🔧 `set_property COMPENSATION INTERNAL [get_cells <mmcm>]`. |
| `31-1115` | WARNING | MBUFG_GROUP transformation blocked | 🔧 `reset_property DONT_TOUCH [get_cells <cell>]`. |
| `31-2386` | WARNING | BUFGCE CE_TYPE issue on Versal | 🔧 `set_property CE_TYPE SYNC [get_cells <bufgce>]`. |
| `31-2387` | WARNING | BUFGCE_DIV invalid HARDSYNC_CLR | 🔧 `set_property HARDSYNC_CLR TRUE [get_cells <cell>]`. |

---

## 13. Clock Constraint Gap

| ID | Severity | Message Summary | Fix | Agent Action |
|---|---|---|---|---|
| `31-2261` | WARNING | Net has no clock defined — CCI skipped | XDC | 📋 Report — user must add clock constraint (`create_clock` or `create_generated_clock`). |

---

## Grep Patterns

```bash
# RTL-fix messages (connectivity, DRC, IO, control sets)
sed -n '/Command: opt_design/,/opt_design: Time/p' <logfile> | grep -E "\[Opt 31-(1|2|6|7|8|30|31|32|33|35|36|42|43|66|67|78|80|110|137|198|214|215|236|290|304|305|349|430|443|1078|1080|1557|1844)\]"

# XDC-fix messages (DONT_TOUCH, property, constraint blocking)
sed -n '/Command: opt_design/,/opt_design: Time/p' <logfile> | grep -E "\[Opt 31-(40|79|111|139|168|232|233|257|258|259|260|261|278|295|313|317|350|351|377|444|445|446|447|448|449|512|513|514|516|520|1012|1075|1079|1090|1091|1115|1556|1842|1843|1845|2261|2386|2387)\]"
```
