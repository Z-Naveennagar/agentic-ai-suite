<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Vitis Python API (vitis.cli_client) — Embedded/Project-Relevant Commands

This document extracts the commands from the provided **`vitis.cli_client`** specification that are relevant to **embedded software development** (workspaces, platforms, app/library components, BSP/boot/DTB, sysroot/toolchain, preferences) and **project management** (repositories, templates, import/export, cloning, listing, lifecycle operations).

> Scope note: Only APIs present in your pasted excerpt are included.

---

## Class: `vitis.cli_client.Accelerated(*args, **kwargs)`
**Bases:** `Embedded`

APIs for accelerated platforms. (All `Embedded` APIs are also supported.)

### Component Creation (AIE / HLS)
| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes / Typical use |
|---|---|---|---|---|---|---|
| `create_aie_component(name, platform=None, part=None, template=None)` | Component / AIE | Creates an **AIE component** for a platform or part | `name`: component name; **one of** `platform` **or** `part` | `template`: component template | AIE component object | Use `platform` OR `part` (not both). Example template: `'empty'` |
| `create_hls_component(name, platform=None, part=None, cfg_file=None, template=None)` | Component / HLS | Creates an **HLS component**, optionally adding an existing config file | `name`: component name | `platform` **or** `part`; `cfg_file`: existing cfg to add; `template` | HLS component object | Useful for hardware acceleration development flow; `cfg_file` lets you attach compile/synth settings |
| `get_vitis_analyzer(path)` *(doc text names it `get_summary_file`)* | Analysis / Reporting | Returns an object for an **analysis summary file** | `path`: summary file path | — | Summary file object | Naming mismatch in excerpt: prototype shows `get_summary_file(path=...)` but heading shows `get_vitis_analyzer(path)` |

---

## Class: `vitis.cli_client.Embedded(*args, **kwargs)`
**Bases:** `object`

Vitis Client APIs for embedded install (also supported by full install). These are accessed through a client object, e.g. `client = vitis.create_client()`.

---

## Workspace & Session Management
| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes |
|---|---|---|---|---|---|---|
| `set_workspace(path)` | Workspace | Sets the current workspace path | `path`: workspace location | — | `True` on success | Fundamental for all subsequent project/component operations |
| `get_workspace()` | Workspace | Gets current workspace path | — | — | workspace path string (empty if not set) | Useful in scripts/CI for path discovery |
| `check_workspace()` | Workspace | Checks whether a workspace is set | — | — | `True` if set | Raises exception if not set |
| `update_workspace(path)` | Workspace / Migration | Migrates workspace to current Vitis version and sets it | `path`: workspace location | — | `True` on success | Helpful when upgrading tool versions in long-lived projects |
| `close()` | Session | Closes comms channel to Vitis Server | — | — | `True` on success | Call in automation/CI teardown |
| `info()` | Diagnostics | Returns client connection information | — | — | connection info | Useful for debugging client-server connectivity |
| `log_level(level=None)` | Diagnostics | Gets/sets logging verbosity | — | `level`: log level; if omitted, returns current | `True` if set; otherwise current level | Example: `DEBUG` |

---

## Repositories (Embedded SW, Platforms, Examples)
These APIs are strongly tied to **project management** (dependency and template sources) and embedded development enablement.

