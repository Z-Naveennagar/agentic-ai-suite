<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Vitis Python API Cheatsheet — XSA App Flow

Source: UG1400 / UG400 (Vitis 2025.2)

---

## Client Setup

```python
import vitis
client = vitis.create_client()
client.set_workspace(path="./my_workspace")
```

---

## create_platform_component

```python
platform = client.create_platform_component(
    name         = "my_platform",
    hw_design    = "/path/to/design.xsa",   # XSA path OR built-in board name
    cpu          = "psu_cortexa53_0",
    os           = "standalone",             # "standalone" | "linux" | "aie_runtime"
    domain_name  = "standalone_psu_cortexa53_0",
    generate_dtb = False,                   # True for linux on ZynqMP/Versal
    architecture = "64-bit",                # optional: "32-bit" | "64-bit"
    compiler     = "gcc",                   # optional: only needed for emu_design XSA
)
platform.build()
xpfm = client.find_platform_in_repos("my_platform")
```

---

## create_app_component

```python
app = client.create_app_component(
    name     = "my_app",
    platform = "/path/to/platform.xpfm",
    domain   = "standalone_psu_cortexa53_0",
    template = "hello_world",
)
app.build()
```

### Common Templates

| Template | Use Case |
|----------|----------|
| `hello_world` | Standalone hello world (most common) |
| `empty_application` | Blank project for custom sources / linux |
| `peripheral_tests` | PS peripheral test suite |
| `lwip_echo_server` | LwIP TCP/UDP echo server |
| `freertos_hello_world` | FreeRTOS hello world |
| `zynqmp_fsbl` | ZynqMP First Stage Boot Loader |
| `versal_plm` | Versal Platform Loader and Manager |
| `versal_psmfw` | Versal PSM Firmware |

---

## import_files

```python
app.import_files(
    from_loc        = "/path/to/src",
    files           = ["main.c", "utils.c"],
    dest_dir_in_cmp = "src",
)
```

---

## vitis.dispose

```python
vitis.dispose()   # Always call; wrap in try/finally
```

---

## Supported Device Families & Processor Cores

### Zynq-7000 (`processing_system7`, ARCH: `zynq`)

| CPU (standalone) | CPU (linux) | Domain (standalone) | Description |
|-----------------|-------------|---------------------|-------------|
| `ps7_cortexa9_0` | `ps7_cortexa9` | `standalone_ps7_cortexa9_0` | Cortex-A9 core 0, 32-bit |
| `ps7_cortexa9_1` | `ps7_cortexa9` | `standalone_ps7_cortexa9_1` | Cortex-A9 core 1, 32-bit |

Boards: ZC702, ZC706, ZedBoard, MicroZed, PicoZed, ZYBO

---

### ZynqMP / Zynq UltraScale+ (`zynq_ultra_ps_e`, ARCH: `zynquplus`)

| CPU (standalone) | CPU (linux) | Domain (standalone) | Description |
|-----------------|-------------|---------------------|-------------|
| `psu_cortexa53_0` | `psu_cortexa53` | `standalone_psu_cortexa53_0` | Cortex-A53 core 0, 64-bit APU |
| `psu_cortexa53_1` | `psu_cortexa53` | `standalone_psu_cortexa53_1` | Cortex-A53 core 1, 64-bit APU |
| `psu_cortexa53_2` | `psu_cortexa53` | `standalone_psu_cortexa53_2` | Cortex-A53 core 2, 64-bit APU |
| `psu_cortexa53_3` | `psu_cortexa53` | `standalone_psu_cortexa53_3` | Cortex-A53 core 3, 64-bit APU |
| `psu_cortexr5_0` | n/a | `standalone_psu_cortexr5_0` | Cortex-R5 core 0, 32-bit RPU |
| `psu_cortexr5_1` | n/a | `standalone_psu_cortexr5_1` | Cortex-R5 core 1, 32-bit RPU (split mode) |
| `psu_pmu_0` | n/a | `standalone_psu_pmu_0` | PMU MicroBlaze |

Boards: ZCU102, ZCU104, ZCU106, ZCU111, KV260, K26, UltraZed

