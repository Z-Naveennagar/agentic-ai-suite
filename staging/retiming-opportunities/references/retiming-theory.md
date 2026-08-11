<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Retiming theory & feasibility conditions

Reference for the `retiming-opportunities` skill. Both forward and backward
retiming **move existing registers across combinational logic** — neither adds
pipeline depth (that is *pipelining*, a latency change). Retiming is
**latency-preserving** and only helps timing by **rebalancing an imbalanced
register boundary** (borrowing slack from a neighbor stage).

## Forward retiming
Move registers **with data flow**, from a gate's **inputs -> output**.
```
FFa-\                          (a)-\
FFb--+-[LUT]->      ==>         (b)--+-[LUT]->[FF]->
FFc-/                          (c)-/
```
- k registered inputs collapse to **1 output register** => register count drops
  by **k-1** (the forward-merge / area win).
- Depth effect: pushes the gate's logic **into the preceding stage** — helps only
  if that stage has slack.

## Backward retiming
Move registers **against data flow**, from a gate's **output -> each input**.
```
      /-[LUT]->[FF]->   ==>   [FF]-\
------/                      [FF]--+-[LUT]->
                            [FF]-/
```
- 1 output register expands to **one register per input** => count *increases* by
  k-1 (trades area for depth).
- Depth effect: pulls the register **into the deep cone**, moving trailing logic
  **into the following stage** — helps only if that stage has slack.

## Opaque/atomic blocks: far end may be BRAM/DSP, but never CROSS them
Retiming moves a register *through LUTs*, never *through* a BRAM/DSP/black box. So:
- Only the register being MOVED must be a FF (`FDRE/FDSE/FDCE/FDPE`).
- The OTHER end of the cone MAY be a BRAM/DSP/LUTRAM. Valid targets:
  - **BACKWARD**: `BRAM -> N*LUT -> FF` (move the capture FF back through the LUTs).
  - **FORWARD** : `FF -> N*LUT -> BRAM` (move the launch FF forward through the LUTs).
- The moved FF stops at the BRAM/DSP boundary (cannot pass its output/input).
- Carry chains (`LOOKAHEAD8`/`LUTCY`/`CARRY*`) inside the cone are atomic -> that
  cone is not retimeable through the carry segment.

### Prioritize building slack AROUND block RAM (BRAM/URAM)
BRAM/URAM are hard blocks with fixed sites and long clock-to-out / setup
requirements, so tight paths into/out of them are harder for the placer & router to
close. Therefore we sample block-RAM paths with a **wider slack window** than logic
paths (`BRAM_SLACK_MAX`, default 0.5ns vs `SLACK_MAX` 0.2ns): a block-RAM path that
already *meets* timing but only with a small positive margin is still worth
retiming when an adjacent LUT cone is imbalanced. **Failing** block-RAM paths need
no special treatment — they are already inside the normal window. The point is the
*passing-but-tight* ones: pulling/pushing the neighboring FF adds headroom around
the hard block, which eases downstream place & route.

## Shared feasibility conditions (both directions)
1. **Same clock domain** — launch clk == capture clk. Never across generated /
   divided / asynchronous clocks unless functional equivalence is proven.
2. **Latency-preserving** — I/O / protocol timing must not change.
3. **Movable registers only** — exclude `DONT_TOUCH==TRUE`, `MARK_DEBUG==TRUE`,
   `ASYNC_REG==TRUE` (CDC), reset-synchronizer FFs, IO-boundary flops (unless
   explicitly allowed), and any endpoint on `set_false_path` / `set_multicycle_path`.
4. **Opaque/atomic blocks can't be crossed** — BRAM, DSP, carry chains
   (`LOOKAHEAD8` / `LUTCY1` / `LUTCY2` / `CARRY*`), black boxes.
5. **Init/reset state reconcilable** — moved register's power-up/reset value must
   be derivable so behavior is bit-exact.
6. **Loop invariant (Leiserson-Saxe)** — register count around every cycle must be
   preserved; cannot retime the last register out of a feedback loop.

## Forward-specific (merge N inputs -> 1 output)
- **Every** used data input of the node is registered (any unregistered input
  blocks it). Constants (`VCC`/`GND`) are allowed.
- All input FFs share an **identical control set** — same `CLK`, `CE`, `SET/RESET`
  net, and same FF primitive TYPE (=> same edge + reset kind/value).
- Each input FF **fans out only to this node** (`fanout==1`); else removing it
  breaks other loads (no net saving).
- Merged output FF reset/init = LUT evaluated at the inputs' reset vector.

## Backward-specific (move 1 output -> regs on each input)
- Each fan-in net must accept a new register — none may be a primary input / IO
  boundary (would change input latency) or an opaque-block output.
- New per-input registers inherit the output register's control set — must be
  legal on every fan-in net.
- **Register explosion**: +（k-1) FFs per move; account for area cost.

## When retiming does NOT help (report separately, do not recommend)
- **Routing-dominated** path (few logic levels, route >> logic): needs placement,
  not retiming.
- **Congestion-dominated** path (route-dominated even for adjacent cells; in a
  `report_design_analysis -congestion` hotspot): needs congestion relief.
- **Clock-skew-dominated** path (large clock-path skew / CPR vs data path): needs
  clock/placement fixes.
- **Deep single stage with balanced neighbors** (no borrowable slack): needs RTL
  **pipelining** (adds latency), not retiming.
- **Carry/arithmetic chain** (`LOOKAHEAD8`/`LUTCY`): atomic — needs pipelining or
  operand-width reduction.

## Gain estimation (rough)
For a logic-depth-dominated cone that qualifies (`logic delay > 60%` of data
path) with borrowable neighbor slack:
```
balanced_depth ~= ceil(current_depth / 2)     # one register split near the middle
est_stage_delay ~= logic_delay * balanced_depth / current_depth + route_share
est_gain        ~= logic_delay * (1 - balanced_depth/current_depth)
```
bounded by the neighbor stage's available slack. If neighbor slack ~ 0 =>
est_gain ~ 0 => flag as PIPELINE (not retiming).

## Direction choice
- **Imbalance with the deep logic BEFORE the capture FF and slack in the PREVIOUS
  stage** -> forward-retime (push logic back toward launch).
- **Imbalance with the deep logic AFTER the launch FF and slack in the NEXT
  stage** -> backward-retime (pull capture register into the cone).
- **Multiple registered inputs converging on one LUT, same control set** ->
  forward-merge (area + timing).

## Placer tagging (this skill targets retiming INSIDE the placer)
Emit cell attributes on the register(s) to move; the placer performs the retiming.
- **Forward** candidate -> `set_property PSIP_RETIMING_FORWARD TRUE [get_cells {cell_name}]`
  - forward-merge: tag the **N input registers** of the LUT.
  - forward-retime of a cone: tag the **launch register**.
- **Backward** candidate -> `set_property PSIP_RETIMING_BACKWARD TRUE [get_cells {cell_name}]`
  - backward-retime of a deep pure-LUT cone: tag the **capture register**.
(Internal AMD placer retiming hints; not in public Vivado docs.)
Rules:
- Tag ONLY registers passing every safety + feasibility check above.
- Never tag `_bret`/`_fret`/`_replica` (already retimed) or `DONT_TOUCH`/`ASYNC_REG`
  cells.
- Do not tag both directions on the same register.
- Emit to a sourceable `set_retiming_tags.tcl` that re-resolves each cell with
  `get_cells -quiet` and skips unmatched (self-validating on re-source).
