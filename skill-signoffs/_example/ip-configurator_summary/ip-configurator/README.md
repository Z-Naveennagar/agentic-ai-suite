<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# IP Configurator -- Usage Guide

## What This Skill Does

Turns a plain-language description of what you want an IP to do into the
`set_property -dict` that actually does it, then proves the IP came out that way.

There is no parameter database behind it. Parameter names come from AMD documentation and
from Vivado's own rejection messages, so the skill works on IP it has never seen and on IP
whose parameters changed between releases.

The reason it verifies rather than just applies: **Vivado accepts writes that do nothing.**

- An unknown `CONFIG.*` key in a block design does not throw. It raises a non-fatal
  `CRITICAL WARNING [BD 41-1276]`, `catch` returns 0, and a script that trusts the exit
  status reports success on a parameter that was ignored.
- A gated attribute reads back cleanly while the feature stays off. Set `RESET_TYPE` without
  `USE_RESET` and the value sticks, the read-back agrees, and the reset pin never appears.

So every run re-reads the cell, checks that each key exists and stuck, checks that enabling
flags are on, and reports coverage per phrase of your prompt.

## Prerequisites

- **Vivado** with a project open and a **block design open** (the skill operates on
  `get_bd_cells`; there is a standalone `create_ip` fallback for parameters that only exist
  outside IPI).
- **Vivado MCP Server** — see [docs/reference/vivado-mcp-tools.md](../../docs/reference/vivado-mcp-tools.md).
  The skill uses exactly three tools: `vivado_doc_search`, `vivado_execute`, and
  `vivado_log_messages`.
- An agent that supports skills (Claude Code, Cursor, or the Copilot/VS Code integration).

Validated on **Vivado 2026.1**. Goldens are version-keyed because the IP catalog changes
between releases.

## Installation

This skill is in `staging/`, so copy it directly:

```bash
cp -r staging/ip-configurator ~/.claude/skills/
```

Once it is promoted to `skills/`, the standard installer applies:

```bash
npx skills add . --skill ip-configurator
```

## How to Use It

Just describe the IP you want. The skill triggers on ordinary engineering language — you do
not name it, and you do not describe its protocol.

```
Add an AXI GPIO to the block design with a 12-bit output-only channel,
all outputs, plus a second 4-bit input channel with interrupts enabled.
```

```
I need a MIPI CSI-2 RX subsystem over D-PHY for a 4-lane camera: 4 active
lanes, 4 pixels per clock, RAW12, all virtual channels, 4096 line-buffer
depth, active-lanes detection and user-data-type filtering on, ISP bridge
and register interface on, 1500 Mbps line rate.
```

```
Configure the clocking wizard for a 100 MHz input and three outputs at
200, 150 and 74.25 MHz, with an active-low synchronous reset and a
locked output.
```

### Operating modes

Say which one you want at the start of the session; otherwise it assumes `unattended`.

| Mode | Use when | Behaviour |
|---|---|---|
| `unattended` (default) | Scripted, CI, or batch runs | Never asks. Makes the documented best choice and records the assumption in its ledger. Minimizes MCP calls. |
| `interactive` | You are working turn by turn | May ask clarifying questions when doc search is inconclusive, and will use Block Automation and Configurable Example Designs to flesh out the design. |

The default is deliberate: a question nobody answers stalls a batch run until it times out,
whereas a recorded assumption is always recoverable.

### What you get back

Every run reports coverage. When something could not be applied, the skill quotes the exact
phrase from your prompt and names the reason rather than quietly grading itself down:

```
I could not fully parameterize axi_noc2 from the prompt.
Applied: NUM_SI=0, NUM_MI=0, NUM_NSI=2, NUM_CLKS=0.
Could NOT apply: "4 memory controllers (NUM_MC)" because integration-derived.
```

Reasons are drawn from a fixed set: `runtime-register-only`, `integration-derived`,
`gated-no-enabler`, `not-a-config-param`, `value-out-of-range`, `wrong-ip-for-capability`.
The overall result is graded `full`, `full_standalone`, `partial`, `negative`, or
`creation_only`.

### Part swaps are guarded

Many IPs exist only on certain device families. Swapping the part on a design that already
has cells is destructive, so `ipcfg::ensure_part` refuses and returns `WARN:SWAP_BLOCKED`.
In `interactive` mode it asks you first; in `unattended` mode it will only swap on an
otherwise-empty block design, and restores the original part afterwards.

### The helper library

