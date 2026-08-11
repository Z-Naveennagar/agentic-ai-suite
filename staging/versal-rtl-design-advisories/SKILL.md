---
name: versal-rtl-design-advisories
description: >
  Checks Versal RTL designs against 42 design advisories mined from 104 Jira CRs covering
  DSP58/DSPCPLX inference, URAM/BRAM coding patterns, carry chain migration, FSM encoding,
  timing methodology, and US+ to Versal migration. Use when user asks to "check RTL design
  advisories", "Versal coding guidelines", "RTL lint for Versal", "DSP inference issues",
  "URAM inference problems", "DSPCPLX cascade", "memory inference", or "migration from
  US+ to Versal".
version: 1.0.0
vivado_version: 2025.1+
categories: [analysis, verification, design-advisories, migration]
device_families: [versal]
estimated_duration: 3-10 minutes
complexity: intermediate
author: Gopinath Pocklas
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->
# Versal RTL Design Advisories

## Introduction

**Purpose:** Analyze Versal-targeted RTL source code and synthesis reports against 42 validated
design advisories to identify inference failures, coding anti-patterns, and migration issues before
they cause timing closure problems or hardware failures.

**Problem Solved:** Engineers porting designs to Versal or writing new Versal RTL frequently hit
inference failures (DSP58, DSPCPLX, URAM, BRAM) and timing issues that are documented only in
scattered Jira CRs. This skill codifies 42 expert-validated patterns from 104 CRs into a
systematic checklist the AI agent can run against any design.

**Expected Outcome:**
- `vivado_agentic_ai_reports/versal-rtl-design-advisories/REPORT.md` — findings with severity,
  affected files/lines, recommended fixes, and source CR references

**Supporting Material:**
- `resolution/` — Per-check fix guides with root cause, before/after code, and validation Tcl
  (see [resolution/README.md](resolution/README.md) for index)
- `examples/` — Sample reports: [report-clean.md](examples/report-clean.md) and
  [report-violations.md](examples/report-violations.md)

**Prerequisites:**
- RTL source files (.v, .sv, .vhd) accessible in the workspace
- Target device is Versal family (xcvc*, xcve*, xcvm*, xcvp*)
- For post-synthesis checks: synthesis must be complete (DCP or open project with synth_1)

---

## When to Use

- User targets a Versal device and asks to review RTL quality
- User migrating design from UltraScale+ to Versal
- Synthesis log shows unexpected DSP, URAM, or BRAM inference results
- Timing closure difficulties on Versal with high logic levels
- User asks about DSP58 NEGATE, DSPCPLX cascade, URAM write modes, or FSM encoding

## When NOT to Use

- Design targets UltraScale+, 7-Series, or non-Versal devices (many checks are Versal-specific)
- User needs general RTL linting → use `rtl-lint` skill instead
- User needs timing methodology checks → use `timing-methodology-checks` skill instead
- Design is pre-RTL (block diagram or HLS C++ only with no generated RTL)

---

## Workflow

Execute checks in order. For each category, scan RTL source files and (if available)
synthesis logs/reports for the listed patterns. Not all checks apply to every design —
skip categories that don't match the design's resource usage.

### Step 1: Gather Design Context

Determine what's available. If a Vivado session is active, run:

```tcl
set part [get_property part [current_project]]
set top [get_property top [current_fileset]]
set family [get_property FAMILY [get_parts $part]]
puts "Part: $part Top: $top Family: $family"
# Check resource usage if synthesis is done
if {![catch {current_design}]} {
    report_utilization -hierarchical -hierarchical_depth 1 -file vivado_agentic_ai_reports/versal-rtl-design-advisories/utilization.rpt
    puts "DSP: [llength [get_cells -hierarchical -filter {PRIMITIVE_TYPE =~ DSP.*}]]"
    puts "URAM: [llength [get_cells -hierarchical -filter {PRIMITIVE_TYPE =~ BLOCKRAM.URAM.*}]]"
    puts "BRAM: [llength [get_cells -hierarchical -filter {PRIMITIVE_TYPE =~ BLOCKRAM.BRAM.*}]]"
}
```

If no Vivado session, read RTL files directly to identify DSP/RAM usage patterns.

**Verify Versal target:** If `$family` is not `versal*`, warn user that most checks are Versal-specific and ask whether to proceed.

