---
name: segcfg-pl-reload
description: Use this skill — not general segcfg skills — specifically for the Versal Segmented Configuration PL reload multi-variant workflow: creating two or more independently-compiled pld.pdi files that swap at runtime while boot.pdi stays fixed. Invoke when a user asks how to fork a golden implemented design into a new PL variant project, which Tcl commands are safe for copying block designs (save_project_as, write_bd_tcl, import_files) and why read_bd must never be used, how to lock NoC boot paths across variants using write_noc_solution and .ncr solution files, how to size address apertures in the golden as supersets so reload variants can use subsets, how to run pr_verify comparing a golden DCP against a variant DCP, or why PLM rejects a pld.pdi at runtime due to UID or parent_unique_id mismatch.
metadata:
   author: George Ohanjanyan, AMD
allowed-tools: Read, Bash, Write
---

Guide the user through the complete PL reload methodology: golden project setup, variant spawning, NoC solution files, address aperture flexibility, UID compatibility, and pr_verify.

## Instructions

1. Read `${CLAUDE_SKILL_DIR}/references/reload-methodology.md` for the full PL reload flow.
   Read `${CLAUDE_SKILL_DIR}/references/address-aperture.md` for aperture flexibility details.

2. Ask the user about their scenario:
   - Setting up a golden project from scratch
   - Spawning a new PL variant from an existing golden design
   - Debugging a pr_verify failure
   - Understanding address aperture requirements
   - Understanding UID compatibility failures at runtime

3. **Explain the PL reload concept**:
   - The boot.pdi remains constant; only pld.pdi changes
   - Multiple independent projects or implementation runs produce different pld.pdi files
   - `pr_verify` is **mandatory** to confirm compatibility before deploying to hardware
   - The golden design must be compiled in the **same Vivado release** as all variant designs

4. **Golden project setup**:
   - Create the golden as a **superset** of all PS-PL boundary connectivity needed for any variant
   - All pin usage, address apertures, and NoC connectivity must be established here
   - Enable PS interfaces, for example FPD to PL or LPD to PL, that will be used later in reload designs, even though they are not utilized in golden design.
   - Run write_noc_solution on post-routed golden design to generate NoC solution file, which later will be used in reload designs to keep consistency with paretn/golden design.
   - Run through `route_design` — the `.ncr` file is generated in the run directory
   - This golden is the parent for all PLD variants

5. **Spawn a PL variant** — choose one approach and generate Tcl:
   ```tcl
   # Option A: Clone entire project
   save_project_as new_variant_project

   # Option B: Import block design (recommended for BD-centric designs)
   import_files <path_to_golden>/design_1.gen/sources_1/bd

   # Option C: Script the block design
   write_bd_tcl -force golden_bd.tcl      
   write_bd_tcl -hier_blks ps_hier golden_ps.tcl 
   ```
   **Warning**: Do NOT use `read_bd` — it creates a reference to the original source; modifications may corrupt the golden.

6. **Import the NoC solution** to ensure boot-path consistency:
   
   # In the non-project project flow, before running implementation:

   ```tcl
      read_noc_solution -file <path_to_golden>/impl_1/<design>.ncr
   ```

   # In the project project flow, set NOC_SOLUTION_FILE property of implementation run:

   ```tcl
   set_property NOC_SOLUTION_FILE <path_to_golden>/impl_1/<design>.ncr [get_runs impl_1]
   ```
   Behind the scenes, this calls `read_noc_solution` before `place_design`.
   

7. **Address Aperture Flexibility** for variant designs:
   - In the golden design, define the **largest** aperture for all anticipated reload use cases
   - Variant designs may use a **subset** of that range (smaller aperture) — this is permitted
   - Variant designs may NOT exceed the golden aperture
   - Set apertures on INI ports to prevent overwrite during automated address assignment
   - `pr_verify` checks aperture consistency between golden and variant designs

8. **Run pr_verify** after route_design:
   ```tcl
   # The -initial DCP must be the golden (superset) design
   pr_verify -segcfg_only -initial <golden>_routed.dcp -additional <variant>_routed.dcp
   ```
   Resolve errors using the DRC reference from `/segcfg-design-check`.

9. **UID compatibility** — understand and preserve:
   - Unique ID of boot.pdi is a hash of the PS domain construction
   - ANY change to the PS domain (CIPS config, NoC, DDR) generates a new Unique ID
   - The PLD PDI's `parent_unique_id` must match the boot PDI's `unique_id` for PLM to accept it
   - Compartmentalize ALL changes to the PL domain only — keep PS domain frozen
   - Verify compatibility: `bootgen -arch versal -read <pdi>` and compare `unique_id` vs `parent_unique_id`

10. **Key restrictions for PL Reload**:
    - Mixed IO banks are supported but should be avoided — IO becomes active before PL loads and cannot change on reload
    - DFX within the PL is supported when Segmented Configuration is enabled starting from 2026.1 Vivado
    - For DFX + Segmented Configuration design scenarios ��� use `/segcfg-dfx` section of `design-entry` skills
    - PL Reload supported only within the same Vivado release (no cross-release forward migration yet for 2025.2)
    - For Gen 2 devices: avoid scenarios where both DDRMC5 ports are connected to PL domain (see Known Issues)
    - The golden design must be compiled in the same Vivado release as variant designs
    - Do not use `read_bd` (creates reference, not copy — may modify golden source)

11. **Compare Tiles in Boot Partition**:
    - Compare SegConfig_BootTiles.tcl (it contains information about Boot partition tiles) files in implementation directory of golden and reload/variant designs, located under hd_visual folder.
    - Files should match, confirming that the same tiles are assigned to the boot partition in both designs. Differences indicate a mismatch in PS domain configuration, which causes UID incompatibility.