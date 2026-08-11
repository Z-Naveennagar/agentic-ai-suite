---
name: ps-software
description: Traditional Embedded Flow — PS firmware build from fixed .xsa through hsi::generate_bsp, application compile+link to .elf, and optional BOOT.BIN packaging. For AIE/acceleration designs, see the v++ flow in soc-orchestration/SKILL.md.
metadata:
  category: amd-soc-design
  tier: tutorial
  tags:
    - ps-software
    - firmware
    - baremetal
    - freertos
    - vitis
    - xsct
    - hsi
    - bootgen
    - elf
  complexity: intermediate
  estimated_duration: 5-15 minutes
  prerequisites_skills:
    - soc-orchestration
  related_skills:
    - soc-orchestration/partitioning
    - soc-orchestration/estimation
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# SKILL: PS Software Generation (Traditional Embedded Flow)

## Overview

This sub-skill generates C/C++ firmware for the PS (Processing System) blocks in a
PS+PL design and builds it end-to-end through the Vitis toolchain to produce a
linked `.elf` binary. It is invoked as **Phase 4b** of the soc-orchestration flow.

### Scope: Traditional Embedded Flow Only

This skill covers the **Traditional Embedded Flow** as defined by AMD (UG1273, UG1701).
It applies when:
- The PS acts as a **control processor** managing PL peripherals via AXI register I/O
- The design has **no AIE graphs** and **no HLS acceleration kernels** (.xo via Vitis kernel flow)
- The hardware is fully specified in Vivado IPI and exported as a **fixed XSA**

**This skill does NOT cover:**
- Designs with AIE graphs → use the **v++ flow** (`v++ --mode aie`, `v++ --link`)
- HLS kernels compiled via Vitis kernel flow → use `v++ --mode hls` + `v++ --link`
- XRT-based Linux host applications → compile against XRT headers with `aarch64-linux-gnu-gcc`

See the **Software Build Flow Selection** decision tree in `soc-orchestration/SKILL.md`
for guidance on choosing the correct flow.

### Build Pipeline

```
Vivado project
  └─ write_hw_platform ─▶ .xsa
                             │
                     xsct (hsi::generate_bsp)
                             │
                        BSP + libxil.a
                             │
              aarch64-none-elf-gcc (compile main.c)
                             │
              aarch64-none-elf-gcc (link against libxil.a)
                             │
                          app.elf
                             │
                     bootgen (optional)
                             │
                         BOOT.BIN
```

**Automation script:** `scripts/vitis_build.tcl` drives the entire flow from xsct.

## When to Invoke

1. The design spec contains at least one block with `workload_type: "bare_metal_firmware"`
2. Phase 4 (PL implementation) completed — a routed DCP exists
3. A `.hwh` file exists or can be generated via `write_hw_platform`

Skip for PL-only designs or AIE-only flows.

## Prerequisites

- **Vivado** with Vivado MCP for project interaction
- **xsct** at `/scratch/AMDDesignTools/2025.2/Vitis/bin/xsct`
- **Toolchains:**
  - Baremetal/FreeRTOS: `aarch64-none-elf-gcc` (Vitis-bundled)
  - Linux userspace: `aarch64-linux-gnu-gcc` (Vitis-bundled)
- **bootgen** at `/scratch/AMDDesignTools/2025.2/Vitis/bin/bootgen`
- **Scripts:**
  - `scripts/extract_addr_map.py` — address map extraction from .hwh
  - `scripts/vitis_build.tcl` — automated xsct build flow
  - `scripts/lscript_a53.ld` — linker script for Cortex-A53 bare-metal
- **Build directory:** Use `/scratch/` for build artifacts (disk quota on home may be limited)

## Step-by-Step Flow

### Step 1: Export Hardware Platform (.xsa)

From the Vivado project with a completed implementation run:

```tcl
# In Vivado (via MCP):
open_run impl_1
write_hw_platform -fixed -force <output_dir>/design.xsa
```

The `.xsa` bundles the `.hwh`, bitstream metadata, and processor configuration.

