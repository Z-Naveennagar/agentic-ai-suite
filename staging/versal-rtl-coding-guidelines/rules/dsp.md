<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# DSP58 Guidelines

Sources: AM004 Versal DSP Engine and UG901 synthesis coding techniques. Verify each claim on
the actual target because arithmetic width, signedness, surrounding logic, and latency affect
mapping.

## DSP-1 — Pipeline to match the required DSP58 configuration

Register arithmetic inputs, multiplier output, and final result where the latency contract
allows. AREG/BREG can have multiple legal depths; MREG and PREG are configuration-dependent.
Do not require every inferred DSP to report the same register values. Compare the observed
properties with the selected arithmetic function and expected latency.

```tcl
set dsps [get_cells -hier -filter {PRIMITIVE_GROUP == ARITHMETIC && PRIMITIVE_SUBGROUP == DSP}]
foreach d $dsps {
  list $d [get_property -quiet AREG $d] [get_property -quiet BREG $d] [get_property -quiet MREG $d] [get_property -quiet PREG $d]
}
```

## DSP-2 — Use reset behavior supported by the packed registers

Mixing incompatible reset types across registers intended for one DSP can prevent packing.
Prefer one compatible synchronous reset scheme where reset is architecturally required, or
leave pure datapath stages unreset and qualify them with valid/control state. Verify both DSP
register properties and any fabric registers around the DSP.

## DSP-3 — Treat specialized DSP features as explicit configuration

AM004 describes PATTERNDETECT hardware, `PATTERN`, `MASK`, and its operating modes. Do not
claim that an arbitrary HDL equality is guaranteed to infer PATTERNDETECT. When the feature is
required, use a documented Vivado language template or instantiate/configure DSP58, then
verify `USE_PATTERN_DETECT`, pattern/mask properties, latency, and absence of an unintended
fabric comparator.

## DSP-4 — Use documented inference structures for cascades

A sum-of-products expression does not by itself guarantee use of DSP cascade routes. For FIR
or systolic structures, use the documented UG901/AM004 coding template or explicit DSP58
configuration. After synthesis/placement, verify the expected DSP count, register settings,
and cascade connectivity. Test numerical behavior and pipeline latency.

`use_dsp` can express mapping intent but is not proof of mapping or timing. Use it selectively
and confirm the resulting netlist.

## Checklist

- [ ] Signedness, widths, truncation, rounding, and saturation are explicit.
- [ ] Pipeline latency matches the interface contract.
- [ ] DSP register properties match the selected configuration, not a universal value.
- [ ] Reset behavior permits the intended packing.
- [ ] PATTERNDETECT or cascade use is explicit and verified when required.
- [ ] Arithmetic simulation and post-synthesis mapping checks pass.