### Embedded Software Repositories
| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes |
|---|---|---|---|---|---|---|
| `add_embedded_sw_repo(level='LOCAL', path=None)` | Repo / SW | Adds embedded software repo path(s) | `path`: string or list of repo paths | `level`: `LOCAL` (default) or `GLOBAL` | `True` | `LOCAL` = workspace scope; `GLOBAL` = across workspaces |
| `remove_embedded_sw_repo(level='LOCAL', path=None)` | Repo / SW | Removes repo path(s) from embedded SW repos | `path`: string or list | `level`: `LOCAL` (default) or `GLOBAL` | `True` | Use when cleaning or deprecating sources |
| `set_embedded_sw_repo(level='LOCAL', path=None)` | Repo / SW | Sets/resets repo path(s); empty path resets | `path`: string/list, or `''` to reset | `level`: `LOCAL` (default) or `GLOBAL` | `True` | “Set” replaces current list at that level |
| `get_embedded_sw_repo(level='')` | Repo / SW | Gets embedded SW repo paths | — | `level`: `LOCAL`, `GLOBAL`, or empty (both) | current paths | Helpful for audit/debug |
| `rescan_embedded_sw_repo(path)` | Repo / SW | Rescans a repo path and updates SW repo list | `path`: repo path | — | success notification | Call after repo content changes |

### Platform Repositories
| API | Category | What it does | Required arguments | Optional arguments | Returns | Notes |
|---|---|---|---|---|---|---|
| `add_platform_repos(platform)` | Repo / Platform | Adds platform path(s) to platform repository | `platform`: string or list of platform paths | — | `True` | Enables discovery/listing of platforms |
| `delete_platform_repos(platform)` | Repo / Platform | Removes platform path(s) from platform repository | `platform`: string or list | — | `True` | Use to prune invalid/outdated paths |
| `rescan_platform_repos(platform)` | Repo / Platform | Rescans platform repo paths and updates platform list | `platform`: string or list | — | `True` | Call after changes in repo contents |
| `list_platform_repos()` | Repo / Platform | Lists configured platform repositories (valid/invalid) | — | — | list | Good for housekeeping |
| `find_platform_in_repos(name)` | Discovery | Finds first platform xpfm path matching a pattern/regex | `name`: pattern/regex | — | xpfm path or `None` | Quick lookup for scripts |
| `find_platforms_in_repos(name)` | Discovery | Finds all platform xpfm paths matching a pattern/regex | `name`: pattern/regex | — | list of xpfm paths | Raises exception if failure |

### Example Repositories (Git/Local)
| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes |
|---|---|---|---|---|---|---|
| `add_git_example_repo(name, git_url, type='ACCL_APP', git_branch='master', local_directory='', git_tag=None, display_name=None, description=None)` | Repo / Examples | Registers a **git-backed** example repository | `name`, `git_url` | `type`: `ACCL_APP`/`HLS`/`AIE`; `git_branch='master'`; `git_tag`; `local_directory`; `display_name`; `description` | `True` | Useful for sharing templates/apps across teams |
| `sync_git_example_repo(name)` | Repo / Examples | Downloads/syncs the configured git example repo locally | `name`: repo name | — | `True` | Use after adding repo, or in CI bootstrap |
| `add_local_example_repo(name, local_directory, type='ACCL_APP', display_name=None, description=None)` | Repo / Examples | Registers a **local** example repository | `name`, `local_directory` | `type`: `ACCL_APP`/`HLS`/`AIE`; `display_name`; `description` | `True` | Great for offline or internal repos |
| `get_example_repo(name)` | Repo / Examples | Gets an existing example repo object | `name` | — | repo object | Used with `update_example_repo()` |
| `get_example_repo_state(name)` | Repo / Examples | Gets repo status (`UP_TO_DATE`, `NOT_DOWNLOADED`, `NEED_UPDATE`) | `name` | — | status string | Helps decide when to sync/update |
| `update_example_repo(repo)` | Repo / Examples | Updates a modified example repository | `repo`: repo object | — | `True` | Requires object from `get_example_repo()` |
| `delete_example_repo(name)` | Repo / Examples | Deletes a repository from configured list | `name` | — | `True` | Cleanup operation |
| `reset_example_repo(type='ACCL_APP')` | Repo / Examples | Resets repos to tool defaults; removes user-specified repos of a type | — | `type='ACCL_APP'` | `True` | Restores baseline configuration |
| `list_example_repos(type='ACCL_APP')` | Repo / Examples | Lists configured example repos and attributes | — | `type`: `ACCL_APP`/`HLS`/`AIE`/`EMBD_APP` | list | Inventory for governance |

