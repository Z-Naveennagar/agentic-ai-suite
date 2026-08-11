---
name: hw-pcie-link-debug
description: >
  Debug PCIe link bring-up and status on live Versal devices via ChipScoPy MCP tools.
  Read LTSSM state, PCIe configuration space registers, link status (speed, width),
  error counters, and correlate with GT eye scans via IBERT. Uses chipscopy_memory for
  register-level PCIe config/status reads and chipscopy_ibert for transceiver-level
  signal integrity. Use when user asks to "check PCIe link", "PCIe status",
  "LTSSM state", "PCIe link training", "PCIe config space", "PCIe speed",
  "PCIe width", "PCIe errors", "link degradation", "PCIe Gen3/Gen4/Gen5",
  "PCIe BAR", or "debug PCIe link failure".
version: 1.1.0-ea
maturity: early-access
chipscopy_version: "2026.1+"
categories: [hardware-debug, pcie, link-debug, versal]
device_families: [versal]
estimated_duration: 2-10 minutes
complexity: intermediate-to-advanced
author: Vivado AI Skills Team
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
# PCIe Link Debug (EA)

> **Early Access** — this skill may change before general availability.

Debugs PCIe link bring-up and status on live Versal hardware via **ChipScoPy MCP**. Uses `chipscopy_memory` for PCIe configuration space and status register reads. Optionally uses `chipscopy_ibert` for GT-level signal integrity analysis on PCIe lanes.

See [REFERENCE.md](REFERENCE.md) for PCIe register addresses, LTSSM state encoding, error register definitions, and report schemas.

## Tools Used

| Tool | Purpose |
|------|---------|
| `chipscopy_memory` | Read PCIe configuration space, LTSSM status, link status, error counters via memory-mapped registers. |
| `chipscopy_ibert` | GT transceiver eye scan on PCIe lanes (when IBERT cores are available). |
| `chipscopy_ibert_eye_scan` | 2D eye scan on PCIe GT lanes for signal integrity analysis. |
| `chipscopy_session` | Connect to hw_server + cs_server. |
| `chipscopy_device` | List/select devices, check resources. |
| `chipscopy_scan` | Discover debug cores including PCIE. |
| Agent file tools | Write output files. |

**Versal only.** Covers all Versal PCIe block variants:

| Block | Versal Families | Max Capability | IP/Doc |
|-------|----------------|----------------|--------|
| **CPM4** | AI Core (VC), Prime (VM), AI Edge (VE) | Gen4 x8 | PG346 |
| **CPM5** | Premium (VP) | Gen5 x16 or 2×Gen5 x8 | PG346 |
| **PL-PCIE4** | All Versal (PL soft block) | Gen4 x8 | PG302 |
| **PL-PCIE5** | Premium (PL soft block) | Gen5 x8 | PG302 |

PCIe configuration space is memory-mapped and accessible via `chipscopy_memory`. CPM (hard block) and PL-PCIE (soft block) have different base addresses and register layouts — the agent must identify which block is present before reading registers.

**Not covered (future work):** UltraScale+ PCIE4C (PG213). ChipScoPy MCP's `chipscopy_memory` is Versal-only. US+ PCIe debug would require Vivado MCP `hw_pcie` Tcl or XSDB register reads.

---

## Efficiency Guidelines

- **Detect PCIe block type first** — CPM4, CPM5, PL-PCIE4, and PL-PCIE5 have different base addresses. Use `chipscopy_device(action='resources')` to identify which block is present.
- **Read link status first** — quick single read tells you speed, width, and training state.
- **Batch register reads** — read contiguous register blocks in one `chipscopy_memory` call using `count`.
- **IBERT is optional** — GT eye scans require IBERT IP in the design. Many PCIe designs don't include IBERT.
- **Do NOT** write to PCIe registers without user confirmation — this can affect link state.
- **Do NOT** use terminal commands or Vivado Tcl. Use ChipScoPy MCP tools only.

---

## Mandatory Workflow

### Step 1: Verify Connection & Device

```
chipscopy_session(action='status')
```

If not connected:
```
chipscopy_session(action='connect', hw_server_url='TCP:<host>:3121')
```

Check resources:
```
chipscopy_device(action='resources')
```

