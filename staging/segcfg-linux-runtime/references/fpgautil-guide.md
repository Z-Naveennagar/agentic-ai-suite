# fpgautil Runtime Guide for Segmented Configuration

## Overview

`fpgautil` is a Linux userspace utility for loading FPGA/PL programming images at runtime. It uses the FPGA Manager framework and device tree overlays to:
1. Deliver the PLD PDI to the Versal PL domain
2. Apply and remove device tree overlays for PL-based IP
3. Trigger driver binding/unbinding via dfx-mgr

## Prerequisites

- Linux booted with boot.pdi (PS domain, DDR active)
- `dfx-mgr` package installed (enabled in PetaLinux or Yocto build)
- PLD firmware files in `/lib/firmware/`:
  - `<design>_pld.pdi` or `<app-name>.pdi`
  - `<app-name>.dtbo` (device tree overlay)

## Command Reference

### Load PLD PDI
```bash
sudo fpgautil -b /lib/firmware/<app-name>.pdi -o /lib/firmware/<app-name>.dtbo
```

| Option | Description |
|--------|-------------|
| `-b <file>` | PDI bitstream file path |
| `-o <file>` | Device tree overlay (.dtbo) file path |

### Remove PL Image (Required Before Reload)
```bash
sudo fpgautil -R
```
This removes the current PL image and its device tree overlay. **Must be run before loading a new PLD PDI.**

### Query PL Status
```bash
# Check FPGA Manager state
cat /sys/class/fpga_manager/fpga0/state
# Expected values: operating, firmware request, etc.

# List loaded overlays
ls /sys/kernel/config/device-tree/overlays/
```

## Complete PL Load Flow

```bash
# Step 1: Verify boot-only state (optional sanity check)
devmem 0xa4000000
# If PL not loaded: Bus error or timeout

# Step 2: Load PLD PDI with device tree overlay
sudo fpgautil -b /lib/firmware/<app-name>.pdi -o /lib/firmware/<app-name>.dtbo

# Step 3: Verify PL is accessible
devmem 0xa4000000
# Expected: 0x00000000 (BRAM reset value)

# Step 4: Test write/read
devmem 0xa4000000 32 0xdeadbeef
devmem 0xa4000000
# Expected: 0xDEADBEEF
```

## PL Reload Flow

```bash
# Step 1: Remove current PL image
sudo fpgautil -R

# Step 2: Load new PLD PDI variant
sudo fpgautil -b /lib/firmware/<new_app-name>.pdi -o /lib/firmware/<new_app-name>.dtbo

# Step 3: Verify new PL behavior
devmem 0xa4000000
# Result depends on new PL design
```

## devmem Command Reference

```bash
# Read 32-bit value from address
devmem <address>
devmem 0xa4000000

# Write 32-bit value to address
devmem <address> <width> <value>
devmem 0xa4000000 32 0xdeadbeef

# Read 64-bit value
devmem 0xa4000000 64
```

## Boot via JTAG (Development Flow)

```bash
# On host machine: start hardware server
hw_server

# Set up TFTP for Linux images
tftpd "<path_to_petalinux_project>/images/linux"

# Boot target via JTAG
petalinux-boot --jtag --u-boot --hw_server-url <hostname>:3121
```

## Considerations for PL Reload

| Concern | Guidance |
|---------|---------|
| Kernel driver state | Unload PL-based drivers before `fpgautil -R`; reload after new PLD loads |
| Application activity | Pause PL-accessing applications during reload |
| CPM Root Port | Must be held in reset during reload; re-initialize after PL loads |
| Memory-mapped IO | Address mappings may change if new PL design uses different IP at different addresses |
| Device tree | New .dtbo adds/removes device nodes; drivers bind/unbind automatically if dfx-mgr is used |

## File Locations

```
/lib/firmware/                 ← PLD PDI and DTBO files
/sys/class/fpga_manager/       ← FPGA Manager sysfs interface
/sys/kernel/config/device-tree/overlays/  ← Loaded DT overlays
```

## Reference

- [UG1144 - PetaLinux Tools Reference Guide](https://docs.amd.com/r/en-US/ug1144-petalinux-tools-reference-guide)
- [meta-xilinx-tools dfx.dtg.versal.full](https://github.com/Xilinx/meta-xilinx-tools/blob/rel-v2025.2/docs/README.dfx.dtg.versal.full.md)
