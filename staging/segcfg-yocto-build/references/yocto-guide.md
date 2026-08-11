# Yocto Build Guide for Segmented Configuration (Gen 2 Devices)

**Applies to**: Second-generation Versal devices (Versal AI Edge Gen 2, Versal Prime Gen 2, Versal Premium Gen 2)
**Does NOT apply to**: First-generation Versal devices — use PetaLinux instead

## Official Reference

AMD Yocto Segmented Configuration build instructions:
```
https://github.com/Xilinx/meta-xilinx-tools/blob/rel-v2025.2/docs/README.dfx.dtg.versal.full.md
```

Follow the above guide as the primary source. This reference provides supplementary context.

## AMD Yocto Layer Stack

| Layer | Purpose |
|-------|---------|
| `meta-xilinx` | Versal machine configurations and BSP recipes |
| `meta-xilinx-tools` | Vivado-based firmware recipes (dfx-mgr, dtg, etc.) |
| `meta-xilinx-standalone` | Standalone (bare-metal) firmware recipes |
| `meta-openembedded` | OpenEmbedded base layers |

## Key Recipes

### dfx_dtg_versal_full
This recipe handles the Gen 2 Segmented Configuration firmware build:
- Parses the XSA to extract hardware info and generate device tree overlay
- Packages `<design>_pld.pdi` as firmware in `/lib/firmware/`
- Creates `.dtbo` for device tree overlay loading via dfx-mgr

### dfx-mgr
The DFX Manager daemon:
- Manages runtime loading and unloading of PL PDI images
- Works with device tree overlays for device driver binding/unbinding
- Pre-installed in AMD reference images

## Differences from PetaLinux (Gen 1)

| Aspect | PetaLinux (Gen 1) | Yocto (Gen 2) |
|--------|-------------------|---------------|
| Build system | PetaLinux wrapper over Yocto | Native Yocto |
| Configuration entry | petalinux-create, petalinux-config | bitbake, local.conf, bblayers.conf |
| Firmware app | petalinux-create -t apps dfx_dtg_versal_full | dfx_dtg_versal_full recipe directly |
| VCU/ISP packaging | Not applicable (Gen 1) | Bundled in pld.pdi recipe |
| ASU crypto extension | Not applicable | Packaged as part of pld.pdi |

## Gen 2 Specific Firmware Components in pld.pdi

The following Gen 2 components are included in the PLD PDI because they depend on PL clock resources:
- VCU (Video Codec Unit) tiles
- ISP (Image Signal Processor) tiles
- ASU soft crypto extension (if enabled in PS Wizard)

The Yocto `dfx_dtg_versal_full` recipe handles packaging these automatically from the XSA.

## Board-Specific Notes

### VEK385 (xc2ve3858)
- Versal AI Edge Gen 2 evaluation board
- Segmented Configuration always enabled
- Use Gen 2 Yocto flow (not PetaLinux)
- DDRMC5 restrictions apply for PL Reload — see AR39028

## Useful Yocto Variables (in local.conf)

```bitbake
# Set target machine
MACHINE = "versal-gen2-<board>"

# Point to XSA file
HDF_PATH = "<absolute_path_to_xsa>"

# Enable FPGA Manager
MACHINE_FEATURES += "fpga-overlay"
```

## Runtime Notes

After building and deploying the Yocto image:
- The dfx-mgr daemon handles automatic PL loading on startup (if configured)
- Manual PL loading uses `fpgautil` as with Gen 1 PetaLinux
- See `/segcfg-linux-runtime` for the complete runtime flow
