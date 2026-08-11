<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# DDRMC Debug — Reference

## chipscope_ddr Tool Reference

### Actions

| Action | Key Parameters | Returns |
|--------|---------------|---------|
| `list` | — | DDR controller names and enabled state |
| `status` | `ddr_name` | Basic DDR status and info |
| `calibration` | `ddr_name` | Per-stage calibration PASS/FAIL |
| `health` | `ddr_name` | Health status and diagnostics |
| `report` | `ddr_name` | Comprehensive status report |
| `config` | `ddr_name` | Memory type, width, ranks, frequency |
| `stages` | `ddr_name` | Detailed per-stage calibration results |
| `margins` | `ddr_name` | Per-byte-lane calibration margins |
| `properties` | `ddr_name`, `property_group` | DDR property groups as JSON |
| `eye_scan` | `ddr_name`, `mode`, `steps`, `unit_index` | Run 2D eye scan |
| `eye_scan_data` | `ddr_name`, `output_format`, `export_path` | Get/export scan results |
| `eye_scan_defaults` | `ddr_name`, `mode` | Default VRef and scan settings |

### Eye Scan Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ddr_name` | string | null | DDR controller name (first if omitted) |
| `mode` | string | null | `'read'` or `'write'` |
| `pattern` | string | null | `'simple'`, `'complex'`, `'prbs23'`, `'prbs10'`, `'prbs7'` |
| `rank` | int | 0 | Memory rank 0-3 |
| `vref_min_pct` | float | null | Minimum VRef percentage |
| `vref_max_pct` | float | null | Maximum VRef percentage |
| `steps` | int | 15 | Number of VRef steps |
| `unit_index` | int | 0 | Nibble (read) or byte (write) index |
| `max_wait_minutes` | float | 5.0 | Scan timeout |

### chipscope_ddr_eye_scan Additional Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `edge` | string | `'rising'` | For read mode: `'rising'` or `'falling'` |
| `display` | string | `auto` | `'ascii'`/`'chat'`/`'app'`/`'both'` |

---

## Calibration Stages

### Stage Sequence

| # | Stage | Purpose | Key Metric |
|---|-------|---------|------------|
| 1 | **ZQ Calibration** | Output driver impedance calibration | PASS/FAIL |
| 2 | **Write Leveling** | Align DQS to CK at DRAM | DQS delay taps |
| 3 | **Read Gate Training** | Find DQS preamble window | Gate delay taps |
| 4 | **Read DQS Centering** | Center read data in DQS window | Left/right margin |
| 5 | **Write DQS Centering** | Center write data in DQS window | Left/right margin |
| 6 | **Read DQ Deskew** | Per-bit read timing alignment | Per-DQ delay |
| 7 | **Write DQ Deskew** | Per-bit write timing alignment | Per-DQ delay |
| 8 | **VRef Training** | Optimize receiver VRef voltage | VRef percentage |

### Calibration Failure Decision Tree

```
Calibration FAIL
├── Stage 1 (ZQ Cal) FAIL
│   ├── Check: ZQ pin connected to 240Ω resistor to GND?
│   ├── Check: VDD/VDDQ supply within spec?
│   └── Check: ZQ pin signal integrity
├── Stage 2 (Write Leveling) FAIL
│   ├── Check: CK/CK# routing matched to DQS?
│   ├── Check: Rank selection correct?
│   └── Check: Memory component spec for tDQSS
├── Stage 3 (Read Gate) FAIL
│   ├── Check: DQS preamble length setting
│   ├── Check: Board trace length DQS vs. CK
│   └── Check: Memory timing: tDQSCK
├── Stages 4-5 (DQS Centering) FAIL
│   ├── Check: Per-byte margin from `margins` action
│   ├── Check: Signal integrity (ISI, crosstalk)
│   └── Run eye scan on failing byte/nibble
├── Stages 6-7 (DQ Deskew) FAIL
│   ├── Check: Per-DQ routing skew on board
│   └── Check: DQ-to-DQS length matching
└── Stage 8 (VRef Training) FAIL
    ├── Check: VRef range adequate?
    └── Check: Noise on VRef supply
```

---

## Margin Interpretation

### Per-Byte Margin Fields

