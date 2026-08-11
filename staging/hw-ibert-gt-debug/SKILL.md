---
name: hw-ibert-gt-debug
description: >
  Debug serial transceiver links and run eye/YK scans on live FPGA/SoC devices via
  ChipScoPy MCP tools. Supports GTY/GTYP eye scans (BER heatmap) and GTM YK scans
  (SNR waveform). Create and configure loopback or external links, sweep TX/RX
  equalization, run 2D eye scans, and assess link margin. Produces inline PNG
  visualizations and exportable scan data. Use when user asks to "run eye scan",
  "check signal quality", "create IBERT link", "show eye diagram", "check BER",
  "IBERT status", "GT link health", "tune TX emphasis", "run YK scan",
  "check SNR", "IBERT loopback test", or "serial link debug".
version: 1.2.0-ea
maturity: early-access
chipscopy_version: "2026.1+"
categories: [hardware-debug, ibert, serial-link, eye-scan, transceiver]
device_families: [versal, ultrascale-plus, ultrascale, 7series]
estimated_duration: 2-15 minutes
complexity: intermediate-to-advanced
author: Vivado AI Skills Team
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
# IBERT Eye Scan & Link Tuning (EA)

> **Early Access** — this skill may change before general availability.

Debugs serial transceiver links and runs eye/YK scans on live hardware via **ChipScoPy MCP**. Three tools cover the full workflow:

- **`chipscope_ibert`** — discover GT cores, create/configure/delete links, check status
- **`chipscope_ibert_eye_scan`** — 2D eye scan with inline PNG heatmap (GTY/GTYP)
- **`chipscope_ibert_yk_scan`** — YK scan with inline PNG waveform (GTM, 56+ Gbps)

See [REFERENCE.md](REFERENCE.md) for GT transceiver types, link configuration options, scan parameters, and report schemas.

**Routing:** GTY/GTYP eye scan can also be driven through Vivado MCP (`vivado_execute` + `create_hw_sio_scan ... 2d_full_eye`/`1d_bathtub`, real Hardware Manager Tcl) — try that first if a Vivado MCP session is available, falling back to `chipscope_ibert_eye_scan` otherwise; both paths are proven on real hardware (VCK190). **GTM YK scan has no vivado-mcp fallback — `chipscope_ibert_yk_scan` is the only path.** Do not attempt `create_hw_sio_scan` against a GTM link expecting it to work; see the error table in Workflow B below for exactly how and where each Vivado scan type fails on GTM.

**Device scoping note:** the frontmatter `device_families` list (versal, ultrascale-plus, ultrascale, 7series) applies to GTY/GTYP eye scan. GTM (YK scan) is narrower — Versal **Premium/HBM-series only** (e.g. VPK120/180), per REFERENCE.md's transceiver table. Do not assume YK scan works on a general Versal part just because "versal" is in the device list.

## Tools Used

| Tool | Purpose |
|------|---------|
| `chipscope_ibert` | List IBERT cores, discover GT groups, create/delete/configure links, check link status and BER, reset. |
| `chipscope_ibert_eye_scan` | Run 2D eye scan on GTY/GTYP link. Returns inline PNG heatmap. Supports export. |
| `chipscope_ibert_yk_scan` | Run YK scan on GTM link. Returns inline PNG waveform + SNR data. Export at scan time only. |
| `chipscope_session` | Connect to hw_server + cs_server. |
| `chipscope_device` | List/select devices, check resources, program device. |
| `chipscope_scan` | Discover debug cores including IBERT. |
| Agent file tools | Write output files (report_data.json, REPORT.md). |

---

## Efficiency Guidelines

- **Check link type first** — GTM uses YK scan, GTY/GTYP uses eye scan. The IBERT core listing indicates transceiver type.
- **Create link before scanning** — eye/YK scan requires an active link. Use `chipscope_ibert(action='create_link')`.
- **Loopback for self-test** — use Near-End PMA loopback for board-independent testing.
- **Export at scan time for YK** — GTM YK scan data is transient; use `export_path` during scan, not after.
- **Do NOT** run scans without a configured link — the tool will error.

