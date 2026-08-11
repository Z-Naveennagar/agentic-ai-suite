<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# NoC Performance Monitor — Reference

## NoC Element Types

| Type | Full Name | Role | Examples |
|------|-----------|------|----------|
| **NMU** | Network Master Unit | Traffic initiator (source) | PS masters, PL AXI masters, AIE |
| **NSU** | Network Slave Unit | Traffic target (sink) | DDR-mapped, PL AXI slaves |
| **NPS** | Network Packet Switch | Internal routing/switching fabric | NPS_0..NPS_N |
| **DDRMC** | DDR Memory Controller | DDR endpoint NoC interface | ddrmc_0, ddrmc_1 |
| **HBMMC** | HBM Memory Controller | HBM endpoint NoC interface | hbmmc_0..hbmmc_N |

### NMU Source Categories

| Category | Description |
|----------|-------------|
| PS NMU | Cortex-A72/R5F processor subsystem masters |
| PL NMU | PL fabric AXI master interfaces |
| AIE NMU | AI Engine array memory-mapped interfaces |
| PMC NMU | Platform Management Controller DMA |

### NSU Sink Categories

| Category | Description |
|----------|-------------|
| DDR NSU | Routes traffic to DDRMC |
| HBM NSU | Routes traffic to HBMMC |
| PL NSU | Routes traffic to PL fabric AXI slaves |
| PS NSU | Routes traffic to PS peripheral slaves |

---

## Element Naming Convention

Elements follow the pattern: `<type>_<index>` or `<type>_<location>`.

Examples from a typical VCK190 design:
```
nmu_0, nmu_1, nmu_2          (PL NMUs)
nsu_0, nsu_1                  (PL NSUs)
nps_0, nps_1, ..., nps_17     (Packet switches)
ddrmc_0, ddrmc_1              (DDR controllers)
```

---

## Direct ChipScoPy Performance Measurement

Use this path when the user asks for bandwidth, latency, utilization, or a
low-bandwidth investigation. It is the current supported measurement path while
the MCP exposes only topology operations.

### Environment and installation

1. Do not infer a reusable Python environment from an installed chipscope-mcp
   release. Released chipscope-mcp artifacts are PyInstaller distributions.
   Use a ChipScoPy interpreter only when the user supplies it or a
   project-specific development environment explicitly provides it.
2. Verify the selected interpreter before use:
   ```bash
   <python> -c "import chipscopy; print(chipscopy.__version__)"
   ```
3. If no verified ChipScoPy interpreter is available, use an isolated virtual
   environment and install the public PyPI package. Do not install into a global
   or bundled tool Python:
   ```bash
   <python> -m venv .chipscopy-venv
   .chipscopy-venv/bin/python -m pip install chipscopy
   ```
   ChipScoPy's public source and installation documentation are
   <https://github.com/Xilinx/chipscopy> and
   <https://xilinx.github.io/chipscopy/2026.1/chipscopy_installation.html>.
   If a specific `cs_server` release requires a matching ChipScoPy release
   line, use `"chipscopy==<release>.*"` after determining that release.
4. Match ChipScoPy to the connected `cs_server` release and record both
   versions.

### Required API flow

Use this skill's `scripts/chipscopy_noc_perfmon_capture.py` helper. Do not
search the filesystem for an example. The installed
`chipscopy/examples/noc_perfmon/noc_perfmon.py` is an interactive plotting
example; the bundled helper is the headless finite-capture version for agent
use. Its required flow is:

1. `create_session(hw_server_url=..., cs_server_url=...)`
2. Select the intended device and NoC core.
3. `NocPerfmon.initialize()` and `discover_noc_elements()`.
4. Validate selected node classes. Do not mix NMU and `DDRMC*_NOC` / NSU
   register models.
5. `get_supported_sampling_periods(...)` using known design clock metadata.
6. `NocPerfmon.configure_monitors(...)` with a finite `sample_count`.
7. Attach `NoCPerfMonNodeListener` and retain its samples, raw trace data, and
   overflow flags.
8. `delete_session(session)` in a `finally` path.

Example:

```bash
<python> <skill-dir>/scripts/chipscopy_noc_perfmon_capture.py \
  --hw-server-url TCP:<host>:<port> \
  --cs-server-url TCP:<host>:<port> \
  --ltx-path <matching-design>.ltx \
  --output direct_capture.json \
  --samples 2 \
  --requested-period-ms 250
```

