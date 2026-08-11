<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Vitis Python API (vitis.platform_component) — Embedded/Project-Relevant Commands

This document extracts the commands from the provided **`vitis.platform_component`** specification that are relevant to **embedded software development** (platform build, boot components, domains, hardware handoff) and **project management** (platform structure, files, reporting, metadata updates).

> Scope note: Only APIs present in your pasted excerpt are included.

---

## Class: `vitis.platform_component.Platform(server)`
**Bases:** `object`

Client class for Vitis Platform service.

---

## Domain Management
| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes / Typical use |
|---|---|---|---|---|---|---|
| `add_domain(cpu, os='standalone', name=None, display_name=None, sd_dir=None, support_app=None, generate_dtb=True, dt_overlay=False, architecture=None, compiler=None)` | Domains | Adds a domain to the platform | `cpu`: processor core(s); `name`: domain name | `os='standalone'`; `display_name`; `support_app`; `sd_dir`; `generate_dtb=True`; `dt_overlay=False`; `architecture`; `compiler` | `True` | For SMP Linux, `cpu` can be a list; Linux-only options include `sd_dir`, DTB/overlay flags |
| `delete_domain(name)` | Domains | Deletes a domain from the platform | `name`: domain name | — | `True` | Removes BSP/domain configuration |
| `get_domain(name)` | Domains | Returns a domain object by name | `name`: domain name | — | `Domain` object | Use to access `vitis.domain.Domain` APIs |
| `list_domains()` | Domains | Lists all domains in the platform | — | — | list of domains | Useful for validation and automation scripts |

---

## Platform Build & Cleanup
| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes / Typical use |
|---|---|---|---|---|---|---|
| `build()` | Platform build | Generates/builds the platform | — | — | `True` | Must be run after domain or HW changes |
| `clean()` | Platform cleanup | Cleans platform build outputs | — | — | `SUCCESS` / `FAILURE` | Useful before rebuilds or CI flows |

---

## Boot Components (FSBL / PMUFW / BSP)
| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes / Typical use |
|---|---|---|---|---|---|---|
| `generate_boot_bsp(target_processor=None)` | Boot | Generates boot components for the platform | — | `target_processor`: default `zynqmp_fsbl` | `True` | Creates FSBL/PMUFW/etc. depending on platform |
| `remove_boot_bsp()` | Boot | Removes generated boot components | — | — | `True` | Use before switching to prebuilt boot artifacts |
| `retarget_fsbl(target_processor=None, domain_name=None)` | Boot | Regenerates FSBL for a specific processor (ZU+ only) | — | `target_processor`; `domain_name` | `True` | Useful when switching boot CPU (e.g. R5 vs A53) |
| `set_fsbl_elf(path)` | Boot | Sets a prebuilt `fsbl.elf` as boot component | `path`: FSBL ELF path | — | `True` | Used when FSBL is built externally |
| `set_pmufw_elf(path)` | Boot | Sets a prebuilt `pmufw.elf` as boot component | `path`: PMUFW ELF path | — | `True` | Used for custom PMU firmware flows |

---

## Platform Files & Sources
| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes / Typical use |
|---|---|---|---|---|---|---|
| `import_files(from_loc, files=None, dest_dir_in_cmp=None)` | Files | Imports files into the platform | `from_loc`: source path | `files`: list of files; `dest_dir_in_cmp`: destination dir | `True` | Import scripts, configs, metadata into platform |
| `remove_files(files)` | Files | Removes files from the platform | `files`: list of files | — | `True` | Clean up unused platform files |

---

## Hardware Specification Updates
| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes / Typical use |
|---|---|---|---|---|---|---|
| `update_hw(hw_design=None, emu_design=None)` | Hardware | Updates platform to use a new HW spec or emulation XSA | `hw_design` **or** `emu_design` | — | `True` | Rebind platform to new Vivado/XSA output |

---

## Platform Metadata & Reporting
| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes / Typical use |
|---|---|---|---|---|---|---|
| `report()` | Reporting | Displays platform information | — | — | prints/returns platform info | Inspect domains, HW, boot settings |
| `update_desc(desc)` | Metadata | Updates the platform description | `desc`: description text | — | `True` | Helpful for documentation and collaboration |
