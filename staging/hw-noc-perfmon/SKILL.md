---
name: hw-noc-perfmon
description: >
  Measure and diagnose NoC (Network on Chip) bandwidth on live Versal devices. Use
  direct ChipScoPy NocPerfmon for bandwidth and latency samples, then use ChipScoPy MCP
  tools for topology discovery and optional Vivado artifacts for design correlation.
  Discover NMU/NSU/NPS/DDRMC/HBMMC elements, validate element status, and report
  measured versus expected performance. Use when user asks to "discover NoC elements", "check NoC topology",
  "list NMU/NSU", "NoC performance", "NoC status", "check NoC health",
  "what NoC elements are in my design", or "validate NoC path".
version: 1.2.0-ea
chipscopy_version: "2026.2+"
categories: [hardware-debug, noc, performance, versal]
device_families: [versal]
estimated_duration: 1-3 minutes
complexity: intermediate
maturity: early-access
author: Vivado AI Skills Team
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
# NoC Performance Monitor (EA)

> **Early Access** — this skill may change before general availability.

Measures NoC bandwidth through **direct ChipScoPy NocPerfmon** and uses **ChipScoPy MCP** for topology discovery, element validation, and structured reports. It can enrich the result with routed-design artifacts when available.

**Measurement rule:** When the user asks for bandwidth or latency, use direct ChipScoPy first. Current `chipscope_noc` MCP actions are topology-only and cannot configure or stream NoC performance monitors. Do not substitute hand-written NPI register offsets, a guessed timebase, or an inferred controller clock for the ChipScoPy measurement path.

**EA Scope:** Direct ChipScoPy measurement is the interim known-good path. A first-class `chipscope_noc_perfmon` MCP tool remains the roadmap path. For subsystem-level error analysis, use the `hw-noc-debug` skill with `sysdbg_noc`.

See [REFERENCE.md](REFERENCE.md) for NoC element types, element naming, JSON schema, and report templates.

## Tools Used

| Tool | Purpose |
|------|---------|
| `chipscope_noc` | Discover NoC elements (`action='discover'`) and validate per-element status (`action='read_registers'`). |
| `chipscope_session` | Connect to hw_server + cs_server (`action='connect'`), check status (`action='status'`). |
| `chipscope_device` | List/select devices (`action='list'`/`'select'`), check resources (`action='resources'`). |
| `chipscope_scan` | Discover debug cores including NoC (`action='scan'`, `include=['noc']`). |
| Direct ChipScoPy | Configure bounded NoC performance-monitor captures with `NocPerfmon.configure_monitors()` and collect samples through `NoCPerfMonNodeListener`. |
| `vivado_execute` | **(Optional)** Extract design artifacts (NCR, NTS, noc_report) from a routed design when Vivado MCP is available. |
| Agent file tools | Read design artifacts, write output files (report_data.json, REPORT.md). |

**Versal only.** NoC elements exist only on Versal devices. Non-Versal devices will have no NoC cores.

**Design context is optional but strongly recommended.** The skill works with ChipScoPy MCP alone (hardware-only topology), but design artifacts (NCR, NTS, noc_report.txt) from a Vivado project or a pre-built metadata folder enrich the analysis with IP connectivity, QoS settings, and NMU→NSU routing paths.

---

## Efficiency Guidelines

- **Connect once** — use `chipscope_session(action='status')` to check existing connection before connecting.
- **Paginate discovery** — `chipscope_noc(action='discover')` returns up to `limit` elements. Use `offset` for large designs (100+ elements).
- **Batch validation** — call `chipscope_noc(action='read_registers')` only for elements the user cares about, not all discovered elements.
- **Measure through ChipScoPy** — use the installed, version-matched `NocPerfmon` API for bandwidth or latency. Do not recreate its counter decoding with raw register reads.
- **Use bounded captures** — request a finite sample count, record the actual sampling period and counter-overflow state, then disconnect the direct ChipScoPy session.
- **Protect shared infrastructure** — reuse a user-provided or agent-owned `cs_server`; never stop a shared `hw_server` or `cs_server`.
- **Write reports to file** — do not dump full element lists in chat. Give a short summary with counts.
- **Use the terminal only for the direct ChipScoPy environment and capture script.** Keep the script, its input URLs, package version, and raw output with the report.

---

