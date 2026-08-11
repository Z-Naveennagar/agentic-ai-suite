---
name: segcfg-yocto-build
description: Build Yocto/meta-xilinx-tools images for a second-generation Versal Segmented Configuration design. Use when generating firmware recipes for Gen 2 devices (Versal AI Edge Gen 2, Prime Gen 2). For first-generation devices, use /segcfg-petalinux-build instead.
metadata:
   author: George Ohanjanyan, AMD
argument-hint: "[path-to-xsa]"
allowed-tools: Read, Bash, Write
---

Guide the user through building Yocto-based firmware images for second-generation Versal Segmented Configuration designs.

## Instructions

1. Read `${CLAUDE_SKILL_DIR}/references/yocto-guide.md` for layer setup, machine configuration, and recipe details.

2. **Important scope check**: Confirm the target is a second-generation Versal device.
   - **Gen 2 devices** (2VE3804, 2VE3858, 2VM3858, etc.): Use Yocto as described here
   - **First-gen devices**: Direct the user to `/segcfg-petalinux-build`

3. **Official Yocto build instructions**:
   The AMD meta-xilinx-tools layer provides the `dfx.dtg.versal.full` build recipe. Direct the user to the official documentation:
   ```
   https://github.com/Xilinx/meta-xilinx-tools/blob/rel-v2025.2/docs/README.dfx.dtg.versal.full.md
   ```

4. **Prerequisites**:
   - Yocto Project environment with AMD BSP layers set up
   - XSA file exported from Vivado with `write_hw_platform -include_bit` (contains both PDIs)
   - Supported layers: `meta-xilinx`, `meta-xilinx-tools`, `meta-xilinx-standalone`

5. **Key Yocto layers and recipes**:
   ```
   meta-xilinx-tools/
   └── recipes-bsp/
       └── dfx-mgr/         # dfx-mgr daemon for runtime PL loading
   ```
   The `dfx_dtg_versal_full` recipe:
   - Parses the XSA to generate the device tree overlay (.dtbo)
   - Packages the pld.pdi as a firmware file deployed to `/lib/firmware/`
   - Creates the `<design>-pld.pdi` and `<design>-pld.dtbo` in the rootfs

6. **Machine configuration** — set the MACHINE variable for your Gen 2 board:
   ```bash
   # In your build/conf/local.conf or site.conf:
   MACHINE = "versal-gen2-<board>"
   ```
   Refer to the yocto-guide.md reference for specific machine names.

7. **Build command flow** (after layers and machine are configured):
   ```bash
   source <yocto-env>/oe-init-build-env build/

   # Add the XSA to the build
   # (board-specific — consult the meta-xilinx-tools README for exact steps)

   bitbake <image-recipe>
   ```

8. **Runtime deployment**:
   - The Yocto image includes `dfx-mgr` daemon pre-installed
   - PLD PDI is placed in `/lib/firmware/`
   - Load PLD using `fpgautil` or the dfx-mgr daemon — see `/segcfg-linux-runtime`

9. **Key differences from first-gen PetaLinux build**:
   - PetaLinux for Gen 1 is NOT used for Gen 2 devices — Yocto native flow is required
   - VCU and ISP tiles are included in the PLD PDI for Gen 2 devices
   - ASU soft crypto extension (if enabled) is also programmed by the PLD PDI

10. Provide the user the GitHub link for the official AMD Yocto Segmented Configuration build instructions and encourage them to follow that guide exactly, as it is maintained for each tool release.
