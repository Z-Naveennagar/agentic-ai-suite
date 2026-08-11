<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Versal RTL Design Advisories — Resolution Guides

Per-check fix references for the versal-rtl-design-advisories skill. Each file provides the
root cause, RTL patterns to detect, before/after code examples, validation commands, and
the source Jira CR.

## Available Guides

### DSP Inference

| Check | Severity | Description | Fix |
|-------|----------|-------------|-----|
| [dsp-pattern-detect](dsp-pattern-detect.md) | HIGH | Pattern detect uses conditional `if/else` | Direct equality operator |
| [dsp-mixed-cascade](dsp-mixed-cascade.md) | HIGH | Mixed inferred + instantiated DSP cascade | All inferred or all instantiated |
| [dsp-preg-feedback](dsp-preg-feedback.md) | HIGH | P→C feedback without PREG | Add PREG output register |
| [dsp-int8-constants](dsp-int8-constants.md) | MEDIUM | DSP INT8 constant inputs optimized away | `(* keep = "true" *)` on constants |

### DSPCPLX Cascade

| Check | Severity | Description | Fix |
|-------|----------|-------------|-----|
| [dspcplx-output-register](dspcplx-output-register.md) | HIGH | DSPCPLX output not registered | Register output, budget latency 7 |
| [dspcplx-keep-hierarchy](dspcplx-keep-hierarchy.md) | HIGH | `keep_hierarchy` blocks cascade | Remove attribute |

### Memory / URAM / BRAM

| Check | Severity | Description | Fix |
|-------|----------|-------------|-----|
| [uram-cascade-latency](uram-cascade-latency.md) | HIGH | Cascaded URAM with low read_latency | Increase to 4–5 |
| [uram-write-mode](uram-write-mode.md) | HIGH | URAM wrong write mode | read-first (2P) or no-change (T2P) |
| [uram-decomp-area](uram-decomp-area.md) | MEDIUM | URAM without `ram_decomp` | Add `(* ram_decomp = "area" *)` |
| [uram-write-first-mismatch](uram-write-first-mismatch.md) | MEDIUM | Write-first URAM mismatched structure | Match enable/reset on R and W paths |

### Carry Chain / Arithmetic

| Check | Severity | Description | Fix |
|-------|----------|-------------|-----|
| [carry-chain-legacy](carry-chain-legacy.md) | HIGH | Legacy carry-chain instantiations | Remove and use behavioral RTL |

### Coding Style

| Check | Severity | Description | Fix |
|-------|----------|-------------|-----|
| [vhdl-counter-else](vhdl-counter-else.md) | MEDIUM | VHDL counter increment placement | Put in `else` branch |
| [vhdl-depth1-addr](vhdl-depth1-addr.md) | LOW | VHDL depth-1 memory addr width | Explicit `(0 downto 0)` |

### BRAM Safety

| Check | Severity | Description | Fix |
|-------|----------|-------------|-----|
| [bram-hardware-safety](bram-hardware-safety.md) | HIGH | BRAM hardware failure risk | Pre-hardware validation flow |

## Adding New Guides

Create `<descriptive-name>.md` following the template in any existing guide:
root cause, detection pattern, before/after code, validation, and CR reference.
