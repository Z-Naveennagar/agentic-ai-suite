<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# B1: BRAM Hardware Failure Risk

**Check:** B1 | **Severity:** HIGH | **Category:** BRAM Safety

## Root Cause

Two synthesis optimizations can interact to cause **hardware failures** that do not
appear in simulation:

1. **BRAM cascading** — synthesis chains multiple BRAMs via cascade ports, which can
   introduce subtle address decode issues
2. **Constant propagation on RAM data** (`constantPropRamData`) — synthesis simplifies
   RAM contents when it determines some data bits are constant, which can incorrectly
   optimize away needed storage

When both features are active (which is the default), certain combinations of RAM
depth, width, and initialization can produce hardware that behaves differently from
simulation.

## When to Apply

Run this check **before taping out or deploying to hardware** on any design that:
- Uses BRAMs with initialization values
- Has cascaded BRAMs (deep memories split across multiple BRAMs)
- Shows simulation-hardware mismatch in memory-related functionality

## Detection

This check cannot be run via static RTL analysis. It requires a **re-synthesis
comparison** to validate.

**Step 1: Check current BRAM cascade usage**
```tcl
# Count cascaded BRAMs
set cascade_count 0
foreach bram [get_cells -hierarchical -filter {PRIMITIVE_TYPE =~ BLOCKRAM.BRAM.*}] {
    set cas [get_property CASCADE_ORDER $bram]
    if {$cas ne "NONE" && $cas ne ""} {
        incr cascade_count
    }
}
puts "Cascaded BRAMs: $cascade_count"
```

## Validation Flow

### Step 1: Baseline Synthesis (default settings)

```tcl
synth_design -top <top_module> -part <part>
write_checkpoint baseline.dcp
```

### Step 2: Re-synthesize with safety settings

```tcl
# Disable BRAM cascading
synth_design -top <top_module> -part <part> -max_bram_cascade_height 1

# OR: Disable constant propagation on RAM data
reset_design
rt::set_parameter constantPropRamData false
synth_design -top <top_module> -part <part>

write_checkpoint safety_check.dcp
```

### Step 3: Compare

```tcl
# Functional comparison
# If behavior changes between baseline and safety_check,
# the design is affected by one or both optimizations.
```

### Interpretation

| Baseline | Safety Check | Action |
|----------|-------------|--------|
| Sim matches HW | — | No action needed |
| Sim ≠ HW | Safety check matches sim | Use safety settings for production |
| Sim ≠ HW | Safety check also fails | Root cause is elsewhere |

## Fix — Production Synthesis Settings

If the safety check reveals a difference, use these settings for production:

```tcl
# Option A: Disable cascade (uses more BRAMs but eliminates cascade risk)
synth_design -top <top> -part <part> -max_bram_cascade_height 1

# Option B: Disable constant propagation (preserves all RAM data)
rt::set_parameter constantPropRamData false
synth_design -top <top> -part <part>

# Option C: Both (most conservative)
rt::set_parameter constantPropRamData false
synth_design -top <top> -part <part> -max_bram_cascade_height 1
```

**Trade-off:**
- `-max_bram_cascade_height 1`: Uses more BRAMs (no cascading) but eliminates cascade bugs
- `constantPropRamData false`: May use slightly more logic but preserves all RAM contents

## Reference

- [TSR-975570](https://jira.xilinx.com/browse/TSR-975570) — Synthesis settings causing hardware failure
- UG901 — Vivado Synthesis Guide, BRAM inference and cascading
