<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Compatibility and alpha limitations

## Validated configuration

- Codex CLI 0.145.0 with the model inherited from the parent invocation
- Vivado and Vitis 2025.2; Vivado MCP server 0.6.9
- Verilator 5.050 and cocotb 2.0.1
- Python 3 with jsonschema 4.26.0, PyYAML 6.0.3, and pytest 9.x

The repository may support newer AMD tool releases elsewhere. This alpha snapshot records the environment in which this specific flow was evaluated; it does not yet claim cross-version qualification.

## Known limitations

- Only the Codex runtime has been validated. The contracts are provider-neutral, but other agent runtimes need their own package and evaluation.
- A recent five-case unattended campaign was blocked before specification because nested Codex processes could not create a loopback interface in the host sandbox. Preflight did not detect that effective nested restriction.
- That infrastructure blockage exposed campaign-reporting gaps: it was summarized as a case failure and a generated run-status file could remain `RUNNING` after the parent process exited. Treat process liveness and gate receipts as authoritative until those classifications are hardened.
- The 50 KV260 cases are an evaluation corpus, not a claim that all 50 have passed place and route or hardware validation.
- Hardware-qualified status requires an authorized run on a matching physical target. Simulation and implementation evidence alone do not establish board-level success.