---

## Workflow A: Eye Scan (GTY/GTYP)

### Step 1: Discover IBERT Cores

```
chipscope_ibert(action='list')
```

Returns IBERT cores with transceiver type hints. Identify **GTY** or **GTYP** cores.

### Step 2: Analyze GT Groups

```
chipscope_ibert(action='analyze')
```

Discovers GT groups and available transceivers within each IBERT core.

### Step 3: Create a Link

`create_link` takes `gt_group` (e.g. `'Quad_205'`, from Step 2's `analyze` output) plus integer `tx_channel`/`rx_channel` indices (0-3) — not `ibert_name`/string channel names. Confirmed against `chipscope-mcp/src/chipscope_mcp/tools/chipscope_ibert.py`.

```
chipscope_ibert(action='create_link',
    gt_group='<gt_group>',
    tx_channel=<tx_channel_index>,
    rx_channel=<rx_channel_index>)
```

For loopback testing (TX feeds back to RX on same channel):
```
chipscope_ibert(action='create_link',
    gt_group='<gt_group>',
    tx_channel=0,
    rx_channel=0)
```

For a cross-quad link, pass `rx_gt_group` if the RX channel is on a different GT group than TX.

### Step 4: Configure Link

```
chipscope_ibert(action='configure_link',
    link_name='<link_name>',
    tx_pattern='PRBS 31',
    rx_pattern='PRBS 31',
    loopback='Near-End PMA')
```

Common patterns: `PRBS 7`, `PRBS 15`, `PRBS 23`, `PRBS 31`. Loopback modes: `None`, `Near-End PMA`, `Near-End PCS`, `Far-End PMA`, `Far-End PCS`.

### Step 5: Check Link Status

```
chipscope_ibert(action='status', link_name='<link_name>')
```

Verify: PLL locked, link up, BER acceptable before scanning.

### Step 6: Run Eye Scan

```
chipscope_ibert_eye_scan(
    link_name='<link_name>',
    horz_step=10,
    vert_step=10,
    target_ber=1e-5)
```

Returns inline PNG heatmap showing eye opening.

**With export:**
```
chipscope_ibert_eye_scan(
    link_name='<link_name>',
    export_path='eye_scan_data.csv',
    save_plot='eye_scan.png')
```

**Display modes:** `display='chat'` (inline only), `display='app'` (structured content), `display='both'` (default), `display='ascii'` (text-only).

### Step 7: Analyze Results & Write Report

Assess eye opening:
- **Eye Width** (horizontal, in UI) — larger = more timing margin
- **Eye Height** (vertical, in mV) — larger = more voltage margin
- **BER** — target vs. measured at eye center

Output directory: `vivado_agentic_ai_reports/hw-ibert-gt-debug/`

| File | Format | Content |
|------|--------|---------|
| `report_data.json` | JSON | Link config, scan parameters, eye metrics |
| `REPORT.md` | Markdown | Summary with eye opening assessment |
| `eye_scan.png` | PNG | Eye diagram (if `save_plot` used) |
| `eye_scan_data.csv` | CSV | Raw scan data (if `export_path` used) |

---

## Workflow B: YK Scan (GTM, 56+ Gbps)

**Proven end-to-end on real hardware (VPK120, 2026-07-01).** GTM transceivers exist only on Versal Premium/HBM-series devices (e.g. VPK120/180). `chipscope_ibert_yk_scan` was run against a real GTM link on VPK120 (Quad_204 CH_0, 56.4 Gbps, Near-End PMA, PRBS 31) and returned SNR 16.75 dB. Workflow A (GTY/GTYP eye scan) has been proven on real hardware (VCK190).

**GTM YK scan is chipscope-mcp-only — confirmed at all three Vivado Hardware Manager Tcl layers, not just documented.** `yk`, `1d_bathtub`, and `2d_full_eye` were each tried against a real GTM link on VPK120 and every one fails, at a different layer:

| `scan_type` | `create_hw_sio_scan` (object creation) | `run_hw_sio_scan` (hardware execution) |
|---|---|---|
| `yk` | **Rejected** — `ERROR: [Labtools 27-1835] Unknown Scan Type: yk.` (not a recognized enum value) | n/a |
| `1d_bathtub` | **Rejected** — `ERROR: [Labtools 27-3784] Performing 1D Bathtub scan is not supported for <RX>!` (valid enum, but rejected per-object; also rejected on GTYP on this board) | n/a |
| `2d_full_eye` | **Accepted** — returns a scan object cleanly (object creation doesn't validate GT capability) | **Rejected** — `ERROR: [Xicom 50-230] ChipScope Server: ChipScope Service IBERT start_eye_scan: OD test Eye scan is not supported!` |

Do not treat `1d_bathtub` and `yk` as interchangeable or as testing the same thing — they fail for different reasons (unrecognized type vs. unsupported-for-this-GT), and neither is equivalent to a YK scan. `2d_full_eye` is the most dangerous case: it looks like it worked (a named `SCAN_N` object comes back) but produces zero real data once run — always check `run_hw_sio_scan`'s return, not just `create_hw_sio_scan`'s, before trusting a Vivado-mcp-path GTM scan result.

### Steps 1-5: Same as Workflow A

Discover, create link, configure, check status. Use a **GTM** IBERT core.

### Step 6: Run YK Scan

```
chipscope_ibert_yk_scan(
    link_name='<link_name>',
    scan_duration_seconds=10.0)
```

Returns inline PNG waveform + SNR statistics.

**With export (MUST be done at scan time — data is transient):**
```
chipscope_ibert_yk_scan(
    link_name='<link_name>',
    scan_duration_seconds=10.0,
    export_path='yk_scan_data.csv')
```

### Step 7: Analyze SNR Results

- **SNR** — signal-to-noise ratio in dB; higher = better
- **Slicer waveform** — shows signal quality at receiver

---

## TX/RX Tuning Workflow

For link optimization, sweep equalization parameters:

### Read Current Settings
```
chipscope_ibert(action='link_properties', link_name='<link_name>')
```

Returns current values and valid options for TX/RX parameters.

### Adjust TX Emphasis
```
chipscope_ibert(action='configure_link',
    link_name='<link_name>',
    tx_pre_cursor=<value>,
    tx_post_cursor=<value>,
    tx_swing=<value>)
```

### Sweep and Compare

1. Capture baseline eye scan
2. Adjust one parameter
3. Re-run eye scan
4. Compare eye width/height
5. Repeat until optimal

---

## Multi-Lane Analysis

For multi-lane links (PCIe x4/x8/x16, multi-lane Ethernet):

1. Create links on each lane
2. Run eye scan on each lane
3. Compare eye openings across lanes
4. Identify weak lanes (smallest eye)
5. Focus tuning on weak lanes

---

## Design-Specific Rules

| Rule | Wrong | Correct |
|------|-------|---------|
| Link status | "link is up" | "Link_0: PLL locked, BER 1.2e-12, line rate 25.78125 Gbps" |
| Eye opening | "eye looks good" | "Eye width: 0.42 UI, height: 180 mV at BER 1e-5" |
| Transceiver | "found IBERT" | "IBERT Versal GTM: 2 GT groups, 4 channels per group, 56.42 Gbps" |
| Scan type | "running scan" | "Running 2D eye scan: horz_step=10, vert_step=10, target_ber=1e-5" |

---

## Error Handling

| Error | Symptom | Action |
|-------|---------|--------|
| No IBERT cores | list returns empty | Design has no IBERT IP. Check bitstream. |
| Wrong scan type | eye_scan on GTM | GTM uses YK scan. Use `chipscope_ibert_yk_scan`. |
| Vivado-mcp on GTM | `create_hw_sio_scan ... yk` errors `Unknown Scan Type: yk`; `1d_bathtub` errors `27-3784 not supported`; `2d_full_eye` creates a scan object but `run_hw_sio_scan` errors `Xicom 50-230 ...Eye scan is not supported!` | None of Vivado Hardware Manager's Tcl scan types work on GTM at any layer (parse, per-object, or execution). Route to chipscope-mcp's `chipscope_ibert_yk_scan` for any GTM link — do not fall back to vivado-mcp for this one capability. |
| No link created | scan fails | Create link first with `chipscope_ibert(action='create_link')` |
| PLL not locked | status shows unlocked | Check: reference clock? loopback mode? board connections? |
| Scan timeout | max_wait exceeded | Increase `max_wait_minutes`. Check link stability. |
| High BER | link_status shows errors | Tune TX emphasis, check SI, verify pattern match. |
| Export after YK | no data available | YK data is transient. Must export during scan with `export_path`. |

---

## Examples

**"Run an eye scan on GT channel 0"** → List IBERT → Create loopback link on CH0 → Configure PRBS 31 → Run eye scan → Report eye width/height.

**"Show me a YK scan on GTM"** → Find GTM IBERT core → Create link → Configure PRBS 31 + PMA loopback → `chipscope_ibert_yk_scan(scan_duration_seconds=10)` → Report SNR.

**"Compare eye before and after tuning"** → Baseline eye scan → Adjust TX pre-cursor → Re-run eye scan → Report: "Eye width improved from 0.35 UI to 0.42 UI (+20%)".

**"Check all IBERT links"** → `chipscope_ibert(action='status')` → Report BER, lock status, line rate for each link.

---

## Integration

**Upstream:** `chipscope_session` (connection), `chipscope_device` (programming)
**Complementary:** `hw-pcie-link-debug` (PCIe uses GT transceivers — eye scan validates SI), `hw-sysmon` (supply voltage affects eye quality)
**Downstream:** Tuning recommendations → design constraint changes or board-level SI fixes

---

## Metadata

**Keywords:** IBERT, eye scan, YK scan, GTY, GTYP, GTM, BER, SNR, serial link, transceiver, loopback, PRBS, equalization, eye diagram, margin
**Confidence Threshold:** 0.80

---

## Changelog

### Version 1.2.0-ea (2026-07-16)
- Designate skill as Early Access (`-ea`); add `maturity: early-access`
- Rename skill identity to hw-ibert-gt-debug: update `name:` frontmatter,
  report output path, and cross-skill references to match the renamed directory

### Version 1.1.0 (2026-07-01)
- Fix stale `chipscopy_*` tool prefix -> `chipscope_*`
- Fix `create_link` example: real tool signature takes `gt_group` + integer
  `tx_channel`/`rx_channel`, not `ibert_name`/string channel names
  (confirmed against chipscope_ibert.py)
- Fix `tx_diff_swing` -> `tx_swing` in the TX tuning example (real param name)
- Clarify device-family scoping: GTM is Versal Premium/HBM-series only, a
  narrower scope than the general `device_families` frontmatter list
- Prove GTM YK scan end-to-end on real VPK120 hardware (SNR 16.75 dB) and
  confirm live that Vivado Hardware Manager's `create_hw_sio_scan` has no
  `yk` scan type — GTM YK scan is chipscope-mcp-only, verified not assumed
- Add explicit Routing note: GTY/GTYP eye scan has a working vivado-mcp
  fallback, GTM YK scan does not
- Rule out `1d_bathtub`/`2d_full_eye` as GTM substitutes: both were tried
  live against a real GTM link and fail at different Tcl layers
  (`1d_bathtub` rejected per-object; `2d_full_eye` accepted at creation but
  fails on `run_hw_sio_scan` with `Xicom 50-230`) — `1d_bathtub` is not a
  synonym for YK scan, cross-checked against UG835/UG908/PG315 via the doc
  server

### Version 1.0.0 (2026-05-01)
- Initial release — IBERT link management + eye scan (GTY/GTYP) + YK scan (GTM) via ChipScoPy MCP
- TX/RX tuning workflow, multi-lane analysis
