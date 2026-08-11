<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Elaboration Resolution Guides

Per-message fix references for Vivado synthesis elaboration (`[Synth 8-XXX]`).
Each guide provides the Vivado message pattern, root cause analysis, fix options
with before/after code examples, and verification steps.

## How to Use

When processing an elaboration message:

1. Look up the `msg_id` in the table below
2. Load the matching guide with `read_file`
3. Follow fix instructions, replacing placeholders with actual design names
4. Include the rationale in the generated report

## Individual Guides

Complex messages with multiple root cause patterns warranting dedicated files.

| Guide | Message IDs | Severity | Description |
|-------|------------|----------|-------------|
| [VLOG-128](VLOG-128.md) | 128 | ERROR | Undeclared identifier — 4 root cause patterns |
| [VLOG-133](VLOG-133.md) | 133 | ERROR | Net on LHS of procedural assignment |
| [VLOG-134](VLOG-134.md) | 134 | ERROR | Variable on LHS of continuous assignment |
| [VLOG-511](VLOG-511.md) | 511, 519, 577, 731, 767 | ERROR | Named port/field/generic not found |
| [VLOG-564](VLOG-564.md) | 564, 758, 585 | WARNING | Incomplete sensitivity list |
| [VLOG-566](VLOG-566.md) | 566 | WARNING | Latch inference — 4 patterns |
| [VLOG-637](VLOG-637.md) | 637, 823 | CRITICAL | Dual driver / driven twice |
| [VLOG-645](VLOG-645.md) | 645 | WARNING | Blocking vs non-blocking mix |
| [VHDL-747](VHDL-747.md) | 747, 790 | WARNING | Missing case choices |
| [VHDL-759](VHDL-759.md) | 759, 514, 781, 760, 857 | ERROR | Width mismatch in assignments |
| [VHDL-833](VHDL-833.md) | 833, 546, 768, 771 | ERROR | Unknown/unresolved identifier |

## Grouped Guides

Messages sharing a common fix pattern, collected into a single file.

| Guide | Message IDs | Description |
|-------|------------|-------------|
| [declaration](declaration.md) | 126, 129, 131, 599, 615, 624, 636, 841, 856 | Declaration and scope errors |
| [port-connection](port-connection.md) | 142-145, 510, 512-513, 596-598, 602, 649 | Port connection issues |
| [case-statement](case-statement.md) | 150, 506-508, 746, 750, 814, 838, 849 | Case statement issues |
| [type-mismatch](type-mismatch.md) | 576, 580, 583, 591-592, 608, 793-794, 839 | Type and interface mismatch |
| [range-index](range-index.md) | 547-549, 742, 745, 766, 769, 803, 825, 869 | Range and index errors |
| [constant-expr](constant-expr.md) | 530, 544-545, 570, 579, 647-648, 744 | Constant expression errors |
| [generate-loop](generate-loop.md) | 581, 630 | Generate and genvar issues |
| [clock-edge](clock-edge.md) | 560-563 | Clock edge and event control issues |

## Adding New Guides

Create `<VLOG-XXX>.md` or `<VHDL-XXX>.md` (individual) or `<topic>.md` (grouped) with:

1. **Vivado Message** — exact `[Synth 8-XXX]` pattern
2. **Root Cause** — why Vivado emits this
3. **Fix Options** — before/after code in diff format
4. **Validation** — how to verify the fix works
5. **References** — UG901/IEEE standards

See any existing guide as a template.
