<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

---
name: macro-clustering-bram2bram
description: "Finds critical mem-to-mem LUT-connected structures in a post-opt/pre-place Vivado DCP and groups BRAM/URAM arrays for co-location. Use when unregistered memory-read chains are timing-limiting. Produces ranked clusters and a USER_CLUSTER tag script."
argument-hint: "<path-to-dcp> (required - a post-opt/pre-place .dcp). Optional env: MIN_LEVELS=<N> (min LUT levels between the two macros, default 2) MAX_LEVELS=<N> (combinational BFS depth bound, default 8) MAX_CLUSTER_MACROS=<N> (capacity cap: macros per cluster, default 32) PATTERNS='BRAM2BRAM BRAM2URAM URAM2URAM' (src->dst prim-type combos to keep) SAME_PARTITION=<0|1> (only cluster within one DFX partition, default 1) MAX_CONE=<N> (per-source LUT-cone guard, 0=unlimited, default 0) SCOPE=<hier-prefix> (only memories under this hierarchy are sources - a FAST way to validate on a portion; default whole design) SRC_LIMIT=<N> (0=all sources; >0 caps sources for a quick test)"
---

# Macro Clustering (BRAM/URAM mem -> N*LUT -> mem)

Find the **critical memory-to-memory macro clusters** - an **unregistered-read**
source memory feeding, through a **good amount of combinational LUT logic**, a
destination memory - and **tag the connected memory arrays so the placer
co-locates them**. Keeping the two ends of a `mem -> N*LUT -> mem` path physically
close removes the route delay that otherwise dominates a path with a large
clock-to-out and several logic levels.

## Why this matters
A memory read that is **not registered** (`DOA_REG/DOB_REG = 0` on a BRAM,
`OREG_A/OREG_B = FALSE` on a URAM) has a **large clock-to-out delay**. If that read
data then passes through **several LUT levels** into another memory's address/data/
write-enable, the path has almost no slack left for routing. If the two memories
are placed far apart, the route delay closes the door. **Co-locating the connected
memory arrays** (a placer hint applied *before* `place_design`) is the direct lever.

The critical `mem -> N*LUT -> mem` structure comes in two forms, both handled:
- **Inter-array**: source array A -> LUTs -> destination array B (two different
  logical memories). Cluster = A ∪ B.
- **Intra-array (self)**: the path runs *between the constituent primitives of one
  logical memory* (e.g. `mem_reg_bram_3 -> 3*LUT6 -> mem_reg_bram_5` inside one XPM
  array). Cluster = that one array, which must be kept **compact** (single column /
  region) so its internal read-to-write path stays short.

## Target patterns (start set)
```
BRAM -> N*LUT -> BRAM
BRAM -> N*LUT -> URAM
URAM -> N*LUT -> URAM        (URAM -> N*LUT -> BRAM is also collected)
```

## Conditions for a critical pair
1. **Source read UNREGISTERED** - traversal starts only from unregistered fabric
   read-data pins: BRAM `DOUTADOUT*/DOUTBDOUT*` on a port whose `DOA_REG/DOB_REG==0`;
   URAM `DOUT_A*/DOUT_B*` on a port whose `OREG_A/OREG_B==FALSE`.
2. **Good amount of logic levels** - the number of LUT levels between the two macros
   is `>= MIN_LEVELS` (default 2). Combinational only; the walk stops at any FF, DSP,
   or memory input.
3. **Same DFX partition** - a cluster stays within one reconfigurable partition
   (co-location across DFX partitions is illegal). `SAME_PARTITION=1`.

## Sibling-array expansion (one logical memory = many primitives)
A logical memory (XPM, altsyncram, FIFO) is implemented as **many BRAM/URAM
primitives**. Once a critical source primitive and destination primitive are found,
**each is expanded to its full sibling array** = the innermost enclosing
`xpm_memory_base_inst` / `xpm_fifo_base_inst` instance in the hierarchy name
(fallback: the immediate parent). The whole arrays - not just the two hit primitives
- go into the cluster.

## Clustering (N clusters per database)
- Build a graph: **nodes = memory arrays**, **edges = qualifying `src-array ->
  dst-array` critical paths**.