| Field | Description |
|-------|-------------|
| `total_margin` | Total calibration window in taps |
| `left_margin` | Left side margin (early) in taps |
| `right_margin` | Right side margin (late) in taps |
| `center_offset` | Offset from ideal center |

### Margin Health Assessment

| Total Margin | Assessment | Action |
|-------------|------------|--------|
| > 80 taps | Excellent | No action needed |
| 50-80 taps | Good | Monitor under temperature variation |
| 30-50 taps | Marginal | Investigate SI, consider board respin |
| < 30 taps | Critical | High risk of field failure |
| 0 taps | Failed | Calibration failed at this byte |

### Margin Asymmetry

| Left/Right Ratio | Interpretation |
|-------------------|---------------|
| 0.8-1.2 | Balanced — good centering |
| 0.5-0.8 or 1.2-2.0 | Moderate skew — check routing |
| < 0.5 or > 2.0 | Severe skew — SI issue |

---

## DDR Memory Types

| Type | Speed | Width | Versal Support |
|------|-------|-------|----------------|
| DDR4 | Up to 3200 MT/s | x8, x16, x32, x64, x72 (ECC) | All Versal |
| LPDDR4 | Up to 4267 MT/s | x16, x32 | Versal AI Edge |
| DDR5 | Up to 4800 MT/s | x4, x8, x32, x40 (ECC) | Versal Premium |
| LPDDR5 | Up to 6400 MT/s | x16, x32 | Versal AI Core |

---

## Eye Scan Interpretation

### Read Eye Scan

- **X-axis:** Timing delay (taps)
- **Y-axis:** VRef voltage (percentage)
- **Color:** Pass/fail at each (delay, VRef) point
- **Eye opening:** Largest pass region = margin available

### Write Eye Scan

- Similar to read but measures write path margin
- `unit_index` selects byte (not nibble) for write mode

### Scan Quality Settings

| Scenario | steps | pattern | max_wait |
|----------|-------|---------|----------|
| Quick check | 10 | simple | 3 min |
| Standard | 15 | prbs23 | 5 min |
| Thorough | 25 | prbs31 | 15 min |

---

## Report JSON Schema

```json
{
  "schema_version": "hw-ddrmc-debug/1.0.0",
  "timestamp": "2026-05-01T12:00:00Z",
  "device": { "part": "...", "dna": "..." },
  "controllers": [
    {
      "name": "ddr_0",
      "enabled": true,
      "config": {
        "memory_type": "DDR4",
        "width": "x72",
        "ranks": 2,
        "speed_mt_s": 3200,
        "capacity_gb": 16
      },
      "calibration": {
        "overall": "PASS",
        "stages": [
          { "name": "ZQ Calibration", "status": "PASS" },
          { "name": "Write Leveling", "status": "PASS" }
        ]
      },
      "margins": {
        "bytes": [
          { "index": 0, "total": 68, "left": 35, "right": 33 },
          { "index": 3, "total": 42, "left": 18, "right": 24 }
        ],
        "weakest_byte": 3,
        "weakest_margin": 42
      }
    }
  ],
  "eye_scans": [],
  "recommendations": []
}
```

---

## Report Template (REPORT.md)

```markdown
# DDRMC Debug Report

**Device:** <part> | **Date:** <timestamp>

## Controller Summary

| Controller | Type | Config | Speed | Cal Status |
|-----------|------|--------|-------|------------|
| ddr_0 | DDR4 | x72 ECC | 3200 MT/s | PASS |

## Calibration Stages — ddr_0

| Stage | Status |
|-------|--------|
| ZQ Calibration | PASS |
| Write Leveling | PASS |
| ... | ... |

## Per-Byte Margins — ddr_0

| Byte | Total | Left | Right | Assessment |
|------|-------|------|-------|------------|
| 0 | 68 | 35 | 33 | Good |
| 3 | 42 | 18 | 24 | Marginal |

## Recommendations

1. <recommendation>
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| No DDR cores | Design has no DDRMC | Verify bitstream includes DDRMC |
| All stages FAIL | No memory connected | Check DIMM/component seating |
| ZQ Cal FAIL only | ZQ resistor missing | Check board for 240Ω to GND |
| Random stage failures | Voltage/temp marginal | Check VCCINT, VCC_DDR with sysmon |
| Eye scan empty | Calibration not complete | Fix calibration first |
| Inconsistent margins | Temperature variation | Run at controlled temperature |
