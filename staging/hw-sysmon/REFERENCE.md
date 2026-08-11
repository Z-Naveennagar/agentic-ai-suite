<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# SysMon Health Check — Reference Data

## Nominal Supply Voltage Ranges

| Supply | Family | Nominal | Warning (±5%) | Critical (±10%) |
|--------|--------|---------|---------------|-----------------|
| VCCINT | 7 Series | 1.000V | 0.950–1.050V | 0.900–1.100V |
| VCCINT | US/US+ | 0.850V | 0.808–0.893V | 0.765–0.935V |
| VCCINT | Versal | 0.700–0.800V | varies by part | varies by part |
| VCCAUX | All | 1.800V | 1.710–1.890V | 1.620–1.980V |
| VCCBRAM | US+ | 1.000V | 0.950–1.050V | 0.900–1.100V |
| VUSER0-3 | US+ only | user-defined | user-defined | user-defined |

## Temperature Thresholds

| Condition | Status | Action |
|-----------|--------|--------|
| Temp < 70°C | GREEN | Normal operation |
| 70–85°C | YELLOW | Monitor closely; check cooling |
| 85–100°C | ORANGE | Reduce workload or improve cooling |
| ≥ 100°C | RED | Critical — approaching OT shutdown |
| OT alarm active | CRITICAL | Device at risk of damage |

## Overall Health Score (1-5)

```
5 = All temps GREEN, all supplies GREEN, no alarms
4 = Temps GREEN/YELLOW, supplies GREEN, no alarms
3 = Any YELLOW temps or supplies, no critical alarms
2 = Any ORANGE temps or supplies, or non-OT alarms active
1 = Any RED condition, OT alarm, or supply out of ±10%
```

## Alarm Threshold Register Map (UG580 — UltraScale/US+)

| Register | Address | Description | Alarm |
|----------|---------|-------------|-------|
| Temp Upper | 50h | Temperature alarm upper | ALM[0] |
| VCCINT Upper | 51h | VCCINT alarm upper | ALM[1] |
| VCCAUX Upper | 52h | VCCAUX alarm upper | ALM[2] |
| OT Upper | 53h | Over-temp upper (LSB[3:0]=0011 to activate) | OT |
| Temp Lower | 54h | Temperature alarm lower | ALM[0] |
| VCCINT Lower | 55h | VCCINT alarm lower | ALM[1] |
| VCCAUX Lower | 56h | VCCAUX alarm lower | ALM[2] |
| OT Lower | 57h | Over-temp lower | OT |
| VCCBRAM Upper | 58h | VCCBRAM alarm upper | ALM[3] |
| VCCBRAM Lower | 5Ch | VCCBRAM alarm lower | ALM[3] |
| VUSER0 Upper | 60h | User supply 0 upper (US+ only) | ALM[8] |
| VUSER1 Upper | 61h | User supply 1 upper (US+ only) | ALM[9] |
| VUSER2 Upper | 62h | User supply 2 upper (US+ only) | ALM[10] |
| VUSER3 Upper | 63h | User supply 3 upper (US+ only) | ALM[11] |
| VUSER0 Lower | 68h | User supply 0 lower (US+ only) | ALM[8] |
| VUSER1 Lower | 69h | User supply 1 lower (US+ only) | ALM[9] |
| VUSER2 Lower | 6Ah | User supply 2 lower (US+ only) | ALM[10] |
| VUSER3 Lower | 6Bh | User supply 3 lower (US+ only) | ALM[11] |

## Status Register Map (UG580 — address → sensor)

| Address | Sensor |
|---------|--------|
| 00h | Temperature |
| 01h | VCCINT |
| 02h | VCCAUX |
| 03h | VP/VN |
| 04h | VREFP |
| 05h | VREFN |
| 06h | VCCBRAM |
| 10h–1Fh | VAUXP[0:15]/VAUXN[0:15] |
| 20h | Max Temperature |
| 21h | Max VCCINT |
| 22h | Max VCCAUX |
| 24h | Min Temperature |
| 25h | Min VCCINT |
| 26h | Min VCCAUX |

## HW_SYSMON Properties (UG912)

**Read-only sensor properties:**
TEMPERATURE, TEMPERATURE_MAX, TEMPERATURE_MIN, TEMPERATURE_SCALE,
VCCINT, VCCINT_MAX, VCCINT_MIN, VCCAUX, VCCAUX_MAX, VCCAUX_MIN,
VCCBRAM, VCCBRAM_MAX, VCCBRAM_MIN, VPVN,
VUSER0, VUSER1, VUSER2, VUSER3 (US+ only),
VCC_PSINTLP, VCC_PSINTFP, VCC_PSAUX (Zynq US+ only)

**Alarm flag properties (read-only):**
FLAG.ALM0 (temp), FLAG.ALM1 (VCCINT), FLAG.ALM2 (VCCAUX), FLAG.ALM3 (VCCBRAM),
FLAG.ALM4 (VUSER0), FLAG.ALM5 (VUSER1), FLAG.ALM6 (VUSER2),
FLAG.OT, FLAG.JTGD (JTAG disable), FLAG.JTGB (JTAG busy), FLAG.REF (reference)

