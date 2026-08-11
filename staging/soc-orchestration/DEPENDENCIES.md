<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# soc-orchestration — Dependency Checklist (breadcrumbs)

This skill orchestrates other skills. This file tracks what `soc-orchestration`
depends on and whether it is already present in this repo. Use it to decide what
still needs to be checked in. Names in the left column are the identifiers used
inside `SKILL.md`; the repo sometimes hosts an equivalent under a different name.

Status legend: PRESENT = already in repo (`skills/` or `staging/`) under the same
name; RENAMED = present under a different name (verify equivalence); MISSING = not
in the repo yet, needs check-in.

## Bundled sub-skills (already included in THIS check-in)
These live under `staging/soc-orchestration/` and travel with this PR:
- `partitioning/` (partitioning)
- `estimation/` (progressive T0-T3 estimation)
- `ps-software/` (PS firmware / hsi::generate_bsp flow)
- `vitis-platform/` (extensible platform / PFM)
- `vitis-acceleration/` (v++ kernel integration)

Note: a `vitis-platform_orig/` backup folder in the source workspace was intentionally
NOT copied.

## Core dependencies (needed for Phases 2-5 to run end-to-end)

| Skill (as referenced) | Repo status | Action |
|---|---|---|
| qor-classification | MISSING | CHECK IN — Phase 5 First-Step classifier (core). Also ships `scripts/source_remediation.py` used by Step 5.6. |
| ipi-block-design | MISSING | CHECK IN — Phase 4 PS+PL block-design construction (core). |
| hls-optimization | RENAMED? | Repo has an `hls-*` family in `skills/` (hls-architect, hls-optimize, hls-dataflow, hls-run-flow, hls-*-report, ...). Decide: map Phase 2/4b references to that family OR check in the monolithic `hls-optimization` skill. |
| hls-timing-closure | MISSING | See hls-* family decision above (Step 5.3/5.6 isolate-and-close). |
| hls-area-opt | MISSING | See hls-* family decision above (Step 5.3 area rebalance). |
| timing-methodology-checks | PRESENT (`skills/`) | none |
| congestion-analysis | PRESENT (`staging/`) | none |
| opt-design-analysis | PRESENT (`staging/`) | none |
| phys-opt-design-analysis | PRESENT (`staging/`) | none |
| device-floorplan | PRESENT (`staging/`) | none |
| rtl-lint | PRESENT (`staging/`) | none |
| rtl-elaboration-analysis | PRESENT (`staging/`) | none |
| versal-rtl-design-advisories | PRESENT (`staging/`) | none |
| vivado-revision-control | PRESENT (`skills/`) | none |
| noc-debug | RENAMED | Present as `hw-noc-debug` (`skills/`). Verify it covers Phase-4/5 NoC error diagnosis, then update the reference name. |

## Related skills (breadth — mentioned in "Related Skills")

Hardware bring-up (live device) — all present under `hw-*` names, verify equivalence:
| Referenced | Repo name |
|---|---|
| ila-vio-debug | `hw-ila-debug` + `hw-vio-debug` (`skills/`) |
| noc-perfmon | `hw-noc-perfmon` (`staging/`) |
| sysmon-health-check | `hw-sysmon` (`staging/`) |
| ddrmc-debug | `hw-ddrmc-debug` (`staging/`) |
| ibert-link-scan | `hw-ibert-gt-debug` (`staging/`) |
| pcie-link-debug | `hw-pcie-link-debug` (`staging/`) |

Segmented Configuration (Versal) — all PRESENT in `staging/`:
`segcfg-overview`, `segcfg-project-setup`, `segcfg-design-check`, `segcfg-build-images`,
`segcfg-programming`, `segcfg-pl-reload`, `segcfg-firmware-build`, `segcfg-debug-guide`.

Skill authoring: `vivado-skill-creator` — PRESENT (`staging/`).

## External / global (do NOT check in here)
- `baselining` — intentionally external/global (CDC + consolidated QoR-score umbrella).
  `SKILL.md` already documents that it is not part of this repo.

## Shared root files now BUNDLED into this skill
These lived at the source workspace root (shared infra) and are now vendored here so the
staged skill is self-contained. In-skill references (`contracts/...`, `specs/...`,
`scripts/...`) resolve relative to this skill root:
- `contracts/__init__.py`, `contracts/types.py` — `DesignSpec`, `PartitionPlan`, `QoRMetrics`, `ClosureReport`.
- `specs/spec_template.md` — design-spec template.
- `scripts/extract_addr_map.py`, `scripts/vitis_build.tcl`, `scripts/lscript_a53.ld` — PS firmware/BSP helpers (Phase 4b / ps-software).

`qor-classification/scripts/source_remediation.py` (referenced in Step 5.6) ships with the
qor-classification skill listed above, not here.

## Dangling script references in SKILL.md (do NOT exist in source workspace)
These are referenced but have no backing file anywhere; fix or remove the references:
- `scripts/report_summary.py` (estimation/SKILL.md)
- `scripts/package_dpu_kernel.tcl`, `scripts/xvdpu_aie_noc.py`, `scripts/system.cfg` (vitis-acceleration/SKILL.md)

## Suggested next check-in batches
1. Batch 2 (core): `qor-classification`, `ipi-block-design`, and the HLS workflow skills
   (or the name mapping decision).
2. Batch 3 (breadth / name reconciliation): confirm the `hw-*` renames and `noc-debug`,
   then update reference names in `SKILL.md`.