- **Union-find** merges arrays into connected components; each component is one
  **cluster**. Merging is **capacity-capped**: an edge is skipped if joining its two
  clusters would exceed `MAX_CLUSTER_MACROS` (32) macros. Edges are processed
  strongest-first (by levels, then #connections).
- A component with **>= 2 arrays** is an **inter** cluster; a single array with an
  internal (intra-array) critical path is a **self** cluster (keep-compact).
- Single logical memories larger than the cap are reported as **oversize arrays**.
- **Score** per cluster = `sum(levels x connections)` over its internal edges.

## Method
1. Collect BRAM (`REF_NAME =~ RAMB*`) and URAM (`REF_NAME =~ URAM*`) primitives; read
   `DOA_REG/DOB_REG` (BRAM) and `OREG_A/OREG_B` (URAM) in bulk.
2. **Array group** each primitive by hierarchy name (innermost `xpm_memory_base_inst`
   / `xpm_fifo_base_inst`). **Partition** each array by the nearest ancestor with
   `HD.RECONFIGURABLE` (else TOP).
3. For every **unregistered-read** source, run a **bulk levelized combinational BFS**
   forward from its DOUT nets (collection `filter` per level, LUT-deduped), recording
   each destination memory at its shortest LUT-level. Bounded by `MAX_LEVELS` (and the
   optional `MAX_CONE` per-source LUT guard).
4. Keep hits with `levels >= MIN_LEVELS` and a kept `PATTERN`; classify intra- vs
   inter-array; build array-level edges.
5. Union-find with the capacity cap; emit clusters, ranking, and the tag script.
   READ-ONLY on the design - nothing is modified.

## Placer tags (USER_CLUSTER)
Tags are applied **one level up from the leaf BRAM/URAM**, on the **designer
instance where the XPM/memory is instantiated** (the resolver walks up past the
`xpm_memory_base_inst` / `xpm_fifo_base_inst` / `altsyncram` boilerplate to the
first user instance; all banks of one logical memory collapse to that node). Every
source **and** destination instance of a cluster gets the **same** `uc_grp_<N>`:
```
# cluster 7  uc_grp_6  (inter, 12 macros, 2 instances, ...)
set_property USER_CLUSTER uc_grp_6 [get_cells {.../u_client_to_gft_oob_async_fifo}]
set_property USER_CLUSTER uc_grp_6 [get_cells {.../u_ptr_id_table}]
```
`get_cells` is given the raw hierarchical name (Vivado matches literal `[N]` bus/
generate indices; do NOT backslash-escape them - that breaks the match).

## How to run
Interactive (design already open):
```
source detect_macro_clusters.tcl
run_macro_cluster_analysis <outdir>
```
LSF batch (opens the DCP on a RHEL8 host):
```
bsub -q long -J bram2bram -n 2 \
  -R "select[ostype==rhelws810 || ostype==rhelws86 || ostype==rhelws89 || ostype==rhelws87] rusage[mem=65536]" \
  -o <outdir>/bram2bram.%J.log \
  ./run_macro_cluster_lsf.csh <dcp> <outdir>
```
Env tunables (LSF forwards them): `MIN_LEVELS` (2), `MAX_LEVELS` (8),
`MAX_CLUSTER_MACROS` (32), `PATTERNS` (`BRAM2BRAM BRAM2URAM URAM2URAM`),
`SAME_PARTITION` (1), `MAX_CONE` (0 = unlimited per-source LUT-cone guard),
`SCOPE` (hierarchy prefix - restrict sources to one module for a **fast portion run**;
default = whole design), `SRC_LIMIT` (0 = all; >0 caps sources for a quick smoke test).

## Output (4 files in `<outdir>`)
| File | Contents |
|------|----------|
| `macro_clusters_summary.rpt` | Run config + counts: memories, array groups, oversize arrays, sources traversed, inter-array edges, intra-array-critical arrays, edges merged / cap-skipped, clusters (inter/self), macros tagged, elapsed. |
| `macro_clusters.csv` | Per cluster: `cluster_id, uc_group, type (inter/self), num_groups, num_macros, num_instances, capped, partition, max_levels, score, pattern_mix` - the ranked cluster list. |
| `macro_cluster_pairs.csv` | Every qualifying array-level connection: `kind (inter/intra), src_group, dst_group, pattern, levels, connections, partition`. |
| `apply_macro_cluster_tags.tcl` | Ready-to-source `USER_CLUSTER` tags. For each cluster, every source + destination **designer memory instance** (a few levels up from the leaf BRAM, where the XPM/altsyncram/FIFO is instantiated) gets `set_property USER_CLUSTER uc_grp_<N> [get_cells {<instance>}]` with the SAME `uc_grp_<N>`. `source` it before `place_design`. |

## Scripts
| Script | Purpose |
|--------|---------|
| [detect_macro_clusters.tcl](./scripts/detect_macro_clusters.tcl) | Main detector (read-only): unregistered-source BFS, array grouping, capacity-capped union-find clustering, ranking, tag emission. |
| [run_macro_cluster_lsf.csh](./scripts/run_macro_cluster_lsf.csh) | LSF wrapper: open the DCP on RHEL8 and run the detector in batch. |
| [macro_cluster_batch_driver.tcl](./scripts/macro_cluster_batch_driver.tcl) | Batch driver (open_checkpoint + source + run + DONE marker). |

## Shell / perf notes (csh on this host)
- No bash `2>&1` / `2>/dev/null`; avoid inline `!` (history expansion). `setenv
  MIN_LEVELS 2` before `bsub` (LSF forwards env).
- Interactive `source` of a big tcl floods the terminal capture (echoes the file) -
  read the RESULT FILES, not the terminal.
- PERF: the BFS is **bulk** (collection `filter` per level, no per-sink-pin
  `get_cells`). Keep DOUT pins as an in-scope collection - a splatted name list
  breaks `get_nets -of_objects`. Reconstruct deduped LUT collections with
  bracket-escaped names (`[N]` hierarchy indices glob-break otherwise). For very
  wide-fanout designs set `MAX_CONE` (e.g. 20000) to bound pathological sources.
- This `opt` checkpoint is **pre-place** (dynamic region unplaced: `LOC` empty). The
  tags are **pre-place placer hints**; there is no placement distance or timing slack
  to use, so criticality is purely structural.
