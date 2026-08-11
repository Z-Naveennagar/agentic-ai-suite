<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# FPGA and Adaptive SoC multi-agent flow for Codex

This is an alpha, customer-evaluation bundle for turning a guided design request into RTL, verification evidence, a routed Vivado design, and—when authorized—hardware-validation evidence. Eleven Codex agents work through explicit, independently checked handoff gates. Each gate records why work ran, exact inputs, actions, decisions, outputs, file changes, side effects, uncertainty, approval state, and a deterministic PASS/BLOCKED/FAIL verdict.

The bundle lives under `staging` because its contracts and transparency model are mature enough for controlled evaluation, while portability and unattended campaign behavior still need broader validation. It has been exercised with Codex CLI 0.145.0, an inherited frontier model, Vivado/Vitis 2025.2, Verilator 5.050, and cocotb 2.0.1. Other agent runtimes have not been validated.

## What is included

- `.codex/agents/`: eleven project-scoped Codex agent definitions.
- `workflow.json`: routing, ownership, approval, and concurrency policy.
- `contracts/`: strict schemas for requirements, architecture, source, verification, implementation, Vitis, hardware validation, handoffs, and gate receipts.
- `skills/`: the six flow-specific skills. Published and staging suite skills are discovered read-only from the repository.
- `scripts/gate_runner.py`: independent transition checks and user-readable gate reports.
- `scripts/v0_1_runner.py`: run initialization, artifact finalization, validation, scoring, and conditional Vitis execution.
- `evals/designs/`: two Basys 3 cases and an ordered 50-case KV260 evaluation suite with independent testbenches and hardware-test plans.
- `hardware/`: reusable debug gates and example target profiles.

The architecture and operating rules are detailed in [AGENT_ARCHITECTURE_v0.1.md](AGENT_ARCHITECTURE_v0.1.md), [ARTIFACT_OWNERSHIP_v0.1.md](ARTIFACT_OWNERSHIP_v0.1.md), [CUSTOMER_GUIDANCE_STANDARD_v0.1.md](CUSTOMER_GUIDANCE_STANDARD_v0.1.md), and [HARDWARE_VALIDATION_STANDARD_v0.1.md](HARDWARE_VALIDATION_STANDARD_v0.1.md).

## Set up and validate

From this directory:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
source env.sh
python3 scripts/validate_prototype.py
python3 scripts/v0_1_runner.py self-test
```

Vivado, Vitis, `v++`, Codex, and Verilator must be installed and discoverable on `PATH`. See [COMPATIBILITY.md](COMPATIBILITY.md) for the validated environment and current limitations.

## Start a guided design

Review the available cases, then run one through the gated flow:

```bash
python3 scripts/v0_1_runner.py list
python3 scripts/v0_1_runner.py run --case basys3_pulse_counter
```

The runner preserves the request under `runs/<request_id>/`, gives each agent a bounded work package, and creates JSON plus Markdown receipts under `runs/<request_id>/gates/`. The default `exception_approval` mode advances through clean PASS gates and pauses for material changes, waivers, hardware actions, or non-PASS results. Use `--assurance-mode approve_every_gate` for a fully supervised first customer run.

Inspect and validate the audit chain with:

```bash
python3 scripts/gate_runner.py validate --run runs/<request_id>
python3 scripts/gate_runner.py render runs/<request_id>/gates/<receipt>.json
```

Programming hardware, resetting a target, or driving VIO always requires explicit user authorization. A routed bitstream is `design_complete`; it is not `hardware_qualified` until a matching target run produces a PASS `hardware-validation-result.json` with target identity, probes, captures, observations, and cleanup evidence.

## Evaluation suites

The two small Basys 3 reference designs have passed independent cocotb/Verilator tests and Vivado synthesis, placement, routing, signoff checks, and bitstream generation. The KV260 suite provides 50 progressively harder cases and can be inspected or run with:

```bash
python3 scripts/kv260_suite.py list
python3 scripts/kv260_suite.py validate
python3 scripts/kv260_suite.py self-test
python3 scripts/kv260_suite.py run
```

Do not interpret the presence of 50 cases as 50 successful routed designs. The latest unattended five-case campaign was blocked before specification by the host's nested sandbox/network-namespace setup. No design result was produced by that campaign. This is recorded as an alpha limitation rather than design failure.

## Release status

Version: `0.2.0-alpha.1`. This snapshot is intended for revision-controlled review and guided customer trials, not an unattended production claim. See [CHANGELOG.md](CHANGELOG.md) for the packaged changes.