---

### Step 2: DSP Inference Checks (10 checks)

Scan RTL for DSP-related patterns. Report any violations found.

| # | Check | What to Look For | Fix | Severity | CR |
|:-:|-------|-----------------|-----|:--------:|:--:|
| D1 | Pattern detect uses conditional | `if (p == pattern) patdet <= 1; else patdet <= 0;` | Change to `patdet <= (p == pattern);` — direct equality operator. [Guide](resolution/dsp-pattern-detect.md) | HIGH | [CR-1034185](https://jira.xilinx.com/browse/CR-1034185) |
| D2 | Complex multiplier not using DSP_CPLX | Separate real/imaginary DSP chains for complex multiply | Restructure for DSP_CPLX inference or instantiate DSP_CPLX primitive | HIGH | [CR-1118919](https://jira.xilinx.com/browse/CR-1118919) |
| D3 | Behavioral NEGATE usage | RTL tries to infer DSP58 NEGATE port via `sel ? -product : product` | DSP58 NEGATE port **requires instantiation** — cannot be inferred behaviorally | MEDIUM | [CR-1102908](https://jira.xilinx.com/browse/CR-1102908) |
| D4 | Missing `use_dsp` control | Arithmetic in fabric path gets pulled into DSP by timing-driven inference | Add `(* use_dsp = "no" *)` on modules/signals that must stay in fabric | MEDIUM | [CR-1052168](https://jira.xilinx.com/browse/CR-1052168) |
| D5 | Mixed inferred + instantiated cascade | Same cascade chain has both inferred DSP and instantiated DSP58 | Use **all inferred** or **all instantiated** — tool cannot merge the two forms. [Guide](resolution/dsp-mixed-cascade.md) | HIGH | [CR-1199907](https://jira.xilinx.com/browse/CR-1199907) |
| D6 | P→C feedback without PREG | DSP58 output P feeds back to input C without output register | Add **PREG** (output register) to the DSP58 — required for feedback timing. [Guide](resolution/dsp-preg-feedback.md) | HIGH | [CR-1150378](https://jira.xilinx.com/browse/CR-1150378) |
| D7 | >48-bit counter in DSP | Counter wider than 48 bits using Binary Counter IP | Use **`dsp_macro` IP** or Vivado language templates — Binary Counter can't chain DSPs | MEDIUM | [TSR-976468](https://jira.xilinx.com/browse/TSR-976468) |
| D8 | Adder DSP causes logic errors | Synthesis log shows adder mapped to DSP with incorrect results | Add `set_property dspInferAdder false [current_design]` before synthesis | MEDIUM | [CR-1246710](https://jira.xilinx.com/browse/CR-1246710) |
| D9 | DSP INT8 constant inputs optimized away | Constants feeding DSP INT8 mode get removed by optimization | Add `(* keep = "true" *)` attribute on constant input signals. [Guide](resolution/dsp-int8-constants.md) | MEDIUM | [CR-1186324](https://jira.xilinx.com/browse/CR-1186324) |
| D10 | HLS DSP intrinsic width mismatch | HLS `ap_int` wider than DSP58 ports (A>27b, B>24b) | Verify widths match hardware: A≤27 bits, B≤24 bits. HLS **silently truncates**. | MEDIUM | [CR-1189796](https://jira.xilinx.com/browse/CR-1189796) |

**RTL patterns to grep for:**
```
# D1: Pattern detect conditional
grep -n "patterndetect\|pattern_detect\|PATTERNDETECT" *.sv *.v *.vhd
# D3: Behavioral negate
grep -n "? -\|sel.*negate\|NEGATE" *.sv *.v
# D4: Missing use_dsp
# Check if arithmetic modules lack use_dsp attribute
# D5: Mixed cascade
grep -n "DSP58\|DSP48E2\|DSPCPLX" *.sv *.v *.vhd
```

---

### Step 3: DSPCPLX Cascade Checks (5 checks)

If design uses complex multipliers or DSPCPLX, check these patterns:

| # | Check | What to Look For | Fix | Severity | CR |
|:-:|-------|-----------------|-----|:--------:|:--:|
| C1 | DSPCPLX output not registered | No output register (speedup register) after DSPCPLX | **Always register DSPCPLX output.** Budget latency **7** (not 5) for FFT butterfly. [Guide](resolution/dspcplx-output-register.md) | HIGH | [CR-1076270](https://jira.xilinx.com/browse/CR-1076270) |
| C2 | Small-bitwidth DSPCPLX optimized away | Optimizer removes DSPCPLX modules with narrow operands | Add `(* dont_touch = "true" *)` on the module to prevent removal | MEDIUM | [CR-1236723](https://jira.xilinx.com/browse/CR-1236723) |
| C3 | `keep_hierarchy` blocks cascade | `keep_hierarchy` attribute on DSPCPLX modules | **Remove `keep_hierarchy`** — it prevents cascade chain formation. [Guide](resolution/dspcplx-keep-hierarchy.md) | HIGH | [CR-1247719](https://jira.xilinx.com/browse/CR-1247719) |
| C4 | Cascade C-port not tied | C-port left floating or driven by logic in cascade chain | Tie **C-port explicitly to 0**. Do not use `dont_touch` on cascade signals. | MEDIUM | [CR-1256048](https://jira.xilinx.com/browse/CR-1256048) |
| C5 | HLS cascade without `cascade<>` | HLS design attempts DSPCPLX cascade via manual coding | Use HLS **`cascade<>` class** — the only supported mechanism for DSPCPLX cascade inference | MEDIUM | [CR-1237378](https://jira.xilinx.com/browse/CR-1237378) |

---

### Step 4: Memory Inference Checks (9 checks)

Scan RTL for RAM/URAM coding patterns:

| # | Check | What to Look For | Fix | Severity | CR |
|:-:|-------|-----------------|-----|:--------:|:--:|
| M1 | Cascaded URAM with low read_latency | `read_latency` < 4 with `cascade_height` ≥ 4 | Increase **`read_latency` to 4–5** for cascade_height=8. [Guide](resolution/uram-cascade-latency.md) | HIGH | [CR-1028747](https://jira.xilinx.com/browse/CR-1028747) |
| M2 | Asymmetric RAM too deep | Address width >32 bits on asymmetric RAM | Reduce depth or split into multiple memories | MEDIUM | [CR-1109135](https://jira.xilinx.com/browse/CR-1109135) |
| M3 | URAM wrong write mode | URAM 2P using write-first, or T2P using read-first | URAM 2P: **read-first** only. True 2P: **no-change** only. [Guide](resolution/uram-write-mode.md) | HIGH | [CR-1058874](https://jira.xilinx.com/browse/CR-1058874) |
| M4 | Simultaneous R/W to same URAM address | Same address read and written in same cycle | URAM does **not support simultaneous R/W** to same address. Use mutually exclusive access. HLS: use `RAM_2P`. | HIGH | [CR-1100014](https://jira.xilinx.com/browse/CR-1100014) |
| M5 | T2P URAM non-NO_CHANGE mode | True dual-port URAM coded with read-first or write-first | T2P URAM **only supports NO_CHANGE** write mode | HIGH | [CR-1168604](https://jira.xilinx.com/browse/CR-1168604) |
| M6 | URAM without `ram_decomp` | Large URAM arrays on Versal without area attribute | Add `(* ram_decomp = "area" *)` — default wastes **25% more URAMs** on Versal. [Guide](resolution/uram-decomp-area.md) | MEDIUM | [CR-1161721](https://jira.xilinx.com/browse/CR-1161721) |
| M7 | Write-first URAM mismatched structure | Enable or reset on read path differs from write path | **Match enable/reset structure** on both read and write paths for write-first inference. [Guide](resolution/uram-write-first-mismatch.md) | MEDIUM | [CR-1263465](https://jira.xilinx.com/browse/CR-1263465) |
| M8 | BRAM with combinational feedback | BRAM read data feeds back into write data combinationally | Use **clean word/byte R/W patterns** — no combinational feedback loops in memory block | MEDIUM | [CR-1241256](https://jira.xilinx.com/browse/CR-1241256) |
| M9 | Shallow RAM in BRAM | Small memories (≤64 entries) inferred as BRAM | Add `(* ram_style = "distributed" *)` to avoid wasting BRAM | LOW | [CR-1111759](https://jira.xilinx.com/browse/CR-1111759) |

**RTL patterns to grep for:**
```
# M3/M4/M5: URAM write mode issues
grep -n "ram_style.*ultra\|URAM\|uram" *.sv *.v *.vhd
# M6: Missing ram_decomp
grep -n "ram_decomp" *.sv *.v *.vhd   # should find attribute if URAMs are used
# M9: Shallow RAM
# Check RAM declarations with depth ≤ 64
```

---

### Step 5: Carry Chain / Arithmetic Checks (2 checks)

| # | Check | What to Look For | Fix | Severity | CR |
|:-:|-------|-----------------|-----|:--------:|:--:|
| A1 | Legacy carry-chain instantiations | `CARRY4`, `CARRY8` primitives in Versal-targeted RTL | **Remove** and use behavioral RTL. Versal LOOKAHEAD8 ≠ US+ CARRY4/CARRY8. [Guide](resolution/carry-chain-legacy.md) | HIGH | [CR-1034326](https://jira.xilinx.com/browse/CR-1034326) |
| A2 | High logic levels from carry chains | Timing report shows LOOKAHEAD8 primitives on critical paths | Versal carry chains are **slower than US+**. Tool may intentionally use LUTs. Consider RTL restructuring to reduce arithmetic depth. | MEDIUM | [CR-1037260](https://jira.xilinx.com/browse/CR-1037260) |

**RTL patterns to grep for:**
```
grep -n "CARRY4\|CARRY8\|CARRY4_inst\|carry_inst" *.sv *.v *.vhd
```

---

### Step 6: Coding Style Checks (8 checks)

| # | Check | What to Look For | Fix | Severity | CR |
|:-:|-------|-----------------|-----|:--------:|:--:|
| S1 | VHDL counter after `if` | Counter increment outside `else` branch | Put increment **in `else` branch**: `if (i=max) then i<=0; else i<=i+1; end if;`. [Guide](resolution/vhdl-counter-else.md) | MEDIUM | [CR-1063518](https://jira.xilinx.com/browse/CR-1063518) |
| S2 | Large FSM with default encoding | FSM with 700+ states using auto/default encoding | Use `(* FSM_ENCODING = "ONE_HOT" *)` or `"SEQUENTIAL"` | MEDIUM | [CR-1147297](https://jira.xilinx.com/browse/CR-1147297) |
| S3 | Registers without INIT or reset | Registers declared without explicit INIT and no reset signal | **Always specify INIT values** or put registers under reset. Synthesis may choose any INIT. | MEDIUM | [CR-1201071](https://jira.xilinx.com/browse/CR-1201071) |
| S4 | Duplicate module names across IPs | Multiple IPs define same module name in global synthesis | Use **OOC mode** for IPs with conflicting module names, or rename modules | MEDIUM | [CR-1029098](https://jira.xilinx.com/browse/CR-1029098) |
| S5 | Control set explosion | Stamped/replicated design with >10K unique control sets | Add `set_property STEPS.SYNTH_DESIGN.ARGS.CONTROL_SET_OPT_THRESHOLD 8` | MEDIUM | [CR-1060792](https://jira.xilinx.com/browse/CR-1060792) |
| S6 | Single-process FSM | FSM coded as single always/process block | Use **two-process or three-process** FSM style for reliable Vivado FSM inference | LOW | [CR-1260624](https://jira.xilinx.com/browse/CR-1260624) |
| S7 | HLS combinational function without INLINE | HLS function with no pipeline pragma and no return register | Add `#pragma HLS INLINE` to prevent **latch inference** in combinational HLS functions | MEDIUM | [CR-1092840](https://jira.xilinx.com/browse/CR-1092840) |
| S8 | VHDL depth-1 memory addr width | Memory with depth=1, addr declared via `clogb2(depth-1)` | Declare addr port as `(0 downto 0)` explicitly — `clogb2(1)` returns 0, creating null range. [Guide](resolution/vhdl-depth1-addr.md) | LOW | [CR-1223300](https://jira.xilinx.com/browse/CR-1223300) |

---

### Step 7: Timing / Constraints Checks (6 checks)

These checks require synthesis reports or timing analysis. If not available, flag as "could not verify — run post-synthesis."

| # | Check | What to Look For | Fix | Severity | CR |
|:-:|-------|-----------------|-----|:--------:|:--:|
| T1 | Missing pipeline on long paths | Data paths spanning CIPS→SmartConnect→AIE (>1/3 device width) | **Add pipeline registers** at module boundaries along the path | HIGH | [CR-1067123](https://jira.xilinx.com/browse/CR-1067123) |
| T2 | ILA/debug cores in closure run | ILA or VIO cores present during timing closure | **Remove ILA/debug** before final closure. Also remove `DONT_TOUCH` on HFN nets. Use `CLOCK_BUFFER_TYPE NONE` on reset nets. | HIGH | [CR-1051861](https://jira.xilinx.com/browse/CR-1051861) |
| T3 | I/O constraints ignoring BUFGCE delay | `set_input_delay`/`set_output_delay` not accounting for inserted BUFGCE | Versal auto-inserts **BUFGCE (~3.5ns skew)**. Add this to I/O delay budget. | MEDIUM | [CR-1089241](https://jira.xilinx.com/browse/CR-1089241) |
| T4 | Wide bus congestion | >256-bit buses causing routing congestion | Use **`USER_CLUSTER`** attributes, pblocks, `ctrl_set_opt=8`, balanced clock tree | MEDIUM | [TSR-976334](https://jira.xilinx.com/browse/TSR-976334) |
| T5 | UDP reset fanout | User Datapath design with high reset fanout | Use `(* direct_reset = "yes" *)` attribute + OOC synthesis mode | MEDIUM | [CR-1212263](https://jira.xilinx.com/browse/CR-1212263) |
| T6 | LOC constraints + BUFG insertion | LOC-constrained FFs near auto-inserted BUFG causing setup violations | Review BUFG insertion near LOC-constrained sites. May need `CLOCK_BUFFER_TYPE NONE`. | MEDIUM | [CR-1218617](https://jira.xilinx.com/browse/CR-1218617) |

**Post-synthesis Tcl checks:**
```tcl
# T2: Check for ILA/debug cores
set ila_count [llength [get_cells -hierarchical -filter {PRIMITIVE_TYPE =~ ADVANCED.MONITOR.*}]]
set vio_count [llength [get_cells -hierarchical -filter {REF_NAME =~ vio_*}]]
if {$ila_count > 0 || $vio_count > 0} {
    puts "WARNING: $ila_count ILA + $vio_count VIO debug cores found — remove before timing closure"
}

# T2: Check for DONT_TOUCH on high-fanout nets
foreach net [get_nets -hierarchical -filter {DONT_TOUCH == true && FANOUT > 100}] {
    puts "WARNING: DONT_TOUCH on high-fanout net: $net (fanout=[get_property FANOUT $net])"
}
```

---

### Step 8: BRAM Safety Check (1 check)

| # | Check | What to Look For | Fix | Severity | CR |
|:-:|-------|-----------------|-----|:--------:|:--:|
| B1 | BRAM hardware failure risk | Design going to hardware with cascaded BRAMs or const-prop on RAM data | **Pre-hardware validation:** Re-run synthesis with `-max_bram_cascade_height 1` and `rt::set_parameter constantPropRamData false`. If behavior changes, that's the culprit. [Guide](resolution/bram-hardware-safety.md) | HIGH | [TSR-975570](https://jira.xilinx.com/browse/TSR-975570) |

---

### Step 9: US+ Migration Checks (2 checks)

Only if design was previously implemented on UltraScale+:

| # | Check | What to Look For | Fix | Severity | CR |
|:-:|-------|-----------------|-----|:--------:|:--:|
| G1 | LOOKAHEAD paths in critical timing | Timing report shows LOOKAHEAD8 primitives on top failing paths | **RTL restructuring required.** Reduce arithmetic expression depth. Review carry chain usage. | HIGH | [TSR-975745](https://jira.xilinx.com/browse/TSR-975745) |
| G2 | US+ primitives in RTL | `CARRY4`, `CARRY8`, `DSP48E2`, `RAMB36E2` instantiations | Replace with Versal equivalents or behavioral RTL for re-inference | HIGH | [CR-1034326](https://jira.xilinx.com/browse/CR-1034326) |

---

### Step 10: Generate Report

Write findings to `vivado_agentic_ai_reports/versal-rtl-design-advisories/REPORT.md`.

See [examples/report-clean.md](examples/report-clean.md) for a passing report and
[examples/report-violations.md](examples/report-violations.md) for a report with findings.

For each finding, link to the relevant resolution guide (e.g., `[Guide](resolution/dsp-pattern-detect.md)`)
so the user can read the detailed before/after code and validation steps.

**Report template:**

```markdown
# Versal RTL Design Advisories Report

| Field | Value |
|-------|-------|
| Project | <project_name> |
| Top Module | <top> |
| Part | <part> |
| Date | <date> |
| Checks Run | <N> of 42 applicable |

## Summary

| Severity | Count |
|----------|:-----:|
| HIGH     | <n>   |
| MEDIUM   | <n>   |
| LOW      | <n>   |
| PASS     | <n>   |
| SKIPPED  | <n>   |

**Total: <N> issues found across <M> categories**

## Findings

### <Check ID>: <Short Description>

- **Severity:** HIGH / MEDIUM / LOW
- **File:** <file_path>:<line>
- **Category:** <DSP / DSPCPLX / RAM / Carry / Style / Timing / Safety / Migration>
- **Current Code:**
```
<snippet — 3-10 lines>
```
- **Recommended Fix:**
```
<fixed snippet>
```
- **Explanation:** <1-2 sentences>
- **Reference:** [<CR-number>](https://jira.xilinx.com/browse/<CR-number>)

## Categories Not Applicable

<List checks skipped because design doesn't use those resources>

## Recommendations

1. **[Priority]** <actionable recommendation>
2. ...
```

---

## Efficiency Guidelines

- **Skip inapplicable categories:** If design has no DSPs, skip Steps 2-3. If no URAMs, skip URAM checks in Step 4. If not migrating from US+, skip Step 9.
- **Batch file reads:** Read all RTL files in one pass and scan for multiple patterns, rather than re-reading per check.
- **Use grep patterns:** The grep patterns listed in each step help quickly identify candidate violations without reading every line.
- **Post-synthesis checks are optional:** Steps 7-9 provide the most value post-synthesis, but Steps 2-6 can run on RTL alone.
- **Do not fabricate findings:** Only report patterns actually found in the code. If a check passes, mark it PASS.

## Rules

- Only report violations actually found in the RTL or synthesis reports. **NEVER fabricate.**
- Use workspace-relative paths for all file references.
- Each finding must include the actual problematic code snippet and a concrete fix.
- Always include the source CR link for traceability.
- Severity levels: HIGH = will cause functional failure or major timing impact. MEDIUM = suboptimal inference or QoR degradation. LOW = style improvement.

---

## Quick Reference: Attribute Cheat Sheet

| Attribute | Syntax (Verilog) | Syntax (VHDL) | Purpose |
|-----------|-----------------|---------------|---------|
| `use_dsp` | `(* use_dsp = "no" *)` | `attribute use_dsp : string; attribute use_dsp of sig : signal is "no";` | Prevent DSP inference |
| `keep` | `(* keep = "true" *)` | `attribute keep : string; attribute keep of sig : signal is "true";` | Prevent optimization |
| `dont_touch` | `(* dont_touch = "true" *)` | `attribute dont_touch : string; attribute dont_touch of inst : label is "true";` | Prevent any optimization |
| `ram_style` | `(* ram_style = "distributed" *)` | `attribute ram_style : string; attribute ram_style of mem : signal is "distributed";` | Force distributed RAM |
| `ram_decomp` | `(* ram_decomp = "area" *)` | `attribute ram_decomp : string; attribute ram_decomp of mem : signal is "area";` | Area-optimal URAM decomposition |
| `FSM_ENCODING` | `(* FSM_ENCODING = "ONE_HOT" *)` | `attribute FSM_ENCODING : string; attribute FSM_ENCODING of state : signal is "ONE_HOT";` | Force FSM encoding |
| `direct_reset` | `(* direct_reset = "yes" *)` | `attribute direct_reset : string; attribute direct_reset of rst : signal is "yes";` | Force direct reset path |

---

## References

- **UG949**: UltraFast Design Methodology Guide — Versal design guidance
- **UG904**: Vivado Implementation Guide — DSP, RAM inference
- **UG901**: Vivado Synthesis Guide — attributes, inference rules
- **AM004**: Versal Adaptive SoC DSP58 Architecture Manual
- **AM007**: Versal Adaptive SoC Memory Resources Architecture Manual
- **Source CRs**: 104 Jira CRs mined — see individual check CR links above
