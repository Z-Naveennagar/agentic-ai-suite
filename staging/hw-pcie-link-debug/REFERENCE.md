<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# PCIe Link Debug — Reference

## LTSSM State Table

*Source: PCI Express Base Specification, Section 4.2 (LTSSM); PG346 Chapter 9 (CPM LTSSM encoding); PG302/PG343 (PL-PCIE LTSSM encoding)*

| Value | State | Description | Action if Stuck |
|-------|-------|-------------|-----------------|
| 0x00 | Detect.Quiet | Waiting for electrical idle exit | Check: refclk, power, cable |
| 0x01 | Detect.Active | Sending detect pulses | Check: partner powered? RX termination? |
| 0x02 | Polling.Active | Training ordered sets | Check: refclk frequency, partner compatibility |
| 0x03 | Polling.Compliance | Compliance pattern | Check: compliance mode forced? |
| 0x04 | Polling.Config | Speed negotiation | Check: common speed support |
| 0x05 | Config.LinkWidthStart | Width negotiation start | Check: lane routing |
| 0x06 | Config.LinkWidthAccept | Width negotiation accept | Check: lane count match |
| 0x07 | Config.LaneNumWait | Lane numbering | Check: lane reversal support |
| 0x08 | Config.LaneNumAccept | Lane number accepted | Normal progression |
| 0x09 | Config.Complete | Configuration complete | Normal progression |
| 0x0A | Config.Idle | Waiting for idle | Normal progression |
| 0x10 | L0 | **Link UP — Normal operation** | — |
| 0x11 | L0s | Low power standby | ASPM active |
| 0x12 | L1 | Low power sleep | ASPM L1 active |
| 0x13 | L2 | Device off | Power management |
| 0x20 | Recovery.RcvrLock | Recovering bit lock | Momentary — if stuck, check SI |
| 0x21 | Recovery.RcvrCfg | Recovery configuration | Speed change in progress |
| 0x22 | Recovery.Speed | Speed change | Normal during Gen transition |
| 0x23 | Recovery.Idle | Recovery complete | Normal progression |
| 0x30 | Hot Reset | Hot reset in progress | Initiated by software |
| 0x31 | Disabled | Link disabled | Intentional or fatal error |
| 0x32 | Loopback | Loopback mode | Test mode |

---

## PCIe Configuration Space Layout

*Source: PCI Express Base Specification, Section 7.5 (Type 0/1 Configuration Space Header)*

### Type 0 (Endpoint) Header

| Offset | Size | Field |
|--------|------|-------|
| 0x00 | 2B | Vendor ID |
| 0x02 | 2B | Device ID |
| 0x04 | 2B | Command |
| 0x06 | 2B | Status |
| 0x08 | 1B | Revision ID |
| 0x09 | 3B | Class Code |
| 0x0C | 1B | Cache Line Size |
| 0x0D | 1B | Latency Timer |
| 0x0E | 1B | Header Type |
| 0x10 | 4B | BAR0 |
| 0x14 | 4B | BAR1 |
| 0x18 | 4B | BAR2 |
| 0x1C | 4B | BAR3 |
| 0x20 | 4B | BAR4 |
| 0x24 | 4B | BAR5 |
| 0x2C | 2B | Subsystem Vendor ID |
| 0x2E | 2B | Subsystem ID |
| 0x34 | 1B | Capabilities Pointer |
| 0x3C | 1B | Interrupt Line |
| 0x3D | 1B | Interrupt Pin |

---

## PCIe Link Capability / Status Registers

*Source: PCI Express Base Specification, Section 7.5.3.6–7.5.3.8 (PCI Express Capability Structure)*

### Link Capabilities (PCI Express Capability + 0x0C)

| Bits | Field | Description |
|------|-------|-------------|
| [3:0] | Max Link Speed | 1=2.5GT, 2=5GT, 3=8GT, 4=16GT, 5=32GT |
| [9:4] | Max Link Width | Maximum supported width |
| [11:10] | ASPM Support | L0s, L1 support |
| [14:12] | L0s Exit Latency | L0s exit time |
| [17:15] | L1 Exit Latency | L1 exit time |
| [18] | Clock PM | Clock power management |
| [19] | Surprise Down Err | Surprise down error reporting |
| [20] | DL Active Report | Data link layer active reporting |

### Link Status (PCI Express Capability + 0x12)