## Mandatory Workflow

**Execute steps SEQUENTIALLY.** Workflow is incomplete until output files exist.

### Step 1: Verify Connection & Device

Check if already connected:
```
chipscope_session(action='status')
```

If not connected:
```
chipscope_session(action='connect', hw_server_url='TCP:<host>:3121')
```

cs_server is auto-derived (same host, port 3042). Both hw_server and cs_server are required for NoC debug core operations.

Select and verify device:
```
chipscope_device(action='list')
chipscope_device(action='resources')
```

Confirm NoC cores appear in the resources list. If not, run:
```
chipscope_scan(action='scan', include=['noc'])
```

**No NoC cores found** → STOP. Only Versal devices have NoC. Check: device is Versal? Device is programmed? Design includes NoC IP?

---

### Step 1.25: Direct ChipScoPy Measurement Preflight

Run this step whenever the user requests **bandwidth, latency, utilization, traffic rate, or a low-bandwidth root-cause investigation**. Do not answer that current MCP streaming is unavailable and stop.

1. **Do not infer an interpreter from an installed chipscope-mcp release.**
   Released chipscope-mcp artifacts are PyInstaller distributions and do not
   expose a reusable Python environment. Use a ChipScoPy interpreter only when
   the user supplies it or a project-specific development environment explicitly
   provides it.
2. **Check the actual interpreter before use:**
   ```bash
   <python> -c "import chipscopy; print(chipscopy.__version__)"
   ```
3. **If no verified ChipScoPy interpreter is available, create an isolated virtual
   environment.** Do not modify a global Python or a Vivado/Vitis bundled Python
   in place. Install the public PyPI package version that matches the
   `cs_server` release:
   ```bash
   <python> -m venv .chipscopy-venv
   .chipscopy-venv/bin/python -m pip install --upgrade pip
   .chipscopy-venv/bin/python -m pip install chipscopy
   ```
   ChipScoPy is public at <https://github.com/Xilinx/chipscopy> and installs
   from PyPI. If a specific `cs_server` release requires a matching ChipScoPy
   release line, replace `chipscopy` with `"chipscopy==<release>.*"` after
   determining that release. On Windows, use
   `.chipscopy-venv\Scripts\python.exe`. Record both ChipScoPy and `cs_server`
   versions.
4. **Use a known server, not a guessed one.** Pass both `hw_server_url` and `cs_server_url` to `chipscopy.create_session()`. Reuse the endpoint supplied by the user or start a private, agent-owned `cs_server` only when authorized. Never kill or restart a shared server.
5. **Run the bundled headless capture helper.** Do not search the filesystem for
   an example. The installed ChipScoPy wheel contains
   `chipscopy/examples/noc_perfmon/noc_perfmon.py`, but it is an interactive
   plotting example and is not suitable for an agent session. This skill's
   `scripts/chipscopy_noc_perfmon_capture.py` uses the same maintained API,
   chooses only supported sampling periods, requests a finite capture, records
   listener data, and calls `delete_session()` in a `finally` path.

**Mandatory node-class check:** Select controller names such as `DDRMC5E_X0Y0` for controller-level measurement only after discovery confirms they are valid. `DDRMC5E_NOC` / NSU monitor registers and NMU monitor registers are different register families. Never apply one family's offsets to the other.

---

### Step 1.5: Design Context Enrichment (Optional)

Design artifacts provide IP-level context that hardware discovery alone cannot: which AXI master connects to each NMU, QoS bandwidth allocation, and full NMU→NPS→NSU routing. This step is **optional** — skip it if no Vivado project, DCP, or pre-built artifacts folder is available.

**Mode detection (in priority order):**

1. **Pre-built artifacts folder** — user provides a folder containing design metadata files. No Vivado needed.
2. **Vivado MCP extraction** — Vivado MCP session is available with a routed design open.
3. **Hardware-only** — no design artifacts available. Proceed with chipscope_noc discovery only.

#### Mode A: Pre-built Artifacts Folder