If the design failed bitstream generation due to I/O constraints (common for
test designs), `write_hw_platform -fixed` still works — it produces a valid .xsa
that is sufficient for firmware development.

### Step 2: Extract Address Map (Optional — for Code Generation)

```bash
python3 scripts/extract_addr_map.py <path_to.hwh> -o addr_map.json --pretty
```

This produces a JSON with all PL peripherals, their base/high addresses, IP types,
and interrupt connectivity. Use it to generate `platform_config.h` and guide the
LLM's code generation for `main.c`.

### Step 3: Generate Firmware Source Code

Generate `main.c` and `platform_config.h` based on the spec's PS block description
and the address map. See the **Code Templates** and **Driver API Reference** sections below.

**Output files placed in `tests/<spec_name>/firmware/`:**
- `platform_config.h` — base address `#define`s
- `main.c` — firmware source code

### Step 4: Run Full Build via vitis_build.tcl

The automated build script handles BSP generation, compilation, linking, and
produces a `.elf`:

```bash
export XILINX_VITIS_DATA_DIR=/scratch/nshirazi_vitis_data

xsct scripts/vitis_build.tcl \
  <path_to.xsa> \
  <firmware_source_dir> \
  <build_output_dir> \
  -os standalone \
  -proc psu_cortexa53_0 \
  -app-name <app_name>
```

**Arguments:**
| Argument | Description |
|----------|-------------|
| `<xsa_path>` | Path to the .xsa file from Step 1 |
| `<app_src_dir>` | Directory containing `main.c` and `platform_config.h` |
| `<build_dir>` | Build output directory (use `/scratch/` for space) |
| `-os` | `standalone` or `freertos` |
| `-proc` | Processor instance (e.g., `psu_cortexa53_0`, `psu_cortexr5_0`) |
| `-app-name` | Application name (used for .elf filename) |

**What the script does internally:**
1. `hsi::open_hw_design` — opens the .xsa (no Eclipse dependency)
2. `hsi::generate_bsp` — generates BSP with real `xparameters.h` and all driver sources
3. `make -C bsp/` — compiles BSP to `libxil.a`
4. `aarch64-none-elf-gcc -c` — compiles application sources
5. `aarch64-none-elf-gcc -T lscript_a53.ld` — links against `libxil.a` to produce `.elf`

**Success criteria:** The script exits with code 0 and reports `Link SUCCEEDED`.

### Step 5: Generate BOOT.BIN (Optional)

For designs that need a bootable image:

```bash
# Create a BIF file:
cat > boot.bif << 'EOF'
the_ROM_image: {
  [bootloader, destination_cpu=a53-0] <path_to_fsbl.elf>
  [pmufw_image] <path_to_pmufw.elf>
  [destination_device=pl] <path_to.bit>
  [destination_cpu=a53-0, exception_level=el-3] <path_to_app.elf>
}
EOF

bootgen -image boot.bif -arch zynqmp -o BOOT.BIN -w on
```

Note: FSBL and PMUFW are built as part of the platform in a full Vitis workspace.
For testing purposes, the `.elf` from Step 4 is the primary validation artifact.

## How it Works: hsi vs xsct platform create

The build script uses **`hsi` (Hardware Software Interface)** commands instead of
`xsct platform create` because:

1. **`hsi`** is a pure TCL API — no Eclipse/Vitis IDE backend required
2. **Works on headless servers** — no display, no Java, no timeouts
3. **Fast** — BSP generation completes in ~2 seconds
4. **Produces identical outputs** — same `xparameters.h`, same driver sources, same `libxil.a`

The `platform create` command in xsct 2025.2 internally launches the Vitis IDE
(Eclipse-based) which requires a working display and can timeout on remote servers.

## Code Templates

### Baremetal Template

```c
#include "platform_config.h"
#include "xil_printf.h"
#include "xstatus.h"
/* Include driver headers per peripheral */

int main(void)
{
    xil_printf("=== <design_name> firmware ===\r\n");

    /* 1. Initialize each peripheral */
    /* 2. Configure peripherals per spec */
    /* 3. Main application loop */

    return XST_SUCCESS;
}
```

