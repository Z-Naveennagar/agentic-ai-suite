<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Vivado MCP Policy

## Session ownership

Maintain one lock per `session_id`. An agent must acquire the lock before `vivado_execute` and release it after the bounded operation. Status, documentation, log, and history tools may run independently when supported, but never overlap Tcl execution on the same session.

## Required patterns

- Discover sessions before connecting or starting Vivado.
- Default to Tcl mode; use GUI only on explicit user request.
- Keep project opening, checkpoints, long design commands, run launches, waits, and bitstream generation as standalone calls.
- Pair `launch_runs` and `wait_on_run`.
- Poll long commands every 30 to 60 seconds.
- Preserve full logs for failures even when the model receives a digest.
- Use documentation search before unfamiliar commands or remedies.

## Mutation levels

| Level | Examples | Policy |
|---|---|---|
| Read-only | project properties, reports, status, history | allowed in all modes |
| Reversible project mutation | add source, set top, create run | require `repair` or `regression` mode |
| Source or constraint edit | RTL, XDC, Tcl | owning source agent only |
| Expensive execution | synthesis, implementation | require validated inputs and budget |
| Hardware action | program device, drive VIO | require explicit user authorization |

For hardware-qualified runs, treat `.bit`/`.pdi`, `.ltx`, and the debug map as
one immutable build set. Use Hardware Manager through Vivado MCP for JTAG,
VIO, and ILA. Bound all capture waits and restore safe VIO values during
cleanup.

Never use a timing exception only to change a report outcome. Tie every constraint to specification intent and design structure.
