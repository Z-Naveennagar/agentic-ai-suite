<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Software Requirements Specification

## Target Context
- Board: ZCU102
- Hardware Input: XSA exported from the ZCU102 hardware design
- Target Processor: psu_cortexa53_0 (Cortex-A53 core 0)
- Target OS: baremetal (standalone)
- Target Domain: standalone_psu_cortexa53_0

## Functional Requirements
- [FR-001] Configure GPIO output pin `MIO17` and initialize it to low at boot.
- [FR-002] Configure GPIO input pin `MIO12` and poll at a 20 ms interval.
- On each valid rising edge on `MIO12`, toggle `MIO17` exactly once.
- Maintain a software counter `g_gpio_event_count` for accepted rising edges.

## Non-Functional Requirements
- [NFR-001] GPIO initialization shall complete within 200 ms of reset.
- Input-to-output toggle latency shall be <= 50 ms in steady state.
- CPU usage for GPIO polling shall remain below 10 percent on `psu_cortexa53_0`.

## Acceptance Criteria
- [AC-001] After boot, `MIO17` stays low until the first valid rising edge on `MIO12`.
- Given 10 clean rising edges on `MIO12`, `MIO17` toggles exactly 10 times.
- [AC-003] Pulses shorter than 40 ms are treated as bounce and ignored.
- `g_gpio_event_count` equals accepted rising-edge count after a 60 second run.