For DDRMC5E, the listener aggregates both NSU ports and uses the NPI sampling
period. Record per-NSU values as well as the controller aggregate when
available. Never replace this flow with a raw-register script unless the user
specifically asks for a cross-check and the direct ChipScoPy result remains the
reference.

### Direct measurement evidence

Every measured result must record:

- ChipScoPy and `cs_server` versions;
- hw_server and cs_server endpoints;
- selected element names and classified types;
- requested and actual sampling periods;
- traffic class and finite sample count;
- per-sample and aggregate read/write bandwidth plus latency-counter values;
- raw counters and counter-overflow flags when available;
- design-clock metadata source, if it was required to choose a period.

### TCF protocol evidence constraint

When a tcflog capture is available, preserve the trace path, analyzer summary,
and every error reply in `report_data.json`. The following narrow
classification was proven on the VCK190 CED fixture:

| Reply | Classify as a discovery observation only when the trace also proves |
|-------|--------------------------------------------------------------------|
| `Memory.getContext` returns `Invalid context` | The same context is a PMC or PL RunControl container and `RunControl.getContext` succeeded for it. |
| `Jtag.getOption("skew")` returns `unsupported property` | The same cable returned values for `frequency`, `frequency_list`, and `timing_class`. |

This is not a blanket exception for `Memory`, `Jtag`, or TCF errors. Do not
change the normal direct-session configuration merely to hide these replies.
Any other error reply, an unmatched command, timeout, or missing corroborating
evidence makes the capture incomplete until diagnosed.

---

## ChipScoPy MCP Tool Reference

### chipscope_noc

| Action | Parameters | Returns |
|--------|-----------|---------|
| `discover` | `limit` (default 50), `offset` (default 0) | `{elements[], total_count, has_more, offset, limit}` |
| `read_registers` | `element_name` (required) | `{element, status: "enabled"\|"disabled"}` |

### chipscope_session

| Action | Key Parameters | Purpose |
|--------|---------------|---------|
| `connect` | `hw_server_url` (required) | Connect to hardware. cs_server auto-derived. |
| `status` | — | Check connection state |
| `disconnect` | — | Release hardware |

### chipscope_device

| Action | Key Parameters | Purpose |
|--------|---------------|---------|
| `list` | — | List connected devices |
| `select` | `device_selector` | Select target device |
| `resources` | — | List debug cores (incl. NoC) |
| `program` | `pdi_path` | Program PDI |

### chipscope_scan

| Action | Key Parameters | Purpose |
|--------|---------------|---------|
| `scan` | `include=['noc']` | Discover NoC cores |
| `status` | — | Check scan state |

---

## Design Artifacts (Optional Context Enrichment)

These files provide design-time metadata that enriches hardware-only discovery. They are extracted from a routed Vivado design or provided in a pre-built artifacts folder.

### noc_report.txt

Generated by `report_noc -file <path>` from a routed design. Contains:
- NoC instance names with Vivado site locations
- NPI base addresses for each NMU/NSU (hex, used for register reads in hw-noc-debug)
- Instance hierarchy paths

Example excerpt:
```
NMU: noc_nmu_0  Site: NOC_NMU512_X0Y0  NPI_ADDR: 0xF6010000
NMU: noc_nmu_1  Site: NOC_NMU512_X0Y1  NPI_ADDR: 0xF6020000
NSU: noc_nsu_0  Site: NOC_NSU512_X0Y0  NPI_ADDR: 0xF7010000
```

### NCR (NoC Compiler Results)

Generated by `write_noc_solution -force <path>.ncr` from a routed design. Contains:
- **NMU/NSU connectivity** — which AXI master/slave IP connects to each NMU/NSU
- **Routing paths** — full NMU → NPS → NSU/DDRMC path with switch hops
- **QoS settings** — per-connection quality-of-service configuration
- **Physical placement** — site locations and clock domain assignments

### NTS (NoC Traffic Spec)

Generated by `write_noc_qos -force <path>.nts` from a routed design. Contains:
- **Bandwidth allocation** — per-path read/write bandwidth in MB/s
- **Traffic class** — best-effort, low-latency, isochronous
- **QoS configuration** — priority, bandwidth guarantees, burst settings

