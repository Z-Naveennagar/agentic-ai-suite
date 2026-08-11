---
name: hw-ddrmc-debug
description: >
  Debug DDR memory controller calibration and health on live Versal devices via
  ChipScoPy MCP tools. Read calibration status per stage, analyze per-byte-lane
  margins, run 2D eye scans with inline PNG heatmaps, and diagnose calibration
  failures. Uses chipscope_ddr for controller status and chipscope_ddr_eye_scan
  for margin visualization. Use when user asks to "check DDR calibration",
  "DDR status", "DDR health", "calibration failed", "DDR margins", "DDR eye scan",
  "run DDR eye scan", "byte lane margins", "DDRMC status", "memory calibration",
  "DDR window analysis", or "check DDR controller".
version: 1.2.0-ea
maturity: early-access
chipscopy_version: "2026.1+"
categories: [hardware-debug, ddr, memory, calibration, versal]
device_families: [versal]
estimated_duration: 2-10 minutes
complexity: intermediate-to-advanced
author: Vivado AI Skills Team
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
# DDRMC Calibration Debug (EA)

> **Early Access** — this skill may change before general availability.

Debugs DDR memory controller calibration and health on live Versal hardware via **ChipScoPy MCP**. Uses `chipscope_ddr` for status, calibration, margins, and eye scans, plus `chipscope_ddr_eye_scan` for dedicated 2D margin visualization with inline PNG heatmaps.

See [REFERENCE.md](REFERENCE.md) for calibration stages, margin analysis, eye scan parameters, and report schemas.