---

## Preferences (Sysroot, RootFS, Kernel Image)
These are important for embedded Linux flows and reproducible builds.

| API | Category | What it does | Required arguments | Optional arguments | Returns | Notes |
|---|---|---|---|---|---|---|
| `get_preference(level, device, key)` | Preferences | Gets a preference value | `level`: `USER`/`WORKSPACE`; `device`: `VERSAL`/`ZYNQ`/`ZYNQMP`; `key`: `SYSROOT`/`KERNELIMAGE`/`ROOTFS` | — | value string | Helps scripts locate toolchain assets |
| `set_preference(level, device, key, value)` | Preferences | Sets a preference value | `level`, `device`, `key`, `value` | — | `True` | Use to standardize environment across developers/CI |

---

## Platform Information & CPU/OS Discovery
| API | Category | What it does | Required arguments | Optional arguments | Returns | Notes |
|---|---|---|---|---|---|---|
| `list_platforms()` | Platform / Discovery | Lists platforms with xpfm paths plus flow/family info | — | — | list | Useful selection UI in scripts |
| `get_hw_platform(xpfm_platform_path)` | Platform / Info | Returns hardware platform information for given xpfm | `xpfm_platform_path` | — | list | Inspect hardware capabilities |
| `get_sw_platform(xpfm_platform_path)` | Platform / Info | Returns software platform information for given xpfm | `xpfm_platform_path` | — | list | Inspect domains, OS, BSP, etc. |
| `get_processor_os_list(xsa=None, platform=None)` | Platform / Discovery | Extracts processor/OS list from XSA or platform | `xsa` **or** `platform` | — | list | Use when creating domains or app components |

---

## Component & System Project Lifecycle (Create/Clone/Delete/List/Get)
These are core **embedded software project management** operations.

### Create Components
| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes |
|---|---|---|---|---|---|---|
| `create_app_component(name, platform, domain=None, cpu=None, os=None, template=None, sysroot_toolchain=None, use_sysroot_toolchain=None)` | Component / App | Creates an **application component** | `name`; `platform` | `domain`; `template`; `cpu`; `os`; `sysroot_toolchain`; `use_sysroot_toolchain` | app component object | CPU/OS are required if no platform is provided (per excerpt). Supports host sysroot/toolchain for host components |
| `create_library_component(name, platform, domain=None, template=None)` | Component / Library | Creates a **static library component** | `name`; `platform` | `domain` (baremetal); `template` | library component object | Domain option only supported for baremetal domains |
| `create_platform_component(name, hw_design='', desc=None, os=None, cpu=None, domain_name=None, template=None, no_boot_bsp=False, fsbl_target=None, fsbl_path=None, pmufw_Elf=None, emu_design='', platform_xpfm_path='', is_pmufw_req=False, generate_dtb=True, advanced_options={}, architecture=None, compiler=None)` | Component / Platform | Creates a **new platform component** from HW handoff/XSA and settings | `name`; `hw_design`; `emu_design`; `platform_xpfm_path` *(as listed in excerpt’s “Required” section)* | many: `desc`, `os`, `cpu`, `domain_name`, `template` (default “Empty” for baremetal), `no_boot_bsp`, `fsbl_target` (default `psu_cortexa53_0` for ZU+), `fsbl_path`, `pmufw_Elf`, `is_pmufw_req=False`, `generate_dtb=True`, `advanced_options`, `architecture`, `compiler` | platform object | Enables boot components, DTB generation, PMUFW; `advanced_options` created via `create_advanced_options_dict()` |
| `create_advanced_options_dict(sdt_repo=None, board_dtsi=None, user_dtsi=None, dt_overlay=None, dt_zocl=None, custom_dtsi=None)` | Platform / Helper | Builds an **advanced options dict** for platform creation (SDT/DT related) | — | `sdt_repo`, `board_dtsi`, `user_dtsi`, `dt_overlay`, `dt_zocl`, `custom_dtsi` | dict | Used as `advanced_options` in `create_platform_component` |