### Vivado MCP Commands for Extraction

```tcl
# All three require a routed design open in Vivado
# All only support -file <path>, NO -return_string variant
file mkdir vivado_agentic_ai_reports/hw-noc-perfmon
report_noc -file vivado_agentic_ai_reports/hw-noc-perfmon/noc_report.txt
write_noc_solution -force vivado_agentic_ai_reports/hw-noc-perfmon/noc_solution.ncr
write_noc_qos -force vivado_agentic_ai_reports/hw-noc-perfmon/noc_traffic_spec.nts
```

> **NCR and NTS MUST come from a routed design.** Post-synthesis artifacts lack final placement and routing.

---

## Report JSON Schema

```json
{
  "schema_version": "hw-noc-perfmon/1.2.0-ea",
  "timestamp": "2026-07-12T00:00:00Z",
  "device": {
    "part": "xcvp1202",
    "dna": "0x00012345...",
    "board": "VPK120"
  },
  "design_context": {
    "mode": "pre-built | vivado | hardware-only",
    "artifacts": {
      "noc_report": "path/to/noc_report.txt",
      "ncr": "path/to/noc_solution.ncr",
      "nts": "path/to/noc_traffic_spec.nts"
    }
  },
  "measurement": {
    "method": "direct-chipscopy-nocperfmon",
    "chipscopy_version": "2026.2.0.18",
    "cs_server_version": "2026.2",
    "traffic_class": "best-effort-read-write",
    "sample_count": 5,
    "sampling_period_ms": {
      "requested": 100.0,
      "actual": 100.0,
      "source": "get_supported_sampling_periods"
    },
    "valid": true,
    "limitations": [],
    "protocol_observations": {
      "tcflog_trace": "path/to/tcflog_hw_server.log",
      "unmatched_commands": 0,
      "discovery_observations": [
        {
          "service": "Memory",
          "method": "getContext",
          "error": "Invalid context",
          "context_type": "PMC or PL RunControl container",
          "classification": "validated-direct-session-discovery"
        },
        {
          "service": "Jtag",
          "method": "getOption",
          "option": "skew",
          "error": "unsupported property",
          "classification": "validated-direct-session-discovery"
        }
      ]
    },
    "elements": [
      {
        "name": "DDRMC5E_X0Y0",
        "type": "ddrmc",
        "read_bandwidth_mb_s": { "min": 1500, "avg": 1600, "max": 2475 },
        "write_bandwidth_mb_s": { "min": 1500, "avg": 1604, "max": 2483 },
        "average_read_latency_counts": { "min": 0, "avg": 0, "max": 0 },
        "average_write_latency_counts": { "min": 0, "avg": 0, "max": 0 },
        "counter_overflow": false
      }
    ]
  },
  "topology": {
    "total_elements": 42,
    "by_type": {
      "nmu": { "count": 12, "enabled": 10, "disabled": 2 },
      "nsu": { "count": 8, "enabled": 8, "disabled": 0 },
      "nps": { "count": 18, "enabled": 18, "disabled": 0 },
      "ddrmc": { "count": 2, "enabled": 2, "disabled": 0 },
      "hbmmc": { "count": 2, "enabled": 0, "disabled": 2 }
    },
    "elements": [
      {
        "name": "nmu_0", "type": "nmu", "status": "enabled",
        "site": "NOC_NMU512_X0Y0",
        "npi_address": "0xF6010000",
        "connected_ip": "axi_dma_0/M_AXI_MM2S",
        "qos": { "bandwidth_mbps": 4000, "traffic_class": "best-effort" }
      },
      {
        "name": "nsu_0", "type": "nsu", "status": "enabled",
        "site": "NOC_NSU512_X0Y0",
        "connected_ip": "ddr4_0/S_AXI",
        "qos": { "bandwidth_mbps": 4000, "traffic_class": "best-effort" }
      }
    ],
    "paths": [
      { "from": "nmu_0", "through": ["nps_0", "nps_3"], "to": "ddrmc_0" }
    ]
  },
  "observations": [
    "All DDRMC endpoints are enabled and active",
    "2 NMUs are disabled — unused PL master interfaces",
    "nmu_0 (axi_dma_0) and nmu_1 (axi_dma_1) share NPS_3 → potential contention"
  ],
  "mcp_limitations": [
    "NPM counter streaming is not available through chipscope_noc",
    "Direct ChipScoPy NocPerfmon was used for measurement"
  ]
}
```

