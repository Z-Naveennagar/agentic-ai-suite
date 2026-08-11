---
name: hw-sysmon
description: >
  Read device health (temperature, supply voltages, alarms) from a live FPGA/SoC via Vivado
  Hardware Manager hw_sysmon Tcl commands. Produces a structured health report (report_data.json),
  markdown summary (REPORT.md), and interactive HTML dashboard (dashboard.html). Supports all
  device families: Versal (AM006), UltraScale/UltraScale+ (UG580/SYSMONE1/SYSMONE4),
  7 Series / Zynq (UG480/XADC), and Zynq UltraScale+ MPSoC (UG1085). Use when user asks to
  "check device health", "read temperature", "check supply voltages", "sysmon status",
  "device health check", "thermal check", "power rail check", "alarm status", "OT status",
  "is the device overheating", "what is die temperature", "VCCINT voltage", or
  "monitor device health".
version: 1.2.0-ea
maturity: early-access
vivado_version: "2025.1+"
categories: [hardware-debug, device-health, sysmon, monitoring]
device_families: [versal, ultrascale-plus, ultrascale, 7series, zynq, zynq-ultrascale-plus]
estimated_duration: 1-3 minutes
complexity: beginner-to-intermediate
author: Vivado AI Skills Team
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
# SysMon / Device Health Check (EA)

> **Early Access** — this skill may change before general availability.

Reads live device health from connected hardware. Produces `report_data.json`, `REPORT.md`, and `dashboard.html`. Requires a live hw_server connection with a programmed device.

See [REFERENCE.md](REFERENCE.md) for register maps, property lists, voltage tables, JSON schema, and report templates.