Check for PCIe cores in scan:
```
chipscopy_scan(action='scan', include=['pcie'])
```

**Identify PCIe block type** from resources output:
- `CPM_PCIE` → Hard block (CPM4 on AI Core/Prime/Edge, CPM5 on Premium)
- `pcie` in PL debug cores → Soft block (PL-PCIE4 or PL-PCIE5)

The block type determines base addresses and available features. See [REFERENCE.md](REFERENCE.md) for per-block register maps.

**Non-Versal device detected?** → STOP. This skill requires Versal. For UltraScale+ PCIe, the user needs Vivado Hardware Manager or XSDB (not yet covered by this skill).

---

### Step 2: Identify Memory Targets

```
chipscopy_memory(action='targets')
```

Select appropriate memory target for PCIe register access. DPC (Debug Packet Controller) is typically the default.

---

### Step 3: Read Link Status

Read PCIe Link Status Register (configuration space offset 0x12 in Link Capabilities/Status):

```
chipscopy_memory(action='read',
    address=<pcie_cfg_base + link_status_offset>,
    count=1,
    word_size='w')
```

Decode:
- **Link Speed**: Bits [3:0] — 1=Gen1 (2.5 GT/s), 2=Gen2 (5 GT/s), 3=Gen3 (8 GT/s), 4=Gen4 (16 GT/s), 5=Gen5 (32 GT/s)
- **Link Width**: Bits [9:4] — negotiated width (x1, x2, x4, x8, x16)
- **Training**: Bit 11 — 1 = link training in progress

---

### Step 4: Read LTSSM State

The LTSSM (Link Training and Status State Machine) state indicates where in link bring-up the PCIe link is:

```
chipscopy_memory(action='read',
    address=<cpm_base + ltssm_offset>,
    count=1,
    word_size='w')
```

Decode the LTSSM state value — see [REFERENCE.md](REFERENCE.md) for full state table.

**Key LTSSM states:**
- `L0` — Link up, normal operation
- `Detect.Quiet` / `Detect.Active` — Initial detection (link not trained)
- `Polling.*` — Speed negotiation
- `Config.*` — Width/lane negotiation
- `Recovery.*` — Link recovering from error
- `Disabled` — Link intentionally disabled

**Stuck in Detect?** → No electrical connection or receiver detection failure.
**Stuck in Polling?** → Speed negotiation failure, SI issue.
**Stuck in Config?** → Lane reversal, width negotiation failure.

---

### Step 5: Read Configuration Space

Read standard PCIe configuration space registers:

```
chipscopy_memory(action='read',
    address=<pcie_cfg_base>,
    count=16,
    word_size='w')
```

Decode key fields:
- **Offset 0x00**: Device ID / Vendor ID
- **Offset 0x04**: Status / Command
- **Offset 0x08**: Class Code / Revision ID
- **Offset 0x10-0x24**: BAR registers (Base Address Registers)

---

### Step 5.5: Targeted Diagnostic Checks

Run these checks **conditionally** based on what Steps 3–5 revealed. Each check reads a specific register to confirm or eliminate a root cause.

**A. LTSSM Stability Check** — If LTSSM shows L0, read it 3 times to verify stability:
```
chipscopy_memory(action='read', address=<cpm_base + ltssm_offset>, count=1, word_size='w')
# repeat 2 more times
```
If LTSSM alternates between L0 (0x10) and Recovery (0x20–0x23), the link is **unstable** — indicates SI/signal integrity issue even though link appears "up". Run IBERT eye scan.

**B. PHY Ready Check (CPM only)** — Read `phy_rdy` register:
```
chipscopy_memory(action='read', address=0xFCE20000 + <phy_rdy_offset>, count=1, word_size='w')
```
If `phy_rdy = 0`, the GT PHY has not completed initialization. Link **cannot** train. Check: refclk present? GT power supplies stable? See `hw-sysmon` for VCCINT_GT.