### FreeRTOS Template

```c
#include "FreeRTOS.h"
#include "task.h"
#include "platform_config.h"
#include "xil_printf.h"

static void MainTask(void *pvParameters);

int main(void)
{
    /* Initialize hardware before scheduler */
    xTaskCreate(MainTask, "main", configMINIMAL_STACK_SIZE * 4, NULL, tskIDLE_PRIORITY + 1, NULL);
    vTaskStartScheduler();
    return XST_FAILURE;
}

static void MainTask(void *pvParameters)
{
    (void)pvParameters;
    for (;;) {
        /* Periodic application logic */
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}
```

### Linux Userspace Template

```c
#include <stdio.h>
#include <stdint.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>
#include "platform_config.h"

#define MAP_SIZE  0x10000

int main(int argc, char *argv[])
{
    int fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (fd < 0) { perror("open /dev/mem"); return 1; }

    /* mmap each peripheral's register space */
    /* Application logic */

    close(fd);
    return 0;
}
```

## Driver API Quick Reference

### AXI GPIO (`xgpio.h`)

```c
#include "xgpio.h"

XGpio Gpio;
XGpio_Initialize(&Gpio, AXI_GPIO_0_BASEADDR);
XGpio_SetDataDirection(&Gpio, 1, 0x0);  /* Channel 1, all output */
XGpio_DiscreteWrite(&Gpio, 1, 0xF);
u32 val = XGpio_DiscreteRead(&Gpio, 1);
```

### AXI Timer (`xtmrctr.h`)

```c
#include "xtmrctr.h"

XTmrCtr Timer;
XTmrCtr_Initialize(&Timer, AXI_TIMER_0_BASEADDR);
XTmrCtr_SetOptions(&Timer, 0, XTC_INT_MODE_OPTION | XTC_AUTO_RELOAD_OPTION | XTC_DOWN_COUNT_OPTION);
XTmrCtr_SetResetValue(&Timer, 0, TIMER_LOAD_VALUE);
XTmrCtr_SetHandler(&Timer, TimerHandler, &Timer);
XTmrCtr_Start(&Timer, 0);
```

### AXI DMA (`xaxidma.h`)

```c
#include "xaxidma.h"

XAxiDma Dma;
XAxiDma_Config *CfgPtr = XAxiDma_LookupConfig(AXI_DMA_0_BASEADDR);
XAxiDma_CfgInitialize(&Dma, CfgPtr);

u8 TxBuf[BUF_LEN] __attribute__((aligned(64)));
Xil_DCacheFlushRange((UINTPTR)TxBuf, BUF_LEN);
XAxiDma_SimpleTransfer(&Dma, (UINTPTR)TxBuf, BUF_LEN, XAXIDMA_DMA_TO_DEVICE);
while (XAxiDma_Busy(&Dma, XAXIDMA_DMA_TO_DEVICE));
```

### GIC / Interrupt Controller (`xscugic.h`)

```c
#include "xscugic.h"

XScuGic Gic;
XScuGic_Config *GicCfg = XScuGic_LookupConfig(XPAR_SCUGIC_0_DIST_BASEADDR);
XScuGic_CfgInitialize(&Gic, GicCfg, GicCfg->CpuBaseAddress);

Xil_ExceptionInit();
Xil_ExceptionRegisterHandler(XIL_EXCEPTION_ID_INT, (Xil_ExceptionHandler)XScuGic_InterruptHandler, &Gic);
Xil_ExceptionEnable();

XScuGic_Connect(&Gic, TIMER_IRQ_ID, (Xil_InterruptHandler)TimerIsr, &Timer);
XScuGic_Enable(&Gic, TIMER_IRQ_ID);
```

PL interrupt IDs for Zynq UltraScale+:
- `pl_ps_irq0[0]` → IRQ 121 through `pl_ps_irq0[7]` → IRQ 128
- `pl_ps_irq1[0]` → IRQ 136