**Routing:** Try Vivado MCP (`vivado_execute` + `hw_sysmon` Tcl, below) first if a Vivado MCP session is available — it works across all device families. Fall back to chipscope-mcp (`chipscope_sysmon`) if Vivado MCP is not installed. See [Chipscope-mcp Fallback](#chipscope-mcp-fallback) below.

## Tools Used

**Primary path — Vivado MCP** (plus the agent's own file tools):

| Tool | Purpose |
|------|---------|
| `vivado_execute` | Run all Tcl commands (`get_hw_sysmons`, `refresh_hw_sysmon`, `get_property`, `get_hw_sysmon_reg`, etc.). Every Tcl block in this skill MUST be run via `vivado_execute(session_id=..., command=<tcl>)`. |
| `vivado_doc_search` | Look up unfamiliar properties, register addresses, or device-family behavior. No `session_id` needed. |
| `vivado_status` | Check if a Vivado session is healthy before starting. No `session_id` needed for listing. |
| `vivado_list_sessions` | Find an active session to use (get its `session_id`). |
| Agent file tools | Write output files (report_data.json, REPORT.md, dashboard.html). |

**Fallback path — chipscope-mcp** (when Vivado MCP is unavailable): `chipscope_session`, `chipscope_device`, `chipscope_sysmon` (`action='read_all'`). See [Chipscope-mcp Fallback](#chipscope-mcp-fallback).

**No terminal commands, no Python.** Everything goes through Vivado MCP or, as fallback, chipscope-mcp.

---

## Efficiency Guidelines

- **Pass `session_id`** to every `vivado_execute` call — get it from `vivado_list_sessions` if unknown.
- **Batch Tcl** — send one `vivado_execute` with all reads, not one call per property.
- **Write reports to file** — do not dump full content in chat. Give a short summary only.
- **Use `vivado_doc_search`** when encountering unfamiliar hw_sysmon properties, register addresses, or device-family-specific behavior (e.g., Versal PMC SysMon vs. UltraScale SYSMONE4).
- **Do NOT** use `shell ls`, `shell find`, or `shell glob` to locate files.
- **Do NOT** use Vivado Tcl (`exec cat`, `open`, `read`) to read files. Use your agent file reader tool.
- **Do NOT** retry a failed Tcl command with different syntax. Use `vivado_doc_search` first, then report the error.

---

## Mandatory Workflow

**⚠️ Execute steps SEQUENTIALLY.** The workflow is incomplete until ALL THREE output files exist (REPORT.md, report_data.json, dashboard.html). Write files before giving any summary.

### Step 1: Verify Connection & Discover SysMon

Run via `vivado_execute(session_id=<id>, command=<tcl below>)`:

```tcl
if {[llength [get_hw_servers]] == 0} { puts "ERROR: No hw_server. Run: connect_hw_server -url <host>:<port>"; return }
if {[llength [get_hw_targets]] == 0} { puts "ERROR: No hw_target. Run: open_hw_target"; return }
refresh_hw_device [current_hw_device]
set sysmons [get_hw_sysmons -quiet]
if {[llength $sysmons] == 0} { puts "ERROR: No hw_sysmon. Run: refresh_hw_device [current_hw_device]"; return }
puts "SYSMON_COUNT:[llength $sysmons]"
foreach s $sysmons { puts "SYSMON:$s DESC:[get_property DESCRIPTION $s]" }
set dev [current_hw_device]
puts "DEVICE:[get_property NAME $dev] PART:[get_property PART $dev]"
```

**Device family detection:**
- DESCRIPTION == `"XADC"` → 7 Series / Zynq (UG480)
- DESCRIPTION == `"System Monitor"` → UltraScale/US+ (UG580) or Versal (AM006)
- Multiple sysmon objects on Zynq US+ → PS + PL SysMon (UG1085)

**No SysMon found** → STOP. Guide user: `refresh_hw_device [current_hw_device]`

---

### Step 2: Read All Sensor Data

**Auto-discover first** via `vivado_execute(session_id=<id>, command=<tcl below>)`, then read known properties:

```tcl
set s [lindex [get_hw_sysmons] 0]
refresh_hw_sysmon $s
puts "=== ALL PROPERTIES ==="
report_property -all $s
```

Parse the `report_property` output to discover device-specific properties (especially Versal extended supplies). Then read structured values:

**Versal note:** the `TEMPERATURE` property does not exist on Versal SysMon objects — use `DEVICE_TEMP` instead. Try `TEMPERATURE` first (UltraScale/US+/7-Series/Zynq) and fall back to `DEVICE_TEMP` (Versal) if it errors:

```tcl
puts "=== TEMPERATURE ==="
if {[catch {get_property TEMPERATURE $s} temp]} { set temp [get_property DEVICE_TEMP $s] }
puts "TEMP:$temp"
puts "TEMP_MAX:[get_property TEMPERATURE_MAX $s]"
puts "TEMP_MIN:[get_property TEMPERATURE_MIN $s]"
puts "TEMP_SCALE:[get_property TEMPERATURE_SCALE $s]"
puts "=== CORE SUPPLIES ==="
foreach prop {VCCINT VCCAUX VCCBRAM VPVN} {
  catch { puts "${prop}:[get_property $prop $s]" }
}
foreach prop {VCCINT_MAX VCCAUX_MAX VCCBRAM_MAX VCCINT_MIN VCCAUX_MIN VCCBRAM_MIN} {
  catch { puts "${prop}:[get_property $prop $s]" }
}
puts "=== US+ SUPPLIES ==="
foreach prop {VUSER0 VUSER1 VUSER2 VUSER3} {
  catch { puts "${prop}:[get_property $prop $s]" }
}
puts "=== ZU+ PS ==="
foreach prop {VCC_PSINTLP VCC_PSINTFP VCC_PSAUX} {
  catch { puts "${prop}:[get_property $prop $s]" }
}
puts "=== ALARMS ==="
foreach prop {FLAG.ALM0 FLAG.ALM1 FLAG.ALM2 FLAG.ALM3 FLAG.ALM4 FLAG.ALM5 FLAG.ALM6 FLAG.OT FLAG.JTGD FLAG.JTGB FLAG.REF} {
  catch { puts "${prop}:[get_property $prop $s]" }
}
foreach prop {CONFIG_REG.OT CONFIG_REG.ALM0 CONFIG_REG.ALM1 CONFIG_REG.ALM2 CONFIG_REG.ALM3 CONFIG_REG.SEQ CONFIG_REG.AVG CONFIG_REG.CH} {
  catch { puts "${prop}:[get_property $prop $s]" }
}
puts "=== CALIBRATION ==="
foreach prop {ADC_A_OFFSET ADC_A_GAIN ADC_B_OFFSET ADC_B_GAIN SUPPLY_OFFSET} {
  catch { puts "${prop}:[get_property $prop $s]" }
}
```

For alarm threshold raw registers (including VUSER on US+):
```tcl
puts "=== THRESHOLDS ==="
foreach {name addr} {TEMP_UPPER 50 VCCINT_UPPER 51 VCCAUX_UPPER 52 OT_UPPER 53 TEMP_LOWER 54 VCCINT_LOWER 55 VCCAUX_LOWER 56 OT_LOWER 57 VCCBRAM_UPPER 58 VCCBRAM_LOWER 5C VUSER0_UPPER 60 VUSER1_UPPER 61 VUSER2_UPPER 62 VUSER3_UPPER 63} {
  catch { puts "THR_${name}:[get_hw_sysmon_reg $s $addr]" }
}
```

For auxiliary analog inputs (7 Series / XADC — 16 channels):
```tcl
puts "=== AUX CHANNELS ==="
for {set i 0} {$i < 16} {incr i} {
  catch { puts "VAUX${i}:[get_hw_sysmon_reg $s [format %02x [expr {0x10 + $i}]]]" }
}
```

**Multi-SysMon / multi-SLR:** Iterate all sysmon objects. On Zynq US+ there are PS + PL objects. On multi-SLR devices (e.g. VU9P) there may be one SysMon per SLR.
```tcl
foreach s [get_hw_sysmons] {
  puts "=== SYSMON: $s ==="
  refresh_hw_sysmon $s
  # ... repeat reads above for each $s ...
}
```

---

### Step 3: Assess Health

**Voltage:** Compare each supply to nominal (see [REFERENCE.md](REFERENCE.md) for tables). Flag ±3% YELLOW, ±5% ORANGE, ±10% RED.

**Temperature:** < 70°C GREEN, 70–85°C YELLOW, 85–100°C ORANGE, ≥100°C RED. Calculate `margin_to_ot = OT_threshold - current_temp`.

**Alarms:** Any FLAG.ALMx == 1 → RED. FLAG.OT == 1 → CRITICAL. CONFIG_REG.OT == 1 (OT disabled) → WARNING.

**Overall score (1-5):** See [REFERENCE.md](REFERENCE.md). Score = min(temp_score, supply_score, alarm_score).

---

### Step 4: Generate Recommendations

Apply all matching rules from the recommendation engine in [REFERENCE.md](REFERENCE.md). Prioritize by severity: CRITICAL → HIGH → MEDIUM → INFO.

---

### Step 5: Write Output Files

**⚠️ Write ALL files before giving any summary.** Use the agent's file creation tool (not Vivado Tcl).

```bash
mkdir -p vivado_agentic_ai_reports/hw-sysmon
```

| File | Format | Content |
|------|--------|---------|
| `report_data.json` | JSON | Structured metrics (schema in [REFERENCE.md](REFERENCE.md)) |
| `REPORT.md` | Markdown | Executive summary (template in [REFERENCE.md](REFERENCE.md)) |
| `dashboard.html` | HTML | Chart.js: temp gauge, voltage bars, alarm panel, min/max chart |

Dashboard loads `report_data.json` via `fetch()` at runtime.

---

## Design-Specific Rules

**All outputs MUST use ACTUAL values. NO generic placeholders.**

| Rule | Wrong | Correct |
|------|-------|---------|
| Temperature | "temperature is fine" | "Die temp: 67.3°C (margin: 57.7°C to OT)" |
| Supply | "VCCINT looks ok" | "VCCINT: 0.848V (nominal 0.850V, -0.24%)" |
| Alarms | "no alarms" | "ALM0-ALM3: CLEAR, OT: CLEAR, OT detection: ENABLED" |
| Part | "the device" | "xcvu9p-flga2104-2L-e" |

---

## Error Handling

| Error | Symptom | Action |
|-------|---------|--------|
| No hw_server | `get_hw_servers` empty | Guide: `connect_hw_server -url localhost:3121` |
| No hw_sysmon | `get_hw_sysmons` empty | Guide: `refresh_hw_device [current_hw_device]` |
| Property missing | `get_property` error | Skip, note as N/A (e.g., VUSER0 on 7 Series) |
| Unknown property | Unfamiliar device/family | `vivado_doc_search` for "hw_sysmon \<family\>" |
| Stale data | `refresh_hw_sysmon` fails | Check: `current_hw_server` |

---

## Examples

**"What is the die temperature?"** → Steps 1-2 (read TEMPERATURE/MAX/MIN only) → "Die temp: 45.2°C (max: 67.1°C, min: 23.4°C). OT margin: 79.8°C. GREEN."

**"Full device health check"** → Full workflow Steps 1-5 → JSON + REPORT.md + dashboard.html with all supplies, alarms, recommendations.

**"Check health on ZU+ board"** → Discover 2 hw_sysmons (PS + PL) → Read both → Unified report with PS/PL sections.

---

## Chipscope-mcp Fallback

Use this path only when Vivado MCP is not installed. Session lifecycle per VIVADO-PATTERNS.md Pattern 19 (vivado-skill-creator):

```
chipscope_session(action="connect", hw_server_url="TCP:<host>:3121", cs_server_url="TCP:<host>:3042")
chipscope_device(action="select", device_selector="0")
chipscope_sysmon(action="read_all")
```

`chipscope_sysmon` actions: `list_sensors`, `read`, `read_all`, `poll` (confirmed against `chipscope-mcp/src/chipscope_mcp/tools/chipscope_sysmon.py`). Use `read_all` for the full health-check workflow; `read` with a `sensors` list for a targeted query (e.g. "what is the die temperature").

---

## Integration

**Downstream:** `hw-ila-debug` / `hw-vio-debug` (if anomalies found), IBERT Eye Scan (if supply marginal)
**Complementary:** congestion-analysis (if running hot from switching activity)
**Multi-SLR:** On SSIT devices (VU9P, VU13P, etc.), iterate all `[get_hw_sysmons]` and report per-SLR health

---

## Metadata

**Keywords:** sysmon, health, temperature, voltage, VCCINT, VCCAUX, VCCBRAM, alarm, OT, thermal, hw_sysmon, dashboard
**Confidence Threshold:** 0.80

---

## Changelog

### Version 1.2.0-ea (2026-07-16)
- Designate skill as Early Access (`-ea`); add `maturity: early-access`
- Rename skill identity to hw-sysmon: update `name:` frontmatter, report
  output path, and cross-skill references to match the renamed directory

### Version 1.1.0 (2026-07-01)
- Fix Versal bug: `TEMPERATURE` property does not exist on Versal SysMon objects,
  use `DEVICE_TEMP` instead (confirmed via vivado_mcp_learning hardware evidence)
- Add `refresh_hw_device` before `get_hw_sysmons` in Step 1 — without it,
  `get_hw_sysmons` can return empty on a freshly connected session
- Add chipscope-mcp fallback path (Vivado-first/chipscope-mcp-fallback routing policy)

### Version 1.0.0 (2026-04-28)
- Initial release — all families via unified `hw_sysmon` Tcl interface
- Split: SKILL.md (workflow) + REFERENCE.md (register maps, schemas, templates)
