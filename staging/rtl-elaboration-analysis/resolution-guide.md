<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Resolution Guide Integration

This file explains the resolution guide system and how to use it when processing
elaboration messages.

---

## Overview

Resolution guides are pre-written, validated fix templates for known message types.
They live in `resolution/` and provide:

- **Consistency** — Same message type always gets the same fix pattern
- **Accuracy** — Fixes validated against IEEE standards and Xilinx documentation
- **Completeness** — Includes rationale, multiple fix options, and verification
- **Speed** — Pre-written templates reduce analysis time

---

## File Organization

```
resolution/
├── VLOG-128.md          # Undeclared identifier (complex, multi-pattern)
├── VLOG-133.md          # Net on LHS of procedural
├── VLOG-134.md          # Variable on LHS of continuous
├── VLOG-511.md          # Named port doesn't exist
├── VLOG-564.md          # Incomplete sensitivity list (covers VHDL-758)
├── VLOG-566.md          # Latch inference
├── VLOG-637.md          # Dual driver
├── VLOG-645.md          # Blocking/non-blocking mix
├── VHDL-747.md          # Missing case choices
├── VHDL-759.md          # Width mismatch (covers VLOG-514, VHDL-781)
├── VHDL-833.md          # Unknown identifier (covers VHDL-768)
├── sensitivity-list.md  # Grouped: 564, 758, 585, 560-563
├── declaration.md       # Grouped: 126, 129, 131, 599, 624, 636
├── port-connection.md   # Grouped: 142-145, 512-513, 596-598, 649
├── case-statement.md    # Grouped: 150, 506-508, 746, 750, 814, 790
├── type-mismatch.md     # Grouped: 576, 580, 583, 793-794
├── range-index.md       # Grouped: 547-549, 742, 745, 769, 869
├── constant-expr.md     # Grouped: 530, 570, 579, 744, 647-648
└── generate-loop.md     # Grouped: 581, 630
```

---

## Available Guides

### Individual Guides (Complex Multi-Pattern)

| Guide | Covers IDs | Description |
|-------|-----------|-------------|
| VLOG-128 | 128 | Undeclared identifier — 4 root cause patterns |
| VLOG-133 | 133 | Net on LHS of procedural assignment |
| VLOG-134 | 134 | Variable on LHS of continuous assignment |
| VLOG-511 | 511, 519, 577, 731, 777, 730, 767 | Named port/field/generic not found (typo detection) |
| VLOG-564 | 564, 758, 585 | Incomplete sensitivity list |
| VLOG-566 | 566 | Latch inference — 4 patterns |
| VLOG-637 | 637, 823 | Dual driver / driven twice |
| VLOG-645 | 645 | Blocking vs non-blocking mix |
| VHDL-747 | 747, 790 | Missing case choices |
| VHDL-759 | 759, 514, 781, 760, 761, 857, 867 | Width mismatch in assignments |
| VHDL-833 | 833, 546, 768, 771, 617 | Unknown/unresolved identifier |

### Grouped Guides (Shared Fix Patterns)

| Guide | Covers IDs | Description |
|-------|-----------|-------------|
| declaration | 126, 129, 131, 599, 615, 624, 636, 841, 856 | Declaration errors |
| port-connection | 142-145, 510, 512-513, 596-598, 602, 649, 631, 646 | Port connection issues |
| case-statement | 150, 506-508, 746, 750, 814, 838, 849 | Case statement issues |
| type-mismatch | 576, 580, 583, 591-592, 608, 622, 793-794, 839, 840 | Type/interface mismatch |
| range-index | 547-549, 742, 745, 766, 769, 803, 806, 825, 827, 869 | Range/index errors |
| constant-expr | 530, 544-545, 570, 579, 647-648, 744 | Constant expression errors |
| generate-loop | 581, 630 | Generate/genvar issues |

---

## Mandatory Workflow (Per Message)

```
1. Parse log — extract [Synth 8-XXX] messages
2. For each message ID:
   a. Check for individual guide: resolution/VLOG-XXX.md or VHDL-XXX.md
   b. If no individual guide, check grouped guides (use table above)
   c. If guide EXISTS:
      - Load with read_file
      - Follow fix recommendations
      - Use code templates (replace placeholders with actual design names)
      - Include rationale in report
   d. If NO guide exists:
      - Use message-handlers.md dispatch table for fix strategy
      - Apply general pattern from "Detailed Handler Instructions"
3. Always read the RTL source at reported file:line before generating a fix
4. Never fabricate code — only propose fixes based on actual source context
```

---

## Naming Convention

- Individual: `resolution/<LANG>-<ID>.md` (e.g., `VLOG-128.md`, `VHDL-833.md`)
- Grouped: `resolution/<category>.md` (e.g., `declaration.md`, `range-index.md`)
- Required sections: Vivado Message, Root Cause, Fix Options, Validation