| Bits | Field | Description |
|------|-------|-------------|
| [3:0] | Current Link Speed | Negotiated speed |
| [9:4] | Negotiated Link Width | Negotiated width |
| [11] | Link Training | 1 = training in progress |
| [12] | Slot Clock Config | Uses slot-provided refclk |
| [13] | DL Active | Data link layer active |
| [14] | Link BW Mgmt Status | Bandwidth change notification |
| [15] | Link Auto BW Status | Autonomous bandwidth change |

---

## AER (Advanced Error Reporting) Registers

*Source: PCI Express Base Specification, Section 7.10 (AER Extended Capability)*

### Uncorrectable Error Status (AER + 0x04)

| Bit | Error | Description |
|-----|-------|-------------|
| 4 | Data Link Protocol Error | DLLP error |
| 5 | Surprise Down Error | Unexpected link down |
| 12 | Poisoned TLP | Received poisoned TLP |
| 13 | Flow Control Protocol Error | Credit error |
| 14 | Completion Timeout | Completion not received |
| 15 | Completer Abort | Completer aborted request |
| 16 | Unexpected Completion | Unsolicited completion |
| 17 | Receiver Overflow | RX buffer overflow |
| 18 | Malformed TLP | Packet format error |
| 19 | ECRC Error | End-to-end CRC failure |
| 20 | Unsupported Request | Invalid request type |

### Correctable Error Status (AER + 0x10)

| Bit | Error | Description |
|-----|-------|-------------|
| 0 | Receiver Error | 8b/10b or 128b/130b error |
| 6 | Bad TLP | TLP with bad LCRC |
| 7 | Bad DLLP | DLLP with bad CRC |
| 8 | Replay Num Rollover | Replay timer rolled over |
| 12 | Replay Timer Timeout | Replay timer expired |
| 13 | Advisory Non-Fatal | Advisory non-fatal error |
| 14 | Corrected Internal | Internal corrected error |
| 15 | Header Log Overflow | Header log overflow |

---

## PCIe Generation Comparison

*Source: PCI Express Base Specifications 1.0–5.0 (PCI-SIG)*

| Gen | Speed | Encoding | BW/lane | GT (Versal) | PCIe Block |
|-----|-------|----------|---------|-------------|------------|
| Gen1 | 2.5 GT/s | 8b/10b | 250 MB/s | — | CPM4/5, PL-PCIE |
| Gen2 | 5.0 GT/s | 8b/10b | 500 MB/s | — | CPM4/5, PL-PCIE |
| Gen3 | 8.0 GT/s | 128b/130b | ~1 GB/s | GTY | CPM4, PL-PCIE4 |
| Gen4 | 16.0 GT/s | 128b/130b | ~2 GB/s | GTY/GTYP | CPM4/5, PL-PCIE4/5 |
| Gen5 | 32.0 GT/s | 128b/130b | ~4 GB/s | GTYP | CPM5, PL-PCIE5 |

---

## Versal PCIe Block Types

*Source: PG346 (Versal CPM Mode for PCI Express); PG302 (Versal PL PCIe); UG863 (Versal PCB Design User Guide)*

### Block Comparison

| Block | Families | Type | Max Gen | Max Lanes | GT | Doc |
|-------|----------|------|---------|-----------|-----|-----|
| **CPM4** | AI Core, Prime, AI Edge | Hard (PS) | Gen4 | x8 | GTY | PG346 |
| **CPM5** | Premium | Hard (PS) | Gen5 | x16 or 2×x8 | GTYP | PG346 |
| **PL-PCIE4** | All Versal | Soft (PL) | Gen4 | x8 | GTY | PG302 |
| **PL-PCIE5** | Premium | Soft (PL) | Gen5 | x8 | GTYP | PG302 |

### CPM (Hard Block) Base Addresses

