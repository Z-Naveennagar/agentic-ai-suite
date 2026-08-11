---
name: segcfg-roadmap
description: Explain upcoming Segmented Configuration enhancements on the AMD Vivado roadmap — PS/PL interface flexibility, Segmented Configuration + DFX, combined PDI, Function ID, and future device support. Use when a user asks what features are coming, plans a design for a future Vivado release, or evaluates whether to wait for a capability.
metadata:
   author: George Ohanjanyan, AMD
allowed-tools: Read, Bash, Write
---

Describe Segmented Configuration roadmap features, their planned availability, and guidance on how to design today to be ready for upcoming capabilities.

## Instructions

1. Explain **PS/PL Interface Flexibility for PL Reload** (planned Early Access in Vivado 2025.2):
   - Lead device: Versal AI Edge Series Gen 2
   - Production and all remaining devices planned for 2026.1

   **What will be allowed to change between PL images:**
   - PMC and LPD GPIO data width
   - LPD and FPD interfaces (AXI, DTI, ACP, CHI, etc.)
   - EMIO/FMIO, EAM signals
   - ASU–PL interfaces
   - PMC PL resets and PMC interrupts
   - Add, remove, or modify PS-PL port connections

   **What will NOT be permitted to change:**
   - PMC PL clock frequencies must remain fixed — use PL-side clock management to adjust frequency within PL
   - MMI and CPM interface connections cannot change
   - DRCs and `pr_verify` will enforce these constraints

2. Explain **Segmented Configuration + DFX** (planned Early Access in Vivado 2025.2):
   - Lead device: Versal AI Edge Series Gen 2
   - Production and all remaining devices planned for 2026.1

   **What this enables:**
   - Support both features in a single design simultaneously
   - Swap at PL level (entire PL reload) OR at RP level (user-defined pblock within PL)
   - Behaves essentially like Nested DFX: PL domain is the outer static shell, RPs are dynamic regions within it

   **System design implications:**
   - System must manage PL swaps at multiple levels (PL reload + DFX RM reloads)
   - Standard DFX techniques for RPs apply: decouple, initialize, reconfigure
   - Device tree overlays must be managed at the target level

   **Compatibility assurance:**
   - DRCs and `pr_verify` check compatibility at each level (boot↔PL and PL↔RP)
   - UID checks confirm incoming image compatibility at every level of hierarchy

3. Explain the **Combined PDI** roadmap item (requested for 2026.1):
   - Simplifies EOU (Ease of Use) when a single one-time programming image is needed
   - Merges BIF contents to produce a single PDI from the segmented design
   - The resulting combined PDI retains segmented characteristics internally — it is not converted to a monolithic flow
   - A request has been made to enable an IDE option for automatic merging

4. Explain the **Function ID** roadmap item:
   - Will allow users to apply their own identifier on each programming partition (Segmented or DFX)
   - Requires a corresponding mechanism to query the PDI header so custom PLM checks can be built
   - Useful for fleet management and ensuring the correct PL variant is loaded for a given use case

5. Explain **Future Device Support** direction:
   - All new adaptive SoC devices going forward will ONLY support Segmented Configuration
   - Versal RF Series is the last device family where Segmented Configuration is optional
   - RF Series contains updated fabric and new features but is NOT branded "Gen 2"
   - Gen 2 devices (AI Edge, Prime, Premium) have Segmented Configuration always enabled

6. Present a **planning table** for the user:

   | Feature | 2025.1 | 2025.2 (EA) | 2026.1 (Production) |
   |---------|--------|-------------|----------------------|
   | PL Reload (current restrictions) | GA | — | — |
   | PS/PL Interface Flexibility | — | EA (Gen 2) | All devices |
   | Segmented Config + DFX | — | EA (Gen 2) | All devices |
   | Combined PDI option | — | — | Requested |
   | Function ID | — | — | Planned |
   | GSC Frame Bug SW Fix | — | In dev | — |

7. Advise the user on **designing today for future compatibility**:
   - Use a second NoC IP instance for PL-side NoC paths — this naturally keeps PS NoC stable across reload variants
   - Define the golden design as a superset of all anticipated boundary connections — flexibility additions in 2025.2 will build on this approach
   - Avoid hardcoding PMC PL clock frequencies in PL logic — use PL clock management IPs
   - If DFX + Segmented Configuration is anticipated, structure the pblock early

8. Ask the user what they are planning:
   - Are they targeting 2025.2 Early Access features or waiting for 2026.1 production?
   - Do they need DFX within the PL domain?
   - Are they considering combined PDI for manufacturing/provisioning?
