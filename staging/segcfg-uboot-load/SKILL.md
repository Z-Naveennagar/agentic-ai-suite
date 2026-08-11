---
name: segcfg-uboot-load
description: Load the PLD PDI via U-Boot using fatload and fpga commands. Use when you want to load PL before Linux boots, delivering the PL image from SD card or JTAG as an alternative to the Linux fpgautil flow.
metadata:
   author: George Ohanjanyan, AMD
allowed-tools: Read, Bash, Write
---

Guide the user through loading a Segmented Configuration PLD PDI via U-Boot, enabling PL to be configured before the Linux kernel boots.

## Instructions

1. Read `${CLAUDE_SKILL_DIR}/references/uboot-guide.md` for U-Boot command reference and boot script customization options.

2. Ask the user:
   - Where the pld.pdi file is located (SD card or to be JTAG-transferred)
   - Whether they want to manually interrupt autoboot or modify the boot script
   - Target DDR address to use as staging area (recommend 0x1000000 if available)

3. **Why use U-Boot for PLD loading**:
   - U-Boot runs before the Linux kernel — PL is configured earlier in the boot sequence
   - Linux sees a fully configured PL on startup — no need for post-boot fpgautil call
   - Ideal for production flows where PL must be ready before any driver is probed

4. **Place pld.pdi on the SD card**:
   - Copy `<design>_pld.pdi` to the SD card FAT partition along with `boot.bin`, `boot.scr`, `image.ub`

5. **Boot to U-Boot prompt** (interrupt autoboot):
   ```bash
   # Boot via JTAG or SD card; watch the UART console
   petalinux-boot --jtag --u-boot --hw_server-url <HostName>:3121

   # When the console shows "Hit any key to stop autoboot"
   # press any key within the timeout window
   ```
   You are now at the U-Boot prompt.

6. **Load PLD PDI from SD card to DDR**:
   ```
   # fatload: load file from FAT filesystem
   # Syntax: fatload <interface> <dev[:part]> <loadaddr> <filename>
   # mmc 0 = SD card (MultiMediaCard 0)
   # 0x1000000 = DDR staging address (must have enough space for the PDI)
   fatload mmc 0 0x1000000 <design>_pld.pdi
   ```
   After fatload, `$filesize` is automatically set to the number of bytes loaded.

7. **Alternative: Load PLD PDI via JTAG** (from XSDB):
   ```bash
   # In XSDB on the host machine, while U-Boot is running:
   xsdb% dow -data <design>_pld.pdi 0x1000000
   ```
   Then use the `fpga load` command in U-Boot as shown below.

8. **Program PLD PDI from DDR to FPGA**:
   ```
   # fpga load: download PDI data from DDR to the FPGA
   # Syntax: fpga load <fpga_dev> <addr> <size>
   fpga load 0 0x1000000 $filesize
   ```
   The PDI downloads to the Versal device. PL is now configured.

9. **Verify PL access from U-Boot**:
   ```
   # md: memory dump (read PL-mapped AXI address)
   # Second parameter = number of 32-bit words to display
   md 0xa4000000 1
   # Expected: a4000000: 00000000   ....

   # mm: memory modify (interactive write)
   mm 0xa4000000
   deadbeef        <-- type the value and press Enter
   (Press Ctrl+C to exit mm)

   # Read back to verify
   md 0xa4000000 1
   # Expected: a4000000: deadbeef   ....
   ```

10. **Continue to Linux boot after PLD load**:
    ```
    # Boot from SD card using the default boot command
    run bootcmd_mmc0
    ```
    Linux will boot with PL already configured. PL drivers will find their peripherals ready.

11. **Automate PLD load in U-Boot boot script** (boot.scr customization):
    For production, add fatload + fpga load commands to the boot.scr or U-Boot environment so PLD is loaded automatically during every boot without manual intervention.

12. For more U-Boot commands, refer to the [official U-Boot documentation](https://u-boot.readthedocs.io/en/latest/).
