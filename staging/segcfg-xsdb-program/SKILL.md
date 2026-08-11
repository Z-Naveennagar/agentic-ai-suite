---
name: segcfg-xsdb-program
description: Program Versal hardware with Segmented Configuration boot.pdi and pld.pdi via XSDB (System Debugger). Use when testing PDI files directly without PetaLinux, verifying PS-only boot, or demonstrating deferred PL loading from a debug console.
metadata:
   author: George Ohanjanyan, AMD
allowed-tools: Read, Bash, Write
---

Guide the user through programming a Versal board with Segmented Configuration PDI files using XSDB.

## Instructions

1. 
   - Read `${CLAUDE_SKILL_DIR}/references/xsdb-guide.md` for XSDB commands and setup details.
   - Read `${CLAUDE_SKILL_DIR}/references/working-with-board.md` for detailed technical guidance about board farm and clusters.

2. Ask the user:
   - Which board they are using (VCK190, VEK280, etc.)
   - Whether they want to test boot-only, boot+PLD, or PL reload scenario
   - Location of their PDI files (typically `<project>.runs/impl_1/`)

3. **Hardware setup prerequisites**:
   - Connect the board via JTAG cable (USB or XVC)
   - Open a serial console for UART0 (baudrate 115200) to monitor boot messages
   - Optionally open a second serial terminal for the system controller console

4. **Step-by-step XSDB programming flow**:

   ```bash
   # Step 1: Start XSDB (from Vivado or Vitis)
   xsdb

   # Step 2: Connect to hardware server
   xsdb% connect

   # Step 3: Target the Versal device (target 1 = PMC/device level)
   xsdb% ta 1

   # Step 4: Program only the boot PDI (PS domain, DDR, hard blocks)
   xsdb% device program <project>.runs/impl_1/<design>_boot.pdi
   ```
   Watch the UART console — you should see PLM messages with no errors.

5. **Verify PS-only boot** (PL NOT yet accessible):
   ```bash
   # Attempt to read a PL-mapped memory location — should fail
   xsdb% mrd -force 0xa4000000
   # Expected: Memory read error at 0xA4000000. AP transaction timeout
   ```
   This confirms the PL memory space is not active until the PLD PDI is loaded.

6. **Power-cycle and program both PDIs** (full Segmented Configuration test):
   ```bash
   # Power cycle the board, then reconnect XSDB
   xsdb% connect
   xsdb% ta 1

   # Program boot PDI first
   xsdb% device program <project>.runs/impl_1/<design>_boot.pdi

   # Then immediately program the PLD PDI
   xsdb% device program <project>.runs/impl_1/<design>_pld.pdi
   ```

7. **Verify PL access after loading pld.pdi**:
   ```bash
   # Read from PL-mapped BRAM or AXI slave
   xsdb% mrd -force 0xa4000000
   # Expected: A4000000: 00000000

   # Write to PL memory
   xsdb% mwr -force 0xa4000000 0xdeadbeef

   # Verify write
   xsdb% mrd -force 0xa4000000
   # Expected: A4000000: DEADBEEF
   ```

8. **PL Reload test** (if multiple pld.pdi files exist):

   Always use the `goto_pmc` helper before every PLD reload. Do NOT use bare `ta 1`
   (target indices shift after boot.pdi executes) and do NOT call `target -set -filter`
   directly from a CPU context (fails on the 3rd+ reload with PLM Error 0x2101/0x36).

   ```tcl
   # Define once at the top of the script
   proc goto_pmc {} {
     ta 1
     after 500
     target -set -filter {name =~ "PMC*"}
     after 1000
   }

   # Before every PLD load
   goto_pmc
   device program <project>.runs/impl_1/<design2>_pld.pdi
   ```
   PLM will apply isolation, reconfigure PL, and release isolation automatically.

9. **Deliver PLD PDI to DDR then load** (alternative using dow):
   ```bash
   # Load PDI binary to DDR at address 0x1000000
   xsdb% dow -data <design>_pld.pdi 0x1000000
   ```
   This approach is useful when testing U-Boot fatload equivalence.

10. Remind the user that programming via XSDB is useful for pre-PetaLinux validation and interactive debugging, but production deployment should use PetaLinux/Yocto or U-Boot flows.