**Notes:**
- R5 cores only available in standalone; check `PSU__RPU__POWER__ON` param
- A53 individually enabled: `PSU__ACPU[0-3]__POWER__ON`
- `generate_dtb=True` required for linux

---

### Versal (`versal_cips`, ARCH: `versal`)

| CPU (standalone) | CPU (linux) | Domain (standalone) | Description |
|-----------------|-------------|---------------------|-------------|
| `psv_cortexa72_0` | `psv_cortexa72` | `standalone_psv_cortexa72_0` | Cortex-A72 core 0, 64-bit APU |
| `psv_cortexa72_1` | `psv_cortexa72` | `standalone_psv_cortexa72_1` | Cortex-A72 core 1, 64-bit APU |
| `psv_cortexr5_0` | n/a | `standalone_psv_cortexr5_0` | Cortex-R5 core 0, 32-bit RPU |
| `psv_cortexr5_1` | n/a | `standalone_psv_cortexr5_1` | Cortex-R5 core 1, 32-bit RPU |
| `ai_engine` | n/a | `aie` | AI Engine (AIE) vector array |
| `psv_pmc_0` | n/a | `standalone_psv_pmc_0` | PMC MicroBlaze |

Boards/Devices: VCK190, VMK180, VEK280, VHK158 (Prime), Versal AI Edge, Versal HBM, Versal Premium

**Notes:**
- `generate_dtb=True` required for linux
- AIE requires `aie_runtime` OS domain, not standalone/linux

---

### Versal NET / Telluride (`versal_net_cips`, ARCH: `versalnet`)

| CPU (standalone) | CPU (linux) | Domain (standalone) | Description |
|-----------------|-------------|---------------------|-------------|
| `psx_cortexa78_0` | `psx_cortexa78` | `standalone_psx_cortexa78_0` | Cortex-A78 core 0, 64-bit APU |
| `psx_cortexa78_1` | `psx_cortexa78` | `standalone_psx_cortexa78_1` | Cortex-A78 core 1, 64-bit APU |
| `psx_cortexa78_2` | `psx_cortexa78` | `standalone_psx_cortexa78_2` | Cortex-A78 core 2, 64-bit APU |
| `psx_cortexa78_3` | `psx_cortexa78` | `standalone_psx_cortexa78_3` | Cortex-A78 core 3, 64-bit APU |
| `psx_cortexr52_0` | n/a | `standalone_psx_cortexr52_0` | Cortex-R52 core 0, 32-bit RPU |
| `psx_cortexr52_1` | n/a | `standalone_psx_cortexr52_1` | Cortex-R52 core 1, 32-bit RPU |
| `psx_cortexr52_2` | n/a | `standalone_psx_cortexr52_2` | Cortex-R52 core 2, 32-bit RPU |
| `psx_cortexr52_3` | n/a | `standalone_psx_cortexr52_3` | Cortex-R52 core 3, 32-bit RPU |
| `psx_pmc_0` | n/a | `standalone_psx_pmc_0` | PMC MicroBlaze |

Devices: VHK158, VPKL085, VP1202, VP1502, VP1702, VP1802

**Notes:**
- Up to 4 A78 and 4 R52 cores (actual count depends on device/config)
- `generate_dtb=True` required for linux

---

### MicroBlaze (PL soft processor, ARCH: any)

| CPU (standalone) | Description |
|-----------------|-------------|
| `microblaze_0` | MicroBlaze instance 0 in PL fabric |
| `microblaze_1` | MicroBlaze instance 1 in PL fabric |

Detected dynamically from `IPTYPE=PROCESSOR` + `microblaze` in VLNV.

---

## generate_dtb Rules

| Family | OS | generate_dtb |
|--------|----|-------------|
| Zynq-7000 | linux | `False` (optional) |
| ZynqMP | linux | `True` |
| Versal | linux | `True` |
| Versal NET | linux | `True` |
| Any | standalone | `False` |

---

## Output Paths

| Artifact | Path Pattern |
|---------|-------------|
| Platform XPFM | `<ws>/<platform>/export/<platform>/<platform>.xpfm` |
| App ELF | `<ws>/<app>/build/<app>.elf` |
| FSBL ELF | `<ws>/<platform>/zynqmp_fsbl/build/fsbl.elf` |