`lib/ipcfg.tcl` holds the repetitive Tcl — availability gating, create, dict-plus-verify,
enabler checks, stub connections, cleanup. Source it once per session, after a block design
is open. The skill does this itself; you only need to know it exists if you are reading the
transcripts.

`cache/learned_params.json` ships empty. It accumulates *where a feature lives*
(`feature → CONFIG.PARAM`) as the skill earns that mapping at runtime, which stops it
re-deriving the same lookup every run. It never stores a parameter *value*, so it cannot
leak an expected answer. Delete it to reset; see [cache/README.md](cache/README.md).

## Latest Test Results

32 customer-phrased cases over a RAVE2 SAPPHIRE Versal AI Edge Gen2 design
(`xc2ve3558-sfva1440-2MP-e-S`), spanning AXI peripherals, clocking, MIPI and video, PCIe,
RFDC, the Versal NoC and CIPS.

Grading reads the **as-built design back out of Vivado** and compares that to the golden
config. The agent's own claim of success is not part of the score.

**Run date 2026-07-29 · Vivado 2026.1 · Cursor CLI · one rep per case**

| | Opus 5 | Composer 2.5 |
|---|---:|---:|
| Cases passed | **31 / 32** | **30 / 32** |
| Failing cases | 21 | 17, 29 |
| Agent time, total | 102.2 min | 56.1 min |
| Agent time, median per case | 159 s | 59 s |
| Tokens, total | 44.1 M | 37.4 M |
| Cost | $50.85 | $8.77 |
| Cost per passing case | $1.640 | $0.292 |

Run ids `6a853663` (`claude-opus-5-thinking-high`) and `27415dc3` (`composer-2.5`).

### The three failures

Each one is a near miss on a single field, and each is instructive:

- **Case 21, Opus 5** — MIPI CSI-2 D-PHY. 13 of 14 fields matched; `CONFIG.C_PHY_MODE` was
  never set. The parameter is genuinely settable and the same case passes on a rerun, so
  this is sampling variance rather than a capability gap. It is the one case in the kit
  known to be unstable.
- **Case 17, Composer 2.5** — clocking wizard. 5 of 6 fields matched; `CONFIG.USE_RESET` was
  missing. `RESET_TYPE` was set without its enabling flag, so the value stuck, the read-back
  agreed, and the design had no reset pin. This is exactly the inert-write class described
  above, caught by the read-back rather than by Vivado.
- **Case 29, Composer 2.5** — Versal CIPS. 4 of 5 fields matched; `CONFIG.MDB5_GT` was
  written as `PCIe0x2_10GbE` where the legal enum is `PCIe0_x2_10GbE`. Vivado accepted the
  malformed value without validating it.

### Reading the cost figures

Cost is recomputed from recorded token counts against the current rate card, not taken from
the value stored at run time — early rows were written before the rate card carried Opus 5
and are understated by roughly 20×. Cache traffic dominates both bills: reads and writes are
about 82% of the Opus 5 total and 78% of Composer's. The gap is a rate-card difference, not
an efficiency one, since Opus 5 consumed only about 18% more tokens.

Figures exclude the Cursor Token Rate surcharge, which applies to third-party models on
Teams and Enterprise plans and is waived on first-party models. Including it widens the gap
rather than scaling both sides.

A third client, Sonnet 4.5 under `opencode`, scored 22/32 on the same kit, but that CLI does
not report token usage — it recorded about 900 tokens per case against a realistic 1 M — so
its cost is not comparable to the two above and is omitted.

## Re-running the Evaluation

The eval kit is deliberately **not** in this directory. Its `test_cases.yaml` is the answer
key, and this skill instructs the agent to read files in its own directory, so shipping the
two together would let a graded run read the answers.

It lives with the harness at
`tests/ip-configurator/ip-configurator_gen/`, alongside the runner and
grader specs.

## Limitations

- **Some parameters are unreachable by design.** The Versal NoC's memory-controller identity
  (`NUM_MC`, `NUM_MCP`, the `DDRMC5_CONFIG` sub-dictionary) only becomes valid once the NoC
  is instantiated as an integrated memory controller through device or board automation. On
  a bare PL NoC cell those keys stay gated, and the skill reports them
  `unapplied:integration-derived` instead of pretending otherwise.
- **Widths that are read-only on the boundary port are connection-derived.** The skill can
  drive a stub port so the cell adopts a connected width, but where that fails it grades
  `partial` and records the value under `runtime_params`.
- **Two Tier-2 retries, then it escalates.** It will not grind indefinitely on an error.
- **A block design must be open.** The standalone `create_ip` path exists only as a fallback
  for parameters unavailable in IPI.