*Source: AM012 (Versal Register Reference — CPM address map); [Register-based debugging of Versal ACAP CPM (blog)](https://forums.xilinx.com/t5/Design-and-Debug-Techniques-Blog/Register-based-debugging-of-Versal-ACAP-CPM-Mode-for-PCI-Express/ba-p/1221922)*

| Block | Typical Base | Description |
|-------|-------------|-------------|
| CPM DMA | 0xFCA00000 | DMA control registers |
| CPM PCIE0 | 0xFCE20000 | PCIe controller 0 |
| CPM PCIE1 | 0xFCE30000 | PCIe controller 1 (CPM5 dual-port only) |
| CPM Bridge | 0xFCE00000 | Bridge configuration |
| CPM SLCR | 0xFCA10000 | CPM system-level control (LTSSM state) |

**CPM4 vs CPM5 differences:**
- CPM5 supports dual-port (2× Gen5 x8) — CPM PCIE1 only exists on CPM5 dual-port config
- CPM5 adds Gen5 equalization registers (preset coefficients)
- CPM5 LTSSM has additional Gen5-specific states (EQ Phase 0-3)
- Both share the same base config space layout for standard PCIe capabilities

### PL-PCIE (Soft Block) Base Addresses

PL-PCIE blocks are instantiated in the PL fabric. Their base addresses are **design-dependent** — determined by the address map in the Vivado block design. There are no fixed addresses.

**How to find PL-PCIE base address:**
1. `chipscopy_device(action='resources')` — look for PCIE core in PL resources
2. The address map from the design's HWH or XSA (if available)
3. Memory-mapped at the address assigned in the Vivado Address Editor

### Versal CPM Debug Registers (AM012)

These CPM-specific registers are readable via `chipscopy_memory` at offsets relative to the CPM PCIE0 base (0xFCE20000). Register names reference the AM012 Versal Register Reference.

*Source: [AM012 — Versal Register Reference](https://www.xilinx.com/html_docs/registers/am012/am012-versal-register-reference.html); [PCIe Debug K-Map — Versal CPM Debug Checklist](https://xilinx.github.io/pcie-debug-kmap/pciedebug/build/html/docs/Versal_ACAP_CPM_Mode_for_PCI_Express/debug_faq.html)*

| Register | Name (AM012) | Purpose | Key Values |
|----------|-------------|---------|------------|
| phy_rdy | `cpm4_pcie0_attr___phy_rdy` | GT PHY initialization status | 1=ready, 0=not ready |
| pl_eq_bypass_phase23 | `cpm4_pcie0_attr___pl_eq_bypass_phase23` | Bypass EQ Phase 2/3 (Gen3+) | 1=bypass, 0=normal |
| cfg_interrupt | `cpm4_pcie0_attr___cfg_interrupt` | MSI/MSI-X interrupt status | See PG346 |
| pfx_bar0_control_0 | `cpm4_pcie0_attr___pfx_bar0_control_0` | BAR0 configuration (PF0) | Aperture, type, enable |
| pfx_bar0_control_1 | `cpm4_pcie0_attr___pfx_bar0_control_1` | BAR0 configuration (PF1) | Aperture, type, enable |

**Reading CPM registers:** Use `chipscopy_memory` with the DPC memory target. The K-Map confirms these same registers are accessible via XSDB — `chipscopy_memory` provides the equivalent mechanism.

**CPM5 additional registers:** CPM5 adds Gen5 equalization preset coefficient registers for per-lane TX/RX tuning. Exact offsets follow the same `cpm5_pcie0_attr___` naming convention in AM012.

---

### PL-PCIE ILA Debug Signals

When PL-PCIE designs include ILA cores, these signals (from PG302/PG343) are the most useful for triggering and analysis. Cross-reference with the `hw-ila-debug` skill.

*Source: PG343 (Versal ACAP Integrated Block for PCI Express — Debug Gotchas section); PG302 (Versal PL PCIe); [PCIe Debug K-Map — PL-PCIE Debug Gotchas](https://xilinx.github.io/pcie-debug-kmap/pciedebug/build/html/docs/Versal_ACAP_Integrated_Block_for_PCI_Express/debug_gotchas.html)*

| Signal | Width | Purpose | Trigger Use |
|--------|-------|---------|-------------|
| `cfg_ltssm_state` | 6-bit | LTSSM state machine | Trigger on specific state (0x10=L0, 0x00=Detect) |
| `cfg_negotiated_width` | 4-bit | Current link width | Trigger on width change (downgrade) |
| `cfg_current_speed` | 3-bit | Current link speed | Trigger on speed change |
| `cfg_local_error_out` | multi-bit | Local errors | Trigger on any error: Replay Timeout, Replay Rollover |
| `cfg_function_status` | multi-bit | Command Register bits | I/O Enable, Mem Enable, Bus Master, INTx Disable |
| `user_lnk_up` | 1-bit | Link up indicator | Trigger on link down (falling edge) |

---

### UltraScale+ PCIe (NOT COVERED — Future Work)

| Block | US+ Families | Max Gen | Lanes | Doc |
|-------|-------------|---------|-------|-----|
| PCIE4C | Virtex/Kintex US+ | Gen3 x16 / Gen4 x8 | 16 | PG213 |
| PL-PCIE | All US+ | Gen3/Gen4 | varies | PG213 |

ChipScoPy MCP (`chipscopy_memory`) does not support UltraScale+ devices. US+ PCIe debug requires Vivado MCP (`vivado_execute` with `hw_pcie` Tcl objects) or XSDB register reads. This is planned as a future skill extension.

**Note:** Use `chipscopy_device(action='resources')` to discover available PCIe blocks and their types. Never hardcode base addresses — always verify from the device.

---

## Diagnostic Decision Tree

*Source: [PCIe Debug K-Map](https://xilinx.github.io/pcie-debug-kmap/pciedebug/build/html/index.html) — aggregated from [Link Training Checklist](https://xilinx.github.io/pcie-debug-kmap/pciedebug/build/html/docs/Link_Training/general_debug_checklist_reasons_questions.html), [PCIe Common Issues](https://xilinx.github.io/pcie-debug-kmap/pciedebug/build/html/docs/PCIe_Common_Issues/index.html), [Versal CPM Debug FAQ](https://xilinx.github.io/pcie-debug-kmap/pciedebug/build/html/docs/Versal_ACAP_CPM_Mode_for_PCI_Express/debug_faq.html); AR73361 (link training debug guide); AR72471 (US+ LTSSM status)*

```
PCIe Link Issue
├── Link not training (LTSSM stuck in Detect)
│   ├── READ phy_rdy → 0? GT PHY not initialized. Check refclk + GT power.
│   ├── READ SysMon VCCINT_GT → out of range? Power supply issue.
│   ├── No partner: cable/connector?
│   ├── No refclk: check reference clock source
│   └── No termination: RX termination present?
├── Link stuck in Polling
│   ├── READ Link Caps [3:0] → max speed. Both ends share common speed?
│   ├── Refclk frequency wrong: 100 MHz required
│   └── SI issue: eye too closed for training
├── Link stuck in Config
│   ├── Width mismatch: lane count doesn't match
│   ├── Lane reversal: neither EP nor RP supports reversal
│   ├── Host bifurcated: slot width doesn't match card
│   └── Dead lanes: run per-lane IBERT eye scan
├── Link at L0 but unstable (cycling to Recovery)
│   ├── READ LTSSM 3× → values alternate L0/Recovery? Link integrity issue.
│   ├── READ AER correctable → Receiver Errors growing? Marginal SI.
│   ├── RUN IBERT eye scan → measure eye width/height vs spec
│   └── READ SysMon → power noise on VCCINT_GT or MGTAVCC?
├── Link at lower speed than expected
│   ├── READ Link Caps vs Link Status → confirm speed downgrade
│   ├── READ Link Status 2 → EQ Complete? Phase 1/2/3 status?
│   ├── If EQ Phase 2/3 failed: try pl_eq_bypass_phase23 = 1
│   ├── For Gen3: check Auto RxEq enabled? TX Preset value (try 5)?
│   └── SI marginal: eye scan shows narrow eye
├── Link at narrower width than expected
│   ├── READ Link Caps [9:4] vs Link Status [9:4] → confirm width downgrade
│   ├── Dead lanes: per-lane IBERT eye scan
│   ├── Lane skew: excessive skew between lanes on board
│   └── Host bifurcation: slot configured for fewer lanes
├── Link up but no data transfer
│   ├── READ Command Register (0x04) bit 1 → Memory Enable = 0? Host didn't enable.
│   ├── READ Command Register (0x04) bit 2 → Bus Master = 0? DMA disabled.
│   ├── READ BAR0-5 (0x10-0x24) → all zeros? Host didn't enumerate.
│   │   └── Warm reboot host. If still zero → BAR too large or enumeration timing.
│   ├── READ cfg_function_status (PL-PCIE via ILA) → same Command Register bits
│   └── Check NoC for timeout errors → endpoint memory not reachable via NoC?
├── Vendor ID = 0xFFFF
│   ├── Device not present on bus. Link went down after training.
│   ├── READ AER Uncorrectable bit 5 → Surprise Down Error?
│   └── READ LTSSM → Disabled (0x31) or back in Detect (0x00)?
└── High error count
    ├── Correctable (Receiver Error, bit 0): SI marginal → IBERT eye scan
    ├── Correctable (Replay Timeout/Rollover, bits 8/12): link retransmission
    ├── Correctable (Bad TLP/DLLP, bits 6/7): data corruption → check SI
    ├── Uncorrectable (Completion Timeout, bit 14): endpoint not responding
    ├── Uncorrectable (Receiver Overflow, bit 17): check relaxed ordering + credits
    ├── Uncorrectable (Surprise Down, bit 5): unexpected link drop
    └── Correlate with: eye scan, SysMon voltage, temperature
```

---

## Link Training Root-Cause Checklist

Each item below has a **register read** the skill can perform to check. Items are ordered by likelihood.

*Source: [PCIe Debug K-Map — Common Link Training Issue Reasons](https://xilinx.github.io/pcie-debug-kmap/pciedebug/build/html/docs/Link_Training/general_debug_checklist_reasons_questions.html); [PCIe Debug K-Map — General Debug Checklist](https://xilinx.github.io/pcie-debug-kmap/pciedebug/build/html/docs/Link_Training/general_debug_checklist_reasons_questions.html#general-debug-checklist)*

| # | Root Cause | Register/Action | How to Check |
|---|-----------|-----------------|---------------|
| 1 | PHY not ready | `phy_rdy` register (CPM) | Read → 0 means GT not initialized |
| 2 | Refclk issue | SysMon MGTAVCC/MGTAVTT | Read supply rails via `hw-sysmon` |
| 3 | L0↔Recovery cycling | LTSSM (read 3×) | If values alternate, link integrity issue |
| 4 | Speed downgrade | Link Caps vs Link Status | Compare max vs negotiated speed |
| 5 | Width downgrade | Link Caps vs Link Status | Compare max vs negotiated width |
| 6 | EQ failure (Gen3+) | Link Status 2 (Cap+0x32) | EQ Complete=0 or Phase 2/3 failed |
| 7 | Host didn't enumerate | BAR0-5 (0x10-0x24) | All zeros → warm reboot host |
| 8 | Memory not enabled | Command Register (0x04) | Bit 1=0 → BARs disabled by host |
| 9 | Bus Master disabled | Command Register (0x04) | Bit 2=0 → DMA cannot initiate |
| 10 | SI marginal | AER Correctable (AER+0x10) | Receiver Error (bit 0) growing |
| 11 | Replay issues | AER Correctable (AER+0x10) | Replay Timeout (bit 12) / Rollover (bit 8) |
| 12 | Surprise link down | AER Uncorrectable (AER+0x04) | Surprise Down (bit 5) set |
| 13 | Receiver overflow | AER Uncorrectable (AER+0x04) | Bit 17 — check relaxed ordering + credits |
| 14 | Device absent | Vendor ID (0x00) | 0xFFFF → device not present or link down |
| 15 | Lane reversal | LTSSM stuck in Config | Neither EP nor RP supports lane reversal |
| 16 | Host bifurcation | Width downgrade despite matching caps | Slot configured for fewer lanes than card |

---

## PCIe Eye Opening Requirements

Minimum eye opening for each PCIe generation (for comparing IBERT eye scan results):

*Source: PCI Express CEM (Card Electromechanical) Specification; PCI Express Base Specification channel compliance requirements*

| Gen | Data Rate | Min Eye Width (UI) | Min Eye Height (mV) | Note |
|-----|-----------|-------------------|---------------------|------|
| Gen1 | 2.5 GT/s | 0.60 UI | 175 mV | 8b/10b |
| Gen2 | 5.0 GT/s | 0.45 UI | 120 mV | 8b/10b |
| Gen3 | 8.0 GT/s | 0.30 UI | 15 mV (inner) | 128b/130b, equalization required |
| Gen4 | 16.0 GT/s | 0.20 UI | 10 mV (inner) | 128b/130b, 3-tap EQ |
| Gen5 | 32.0 GT/s | 0.15 UI | 8 mV (inner) | 128b/130b, CTLE+DFE required |

**Interpretation:** If IBERT eye scan shows values below these thresholds, link training failures or high error rates are expected. Recommend: check AC coupling caps (75–200 nF), refclk jitter, power supply decoupling, channel loss.

---

## Report JSON Schema

```json
{
  "schema_version": "hw-pcie-link-debug/1.0.0",
  "timestamp": "2026-05-01T12:00:00Z",
  "device": { "part": "...", "dna": "..." },
  "link_status": {
    "ltssm_state": "L0",
    "current_speed": "Gen4",
    "current_speed_gt_s": 16.0,
    "negotiated_width": "x8",
    "max_speed": "Gen4",
    "max_width": "x8",
    "training": false,
    "dl_active": true
  },
  "config_space": {
    "vendor_id": "0x10EE",
    "device_id": "0xB03F",
    "class_code": "0x058000",
    "bars": [
      { "index": 0, "address": "0x...", "size": "256 MB", "type": "Memory 64-bit" }
    ]
  },
  "errors": {
    "correctable": { "total": 0, "bits": {} },
    "uncorrectable": { "total": 0, "bits": {} }
  },
  "eye_scan": null,
  "diagnosis": {
    "status": "healthy",
    "issues": [],
    "recommendations": []
  }
}
```

---

## Report Template (REPORT.md)

```markdown
# PCIe Link Debug Report

**Device:** <part> | **Date:** <timestamp>

## Link Status

| Field | Value |
|-------|-------|
| LTSSM State | <state> |
| Speed | <GenN> (<N> GT/s) |
| Width | x<N> |
| Max Speed | <GenN> |
| Max Width | x<N> |
| DL Active | <yes/no> |

## Configuration Space

| Field | Value |
|-------|-------|
| Vendor ID | <vid> |
| Device ID | <did> |
| Class Code | <class> |

## Error Summary

| Type | Count | Details |
|------|-------|---------|
| Correctable | <n> | <error types> |
| Uncorrectable | <n> | <error types> |

## Diagnosis

<analysis and recommendations>
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Memory read fails at CPM address | Wrong base address | Check device resources for correct CPM offset |
| Wrong block type assumed | CPM4 vs CPM5 vs PL-PCIE | Verify block type from `chipscopy_device(action='resources')` |
| PL-PCIE address unknown | Soft block, design-dependent | Check HWH/XSA address map or Vivado Address Editor |
| Non-Versal device | US+ PCIE4C not supported | This skill is Versal-only. US+ requires Vivado MCP (future) |
| All zeros from config space | Link not trained | Fix LTSSM issue first |
| Vendor ID 0xFFFF | Device not present / link down | Check physical connection |
| Speed downgrade | SI or partner limitation | Eye scan + partner capability check |
| Replay errors growing | Signal integrity marginal | IBERT eye scan, check board design |
| L0↔Recovery cycling | LTSSM alternates between 0x10 and 0x20-0x23 | Link integrity issue — run eye scan, check SI |
| Command reg Mem Enable = 0 | Host didn't enable endpoint | Check host driver, try warm reboot |
| BARs all zeros | Host didn't enumerate | Warm reboot; if persists, BAR size too large or enumeration timing |
| EQ Phase 2/3 failed | Link Status 2 shows incomplete EQ | Try `pl_eq_bypass_phase23 = 1` (CPM) or TX Preset = 5 |

---

## Sources & References

### AMD/Xilinx Documentation

| ID | Title | Content Used |
|----|-------|---------------|
| PG346 | Versal Adaptive SoC CPM Mode for PCI Express | CPM4/CPM5 architecture, LTSSM encoding, register map, debug features |
| PG302 | Versal Adaptive SoC Integrated Block for PCI Express | PL-PCIE4/5 IP, split-IP flow, debug signals |
| PG343 | Versal ACAP Integrated Block for PCI Express (LogiCORE) | PL-PCIE debug gotchas, ILA trigger signals, cfg_ltssm_state encoding |
| PG213 | UltraScale+ Integrated Block for PCI Express | US+ PCIE4C (future work reference) |
| AM012 | Versal Adaptive SoC Register Reference | CPM register names/addresses: phy_rdy, pl_eq_bypass_phase23, pfx_bar0_control, cfg_interrupt |
| UG863 | Versal Adaptive SoC PCB Design User Guide | Board design guidelines, GT reference clock, SI requirements |
| XTP546 | Versal ACAP Schematic Review Checklist | Board-level debug checklist |

### PCIe Debug K-Map Pages

| Page | URL | Content Used |
|------|-----|--------------|
| PCIe Common Issues | https://xilinx.github.io/pcie-debug-kmap/pciedebug/build/html/docs/PCIe_Common_Issues/index.html | Enumeration failures, completion timeout, receiver overflow, BAR issues |
| Link Training — Reasons & Checklist | https://xilinx.github.io/pcie-debug-kmap/pciedebug/build/html/docs/Link_Training/general_debug_checklist_reasons_questions.html | 15+ root causes, SI checklist, Gen3 EQ debug, AC coupling spec (75–200 nF) |
| PCIe General Debug Techniques | https://xilinx.github.io/pcie-debug-kmap/pciedebug/build/html/docs/PCIe_Debug_General_Techniques/index.html | LTSSM check methods, Gen1x1 isolation, enumeration verification |
| Versal CPM Debug Checklist | https://xilinx.github.io/pcie-debug-kmap/pciedebug/build/html/docs/Versal_ACAP_CPM_Mode_for_PCI_Express/debug_faq.html | CPM register reads (phy_rdy, BAR control, EQ bypass), xsdb register access |
| Versal CPM Issues & Tips | https://xilinx.github.io/pcie-debug-kmap/pciedebug/build/html/docs/Versal_ACAP_CPM_Mode_for_PCI_Express/issue_q%26a_debug_tips.html | ES1 SSC issue, PMC MIO37 configuration |
| Versal PL-PCIE Debug Checklist | https://xilinx.github.io/pcie-debug-kmap/pciedebug/build/html/docs/Versal_ACAP_Integrated_Block_for_PCI_Express/debug_faq.html | PL-PCIE debug flow, Link Debug Feature (PG343), eye diagram checks |
| Versal PL-PCIE Debug Gotchas | https://xilinx.github.io/pcie-debug-kmap/pciedebug/build/html/docs/Versal_ACAP_Integrated_Block_for_PCI_Express/debug_gotchas.html | ILA trigger signals: cfg_ltssm_state, cfg_negotiated_width, cfg_local_error_out |

### Answer Records & Blogs

| ID | Title / URL | Content Used |
|----|------------|---------------|
| AR73361 | [PCIe Link Training Debug Guide](https://www.xilinx.com/support/answers/73361.html) | Comprehensive link training debug methodology |
| AR72471 | [US+ LTSSM Status Check](https://www.xilinx.com/support/answers/72471.html) | LTSSM register read technique (US+ reference) |
| Blog | [Debugging Versal PL-PCIE Link Training](https://forums.xilinx.com/t5/Design-and-Debug-Techniques-Blog/Debugging-Versal-ACAP-Integrated-Block-for-PCIe-Express-link/ba-p/1203707) | PCIe Link Debug Feature enablement, LTSSM graph, eye diagram |
| Blog | [Register-based CPM Debugging](https://forums.xilinx.com/t5/Design-and-Debug-Techniques-Blog/Register-based-debugging-of-Versal-ACAP-CPM-Mode-for-PCI-Express/ba-p/1221922) | Reading CPM registers via XSDB (equivalent to chipscopy_memory) |
| Blog | [Debugging CPM Designs with ILA](https://forums.xilinx.com/t5/Design-and-Debug-Techniques-Blog/Debugging-Versal-ACAP-CPM-Mode-for-PCI-Express-Designs-using/ba-p/1218411) | ILA-based CPM debug technique |
| Blog | [PCIe Issues using lspci/setpci](https://forums.xilinx.com/t5/Design-and-Debug-Techniques-Blog/Debugging-PCIe-Issues-using-lspci-and-setpci/ba-p/1148199) | Host-side enumeration verification |
| Blog | [Versal PL-PCIE IP Generation Flow](https://forums.xilinx.com/t5/Design-and-Debug-Techniques-Blog/Understanding-the-new-PL-PCIE-IP-Generation-flow-for-Versal-ACAP/ba-p/1215986) | Split-IP concept for PL-PCIE in Versal |

### PCI-SIG Specifications

| Spec | Content Used |
|------|--------------|
| PCI Express Base Specification (Rev 5.0) | Config space layout, Link Capability/Status registers, AER registers, LTSSM state definitions |
| PCI Express CEM Specification | Eye opening requirements per generation, channel compliance |
