---
name: segcfg-petalinux-build
description: Build PetaLinux images for a first-generation Versal Segmented Configuration design. Use when generating boot.bin, image.ub, and PLD firmware app from an XSA exported by Vivado. For second-generation devices (Gen 2), use /segcfg-yocto-build instead.
metadata:
   author: George Ohanjanyan, AMD
argument-hint: "[path-to-xsa]"
allowed-tools: Read, Bash, Write
---

Guide the user through building PetaLinux images for a first-generation Versal Segmented Configuration design.

## Instructions

1. Read `${CLAUDE_SKILL_DIR}/references/petalinux-guide.md` for detailed configuration options and output file descriptions.

2. **Important scope check**: Ask whether the target is a first-generation or second-generation Versal device.
   - **First-gen** (VCK190, VEK280, VPK120, VMK180, etc.): Use PetaLinux as described here
   - **Gen 2** (2VE3858, 2VM3858, etc.): Use Yocto — direct the user to `/segcfg-yocto-build`

3. **Prerequisites**:
   - PetaLinux 2025.2 installed and `settings.sh` sourced
   - XSA file exported from Vivado with `write_hw_platform -include_bit` (contains both boot.pdi and pld.pdi)
   - If `$ARGUMENTS` provided, use it as the XSA path; otherwise ask the user

4. **Step 1 — Set up the PetaLinux environment**:
   ```bash
   source <path_to_installed_petalinux>/settings.sh
   ```

5. **Step 2 — Create the PetaLinux project**:
   ```bash
   petalinux-create -t project -n <project-name> --template versal
   cd <project-name>
   ```

6. **Step 3 — Configure with XSA** (choose menuconfig or command-line method):

   *Command-line method (recommended for automation):*
   ```bash
   # Set machine name for your board (e.g., VCK190)
   sed -i '/CONFIG_SUBSYSTEM_MACHINE_NAME/ c\CONFIG_SUBSYSTEM_MACHINE_NAME="versal-vck190-reva-x-ebm-01-reva"' \
       project-spec/configs/config

   # Enable FPGA Manager
   sed -i '/CONFIG_SUBSYSTEM_FPGA_MANAGER/ c\CONFIG_SUBSYSTEM_FPGA_MANAGER=y' \
       project-spec/configs/config

   # Enable dfx-mgr package
   sed -i '/CONFIG_dfx-mgr/ c\CONFIG_dfx-mgr=y' \
       project-spec/configs/rootfs_config

   # Apply XSA
   petalinux-config --silentconfig --get-hw-description=<path_to_xsa>
   ```

   *Menuconfig method:*
   ```bash
   petalinux-config --get-hw-description=<path_to_xsa>
   # Navigate: DTG Settings → MACHINE_NAME → enter board name
   # Navigate: FPGA Manager → enable
   # petalinux-config -c rootfs → Filesystem Packages → base → dfx-mgr → enable
   ```

7. **Step 4 — Create a PLD firmware app**:
   ```bash
   # Note: app name must NOT contain underscores
   petalinux-create -t apps --template dfx_dtg_versal_full --enable \
       -n <pld-firmware-app-name> \
       --srcuri "<path_to_xsa>"
   ```
   The app packages the pld.pdi and generates the device tree overlay (.dtbo) needed by fpgautil.

8. **Step 5 — Build and package**:
   ```bash
   petalinux-build
   petalinux-package --boot --format BIN --plm --psmfw --u-boot --dtb --force
   ```

9. **Output files** (in `images/linux/`):

   | File | Description |
   |------|-------------|
   | `boot.bin` | Boot image: boot PDI + U-Boot + ATF + PLM + PSMFW |
   | `boot.scr` | U-Boot boot script for SD/eMMC boot modes |
   | `image.ub` | Flat image: Kernel + DTB + rootfs |
   | `system.dtb` | Device tree blob |
   | `rootfs.cpio.gz.u-boot` | Root filesystem (cpio format) |

10. Remind the user:
    - The PLD firmware app (`<pld-firmware-app-name>.pdi`) is placed in `/lib/firmware/` on the rootfs
    - Load PLD at runtime using `fpgautil` — see `/segcfg-linux-runtime`
    - For next steps: copy output files to SD card or use TFTP/JTAG boot
