<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Vitis Python API (vitis.component) — Embedded/Project-Relevant Commands

This document extracts the commands from the provided **`vitis.component`** specification that are relevant to **embedded software development** (build/clean/run, sysroot/toolchain, linker scripts, file import) and **project management** (component configuration, reporting, build file generation).

> Scope note: Only APIs present in your pasted excerpt are included.

---

## Base Class: `vitis.component.Component(serverObj)`
**Bases:** `object`

General component-management operations common across component types.

| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes / Typical use |
|---|---|---|---|---|---|---|
| `import_files(from_loc, files=None, files_to_exclude=None, dest_dir_in_cmp=None, is_skip_copy_sources=False)` | Source management | Imports source/config files into the component | `from_loc`: directory or file path (abs/rel) | `files`: list of specific files (if omitted, imports whole folder); `files_to_exclude`: list; `dest_dir_in_cmp`: destination folder in component; `is_skip_copy_sources=False` | `True` on success | `is_skip_copy_sources=True` supported only for **Application** component: references sources instead of copying |
| `remove_files(files)` | Source management | Removes files from the component | `files`: list of files to remove | — | `True` on success | Paths can be given like `'/src/file1.txt'` |
| `report()` | Reporting | Prints/returns component information | — | — | component information (or error) | Useful to discover cfg paths and validate component membership |

---

## Class: `vitis.component.AIEComponent(serverObj)`
**Bases:** `Component`

AIE component service APIs.

| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes / Typical use |
|---|---|---|---|---|---|---|
| `add_cfg_file(cfg_file)` | Configuration | Adds a configuration file to the AIE component | `cfg_file`: path to cfg | — | `True` | Helps parameterize AIE build/sim flows |
| `remove_cfg_file(cfg_file)` | Configuration | Removes a configuration file from the AIE component | `cfg_file`: exact path used when added | — | `True` | Tip: use `component.report()` to obtain exact cfg path |
| `update_top_level_file(top_level_file)` | Source / Top-level | Sets/updates the AIE top-level source file | `top_level_file`: file name/path | — | `True` | Example: `graph1.cpp` |
| `generate_build_files()` | Build system | Generates/regenerates CMake build files | — | — | `True` | Edits made outside tool in CMake files will be lost |
| `build(target=None)` | Build | Builds the AIE component for a target | — | `target`: one of supported targets (`x86sim`, `hw`); default `x86sim` | `SUCCESS`/`FAILURE` | Used for simulation or hardware builds |
| `clean(target=None)` | Build cleanup | Cleans build outputs for a specified target | `target`: one of supported targets (`hw_emu`, `hw`) | — | `SUCCESS`/`FAILURE` | Note: excerpt labels target as “Required” for clean |

---

## Class: `vitis.component.HLSComponent(serverObj)`
**Bases:** `Component`

HLS component service APIs.

| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes / Typical use |
|---|---|---|---|---|---|---|
| `add_cfg_file(cfg_file)` | Configuration | Adds a configuration file to the HLS component | `cfg_file`: path to cfg | — | `True` | Attach custom HLS build/synth directives |
| `remove_cfg_file(cfg_file)` | Configuration | Removes a configuration file from the HLS component | `cfg_file`: path; to remove default use `hls_config.cfg` | — | `True` | Must match exact path used when adding; default cfg removable via literal name |
| `run(operation)` | Flow execution | Runs an HLS flow operation | `operation`: one of `C_SIMULATION`, `SYNTHESIS`, `CO_SIMULATION`, `IMPLEMENTATION`, `ANALYSIS_OPTIMIZATION`, `PACKAGE` | — | `True` | Drives typical HLS workflow stages |

---

## Class: `vitis.component.BuildSettings(serverObj)`
**Bases:** `Component`

C/C++ build settings management (commonly used for application and library components).

| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes / Typical use |
|---|---|---|---|---|---|---|
| `get_app_config(key=None)` | Build config | Gets current build configuration value(s) | — | `key`: config parameter; if omitted returns entire config | value(s) | Use to read flags like optimization/debug levels |
| `set_app_config(key, values)` | Build config | Sets a build setting to a value or list of values | `key`; `values` | — | `True` | Used to set e.g. debug level `-g1` |
| `append_app_config(key, values)` | Build config | Appends value(s) to supported list-type settings | `key`; `values` | — | `True` | Append supported only for: `USER_COMPILE_DEFINITIONS`, `USER_LINK_LIBRARIES`, `USER_UNDEFINE_SYMBOLS`, `USER_INCLUDE_DIRECTORIES` |
| `remove_app_config(key, values)` | Build config | Removes value(s) from supported list-type settings | `key`; `values` | — | `True` | Remove supported only for same list-type keys as append |
| `get_config_info(key)` | Build config help | Shows possible values/operations for a config parameter | `key` | — | info object/string | Handy for validation in scripts and tooling |

---

## Class: `vitis.component.HostComponent(serverObj)`
**Bases:** `BuildSettings`

Application (host) component service APIs.

Important compatibility note:
- Build return semantics can vary by Vitis version.
- Some versions report string states (`SUCCESS`/`FAILURE`), while others may return integer-like status codes (`0` success, non-zero failure).
- Automation should normalize both forms before deciding retry/failure behavior.
- In SDT-mode BSP flows, generated headers may omit legacy `*_DEVICE_ID` macros and require `*_BASEADDR` lookup paths.
- Driver helper function names can vary by BSP generation mode/version; generated app code should verify symbols from installed BSP headers before finalizing calls.

| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes / Typical use |
|---|---|---|---|---|---|---|
| `build(target=None)` | Build | Builds the application component for a target | — | `target`: supported targets include `x86sim`, `hw`; default depends on flow (baremetal: `hw`, accelerated: `x86sim`) | `SUCCESS`/`FAILURE` | Primary embedded app build entry point |
| `clean(target=None)` | Build cleanup | Cleans build outputs for a specified target | `target`: one of supported targets (`hw_emu`, `hw`) | — | `SUCCESS`/`FAILURE` | Excerpt marks target as required for clean |
| `generate_build_files()` | Build system | Generates/regenerates CMake build files | — | — | `True` | External edits to generated CMake will be overwritten |
| `get_ld_script(path=None)` | Linker | Returns linker script file object for the component | — | `path`: linker script to edit; default is `lscript.ld` associated with component | linker script object | Useful for baremetal memory layout control |
| `get_sysroot()` | Sysroot | Gets sysroot path for the app component | — | — | sysroot location | Excerpt notes: “Waiting for backend support” |
| `set_sysroot(sysroot)` | Sysroot | Sets sysroot for the app component | `sysroot`: sysroot path | — | `True` on success (`False` on failure) | Supports Linux cross build setups |
| `update_sysroot_toolchain(sysroot_toolchain)` | Toolchain | Updates sysroot toolchain path for the app component | `sysroot_toolchain`: toolchain path | — | updated sysroot toolchain location | Used for host builds requiring external toolchains |
| `use_sysroot_toolchain(use_sysroot_toolchain)` | Toolchain | Enables/disables using the sysroot toolchain | `use_sysroot_toolchain`: boolean | — | use-sysroot-toolchain setting/location | Control whether toolchain is applied for host component builds |

---

## Class: `vitis.component.LibraryComponent(serverObj)`
**Bases:** `BuildSettings`

Static library component service APIs.

| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes / Typical use |
|---|---|---|---|---|---|---|
| `build()` | Build | Builds the library component | — | — | `SUCCESS`/`FAILURE` | Compile reusable code for linking into applications |
