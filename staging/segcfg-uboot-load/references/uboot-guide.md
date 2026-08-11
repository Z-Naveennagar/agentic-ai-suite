# U-Boot PLD Loading Guide for Segmented Configuration

## Overview

U-Boot can load the PLD PDI before the Linux kernel boots. This provides faster time-to-PL-ready compared to the Linux fpgautil flow, since PL is configured during the U-Boot stage of the boot sequence.

## Why U-Boot?

- PL is configured **before Linux boots** — drivers see a fully operational PL on first probe
- Avoids the need for fpgautil and device tree overlay application at runtime
- Useful for production systems where PL must be ready immediately after boot

## Boot Sequence with U-Boot PLD Load

```
Power On
  → PLM loads boot.pdi (PS, DDR, hard blocks)
  → U-Boot starts
  → [USER ACTION] Load pld.pdi from SD card or JTAG
  → PL is configured
  → U-Boot loads Linux kernel
  → Linux boots with PL fully ready
```

## Interrupting Autoboot

When the board boots, watch the UART console for:
```
Hit any key to stop autoboot:  3
```
Press any key within the countdown to enter the U-Boot prompt (`=> `).

## Loading PLD PDI from SD Card

```
# fatload: load a file from FAT filesystem
# Format: fatload <interface> <dev[:part]> <loadaddr> <filename>
# mmc 0 = SD card (MultiMediaCard 0)
# 0x1000000 = DDR staging address (~16MB into DDR)

=> fatload mmc 0 0x1000000 <design>_pld.pdi
```

After fatload succeeds, `$filesize` is automatically populated with the file size in bytes.

## Loading PLD PDI via JTAG (from XSDB)

While U-Boot is running (before Linux boots), use XSDB on the host:
```tcl
xsdb% dow -data <design>_pld.pdi 0x1000000
```
Then proceed with `fpga load` in U-Boot.

## Programming PL from DDR

```
# fpga load: send PDI from DDR to FPGA
# Format: fpga load <fpga_dev> <addr> <size>
# fpga_dev 0 = first FPGA device

=> fpga load 0 0x1000000 $filesize
```

## Verifying PL Access from U-Boot

```
# md: memory dump — read DDR or PL-mapped addresses
# Format: md <address> [count]
# count = number of 32-bit words to display

=> md 0xa4000000 1
a4000000: 00000000    ....

# mm: memory modify — interactive write
# Format: mm <address>
# Type hex values; press Ctrl+C to exit

=> mm 0xa4000000
a4000000: deadbeef
(Ctrl+C)

# Verify write
=> md 0xa4000000 1
a4000000: deadbeef    ....
```

## Continuing to Linux Boot

After PLD is loaded, boot Linux from SD card:
```
=> run bootcmd_mmc0
```

Or boot from TFTP:
```
=> run netboot
```

## U-Boot Environment Variables

```
# View all environment variables
=> printenv

# View specific variables relevant to boot
=> printenv bootcmd
=> printenv bootargs

# Set PLD load address
=> setenv pld_loadaddr 0x1000000
=> setenv pld_file <design>_pld.pdi

# Create a custom boot command that loads PLD first
=> setenv bootcmd_pld 'fatload mmc 0 ${pld_loadaddr} ${pld_file}; fpga load 0 ${pld_loadaddr} ${filesize}'
=> setenv bootcmd 'run bootcmd_pld; run bootcmd_mmc0'

# Save environment to flash (persists across power cycles)
=> saveenv
```

## Automating PLD Load in boot.scr

To automate PLD loading without manual U-Boot intervention, create a `boot.scr` script:

```bash
# On the host, create boot.cmd:
cat > boot.cmd << 'EOF'
fatload mmc 0 0x1000000 <design>_pld.pdi
fpga load 0 0x1000000 ${filesize}
run default_bootcmd
EOF

# Convert to boot.scr (binary U-Boot script):
mkimage -c none -A arm -T script -d boot.cmd boot.scr
```

Copy the resulting `boot.scr` to the SD card FAT partition.

## Reference

- [U-Boot Documentation](https://u-boot.readthedocs.io/en/latest/)
- U-Boot `fpga` command: `help fpga`
- U-Boot `fatload` command: `help fatload`
- U-Boot `md`/`mm` commands: `help md`, `help mm`