If the user provides a metadata folder (or it's co-located with the design), search for:

| File | Purpose | Required? |
|------|---------|-----------|
| `noc_report.txt` | NPI base addresses, NoC instance names with site locations | Recommended |
| `*.ncr` | NoC topology — NMU/NSU connectivity, routing paths, QoS | Recommended |
| `*.nts` | NoC traffic spec — bandwidth allocation, traffic class, QoS config | Recommended |
| `*.xsa` | Hardware handoff — IP instance names, AXID-to-master mapping (via HWH) | Optional |

Validate each file exists and has content. Record paths for use in Step 4.

#### Mode B: Vivado MCP Extraction

If Vivado MCP is available (`vivado_execute` tool present) with a routed design open:

```tcl
# Generate noc_report.txt (NPI addresses + instance names)
report_noc -file vivado_agentic_ai_reports/hw-noc-perfmon/noc_report.txt

# Extract NCR (NoC topology) — MUST be from routed design
write_noc_solution -force vivado_agentic_ai_reports/hw-noc-perfmon/noc_solution.ncr

# Extract NTS (traffic spec) — MUST be from routed design
write_noc_qos -force vivado_agentic_ai_reports/hw-noc-perfmon/noc_traffic_spec.nts
```

Run via `vivado_execute(session_id=<id>, command=<tcl>)`. Create the output directory first with `file mkdir`.

> ⚠️ `report_noc`, `write_noc_solution`, and `write_noc_qos` only support `-file <path>`. No `-return_string` variant exists. Write to file, then read back with agent file tools.

> ⚠️ NCR and NTS **must** come from a routed design (completed implementation). Post-synthesis artifacts are incomplete.

#### Mode C: Hardware-Only

No design artifacts available. Proceed directly to Step 2. Topology analysis will be based on element names and enabled/disabled status only (no IP connectivity or QoS context).

---

### Step 2: Discover NoC Elements

```
chipscope_noc(action='discover', limit=50, offset=0)
```

Returns:
```json
{
  "success": true,
  "elements": ["nmu_0", "nmu_1", "nsu_0", "nsu_1", "ddrmc_0", ...],
  "total_count": 42,
  "has_more": false,
  "offset": 0,
  "limit": 50
}
```

For large designs (total_count > limit), paginate:
```
chipscope_noc(action='discover', limit=50, offset=50)
```

**Classify elements by type** from their names:
- **NMU** (Network Master Unit): Traffic sources (PS, PL, AIE masters)
- **NSU** (Network Slave Unit): Traffic destinations (DDR, PL slaves)
- **NPS** (Network Packet Switch): Routing/switching fabric
- **DDRMC**: DDR memory controller NoC interface
- **HBMMC**: HBM memory controller NoC interface

---

### Step 3: Validate Element Status

For elements of interest, check enabled/disabled status:

```
chipscope_noc(action='read_registers', element_name='nmu_0')
```

Returns:
```json
{
  "success": true,
  "element": "nmu_0",
  "status": "enabled"
}
```

Or for disabled elements:
```json
{
  "success": true,
  "element": "nmu_0",
  "status": "disabled",
  "note": "Element is disabled in current design configuration"
}
```

Validate key elements the user asks about. For a full topology survey, validate a representative sample of each type.

---

### Step 3.5: Capture Measured Bandwidth With Direct ChipScoPy

Run this step after discovery for any performance request.

1. Run the bundled helper with the verified endpoints and matching LTX:
   ```bash
   <python> <skill-dir>/scripts/chipscopy_noc_perfmon_capture.py \
     --hw-server-url TCP:<host>:<port> \
     --cs-server-url TCP:<host>:<port> \
     --ltx-path <matching-design>.ltx \
     --output vivado_agentic_ai_reports/hw-noc-perfmon/direct_capture.json \
     --samples 2 \
     --requested-period-ms 250
   ```
   Use `--node <discovered-node>` only when the user requested a specific
   element. Otherwise the helper selects the first enabled DDRMC, then the
   first enabled NMU.
2. The helper creates a separate direct session, initializes and discovers the
   NoC monitor, validates selected nodes, queries supported periods, configures
   best-effort read/write monitors, and attaches `NoCPerfMonNodeListener`.
3. Preserve `direct_capture.json` as raw evidence. It contains:
   - actual sampling period;
   - per-sample read/write bandwidth and latency-counter values;
   - raw counters when the listener provides them;
   - counter-overflow flags;
   - ChipScoPy version, `cs_server` version, selected nodes, traffic class, and capture count.
4. The helper disconnects the direct session in a `finally` path. Do not stop a
   user-owned or shared server.

**TCF discovery constraint:** When a tcflog trace is captured, preserve and
analyze it. On the validated VCK190 CED path, ChipScoPy session setup can
produce two `Memory.getContext: Invalid context` replies for RunControl-only
PMC and PL contexts and one `Jtag.getOption("skew"): unsupported property`
reply. Classify those replies as discovery observations only when the trace
also proves the same PMC/PL contexts succeed through RunControl and the cable
supports `frequency`, `frequency_list`, and `timing_class`. Record that
classification and its raw trace path in the report. Do not suppress the
replies by changing the normal direct-session configuration. Any other error
reply, unmatched command, timeout, or missing corroborating evidence is
unresolved: report the capture as incomplete and diagnose it before drawing a
bandwidth conclusion.

**Measurement validity gate:** A bandwidth result is valid only when the node class, supported sample period, traffic class, sample count, overflow state, and any captured protocol observations are recorded. If any are unavailable, report the capture as incomplete. The helper's latency values are counter-derived values, not nanoseconds; do not convert or label them with time units without device-specific, documented conversion evidence. Do not infer a bandwidth value from a topology-only MCP response.

---

### Step 4: Analyze Topology

From the discovered elements and any design artifacts (Step 1.5), build a topology summary:

**Always (hardware-only baseline):**
1. **Count by type**: NMU count, NSU count, NPS count, DDRMC count, HBMMC count
2. **Identify traffic sources**: Which NMUs are active (PS masters, PL masters, AIE)
3. **Identify traffic sinks**: Which NSUs route to DDR, HBM, or PL
4. **Flag disabled elements**: Elements present but disabled in current configuration

**If design artifacts are available (from Step 1.5):**
5. **Map IP connectivity** (from NCR): Which AXI master/slave IP connects to each NMU/NSU
6. **Report QoS configuration** (from NTS): Per-path bandwidth allocation, traffic class, read/write QoS
7. **Trace routing paths** (from NCR): Full NMU → NPS → NSU/DDRMC path with switch hops
8. **Correlate Vivado site names** (from noc_report.txt): Map hardware element names to Vivado site locations and NPI base addresses

This enrichment turns a bare element list into an actionable connectivity map — essential for identifying which IP masters are competing for bandwidth on shared NoC paths.

---

### Step 5: Write Output Files

**Write ALL files before giving any summary.** Use agent file tools.

Output directory: `vivado_agentic_ai_reports/hw-noc-perfmon/`

| File | Format | Content |
|------|--------|---------|
| `report_data.json` | JSON | Structured topology data and direct ChipScoPy measurement evidence (schema in [REFERENCE.md](REFERENCE.md)) |
| `REPORT.md` | Markdown | Topology summary, measured bandwidth/latency, status, observations, and bounded inferences |

---

## MCP-Only Limitations

The following capabilities remain unavailable through `chipscope_noc` alone. Use the direct ChipScoPy pathway above until the MCP enhancement exists:

| Capability | Status | What's Missing |
|------------|--------|----------------|
| NPM counter configuration | Not available | `configure_monitors()` not exposed in MCP |
| Bandwidth measurement | Not available | Requires NPM streaming API |
| Latency measurement | Not available | Requires NPM streaming API |
| Traffic class filtering | Not available | Requires NPM configuration |
| Sampling period control | Not available | `get_supported_sampling_periods()` not exposed |
| Real-time traffic visualization | Not available | Requires streaming + dashboard |

**Current skill capability:** Direct ChipScoPy measurement plus MCP topology discovery and structural analysis. For error-level NoC analysis (ISR bits, error registers, timeout state), use the `hw-noc-debug` skill.

---

## Design-Specific Rules

**All outputs MUST use ACTUAL values. NO generic placeholders.**

| Rule | Wrong | Correct |
|------|-------|---------|
| Element count | "found some elements" | "Discovered 42 NoC elements: 12 NMU, 8 NSU, 18 NPS, 2 DDRMC, 2 HBMMC" |
| Element status | "element is active" | "nmu_0: enabled, nsu_2: disabled in current configuration" |
| Topology | "NoC looks fine" | "12 active NMUs → 18 NPS switches → 8 active NSUs + 2 DDRMC endpoints" |
| IP context | "nmu_0 is a master" | "nmu_0 ← axi_dma_0/M_AXI_MM2S (BW: 4000 MB/s, best-effort) at NOC_NMU512_X0Y0" |
| Device | "the Versal" | "xcvp1202 on VPK120 board" |

---

## Error Handling

| Error | Symptom | Action |
|-------|---------|--------|
| No NoC cores | `chipscope_noc` returns CORE_NOT_FOUND | Only Versal has NoC. Check device family. |
| Not connected | session status shows disconnected | Connect: `chipscope_session(action='connect', hw_server_url=...)` |
| Device not programmed | CORE_NOT_FOUND after connect | Program device first: `chipscope_device(action='program', pdi_path=...)` |
| Invalid element name | read_registers returns ELEMENT_NOT_FOUND | Use discover to get valid names first |
| Pagination needed | has_more=true in discover result | Continue with offset += limit |

---

## Examples

**"What NoC elements are in my design?"** → Connect → Discover → Classify → "Found 42 elements: 12 NMU, 8 NSU, 18 NPS, 2 DDRMC, 2 HBMMC. All DDRMC endpoints enabled."

**"Show me the full NoC topology"** (with design artifacts) → Check for artifacts folder or Vivado MCP → Extract NCR/NTS → Discover elements → Enrich with IP connectivity → "nmu_0 (axi_dma_0/M_AXI, 4000 MB/s) → NPS_0 → NPS_3 → ddrmc_0. nmu_1 and nmu_0 share NPS_3 — potential contention point."

**"Show me the full NoC topology"** (hardware-only) → Discover all elements → Validate representative set → "12 NMU, 8 NSU, 18 NPS, 2 DDRMC. Note: no design artifacts — for IP connectivity and QoS details, provide a metadata folder or open the design in Vivado."

**"Is nmu_3 active?"** → `chipscope_noc(action='read_registers', element_name='nmu_3')` → "nmu_3: enabled"

**"Check NoC bandwidth"** → Verify the direct ChipScoPy environment → discover valid controller nodes → query supported sampling periods → run a finite `NocPerfmon` capture → report per-controller and aggregate read/write values with period, traffic class, and overflow state. Use MCP discovery only as supporting topology evidence.

---

## Integration

**Upstream:** `chipscope_session` + `chipscope_device` (connection and device setup)
**Complementary:** `hw-noc-debug` (error analysis via `sysdbg_noc`), `hw-ddrmc-debug` (DDRMC endpoint health)
**Downstream:** Replace the direct ChipScoPy capture with `chipscope_noc_perfmon` when its MCP surface is available, while preserving the same validity and reporting contract.

---

## Metadata

**Keywords:** NoC, NMU, NSU, NPS, DDRMC, HBMMC, performance, topology, Versal, chipscope_noc, network on chip
**Confidence Threshold:** 0.80

---

## Changelog

### Version 1.2.0-ea (2026-07-16)
- Rename skill identity to hw-noc-perfmon: update `name:` frontmatter, report
  output paths, and cross-skill references to match the renamed directory
- Note: frontmatter `version:` had drifted behind this changelog (was
  1.1.0-ea while the latest entry below was already 1.1.1-ea); this bump
  corrects both to agree

### Version 1.1.1-ea (2026-07-12)
- Correct the customer installation path: use public PyPI ChipScoPy from
  <https://github.com/Xilinx/chipscopy>.

### Version 1.1.0-ea (2026-07-12)
- Make direct ChipScoPy `NocPerfmon` the required first-line path for bandwidth
  and latency requests while the MCP surface remains topology-only.
- Add isolated-environment installation guidance.
- Add bounded-capture, node-class, sampling-period, counter-overflow, and shared
  server safety gates. Explicitly prohibit raw-offset/timebase reimplementation.
- Add a headless bounded-capture helper so agents do not search for or run the
  interactive ChipScoPy example.

### Version 1.0.1-ea (2026-07-01)
- Fix stale tool name prefix: `chipscopy_*` -> `chipscope_*` (chipscope-mcp renamed its
  tool surface after this skill's initial release; verified against the live
  `chipscope_noc` tool signature — `discover`/`read_registers` actions unchanged)

### Version 1.0.0-ea (2026-05-01)
- Initial EA release — NoC element discovery + status validation via ChipScoPy MCP
- Topology analysis from discover results
- NPM counters/streaming documented as roadmap