**Config properties (read-write):**
CONFIG_REG.OT, CONFIG_REG.ALM0–ALM6,
CONFIG_REG.SEQ (sequencer mode), CONFIG_REG.AVG (averaging),
CONFIG_REG.CH (channel selection), CONFIG_REG.PD, CONFIG_REG.BU,
CONFIG_REG.EC, CONFIG_REG.MUX, CONFIG_REG.ACQ

**Calibration (read-only):**
ADC_A_OFFSET, ADC_A_GAIN, ADC_B_OFFSET, ADC_B_GAIN, SUPPLY_OFFSET

## Recommendation Engine

| Condition | Severity | Recommendation |
|-----------|----------|---------------|
| FLAG.OT == 1 | CRITICAL | Reduce device activity immediately. Check heatsink/fan. |
| Temp > 100°C | CRITICAL | Approaching OT shutdown. Reduce clock frequency. |
| Temp > 85°C | HIGH | Verify heatsink contact, airflow, ambient temperature. |
| CONFIG_REG.OT == 1 (disabled) | HIGH | OT shutdown disabled. Enable: `set_property CONFIG_REG.OT 0 $s; commit_hw_sysmon $s` |
| Supply outside ±10% | CRITICAL | Check board power delivery, decoupling, regulator output. |
| Supply outside ±5% | HIGH | Supply rail marginal. Monitor under load. |
| VCCINT min < nominal - 5% | HIGH | VCCINT drooped. Check IR drop, decoupling capacitors. |
| Any alarm active | MEDIUM | Review threshold: `get_hw_sysmon_reg $s <addr>` |
| Temp max >> current | MEDIUM | Temperature spiked earlier. Review thermal design. |

## report_data.json Schema

```json
{
  "metadata": {
    "skill": "hw-sysmon", "version": "1.0.0",
    "timestamp": "<ISO8601>", "device": "<part>",
    "device_family": "versal|ultrascale-plus|ultrascale|7series|zynq-us-plus",
    "sysmon_description": "XADC|System Monitor", "temperature_scale": "Celsius"
  },
  "temperature": {
    "current": 45.2, "max_recorded": 67.1, "min_recorded": 23.4,
    "ot_threshold": 125.0, "margin_to_ot": 79.8, "status": "GREEN"
  },
  "supplies": [
    { "name": "VCCINT", "current": 0.851, "nominal": 0.850,
      "max_recorded": 0.862, "min_recorded": 0.840,
      "deviation_pct": 0.12, "status": "GREEN" }
  ],
  "alarms": {
    "ot_active": false, "ot_enabled": true, "active_alarms": [],
    "threshold_registers": {}
  },
  "calibration": { "adc_a_offset": "0x007e", "adc_a_gain": "0x0000" },
  "assessment": {
    "temperature_status": "GREEN", "supply_status": "GREEN",
    "alarm_status": "CLEAR", "overall_score": 5, "overall_status": "GREEN"
  },
  "recommendations": []
}
```

## REPORT.md Template

```markdown
# Device Health Check Report

**Device:** [part] | **Family:** [family] | **Date:** [timestamp]

## Executive Summary

| Metric | Value | Status |
|--------|-------|--------|
| Overall Health | X/5 | 🟢/🟡/🔴 |
| Die Temperature | XX.X °C | 🟢/🟡/🔴 |
| OT Margin | XX.X °C | ✅/⚠️/❌ |
| VCCINT | X.XXX V | 🟢/🟡/🔴 |
| VCCAUX | X.XXX V | 🟢/🟡/🔴 |
| Active Alarms | N | ✅/❌ |

## Supply Voltages
| Supply | Current | Nominal | Deviation | Min | Max | Status |
|--------|---------|---------|-----------|-----|-----|--------|

## Alarm Status
| Alarm | Status | Threshold |
|-------|--------|-----------|

## Recommendations
[Prioritized list]
```

## Tcl Command Quick Reference

| Command | Purpose |
|---------|---------|
| `get_hw_sysmons` | List SysMon objects on current device |
| `refresh_hw_sysmon $s` | Refresh all properties from hardware |
| `get_property TEMPERATURE $s` | Read formatted temperature |
| `get_property VCCINT $s` | Read formatted supply voltage |
| `get_hw_sysmon_reg $s 00` | Read raw register at hex address |
| `set_hw_sysmon_reg $s 50 <hex>` | Write alarm threshold register |
| `commit_hw_sysmon $s` | Commit property changes to hardware |
| `report_property -all $s` | List all properties on this SysMon |

## References

- **UG908**: Vivado Programming and Debugging — hw_sysmon Tcl commands
- **UG912**: Vivado Properties Reference — HW_SYSMON properties
- **UG835**: Vivado Tcl Commands Reference — get_hw_sysmons, refresh_hw_sysmon, get/set_hw_sysmon_reg
- **UG580**: UltraScale System Monitor User Guide — register map, alarms, SYSMONE1/E4
- **AM006**: Versal System Monitor Architecture Manual — PMC SysMon, Q8.7 format
- **UG480**: 7 Series XADC User Guide
- **UG1085**: Zynq UltraScale+ TRM Ch.9 — PS/PL SYSMON
