<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Vitis Python API (vitis.ldfile) — Embedded/Project-Relevant Commands

This document extracts the commands from the provided **`vitis.ldfile`** specification that are relevant to **embedded software development** (linker script memory maps, stack/heap sizing, section placement) and **project management** (regenerating defaults, inspecting current linker configuration).

> Note: Your message says “vitis.idfile module” but the excerpt is clearly **`vitis.ldfile`**. This MD documents the APIs as provided.

---

## Class: `vitis.ldfile.Ldfile(serverObj)`
**Bases:** `object`

Client class for linker script file manipulation.

---

## Memory Regions (MEMORY map)
| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes / Typical use |
|---|---|---|---|---|---|---|
| `get_memory_regions()` *(spec typo: prototype shows `get_memory_region()`)* | Inspect | Returns list of memory regions defined in the linker script | — | — | list of memory regions | Use to audit current MEMORY layout |
| `add_memory_region(name, base_address, size)` | Modify | Adds a new memory region | `name`: region name; `base_address`: base addr; `size`: region size | — | `True` | Used when adding new RAM/flash regions or carving dedicated heaps |
| `update_memory_region(name, base_address, size)` | Modify | Updates an existing memory region | `name`: region name; `base_address`: new base addr; `size`: new size | — | `True` | Used when memory map changes (new HW design, different DDR carve-out) |

---

## Section Placement (SECTIONS mapping)
| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes / Typical use |
|---|---|---|---|---|---|---|
| `get_ld_sections()` | Inspect | Returns section mapping information from the linker script | — | — | list of section maps | Use to see which sections map to which memory regions |
| `update_ld_section(section, region)` | Modify | Updates an existing section-to-region mapping | `section`: section identifier; `region`: target memory region | — | `True` | Place `.text`, `.data`, etc. into specific regions (e.g. OCM vs DDR) |

---

## Stack & Heap Sizing
| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes / Typical use |
|---|---|---|---|---|---|---|
| `get_heap_size()` | Inspect | Returns heap size configured in linker script | — | — | heap size | Helps confirm runtime memory availability |
| `set_heap_size(size)` | Modify | Updates heap size in linker script | `size`: new heap size | — | `True` | Tune dynamic allocation budget for RTOS/baremetal apps |
| `get_stack_size()` *(spec typo: prototype shows `get_stack_size(size=<stack_size>)` but args say none)* | Inspect | Returns stack size configured in linker script | — | — | stack size | Confirms thread/main stack sizing |
| `set_stack_size(size)` | Modify | Updates stack size in linker script | `size`: new stack size | — | `True` | Avoid stack overflow; adjust for deep call trees/interrupt usage |

---

## Reset / Regenerate
| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes / Typical use |
|---|---|---|---|---|---|---|
| `regenerate()` | Reset | Regenerates linker script with default values | — | — | `True` | Useful to revert experimental changes or sync with platform defaults |

---

## Practical Notes (from the provided spec)

- There are minor inconsistencies/typos in the excerpt:
  - `get_memory_regions()` description says `get_memory_region()` in the prototype.
  - `get_stack_size()` prototype includes a `size` argument, but the arguments section says **None**.
- All “modify” functions return `True` on success and raise exceptions on failure according to the excerpt.