**C. Command Register Check** — Read config space offset 0x04:
```
chipscopy_memory(action='read', address=<pcie_cfg_base + 0x04>, count=1, word_size='w')
```
Decode bits:
- Bit 1 = **Memory Space Enable** — if 0, BARs are disabled (host didn't enable endpoint)
- Bit 2 = **Bus Master Enable** — if 0, endpoint cannot initiate DMA transactions
- Bit 10 = **INTx Disable** — interrupt routing control

If Memory Enable = 0 and link is L0, the host enumerated but didn't enable the device. This explains "link up but no data transfer" symptoms.

**D. BAR Enumeration Check** — Read BAR0–BAR5 (offsets 0x10–0x24):
```
chipscopy_memory(action='read', address=<pcie_cfg_base + 0x10>, count=6, word_size='w')
```
If all BARs = 0x00000000, the host has **not enumerated** the endpoint. Possible causes:
- Host enumerated before FPGA was configured (PCIe spec requires device present within 100ms of power-good). Warm reboot the host.
- BAR sizes too large — host ran out of contiguous memory. Recommend: reduce BAR size or use 64-bit BARs.

**E. Link Capability vs Status (Downgrade Detection)** — Read Link Capabilities (PCIe Cap + 0x0C) and Link Status (PCIe Cap + 0x12):
```
chipscopy_memory(action='read', address=<pcie_cap_base + 0x0C>, count=2, word_size='w')
```
Compare: `max_speed` vs `negotiated_speed`, `max_width` vs `negotiated_width`. If negotiated < max:
- Speed downgrade → check partner capability, SI (eye scan), equalization settings
- Width downgrade → check for dead lanes, lane reversal, host slot bifurcation

**F. Equalization Status (Gen3+ only)** — Read Link Status 2 (PCIe Cap + 0x32):
```
chipscopy_memory(action='read', address=<pcie_cap_base + 0x32>, count=1, word_size='h')
```
- Bit 1 = **Equalization Complete** — if 0 at Gen3+, EQ failed
- Bit 2 = **Equalization Phase 1 Successful**
- Bit 3 = **Equalization Phase 2 Successful**
- Bit 4 = **Equalization Phase 3 Successful**

If EQ Phase 2/3 failing: for CPM, read `pl_eq_bypass_phase23` register and consider recommending Phase 2/3 bypass as a workaround (requires user to rebuild with IP setting or register write with confirmation). See [REFERENCE.md](REFERENCE.md) for CPM EQ registers.

**G. Vendor ID Sanity** — From Step 5, if Vendor ID = 0xFFFF:
- Device is **not present** on the bus. Link may have gone down after initial training.
- Check LTSSM for Disabled (0x31) or Detect (0x00/0x01) state.
- Check for Surprise Down Error in AER uncorrectable status (bit 5).

---

### Step 6: Read Error Counters

**Correctable errors (AER offset + 0x10):**
```
chipscopy_memory(action='read',
    address=<aer_base + 0x10>,
    count=1,
    word_size='w')
```

**Uncorrectable errors (AER offset + 0x04):**
```
chipscopy_memory(action='read',
    address=<aer_base + 0x04>,
    count=1,
    word_size='w')
```

See [REFERENCE.md](REFERENCE.md) for error bit definitions.

---

### Step 7: GT Eye Scan (Optional)

If IBERT cores are available on the PCIe GT lanes:

1. `chipscopy_ibert(action='list')` — find IBERT core on PCIe GTs
2. `chipscopy_ibert(action='create_link', ...)` — create link on PCIe lane
3. `chipscopy_ibert_eye_scan(link_name=..., target_ber=1e-12)` — run eye scan

Compare measured eye opening against PCIe spec requirements (see [REFERENCE.md](REFERENCE.md)).

---

### Step 8: Root Cause Analysis

Correlate findings across:

| Source | Data | Correlates With |
|--------|------|-----------------|
| LTSSM state | Training stuck point | SI issue, clock, partner device |
| LTSSM stability | L0↔Recovery cycling | SI marginal — link trains but can't sustain |
| Link status | Speed/width degradation | GT eye quality, error count |
| phy_rdy | PHY initialization | GT power/clock prerequisite |
| Command register | Mem Enable, Bus Master | Host enumeration completeness |
| BAR values | All zeros vs allocated | Enumeration timing, BAR sizing |
| EQ status (Gen3+) | Phase 1/2/3 completion | Equalization convergence |
| Error counters | Correctable/uncorrectable | SI, noise, equalization |
| Eye scan (IBERT) | Eye width/height | Board SI, TX/RX settings |
| NoC debug | Timeout errors | PCIe endpoint unreachable |
| SysMon | Supply voltage | Voltage affecting GT performance |

---

### Step 9: Write Output Files

Output directory: `vivado_agentic_ai_reports/hw-pcie-link-debug/`

| File | Format | Content |
|------|--------|---------|
| `report_data.json` | JSON | Link status, LTSSM, config space, errors |
| `REPORT.md` | Markdown | Summary with link status, LTSSM analysis, recommendations |

---

## Design-Specific Rules

| Rule | Wrong | Correct |
|------|-------|---------|
| Link status | "PCIe is up" | "PCIe link: Gen3 x8, LTSSM=L0, BER: no errors" |
| LTSSM | "link training" | "LTSSM stuck in Detect.Active — receiver detection failing" |
| Speed | "running at Gen3" | "Negotiated Gen3 (8 GT/s), target Gen4 (16 GT/s) — downgraded" |
| Errors | "some errors" | "Correctable: 142 (RxErr), Uncorrectable: 0. Pattern: replay errors suggesting SI issue" |

---

## Error Handling

| Error | Symptom | Action |
|-------|---------|--------|
| No PCIe cores | scan shows no PCIE | Design has no PCIe block. Check bitstream. |
| Non-Versal device | chipscopy reports non-Versal part | This skill covers Versal CPM/PL-PCIE only. US+ PCIE4C is future work. |
| Wrong base address | reads return all-F or unexpected data | CPM4 vs CPM5 vs PL-PCIE have different bases. Verify block type from resources. |
| Register read fails | memory read returns error | Check address, memory target, device state |
| LTSSM stuck in Detect | No partner device | Check: cable connected? Partner powered? Refclk present? |
| Link speed degraded | Gen3 instead of Gen4 | Check: both ends support target speed? SI adequate? |
| Width degraded | x4 instead of x8 | Check: all lanes routed? Lane reversal? Dead lanes? |
| High error count | Correctable errors growing | SI issue — run eye scan, check board design |

---

## Examples

**"Check PCIe link status"** → Connect → Read link status register → "Gen4 x8, LTSSM=L0, link up and operational"

**"PCIe link won't train"** → Read LTSSM → "Stuck in Detect.Active" → Check: refclk present? Cable connected? → Recommendations.

**"Why is PCIe running at Gen3 instead of Gen4?"** → Read link caps (max supported) + link status (negotiated) → Compare → Check partner device capability and SI.

**"Check PCIe error counters"** → Read AER registers → "142 correctable (receiver errors), 0 uncorrectable. Suggests marginal SI."

**"Full PCIe debug with eye scan"** → Link status + LTSSM + config space + error counters + IBERT eye scan → Comprehensive report.

---

## Integration

**Upstream:** `chipscopy_session` (connection), `chipscopy_device` (programming)
**Complementary:** `hw-ibert-gt-debug` (GT-level eye scan on PCIe lanes), `hw-noc-debug` (NoC timeout may indicate PCIe endpoint issue), `hw-sysmon` (supply affecting GT)
**Downstream:** SI findings → board respin, equalization tuning, partner device configuration

---

## Metadata

**Keywords:** PCIe, LTSSM, link training, configuration space, Gen3, Gen4, Gen5, BAR, error counter, AER, correctable, uncorrectable, link speed, link width
**Confidence Threshold:** 0.80

---

## Changelog

### Version 1.1.0-ea (2026-07-16)
- Designate skill as Early Access (`-ea`); add `maturity: early-access`
- Rename skill identity to hw-pcie-link-debug: update `name:` frontmatter,
  report output path, and cross-skill references to match the renamed directory

### Version 1.0.0 (2026-05-01)
- Initial release — PCIe link debug via chipscopy_memory register reads
- Covers Versal CPM4, CPM5, PL-PCIE4, PL-PCIE5
- LTSSM analysis, config space inspection, error counter decoding
- Optional GT eye scan integration via chipscopy_ibert
- UltraScale+ PCIE4C documented as future work (requires Vivado MCP backend)