Fields under `design_context`, `site`, `npi_address`, `connected_ip`, `qos`, and `paths` are only populated when design artifacts are available. In hardware-only mode, elements contain only `name`, `type`, and `status`.

---

## Report Template (REPORT.md)

```markdown
# NoC Performance Monitor Report

**Device:** <part> | **Board:** <board> | **Date:** <timestamp>
**Skill:** hw-noc-perfmon v1.2.0-ea | **Maturity:** Early Access
**Design Context:** <pre-built | vivado | hardware-only>

## Measurement Method

- Method: direct ChipScoPy NocPerfmon
- ChipScoPy / cs_server: <versions>
- Traffic class: <class>
- Samples / actual period: <count> / <period ms>
- Validity: <valid | incomplete, with reason>

## Measured Performance

| Element | Read MB/s (min/avg/max) | Write MB/s (min/avg/max) | Latency counter values | Overflow |
|---------|--------------------------|---------------------------|------------------------|----------|
| <name> | <min/avg/max> | <min/avg/max> | <read/write values> | <yes/no> |

## Topology Summary

| Element Type | Total | Enabled | Disabled |
|-------------|-------|---------|----------|
| NMU | <n> | <n> | <n> |
| NSU | <n> | <n> | <n> |
| NPS | <n> | <n> | <n> |
| DDRMC | <n> | <n> | <n> |
| HBMMC | <n> | <n> | <n> |
| **Total** | **<n>** | **<n>** | **<n>** |

## Active Traffic Paths

- <n> NMU sources → <n> NPS switches → <n> NSU/DDRMC sinks
- DDRMC endpoints: <list>
- Disabled elements: <list or "none">

## IP Connectivity (if design artifacts available)

| NMU/NSU | Site | Connected IP | BW (MB/s) | Traffic Class |
|---------|------|-------------|-----------|---------------|
| nmu_0 | NOC_NMU512_X0Y0 | axi_dma_0/M_AXI | 4000 | best-effort |
| nsu_0 | NOC_NSU512_X0Y0 | ddr4_0/S_AXI | 4000 | best-effort |

## Routing Paths (if NCR available)

| Source | Switches | Destination |
|--------|----------|-------------|
| nmu_0 | NPS_0 → NPS_3 | ddrmc_0 |

## Observations

- <observation 1>
- <observation 2>

## MCP-Only Limitations

NPM counter streaming and bandwidth/latency measurement are not yet available
through ChipScoPy MCP. This report uses direct ChipScoPy NocPerfmon for
measurement and MCP for topology discovery. For error analysis, use the
hw-noc-debug skill.
```

---

## NoC Performance Metrics

Direct ChipScoPy exposes the following metrics now. A future MCP tool should
return the same measurement contract:

| Metric | Unit | Description |
|--------|------|-------------|
| Read Bandwidth | MB/s | Read throughput per NMU/NSU path |
| Write Bandwidth | MB/s | Write throughput per NMU/NSU path |
| Read Latency Counter | counter-derived value | Average read latency accumulator divided by burst count. Do not convert to time without documented device-specific evidence. |
| Write Latency Counter | counter-derived value | Average write latency accumulator divided by burst count. Do not convert to time without documented device-specific evidence. |
| Channel Utilization | % | NoC link utilization percentage |

### Clock Domains

| Domain | Description |
|--------|-------------|
| NPI | NoC Programming Interface clock |
| NoC | NoC interconnect clock (data plane) |
| MC | Memory controller clock |

### Sampling Periods

Supported sampling periods vary by device. Use `get_supported_sampling_periods()` (when available) to query.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| "No NoC performance monitor found" | Device is not Versal, or design has no NoC | Verify device family and design |
| Zero elements discovered | NoC core not scanned | Run `chipscope_scan(include=['noc'])` |
| Element shows "disabled" | Element unused in current design config | Expected — design-dependent |
| Connection refused | hw_server/cs_server not running | Start servers, verify URLs |
| "requires element_name" | Called read_registers without element_name | Run discover first to get names |
