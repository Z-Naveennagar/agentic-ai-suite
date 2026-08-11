<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

---
name: bram-uram-output-register
description: "Analyzes a post-opt/placed Vivado DCP to find BRAM/URAM ports where unpacking embedded output registers can improve output-path timing. Use when read-path timing is failing or near-critical. Produces ranked candidates and an iphysOptRAM2FF.tcl command script."
argument-hint: "<path-to-dcp> (required - a post-opt/placed .dcp). Optional: slack_max=<ns> (output-side near-critical window, default 0.5) maxpaths=<N> (timing paths sampled, default 200000)"
---

# BRAM / URAM Output-Register Timing Candidates

Analyze a Vivado Design Checkpoint to find **block-RAM (BRAM) and UltraRAM (URAM)**
memories whose **embedded output register is turned ON** and whose **output-side
paths** (registered read data -> downstream capture flop) are **failing or
near-critical**. For those, **pull the output register OUT of the hard block**
(UNPACK it into a fabric SLICE flop) so the placer/retimer can relocate it next to
its load and close the output stage. A register locked inside the block cannot
move; unpacking makes it movable. The move is **latency-preserving** (the register
is relocated, not removed).

The unpack is done by physical optimization, **per cell + port**, and the lines are
written to `iphysOptRAM2FF.tcl` (consumed by `read_iphys_opt_tcl` before `place_design`):
- BRAM: `iphys_opt_design -bram_register_opt -cell {<cell>} -unpacking -port <A|B>`
- URAM: `iphys_opt_design -uram_register_opt -cell {<cell>} -unpacking -port <A|B>`

## When to Use
- Timing closure on **BRAM/URAM read (output) paths**
- Deciding whether to **unpack DOA_REG / DOB_REG** (BRAM) or **OREG_A / OREG_B** (URAM)
- Moving a block output register **into the fabric** so it can be placed/retimed
- Auditing which memories have a **packed output register on a critical read path**

## Core idea (direction of the move)
```
  reg ON, packed:   [MEM|OREG]===long route===> [fabric FF]   <- reg stuck in block, far from load
  after unpacking:  [MEM]==> [fabric FF (was OREG)] ==> ...    <- reg movable: place near load / retime
```
With the output register packed inside the block, its location is fixed at the
memory tile; if the load is far, the block-to-FF route fails. `iphys_opt_design
-bram_register_opt/-uram_register_opt -unpacking` extracts that register into a
fabric flop the placer can move (and the retimer can rebalance), shortening the
output stage without changing latency.

## HARD SCOPE RULES
- **Non-cascade only.** Exclude any memory in a cascade chain: ANY `CASCADE_ORDER*`
  property != `NONE` (variants seen on Versal E5: `CASCADE_ORDER_A/B`, or
  `CASCADE_ORDER_CTRL_A/B` + `CASCADE_ORDER_DATA_A/B`), OR any `CAS*` pin wired to
  a real (non-constant) net.
- **Per port.** BRAM/URAM are dual-port; the register is **per port**, and only a
  port whose register is **ON** has something to unpack:
  - BRAM: `DOA_REG` (port A), `DOB_REG` (port B) == 1
  - URAM: `OREG_A` (port A), `OREG_B` (port B) == 1
  A port is "used" only if its data-out pins drive a real net (fanout >= 1).
- **Output-side = paths that START at the memory's data-out pins** (`DOUT*`/`DO*`,
  excluding `CAS*`). Do not use input/write-side paths.
- **Near-critical/failing window** = worst output-side setup slack `< SLACK_MAX`
  (default 0.5 ns) - i.e. failing plus a positive margin (0.5 ns suits block-RAM
  output paths; use 0.2 for failing-only).

## Checkpoint stage
- Requires a **placed/routed** post-opt DCP so the output-side **slack is real**
  and `iphys_opt_design` can actually relocate the register. On a pre-place netlist
  slack is not meaningful; use `LOGIC_LEVELS` only as a rough proxy.

## Latency & correctness caveats
- Unpacking is **latency-preserving** by construction (the register is relocated,
  not added/removed) - no absorb needed and no protocol-latency change.
- Respect `DONT_TOUCH` / `MARK_DEBUG`; skip memories inside a black box.
- `iphys_opt_design` only helps if the output stage is **routing/placement limited**
  (register stuck far from its load). If the failure is logic-depth on the output
  cone, unpacking alone will not fix it - flag for retiming/pipelining instead.
- Re-time/verify after applying: run `report_timing` on the same endpoints to
  confirm the output slack improved and nothing else regressed.

## Methodology
1. **Collect** `RAMB*` (BRAM) and `URAM288*` (URAM) cells.
2. **Drop cascaded** memories (property + CAS-pin check).
3. Per memory, read **per-port output-register** state and which ports are **used**.
4. **Candidate cells** = memories with >=1 used port whose register is **ON**
   (only a packed register can be unpacked).