### Driver-to-IP Mapping

| IP Type (from .hwh) | Driver | Header |
|---------------------|--------|--------|
| `axi_gpio`          | `gpio_v4_12` | `xgpio.h` |
| `axi_timer`         | `tmrctr_v4_14` | `xtmrctr.h` |
| `axi_dma`           | `axidma_v9_20` | `xaxidma.h` |
| `axi_vdma`          | `axivdma_v6_16` | `xaxivdma.h` |
| GIC (always present)| `scugic_v5_6` | `xscugic.h` |

## Structural Assertions

After generating code, verify before building:

1. **Address coverage**: Every peripheral in `addr_map.json` has a matching
   `#define` in `platform_config.h` and an `Initialize()` call in `main.c`
2. **Interrupt wiring**: Peripherals with `"interrupts"` in addr_map.json have
   `XScuGic_Connect` calls with correct IRQ IDs
3. **Cache management**: DMA transfers include `Xil_DCacheFlushRange` (TX) and
   `Xil_DCacheInvalidateRange` (RX) calls
4. **Buffer alignment**: DMA buffers use `__attribute__((aligned(64)))`
5. **FreeRTOS tasks**: If `os: "freertos"`, code uses `xTaskCreate` and
   `vTaskStartScheduler` — never bare `while(1)` in `main()`

## Output Artifacts

```
tests/<spec_name>/firmware/
    addr_map.json        # extracted from .hwh
    platform_config.h    # base address #defines
    main.c               # generated PS firmware
    <design>.xsa         # hardware platform export

/scratch/.../build/
    bsp/                 # hsi-generated BSP
        psu_cortexa53_0/
            include/     # xparameters.h + all driver headers
            lib/libxil.a # compiled BSP library
    app/                 # compiled objects
    <app_name>.elf       # linked firmware binary
```

## Processor Instances

| Architecture | Processor Instance | Toolchain Prefix |
|-------------|-------------------|-----------------|
| Zynq UltraScale+ APU | `psu_cortexa53_0` | `aarch64-none-elf-` |
| Zynq UltraScale+ RPU | `psu_cortexr5_0` | `arm-none-eabi-` |
| Versal APU | `psv_cortexa72_0` | `aarch64-none-elf-` |
| Versal RPU | `psv_cortexr5_0` | `arm-none-eabi-` |

## Troubleshooting

### xsct platform create times out
This is expected on headless servers — `platform create` requires Eclipse.
Use `hsi::generate_bsp` instead (this is what `vitis_build.tcl` does).

### Disk quota exceeded
Build to `/scratch/` instead of home directory. Set the build_dir argument
to a path under `/scratch/`.

### Multiple definition errors during link
The script filters out `psu_init.c` and `psu_init_gpl.c` from the source directory
(these contain overlapping PS initialization functions). Only `main.c` and
user-created files are compiled.

### Address conversion warnings (-Woverflow)
The BSP's non-SDT `Initialize()` functions accept `u16 DeviceId` but the generated
code passes `UINTPTR BaseAddress`. The code works correctly at runtime because
the driver internally maps from DeviceId to BaseAddress. These warnings are cosmetic.

### Missing linker script
The script uses `scripts/lscript_a53.ld` which defines memory regions, stack,
heap, and BSP-required symbols (`__el3_stack`, `__bss_start__`, etc.).

## Environment Setup

```bash
export XILINX_VITIS_DATA_DIR=/scratch/nshirazi_vitis_data
```

This is required because the Vitis tools check for minimum disk space in `~/.Xilinx/`
and the VITIS_DATA_DIR redirect avoids quota issues.

## References

- UG1400 — Vitis Unified Software Platform: Embedded Software Development
- UG1283 — Bootgen User Guide
- UG1209 — Zynq UltraScale+ MPSoC: Embedded Design Tutorial
- UG1725 — XSDB/XSCT Reference Guide
- Driver API headers in `$EMBEDDEDSW/XilinxProcessorIPLib/drivers/*/src/*.h`