### Create System Projects
| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes |
|---|---|---|---|---|---|---|
| `create_sys_project(name, platform, template=None)` | System Project | Creates a **system project** for a platform | `name`; `platform` (xpfm path) | `template` (default `empty_application` for embedded; `empty_accelerated_application` for accelerated) | system project object | Template also supports accelerated flows with AIE/HLS components |

### Clone / Delete / Get / List
| API | Category | What it does | Required arguments | Optional arguments | Returns | Notes |
|---|---|---|---|---|---|---|
| `clone_component(name, new_name)` | Lifecycle | Clones an existing component | `name`; `new_name` | — | component object | Can also clone platforms (per example) |
| `delete_component(name)` | Lifecycle | Deletes a component by name | `name` | — | `True` | Raises on failure |
| `get_component(name)` | Lifecycle | Gets a component object | `name` | — | component object | Useful for scripting subsequent ops |
| `list_components()` | Inventory | Lists all components in current workspace | — | — | list | Helps automation enumerate build targets |
| `clone_sys_project(name, new_name)` | Lifecycle | Clones a system project | `name`; `new_name` | — | system project object | Raises exception on failure |
| `delete_sys_project(name)` | Lifecycle | Deletes a system project | `name` | — | `True` | Cleanup |
| `get_sys_project(name)` | Lifecycle | Gets a system project object | `name` | — | system project object | |
| `list_sys_projects()` | Inventory | Lists all system projects in workspace | — | — | list of dicts | Empty list if none; exception on failure |
| `list_platform_components()` | Inventory | Lists platform projects in workspace | — | — | list | Excerpt’s example shows `list_platform_projects()` but API name is `list_platform_components()` |

---

## Templates (Project Starters)
Templates accelerate project bootstrapping (project management + standardization).

Important compatibility note:
- Template display names and accepted template identifiers may differ by Vitis version.
- Always query the live tool (`get_templates(...)`) and pass an exact returned identifier to creation APIs.

| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes |
|---|---|---|---|---|---|---|
| `get_template(type='ACCL_APP', name='', platforms=None)` | Templates | Gets the **first matched** template hierarchical name | — | `type`: `ACCL_APP`/`HLS`/`AIE`/`EMBD_APP`; `name` filter; `platforms` (accelerated-only) | first match hierarchical name | Note: accelerated flows not supported for Embedded installer (per excerpt) |
| `get_templates(type='ACCL_APP', name='', platforms=None)` | Templates | Gets **all matched** templates | — | same as above | list of matched templates (or `None`) | Useful for selecting among multiple starters |

---

## Import / Export (Sharing & Archiving)
Key for collaboration, backups, CI artifact handling.

| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes |
|---|---|---|---|---|---|---|
| `export_projects(components=None, system_projects=None, dest=None, include_build_dir=False)` | Portability | Exports components and/or system projects from workspace into a zip | — | `components`; `system_projects`; `dest` (default `<workspace>_exported.zip`); `include_build_dir=False` | Status | If no names provided, exports all |
| `get_project_info(src)` | Portability | Lists components and system projects contained in a zipped export | `src`: zip path | — | `components, system_projects` | Use before import to choose subset |
| `import_projects(src, components=None, system_projects=None, dest=None)` | Portability | Imports selected/all projects from zip into current workspace | `src`: zip path | `components`; `system_projects`; `dest` (default current workspace) | Status | Supports partial imports |

---

## Config File Access
| API | Category | What it does | Required arguments | Optional arguments | Returns | Notes |
|---|---|---|---|---|---|---|
| `get_config_file(path)` | Configuration | Returns an object to read/write a config file | `path`: config path | — | config file object | Useful for managing build/run configuration programmatically |
