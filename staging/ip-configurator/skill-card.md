<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# IP Configurator

**Description:** Configures any Vivado IP block from a natural-language intent by grounding parameters in documentation, applying them in one dict, then verifying against the live cell and recovering from Vivado's own error feedback.

**Owner:** AMD AECG

**License:** MIT

## Scope

Takes a customer-phrased request ("a 4-lane MIPI CSI-2 receiver at 1500 Mbps, RAW12, all
virtual channels") and produces the `set_property -dict` that realizes it, without a
pre-built parameter database. Parameter names come from doc search and from Vivado's
rejection messages, so the skill works on IP it has never seen.

Two properties distinguish it from a lookup table:

- **It verifies what it built.** After applying a dict it re-reads the cell, because Vivado
  accepts writes that do nothing: an unknown `CONFIG.*` key in a block design raises only a
  non-fatal critical warning, and a gated attribute such as `RESET_TYPE` reads back cleanly
  while its enabling flag `USE_RESET` stays false and the promised port never appears.
- **It reports its own coverage.** Every run emits a requirement ledger marking each phrase
  in the prompt as applied or unapplied-and-why, so a partial result is legible instead of
  looking like a success.

## Dependencies

- Vivado with an open block design, reachable over the Vivado MCP server
  (`vivado_execute`, `vivado_doc_search`, `vivado_log_messages`).
- `lib/ipcfg.tcl` sourced once per session; `lib/ipcfg_cache.py` for the learned-parameter
  cache described in `cache/README.md`.

## Evaluation

Graded by the `ip-configurator` test kit: 32 customer-phrased cases drawn from a RAVE2
SAPPHIRE Versal AI Edge Gen2 design (`xc2ve3558-sfva1440-2MP-e-S`), scored by reading the
as-built design back out of Vivado rather than trusting the agent's self-report. Cases span
AXI peripherals, clocking, MIPI/video, PCIe, RFDC, the Versal NoC and CIPS.

Measured on Vivado 2026.1 via the Cursor CLI: **31/32 with Opus 5, 30/32 with Composer 2.5.**
The remaining failures are parameters Vivado only exposes once an IP is instantiated through
device or board automation, not gaps in the doc-driven flow.

The kit is not shipped in this directory on purpose. Its `test_cases.yaml` holds the answer
key, and this skill instructs the agent to read its own directory, so co-locating the two
would let a graded run read the answers. It lives with the evaluation harness instead:
`tests/ip-configurator/ip-configurator_gen/`.
