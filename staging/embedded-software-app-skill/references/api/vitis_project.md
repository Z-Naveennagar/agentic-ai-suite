<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Vitis Python API (vitis.project) — Embedded/Project-Relevant Commands

This document extracts the commands from the provided **`vitis.project`** specification that are relevant to **embedded software development** (system project build/clean, component & container composition, kernel packaging) and **project management** (project structure, configuration files, importing/exporting sources, reporting, platform updates).

> Scope note: Only APIs present in your pasted excerpt are included.

---

## Class: `vitis.project.Project(server)`
**Bases:** `object`

Client class for Vitis system project service.

---

## Project Composition: Components & Containers
These APIs manage the system-project topology: components (APP/HLS/AIE) and binary containers.

| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes / Typical use |
|---|---|---|---|---|---|---|
| `add_component(name, container_name=None)` | Composition | Adds a component to the system project (optionally into specific container(s)) | `name`: component name | `container_name`: container or list of containers (default: add to project) | `True` | Use when assembling accelerated designs (HLS/AIE kernels + host app) |
| `remove_component(name)` | Composition | Removes a component from the system project | `name`: component name | — | `True` | Detach a component without deleting it from workspace |
| `list_components(type=None)` | Inventory | Lists components associated with the system project | — | `type`: filter list by `HLS`, `AI_ENGINE`, `APP` (default: all) | list of components | Useful in automation for enumerating build inputs |
| `add_container(name, cfg_file_list=None)` | Containers | Adds a binary container (optionally with linker cfg files) | `name`: container name | `cfg_file_list`: list of cfg files | `True` | `cfg_file_list` can be updated later via `add_cfg_files()` |
| `remove_container(name)` | Containers | Removes a binary container from the project | `name`: container name | — | `True` | Use `list_containers()` (not in excerpt) to discover container names |

---

## Config Files (Linker/Packaging)
These APIs manage configuration files attached to containers or package.

| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes / Typical use |
|---|---|---|---|---|---|---|
| `add_cfg_files(cfg_files, name=None)` | Config | Adds configuration files to the system project (container-specific or package) | `cfg_files`: list of cfg file paths; `name`: container name or `PACKAGE` | — | `True` | Excerpt heading uses singular `add_cfg_file` but signature says `add_cfg_files` |
| `remove_cfg_files(cfg_files, name=None)` | Config | Removes configuration files from the system project | `cfg_files`: list of cfg file paths | `name`: container name or `PACKAGE` | `True` | Must reference the cfg files as associated with the specified scope |

---

## Precompiled Kernels (XO) in Containers
Used for incorporating externally-built kernels into a system project.

| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes / Typical use |
|---|---|---|---|---|---|---|
| `add_precompiled_kernel(xo_file_path, containers)` | Kernels | Adds a precompiled kernel `.xo` to one or more containers | `xo_file_path`: path to `.xo`; `containers`: list of container names | — | `True` | Path may be absolute, build-relative, or macro-based (`BUILD/…`, `PROJECT/…`) |
| `remove_precompiled_kernel(xo_file_path, containers)` | Kernels | Removes a precompiled kernel `.xo` from one or more containers | `xo_file_path`: path to `.xo`; `containers`: list of container names | — | `True` | Use when swapping kernel versions or simplifying a container |

---

## Build, Clean & Build File Generation
These APIs are core to embedded/accelerated build automation and CI.

| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes / Typical use |
|---|---|---|---|---|---|---|
| `build(target=None, comp_name=None, build_package=False, build_comps=True)` | Build | Builds the system project for a specified target | — | `target`: `hw_emu`/`hw` (defaults vary by platform); `comp_name`: component name (default all); `build_package=False`; `build_comps=True` | `SUCCESS` / `FAILURE` | Use `sys_proj.report()` to see valid targets for a platform |
| `clean(target=None, comp_name=None)` | Clean | Cleans the system project for a specified build target | `target`: `hw_emu`/`hw` (defaults vary by platform) | `comp_name`: component name (default all) | `SUCCESS` / `FAILURE` | Removes build outputs for the project (component-specific if provided) |
| `clean_all(target=None, comp_name=None)` | Clean | Cleans the system project **and its associated components** for a build target | `target`: `hw_emu`/`hw` (defaults vary by platform) | `comp_name`: component name (default all) | `SUCCESS` / `FAILURE` | Useful in CI to ensure fully clean rebuilds |
| `generate_build_files()` | Build system | Generates/regenerates CMake build files for system project build | — | — | `True` | Edits made outside the tool in CMake files will be lost |

---

## Files (Project-level Import/Remove)
Useful for adding sources, configs, or scripts into the system project.

| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes / Typical use |
|---|---|---|---|---|---|---|
| `import_files(from_loc, files=None, dest_dir_in_cmp=None)` | Files | Imports files into the system project | `from_loc`: directory/file path | `files`: list; if omitted imports whole folder; `dest_dir_in_cmp`: destination folder | `True` | Use to add source code (e.g., `src/`) or config assets |
| `remove_files(files)` | Files | Removes files from the system project | `files`: list of file paths | — | `True` | Excerpt has incomplete example; treat API as project cleanup |

---

## Reporting & Platform Updates
Project governance and migration operations.

| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes / Typical use |
|---|---|---|---|---|---|---|
| `report()` | Reporting | Displays information of matching projects in workspace/secondary folders | — | — | project info (or error) | Use to confirm valid build targets, containers, and mapping |
| `update_platform(platform)` | Migration / Retargeting | Updates system project to use a new platform (requires new domain mapping) | `platform`: new `.xpfm` path | — | updated system project object | Used when moving a design to new board/platform variant |

---

## Notes on APIs Mentioned but Not Specified
The excerpt lists **`exportProject(...)`** and **`importProject(...)`** without providing their full specifications. If you paste those sections, I can add them in the same table format.
