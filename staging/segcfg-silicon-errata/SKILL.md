---
name: segcfg-silicon-errata
description: Explain the DFX GSC Frame Programming silicon bug affecting Segmented Configuration PL Reload and DFX on Gen 2 Versal devices. Use when a user reports unexpected current draw during reconfiguration, hits a write_device_image block, or needs to assess risk before deploying PL Reload on affected silicon.
metadata:
   author: George Ohanjanyan, AMD
allowed-tools: Read, Bash, Write
---

Explain the DFX GSC Frame Programming Bug, its implications for Segmented Configuration PL Reload and DFX, and guide the user on safe development practices.

## Instructions

1. State the **issue clearly**:
   - An emerging silicon bug affects DFX and Segmented Configuration PL Reload use cases
   - Found during silicon testing in June 2025
   - Root cause: GSC (Golden Sector Checker) frame programming behavior in second-generation Versal fabric

2. List **affected devices** (Gen 2 fabric only):
   | Device Family | Affected Parts |
   |---------------|----------------|
   | Versal AI Edge Series Gen 2 | XC2VE3858, XC2VE3804, XC2VE3558, XC2VE3504 |
   | Versal Prime Series Gen 2 | XC2VM3858, XC2VM3558 |
   | Versal RF Series ES1 | XCVR1652, XCVR1602 |

   Gen 1 Versal devices are **not affected**.

3. Explain the **implications**:
   - **Segmented Configuration PL Reload IS impacted** when the boot.pdi and pld.pdi contain different PL images
   - One-time programming of PL or identical reprogramming of the same PL image is **NOT impacted**
   - EDF reload flows utilize PL Reload and are also impacted
   - **DFX IS impacted** for all dynamic reload use cases — currently loaded RM logic may glitch and/or have contention during reconfiguration

4. Clarify **observed behavior**:
   - No functional change in design behavior has been confirmed from silicon testing
   - Device damage is **NOT expected** even with contention and crowbar current — safe to continue development and testing
   - Current draw is higher than specified during reconfiguration, but still below full-design operating current
   - No logic corruption or data loss was observed in silicon testing

5. State the **software guardrails in place** (through Vivado 2025.1.1):
   - DFX PDI generation is blocked by a parameter check at `write_device_image` for affected ES1 devices
   - PL Reload for production silicon is **NOT blocked** in software — users must avoid it voluntarily for production use
   - Production silicon PL Reload should be treated as engineering/development use only until 2025.2

6. Explain **next steps and resolution timeline**:
   - No silicon changes to existing tapeouts — impact deemed too minor to require repair on current production runs
   - A software fix in **Vivado 2025.2** is in development to reduce current draw during reconfiguration; change is contained within `write_device_image`
   - Subsequent tapeouts (Versal RF production, additional Gen 2 AI Edge / Prime / Premium devices) will have the silicon issue repaired

7. Provide **practical guidance** for the user's situation:
   - If evaluating or developing with affected silicon: continue development; no device damage risk
   - For production deployments requiring PL Reload: wait for Vivado 2025.2 software fix
   - For one-time PL programming (no reload): fully supported and unaffected
   - For DFX use cases on ES1 parts: PDI generation is blocked; upgrade to 2025.2 when available
   - Check AMD GitHub documentation under `Versal/Boot_and_Config/Segmented_Configuration` for updates

8. Ask the user:
   - Which device and Vivado version they are using
   - Whether they need PL Reload for development only or for production deployment
   - Whether they are also using DFX in combination with Segmented Configuration