5. **Prefilter + refine**: one `get_timing_paths -setup -from <candCells>
   -slack_lesser_than SLACK_MAX` finds cells with a near-critical output path (a
   DOUT *pin* is NOT a valid `-from` startpoint - the startpoint pin is the port
   CLOCK, so query `-from` the CELL); then for each hit, `-through <that port's
   DOUT pins>` attributes the worst slack to the exact reg-ON port (uniform for
   BRAM split clocks and URAM's shared clock). Reduce to worst per **cell|port**.
6. **Rank** flagged memories by worst output slack; record endpoint clock, logic
   levels, and the critical port(s).
7. **Emit** `iphysOptRAM2FF.tcl` - one line per flagged cell+critical port:
   `iphys_opt_design -bram_register_opt/-uram_register_opt -cell {..} -unpacking
   -port <A|B>` (BOTH ports emitted only when each is individually < SLACK_MAX).
   READ-ONLY - the detector changes nothing itself.

## Procedure

### Step 1 - Load the DCP via LSF (never on the login node)
Interactive (drive it live), csh shell, RHEL8 pin required:
```
bsub -I -R "select[type=X86_64 && osdistro=rhel && osver=ws8] rusage[mem=60000]" \
     -q long /proj/primebuilds/2026.1_PRIME_daily_latest/installs/lin64/2026.1/Vivado/bin/vivado -mode tcl
```
then `open_checkpoint <dcp>`. Or batch via
[run_bram_uram_lsf.csh](./scripts/run_bram_uram_lsf.csh) (opens the DCP + runs the
detector unattended - more robust for long sessions).

### Step 2 - (first time on a new device) confirm primitive names
Versal E5 primitives can rename ports/properties. Source
[probe_mem_props.tcl](./scripts/probe_mem_props.tcl) and run `probe_mem_props` to
print the REG/CASCADE properties and the data-out pin names of a sample BRAM and
URAM, then confirm the detector's patterns match (`DOA_REG/DOB_REG`, `OREG_A/OREG_B`,
`CASCADE_ORDER_*`, `DOUT*`/`DO*` out pins).

### Step 3 - Run the detector
```
source detect_bram_uram_oreg.tcl
run_bram_uram_oreg <outdir>
```
Writes `bram_uram_oreg_summary.rpt` (totals, ON/OFF census, slack histogram, top 25),
`bram_uram_oreg_candidates.csv` (per flagged memory: kind, per-port reg state, used
ports, critical port(s), worst output slack, logic levels, endpoint clock, endpoint
pin), and `iphysOptRAM2FF.tcl` (one `iphys_opt_design ... -unpacking -port <A|B>`
per flagged cell+critical port). Env: `SLACK_MAX` (default 0.5), `MAXPATHS` (default 200000).

### Step 4 - Reason on the ranked candidates
For the top candidates confirm, with numbers: non-cascade; the used port's register
is ON; worst output slack, endpoint clock, and logic levels; and that the stage is
**route/placement limited** (few logic levels, register far from load) so unpacking
can help. Consume the emitted file before placement (guarded so an empty file is
skipped), then re-check `report_timing` on those endpoints:
```
if {[file exists ./iphysOptRAM2FF.tcl] && [file size ./iphysOptRAM2FF.tcl] > 0} {
    read_iphys_opt_tcl ./iphysOptRAM2FF.tcl
}
```
(run before `place_design`).

## Output (3 files in `<outdir>` - set `<outdir>` = the `place_design` run dir)
| File | Contents |
|------|----------|
| `iphysOptRAM2FF.tcl` | **The deliverable.** One `iphys_opt_design -bram_register_opt/-uram_register_opt -cell {..} -unpacking -port <A\|B>` line per flagged cell+critical port (both A and B only when EACH port is individually near-critical). Empty file if nothing qualifies. Consumed by `read_iphys_opt_tcl` before `place_design`. |
| `bram_uram_oreg_candidates.csv` | Per flagged memory: kind, ref, per-port reg state, ports used, critical port(s), worst output slack, logic levels, endpoint clock, endpoint pin (human review / ranking). |
| `bram_uram_oreg_summary.rpt` | Totals, reg ON/OFF port census, worst-output-slack histogram, ranked top-25. |

Everything is decided at **cell + port** granularity - one unpack command per
(cell, port). Individual DOUT **bits are never iterated**: each port's whole bus is
handled in one `get_pins` (used-check) and one `-through` query (worst-bit slack).

### Consumption (hook it into the implementation run)
The generated `iphysOptRAM2FF.tcl` is read **before `place_design`**. The standard
guard uses a path **relative to the placement run's working directory**:
```
if {[file exists ./iphysOptRAM2FF.tcl] && [file size ./iphysOptRAM2FF.tcl] > 0} {
    read_iphys_opt_tcl ./iphysOptRAM2FF.tcl
}
```
**Required setup:** run the detector with `<outdir>` = the **same directory where
`place_design` runs**, so `./iphysOptRAM2FF.tcl` resolves at placement time.
(Alternatively copy the file into that CWD, or pass its absolute path to
`read_iphys_opt_tcl`.) The `file size > 0` test skips the empty file (no candidates).

## Scripts
| Script | Purpose |
|--------|---------|
| [detect_bram_uram_oreg.tcl](./scripts/detect_bram_uram_oreg.tcl) | Main detector (read-only). Non-cascade filter, per-port reg state, output-side slack, ranked candidates. |
| [probe_mem_props.tcl](./scripts/probe_mem_props.tcl) | Print REG/CASCADE properties + data-out pin names of a sample BRAM/URAM to confirm device naming. |
| [run_bram_uram_lsf.csh](./scripts/run_bram_uram_lsf.csh) | LSF wrapper: open the DCP on RHEL8 and run the detector in batch. |
| [bram_uram_batch_driver.tcl](./scripts/bram_uram_batch_driver.tcl) | Batch driver sourced by the wrapper (open_checkpoint + run + DONE marker). |

## Shell notes (csh on this host)
- No bash `2>&1` / `2>/dev/null`; use `>&` or omit. No bash `for`. Avoid inline `!`
  (history expansion) - put awk in files. `set VAR = val`, `$status`.
- Vivado 2026.1 PRIME daily opens 2025.2_KSB1 checkpoints. LSF cluster = xsj-tempest.
- Write all outputs to the shared workspace dir (compute node cannot see login /tmp).
