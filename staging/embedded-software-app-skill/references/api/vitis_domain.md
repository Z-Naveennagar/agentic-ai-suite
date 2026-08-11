<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Vitis Python API (vitis.domain) — Embedded/Project-Relevant Commands

This document extracts the commands from the provided **`vitis.domain`** specification that are relevant to **embedded software development** (BSP configuration, drivers/libs, device tree/DTB, Linux boot artifacts, QEMU settings) and **project management** (domain reporting, naming, path updates).

> Scope note: Only APIs present in your pasted excerpt are included.

---

## Class: `vitis.domain.Domain(server)`
**Bases:** `object`

Client class for Vitis Domain service.

---

## Boot & Linux Image Artifacts
| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes / Typical use |
|---|---|---|---|---|---|---|
| `generate_bif()` | Boot image / Linux | Generates a standard **BIF** for the domain (Linux domains only) | — | — | `True` | Location of generated BIF is shown in domain report; used for boot image creation |
| `set_bif(path)` | Boot image / Linux | Sets a BIF file used to create Linux boot image | `path`: BIF file path | — | `True` | Use custom boot image layout/scripts |
| `set_boot_dir(path)` | Boot image / Linux | Sets a boot directory to generate components after Linux image build | `path`: boot directory | — | `True` | Organize boot artifacts output location |
| `set_sd_dir(path)` | Linux images | Uses pre-built Linux images from a directory when creating PetaLinux project (Linux domains only) | `path`: pre-built Linux images directory | — | `True` | Speeds up flows by reusing prebuilt kernel/rootfs/etc. |

---

## Device Tree (DTB) Management
| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes / Typical use |
|---|---|---|---|---|---|---|
| `recompile_dtb()` | Device Tree | Recompiles device tree source to regenerate the **DTB** | — | — | `True` | Used after DTS/overlay changes |
| `set_dtb(path)` | Device Tree | Replaces existing DTB boot component with a custom DTB | `path`: DTB file path | — | `True` | Use when providing externally-built DTB |

---

## BSP / Domain Configuration (OS / Processor / Libraries)
Important compatibility note:
- Valid OS config keys are version and domain dependent.
- Always call `list_params(option='os')` before `set_config(...)` instead of assuming generic keys such as `stdin`/`stdout`.
- In standalone domains, keys are commonly prefixed (for example `standalone_stdin`, `standalone_stdout`).

| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes / Typical use |
|---|---|---|---|---|---|---|
| `list_params(option, lib_name=None)` | BSP config | Lists configurable parameters for an option | `option`: one of `lib`, `os`, `proc` | `lib_name`: required when `option='lib'` | list of parameter names | Use to discover valid config keys for `get_config`/`set_config` |
| `get_config(option, param, lib_name=None)` | BSP config | Gets current value for a configurable parameter | `option`: `lib`/`os`/`proc`; `param`: parameter name | `lib_name`: if `option='lib'` | value | Read current BSP/OS/proc settings (e.g., stdin/stdout routing) |
| `set_config(option, param, value, lib_name=None)` | BSP config | Sets value for a configurable parameter | `option`: `lib`/`os`/`proc`; `param`: parameter name; `value`: parameter value | `lib_name`: if `option='lib'` | `True` | Changes take effect according to platform/domain generation rules |
| `get_os()` | BSP info | Returns OS details from BSP settings | — | — | current OS details | Useful to verify domain OS selection |
| `get_drivers()` | BSP info | Lists IPs and drivers assigned in BSP | — | — | list of IP/driver mappings | Validate driver binding and BSP composition |
| `get_libs()` | BSP info | Lists libraries added in BSP settings | — | — | list of libraries | Verify what libs are currently enabled |
| `get_applicable_libs()` | BSP info | Lists libraries applicable for current domain | — | — | list of applicable libraries | Use to choose valid libraries before calling `set_lib()` |
| `set_lib(lib_name, path=None)` | BSP libraries | Adds a library to BSP settings | `lib_name`: library name | `path`: optional library path | `True` | Newly added libs become available to app projects after platform is generated |
| `remove_lib(lib_name)` | BSP libraries | Removes a library from BSP settings | `lib_name`: library name | — | `True` | Changes take effect when platform is generated |
| `regenerate()` | BSP generation | Regenerates BSP sources | — | — | `True` | Use after config/lib/driver changes |

---

## QEMU Configuration (Emulation)
| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes / Typical use |
|---|---|---|---|---|---|---|
| `set_qemu_args(qemu_option, path)` | QEMU / Emulation | Adds a file containing PS/PMC/PMU QEMU args | `qemu_option`: `PS`/`PMC`/`PMU`; `path`: args file | — | `True` | Centralize and version-control emulation args |
| `set_qemu_data(path)` | QEMU / Emulation | Sets directory containing files referenced by qemu-args/pmuqemu-args | `path`: data directory | — | `True` | Ensures QEMU has access to all referenced inputs |

---

## Domain Metadata, Reporting & Path Updates
| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes / Typical use |
|---|---|---|---|---|---|---|
| `report()` | Reporting | Displays information about the domain | — | — | prints/returns domain info | Use to locate generated artifacts like BIF |
| `update_name(name)` | Project management | Renames the domain (display name) | `name`: new name | — | `True` | Helpful for organizing multi-domain platforms |
| `update_path(option, name, new_path)` | Dependency paths | Updates OS/Driver/Library path | `option`: `OS`/`DRIVER`/`LIB`; `name`: target name; `new_path`: new path | — | `True` | Relink domain to custom OS/driver/lib locations |
