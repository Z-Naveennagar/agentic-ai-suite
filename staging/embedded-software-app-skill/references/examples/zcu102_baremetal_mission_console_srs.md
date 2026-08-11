<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Software Requirements Specification

## Project Overview
Project name: ZCU102 Mission Console
Target board: AMD ZCU102
Execution model: Bare-metal (no RTOS)
Hardware source: Standard ZCU102 XSA export without custom Vivado PL implementation

Concept:
Build a command-driven mission-console firmware that turns the board into a small telemetry appliance. Over UART, a user can issue commands to inspect system health, run timed diagnostics, and stream a compact status frame at fixed intervals.

## Assumptions and Constraints
- [FR-000] The solution shall use only capabilities available from a standard ZCU102 XSA (PS-centric flow, no custom AXI PL IP required).
Owner: System Architect
Priority: P0
Verification: analysis

- [FR-001] The application shall target Cortex-A53 in standalone bare-metal mode.
Owner: Embedded Lead
Priority: P0
Verification: build

- [FR-002] The application shall not require Vivado re-implementation, bitstream regeneration, or hardware design edits.
Owner: System Architect
Priority: P0
Verification: review

## Functional Requirements
- [FR-101] On boot, the application shall initialize platform services, UART console I/O, timer services, and interrupt controller services.
Owner: Firmware
Priority: P0
Verification: test

- [FR-102] The application shall print a startup banner with build metadata (project name, build profile, compile date/time, selected CPU/domain).
Owner: Firmware
Priority: P1
Verification: test

- [FR-103] The application shall expose a UART command shell supporting: `help`, `status`, `diag run`, `diag last`, `stream on`, `stream off`, `uptime`, and `reset stats`.
Owner: Firmware
Priority: P0
Verification: test

- [FR-104] The `status` command shall report heartbeat counter, interrupt count, shell command count, error count, and uptime in milliseconds.
Owner: Firmware
Priority: P1
Verification: test

- [FR-105] The firmware shall run a 1 Hz heartbeat task driven by a timer interrupt and increment a heartbeat counter.
Owner: Firmware
Priority: P0
Verification: test

- [FR-106] The `diag run` command shall execute a deterministic diagnostic sequence including UART loopback-style transmit/receive check (software-level), timer latency sample, and basic memory pattern check over a bounded RAM buffer.
Owner: Firmware
Priority: P0
Verification: test

- [FR-107] The application shall store the latest diagnostic result in memory and make it available via `diag last`.
Owner: Firmware
Priority: P1
Verification: test

- [FR-108] When `stream on` is enabled, the firmware shall emit one telemetry line every 500 ms over UART containing uptime, heartbeat, last diagnostic status, and a rolling sequence number.
Owner: Firmware
Priority: P1
Verification: test

- [FR-109] The command parser shall reject unknown commands safely and return a clear error message without crashing or hanging.
Owner: Firmware
Priority: P0
Verification: test

- [FR-110] The firmware shall maintain an in-memory error/event ring buffer with at least 32 entries and expose the latest 5 entries in `status` output.
Owner: Firmware
Priority: P1
Verification: test

- [FR-111] The application shall include a compile-time option to build in `debug` or `release` mode with behavior differences documented in logs.
Owner: Firmware
Priority: P2
Verification: build

## Non-Functional Requirements
- [NFR-001] Boot banner shall appear within 2 seconds after reset under normal board startup conditions.
Owner: Systems
Priority: P1
Verification: test

- [NFR-002] Heartbeat jitter shall remain within +/- 20 ms for 95% of 1 Hz intervals over a 2-minute run.
Owner: Systems
Priority: P1
Verification: analysis

- [NFR-003] Command response latency for `help`, `status`, and `uptime` shall be under 100 ms for 95% of invocations.
Owner: Systems
Priority: P1
Verification: test

- [NFR-004] The firmware shall be resilient to malformed UART input up to 256 bytes and continue operating without reset.
Owner: Systems
Priority: P0
Verification: test

- [NFR-005] The implementation shall avoid undefined behavior and perform explicit return-code checks for all BSP/driver calls used by the app.
Owner: Quality
Priority: P0
Verification: review

- [NFR-006] The solution shall compile cleanly with no fatal errors and no unresolved symbols in the selected Vitis toolchain.
Owner: Quality
Priority: P0
Verification: build

## Acceptance Criteria
- [AC-001] Build succeeds in Vitis for standalone Cortex-A53 domain with generated sources and project settings.
Owner: QA
Priority: P0
Verification: build

- [AC-002] Serial console shows startup banner and command prompt after boot.
Owner: QA
Priority: P0
Verification: test

- [AC-003] Running `help` lists all required commands from FR-103.
Owner: QA
Priority: P0
Verification: test

- [AC-004] Running `diag run` followed by `diag last` reports a timestamped PASS/FAIL result and measured values.
Owner: QA
Priority: P0
Verification: test

- [AC-005] With `stream on`, at least 10 telemetry lines are emitted in 6 seconds and sequence numbers increase monotonically.
Owner: QA
Priority: P1
Verification: test

- [AC-006] Unknown commands return a controlled error message and the prompt remains responsive.
Owner: QA
Priority: P0
Verification: test

- [AC-007] `status` output includes heartbeat, uptime, interrupt count, error count, and recent events.
Owner: QA
Priority: P1
Verification: test

- [AC-008] If diagnostics fail, failure reason is logged in the event ring buffer and shown in `diag last`.
Owner: QA
Priority: P1
Verification: test

## Out of Scope
- Linux kernel driver development.
- FreeRTOS migration.
- Custom PL peripheral integration requiring Vivado hardware edits.
- Network stack features (lwIP) unless explicitly requested in a future revision.