**Routing:** Try Vivado MCP (`vivado_execute` + `get_hw_ddrmcs`/`report_hw_ddrmc` Tcl, below) first if a Vivado MCP session is available. Fall back to chipscope-mcp (`chipscope_ddr`/`chipscope_ddr_eye_scan`) if Vivado MCP is not installed. See [Vivado MCP Fallback (Primary Path)](#vivado-mcp-path-primary) below — note Vivado's `get_hw_ddrmcs` object works natively on Versal, so this is the primary path per the routing policy, with chipscope-mcp as the documented alternative when only chipscope-mcp is available.

## Tools Used

**Primary path — Vivado MCP** (when available):

| Tool | Purpose |
|------|---------|
| `vivado_execute` | Run Tcl (`get_hw_ddrmcs`, `report_hw_ddrmc`). No `-return_string` decode helper exists for calibration flags — parse the text report. |

**Fallback path — chipscope-mcp** (when Vivado MCP is not installed):

| Tool | Purpose |
|------|---------|
| `chipscope_ddr` | List DDR controllers, check status/calibration/health, read config, analyze margins, run eye scans, export data. |
| `chipscope_ddr_eye_scan` | Dedicated 2D eye scan with inline PNG heatmap. |
| `chipscope_session` | Connect to hw_server + cs_server. |
| `chipscope_device` | List/select devices, check resources. |
| `chipscope_scan` | Discover debug cores including DDR. |
| Agent file tools | Write output files. |

**Versal only.** DDRMC debug cores exist only on Versal devices.

---

## Vivado MCP Path (Primary)

```tcl
refresh_hw_device [current_hw_device]
foreach ddrmc [get_hw_ddrmcs] {
  puts "DDRMC:$ddrmc"
  puts [report_hw_ddrmc $ddrmc -return_string]
}
```

**No `CALIB_COMPLETE` flat property exists** — there is no single property to check calibration pass/fail. Parse the `report_hw_ddrmc -return_string` text output for calibration stage results instead (confirmed via vivado_mcp_learning hardware evidence on VCK190, 4 controllers, all PASS).

---

## Efficiency Guidelines

- **Check calibration before eye scan** — if calibration failed, eye scan will not produce useful data.
- **Use `action='report'`** for a comprehensive single-call DDR status summary.
- **Eye scan takes time** — increase `max_wait_minutes` for high-step-count scans.
- **Multi-DDRMC** — use `ddr_name` to target specific controllers. Omit to use the first.
- **Do NOT** use terminal commands or Vivado Tcl. Use ChipScoPy MCP tools only.

---

## Mandatory Workflow

### Step 1: Verify Connection & Discover DDR

```
chipscope_session(action='status')
```

If not connected:
```
chipscope_session(action='connect', hw_server_url='TCP:<host>:3121')
```

```
chipscope_device(action='resources')
```

If DDR cores not shown:
```
chipscope_scan(action='scan', include=['ddr'])
```

---

### Step 2: List DDR Controllers

```
chipscope_ddr(action='list')
```

Reports available DDRMC instances with names and enabled state.

---

### Step 3: Check Status & Calibration

**Quick status:**
```
chipscope_ddr(action='status', ddr_name='ddr_0')
```

**Detailed calibration:**
```
chipscope_ddr(action='calibration', ddr_name='ddr_0')
```

Reports PASS/FAIL per calibration stage.

**Comprehensive report:**
```
chipscope_ddr(action='report', ddr_name='ddr_0')
```

Combines status + calibration + config in one call.

**Health check:**
```
chipscope_ddr(action='health', ddr_name='ddr_0')
```

Returns health status and diagnostic messages.

---

### Step 4: Analyze Calibration Stages

```
chipscope_ddr(action='stages', ddr_name='ddr_0')
```

Returns per-stage calibration results. Key stages:

| Stage | Description |
|-------|-------------|
| ZQ Calibration | Output impedance calibration |
| Write Leveling | DQS-to-CK alignment |
| Read Gate | Read DQS gate training |
| Read DQS Centering | Read data eye centering |
| Write DQS Centering | Write data eye centering |
| Read DQ Deskew | Per-bit read timing alignment |
| Write DQ Deskew | Per-bit write timing alignment |

---

### Step 5: Analyze Per-Byte Margins

```
chipscope_ddr(action='margins', ddr_name='ddr_0')
```

Reports calibration window margins per byte lane. Identify:
- **Weak lanes** — smallest margin (candidate for failure under voltage/temp variation)
- **Asymmetric windows** — left/right margin imbalance indicates SI issue
- **Zero margin** — calibration barely passed; design is at risk

---

### Step 6: Run 2D Eye Scan (Optional)

**Via dedicated tool (recommended — inline PNG):**
```
chipscope_ddr_eye_scan(
    ddr_name='ddr_0',
    mode='read',
    steps=15,
    unit_index=0)
```

Returns inline PNG heatmap showing margin per VRef step.

**Or via chipscope_ddr:**
```
chipscope_ddr(action='eye_scan',
    ddr_name='ddr_0',
    mode='read',
    steps=15,
    unit_index=0)
```

**Get defaults before scanning:**
```
chipscope_ddr(action='eye_scan_defaults', ddr_name='ddr_0', mode='read')
```

Returns default VRef values and recommended scan settings.

**Export scan data:**
```
chipscope_ddr(action='eye_scan_data',
    ddr_name='ddr_0',
    output_format='csv',
    export_path='ddr_eye_scan.csv')
```

---

### Step 7: Read Configuration

```
chipscope_ddr(action='config', ddr_name='ddr_0')
```

Reports memory type, width, ranks, frequency, and other configuration details.

---

### Step 8: Write Output Files

Output directory: `vivado_agentic_ai_reports/hw-ddrmc-debug/`

| File | Format | Content |
|------|--------|---------|
| `report_data.json` | JSON | Structured DDR status, calibration, margins |
| `REPORT.md` | Markdown | Summary with calibration table, margin analysis, recommendations |
| `ddr_eye_scan.png` | PNG | Eye scan heatmap (if `save_plot` used) |
| `ddr_eye_scan.csv` | CSV | Raw scan data (if exported) |

---

## Calibration Failure Diagnosis

When calibration fails:

1. **Identify failing stage** — `chipscope_ddr(action='stages')` shows which stage failed
2. **Check per-stage details:**

| Failing Stage | Common Causes | Debug Steps |
|---------------|---------------|-------------|
| ZQ Cal | Missing VREF, ZQ resistor | Check board ZQ resistor (240Ω to GND) |
| Write Leveling | CK-DQS routing | Check DQS-CK flight time, board SI |
| Read Gate | DQS preamble | Check memory timing parameters, tDQSCK |
| Read DQS Centering | Jitter, ISI | Run read eye scan, check per-bit margins |
| Write DQS Centering | Write path SI | Run write eye scan, check VREF |

3. **Cross-reference:**
   - `hw-sysmon` — supply voltage affecting DDR PHY
   - `hw-noc-debug` — NoC timeout errors pointing to DDRMC

---

## Multi-DDRMC Support

For designs with multiple DDR controllers:

1. List all: `chipscope_ddr(action='list')`
2. Check each: iterate `chipscope_ddr(action='calibration', ddr_name='ddr_N')` for each
3. Compare margins across controllers
4. Report weakest controller and lanes

---

## Design-Specific Rules

| Rule | Wrong | Correct |
|------|-------|---------|
| Calibration | "DDR calibration passed" | "ddr_0: Calibration PASS — all 8 stages complete. Weakest margin: byte 3 (42 taps)" |
| Margins | "margins look ok" | "Byte 0: 68 taps (left: 35, right: 33). Byte 3: 42 taps (left: 18, right: 24) — weakest" |
| Eye scan | "eye is open" | "Read eye scan: VRef sweep 15 steps, unit 0. Margin 120 mV at center." |
| Config | "DDR4 memory" | "ddr_0: DDR4, x72 (ECC), 2 ranks, 3200 MT/s, 16 GB total" |

---

## Error Handling

| Error | Symptom | Action |
|-------|---------|--------|
| No DDR cores | list returns empty | Design has no DDRMC. Check bitstream. |
| Calibration failed | calibration shows FAIL | Run `stages` to identify failing stage. See diagnosis table. |
| Eye scan fails | Calibration not complete | Calibration must pass before eye scan. Fix calibration first. |
| DDR not enabled | status shows disabled | DDRMC not used in current design. Check NoC address map. |
| Scan timeout | eye_scan takes too long | Increase `max_wait_minutes`. Reduce `steps`. |

---

## Examples

**"Check DDR status"** → List → Status → Calibration → "ddr_0: Calibration PASS, all stages complete, DDR4 x72 @ 3200 MT/s"

**"DDR calibration failed, help debug"** → Status → Stages → Identify failing stage → Margin analysis → Recommendations.

**"Run DDR eye scan"** → Check calibration passed → Get defaults → Run `chipscope_ddr_eye_scan(mode='read', steps=15)` → Report margin heatmap.

**"Compare margins across DDR controllers"** → List all → Margins for each → Compare → Report weakest.

---

## Integration

**Upstream:** `chipscope_session` (connection), `chipscope_device` (programming)
**Complementary:** `hw-noc-debug` (NoC timeout → DDRMC failure), `hw-sysmon` (supply affects DDR PHY), `hw-noc-perfmon` (DDRMC endpoint topology)
**Downstream:** Margin issues → board SI investigation, memory timing parameter adjustment

---

## Metadata

**Keywords:** DDR, DDRMC, calibration, eye scan, margins, byte lane, memory, DDR4, DDR5, LPDDR, VRef, training, write leveling, read gate
**Confidence Threshold:** 0.80

---

## Changelog

### Version 1.2.0-ea (2026-07-16)
- Designate skill as Early Access (`-ea`); add `maturity: early-access`
- Rename skill identity to hw-ddrmc-debug: update `name:` frontmatter, report
  output path, and cross-skill references to match the renamed directory

### Version 1.1.0 (2026-07-01)
- Fix stale `chipscopy_*` tool prefix -> `chipscope_*`
- Add Vivado MCP fallback path (`get_hw_ddrmcs`/`report_hw_ddrmc`), which is
  actually the primary path per the routing policy since it works natively
  on Versal; chipscope-mcp remains available as the documented alternative
- Confirmed `chipscope_ddr`'s action list (list/status/calibration/health/
  report/config/stages/margins/eye_scan/eye_scan_data/eye_scan_defaults)
  matches this skill's usage exactly against the live tool source

### Version 1.0.0 (2026-05-01)
- Initial release — DDRMC calibration debug + eye scan via ChipScoPy MCP
- Per-stage analysis, per-byte margins, 2D eye scan with inline PNG
