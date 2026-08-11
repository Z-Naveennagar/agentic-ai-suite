# PetaLinux Build Guide for Segmented Configuration (Gen 1 Devices)

**Applies to**: First-generation Versal devices (VCK190, VEK280, VMK180, VPK120, VPK180, VHK158)
**Does NOT apply to**: Gen 2 devices — use Yocto/meta-xilinx-tools instead

Reference: [UG1144 - PetaLinux Tools Reference Guide](https://docs.amd.com/r/en-US/ug1144-petalinux-tools-reference-guide/Versal-Segmented-Configuration-Flow)

## Prerequisites

- PetaLinux 2025.2 installed
- XSA file from Vivado with `write_hw_platform -include_bit` (contains both boot.pdi and pld.pdi)
- Network access to download packages (or offline sstate cache configured)

## Machine Name Strings

| Board | Machine Name |
|-------|-------------|
| VCK190 | versal-vck190-reva-x-ebm-01-reva |
| VEK280 | versal-vek280-revb |
| VMK180 | versal-vmk180-reva-x-ebm-01-reva |
| VPK120 | versal-vpk120-revb |
| VPK180 | versal-vpk180-reva |
| VHK158 | versal-vhk158-revb |

## Full Build Procedure

### Step 1: Source PetaLinux Environment
```bash
source <path_to_installed_petalinux>/settings.sh
```

### Step 2: Create Project
```bash
petalinux-create -t project -n <project-name> --template versal
cd <project-name>
```

### Step 3: Configure with XSA (Command-Line Method)
```bash
# Set machine name (replace with your board's string)
sed -i '/CONFIG_SUBSYSTEM_MACHINE_NAME/ c\CONFIG_SUBSYSTEM_MACHINE_NAME="versal-vck190-reva-x-ebm-01-reva"' \
    project-spec/configs/config

# Enable FPGA Manager (required for runtime PL loading)
sed -i '/CONFIG_SUBSYSTEM_FPGA_MANAGER/ c\CONFIG_SUBSYSTEM_FPGA_MANAGER=y' \
    project-spec/configs/config

# Enable dfx-mgr package (userspace PL management daemon)
sed -i '/CONFIG_dfx-mgr/ c\CONFIG_dfx-mgr=y' \
    project-spec/configs/rootfs_config

# Apply XSA and run silent configuration
petalinux-config --silentconfig --get-hw-description=<path_to_xsa>
```

### Step 4: Create PLD Firmware Application
```bash
# IMPORTANT: app name must NOT contain underscores
petalinux-create -t apps \
    --template dfx_dtg_versal_full \
    --enable \
    -n <pld-firmware-app-name> \
    --srcuri "<path_to_xsa>"
```

This app:
- Generates the device tree overlay (.dtbo) from XSA hardware info
- Packages pld.pdi as a firmware file in `/lib/firmware/`

### Step 5: Build and Package
```bash
petalinux-build
petalinux-package --boot --format BIN --plm --psmfw --u-boot --dtb --force
```

## Output Files (images/linux/)

| File | Description | Used For |
|------|-------------|---------|
| `boot.bin` | Boot image: boot PDI + U-Boot + ATF + PLM + PSMFW | Primary boot from flash or SD |
| `boot.scr` | U-Boot boot script | SD/eMMC automatic boot |
| `image.ub` | FIT image: Kernel + DTB + rootfs | Linux boot |
| `system.dtb` | Separate device tree blob | Linux device enumeration |
| `rootfs.cpio.gz.u-boot` | Root filesystem (cpio) | Embedded in image.ub |

The PLD firmware app generates:
| File | Location | Description |
|------|----------|-------------|
| `<app-name>.pdi` | `/lib/firmware/` in rootfs | PLD programming image |
| `<app-name>.dtbo` | `/lib/firmware/` in rootfs | Device tree overlay for PL IP |

## Menuconfig Alternative

```bash
# Interactive configuration
petalinux-config --get-hw-description=<path_to_xsa>
# Navigate: DTG Settings → MACHINE_NAME
# Navigate: FPGA Manager → enable

petalinux-config -c rootfs
# Navigate: Filesystem Packages → base → dfx-mgr → enable
```

## Deploying to Board

### SD Card Boot
Copy to the FAT partition of an SD card:
```
boot.bin    boot.scr    image.ub
```

### JTAG Boot (Development)
```bash
petalinux-boot --jtag --u-boot --hw_server-url <hostname>:3121
```

## Runtime PL Loading

After Linux boots, use `fpgautil` to load the PL domain:
```bash
sudo fpgautil -b /lib/firmware/<app-name>.pdi -o /lib/firmware/<app-name>.dtbo
```

See `/segcfg-linux-runtime` for the full runtime flow.
