<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Platform Pitfalls — Zynq UltraScale+ and Versal

Device-family-specific pitfalls learned from real builds. Consult this file before
Phase 4 implementation and during v++ link troubleshooting.

---

## Zynq UltraScale+ DPU Pitfalls

### DPU Encrypted RTL — Cannot Swap dpu_conf.vh Post-Build

The DPUCZDX8G RTL is encrypted (`.vp` files). Architecture parameters from `dpu_conf.vh`
are baked into the IP during the TRD's packaging step. Dropping a different `dpu_conf.vh`
into a pre-built XO does NOT change the architecture — the encrypted netlists are already
parameterized. You must regenerate the XO from scratch for each DPU arch. See
`vitis-acceleration/SKILL.md` Step 1 for the correct procedure.

### IP Cache Serves Stale DPU Architecture

After generating a DPU XO with one architecture (e.g., B1024), changing to B512 and
regenerating may still produce a B1024 kernel due to Vivado's IP cache. Always:
1. Delete the `.ipcache` directory before regenerating
2. Bump the version in `component.xml` to force re-synthesis
3. Verify the output XO with `unzip -o <xo> kernel.xml && grep S_AXI_CONTROL kernel.xml`

### PFM Control Master — M_AXI_HPM0_FPD Must Be Tagged

The DPUCZDX8G has an `S_AXI_CONTROL` AXI-Lite slave. The v++ linker needs an `M_AXI_GP`
tagged port in the platform to connect it. On Zynq UltraScale+, tag `M_AXI_HPM0_FPD`
(or HPM1) directly on the PS8 — do NOT pre-connect through a SmartConnect. See
`vitis-platform/SKILL.md` for details.

### PS8 PL Clock Frequency Is Never Exact

PS8 PL clocks are PLL-derived and never hit round numbers (e.g., 249.997498 MHz instead
of 250 MHz). When connecting a clocking wizard for DPU (300/600 MHz), use the exact
frequency from `CONFIG.PSU__CRL_APB__PLn_REF_CTRL__ACT_FREQMHZ`, not a rounded value.

---

## Versal Platform Pitfalls

### CRITICAL: Custom Platform PS-NoC Clock Routing Failure

**Problem:** Manually creating `axi_noc` IP instances in Vivado and connecting them to
CIPS PS CCI / PS RPU / PS PMC interfaces causes `v++ --link` to fail during VPL
implementation with:
```
ERROR: [VPL 35-19] Pin mapping failure, cannot reach driver pin:
  .../PSPSNOCCCIAXI0CLK at site PS9_X0Y0
```

**Root cause:** The `noc_nmu` sub-IP generated inside a manually created `axi_noc` is
always a PL-type NMU with fabric clocking. Even when `CONFIG.CATEGORY` is set to
`ps_cci` at the BD level, the generated NMU still expects PL clock routing. However,
PS CCI dedicated NMU sites (e.g., `NOC_NMU128_X0Y6`) require direct clock routing
from the PS9 hard block — these dedicated clock paths are only established by Vivado's
board automation during initial platform creation or by vendor-provided base platforms.

**Resolution:** For `v++ --link` flows on Versal, **always use AMD-provided base
platforms** (e.g., `xilinx_vck190_base_202520_1`) rather than custom-built platforms,
unless the custom platform was generated through the full Vivado Platform Creation
Wizard with board automation (not manual Tcl NoC construction).

### Versal Implementation Directives

Not all Vivado implementation directives are valid for Versal devices:
- `EarlyBlockPlacement` is **NOT valid** for Versal `PLACE_DESIGN`. Use `Explore`
  or other Versal-supported directives instead (see UG904 for the full list).
- Versal does not support `Performance_ExploreWithRemap` in all contexts — verify
  directive compatibility with `vivado_doc_search` before specifying in `system.cfg`.

### Custom HLS Data Movers vs DMA IP

For `v++ --link` kernel-based designs, **custom HLS mm2s/s2mm data movers** are
preferred over `axi_dma` IP blocks in the platform:
- HLS data movers compile as `.xo` files and integrate cleanly via `v++ stream_connect`
  and `sp=` directives
- They avoid the complexity of platform-embedded DMA IP (interrupt routing, address
  space conflicts, AXI interconnect overhead)
- 128-bit AXI-Stream width matches AIE PLIO bandwidth requirements
- They are instantiated by v++ (`nk=mm2s:1:mm2s_1`) rather than fixed in the BD
