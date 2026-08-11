<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Vitis Python API (vitis.configfile) — Embedded/Project-Relevant Commands

This document extracts the commands from the provided **`vitis.configfile`** specification that are relevant to **embedded software development** and **project management**, specifically for **reading/writing Vitis-style configuration files** (e.g., build/run configuration, tool settings, per-section key/value assignments).

> Scope note: Only APIs present in your pasted excerpt are included.

---

## Class: `vitis.configfile.ConfigFileService(server)`
Client class for the Vitis config file service.

| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes / Typical use |
|---|---|---|---|---|---|---|
| `config_file(path) -> ConfigFile` | Factory / Access | Opens a config file and returns a `ConfigFile` object for editing/inspection | `path`: path to config file | — | `ConfigFile` object | Use this first to manipulate `.cfg`-style files programmatically |

---

## Class: `vitis.configfile.ConfigFile(config_service, path)`
**Bases:** `object`

API for reading and editing config files using **sections** and **key=value assignments**.

### Write / Modify Operations
| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes / Typical use |
|---|---|---|---|---|---|---|
| `add_lines(section='', lines=[])` | Config write | Adds assignment line(s) to a section **without enforcing uniqueness** and **without removing existing assignments** | `section`: section name (or `''` for top-level); `lines`: list of assignment strings | Defaults shown in signature (`section=''`, `lines=[]`) | Nothing | Use to append raw assignments like `key=value` exactly as provided |
| `add_values(section='', key='', values=[])` | Config write | Adds repeated values for a key by writing one `key=value` line per value; **does not remove earlier values** | `section`: section name (or `''`); `key`: assignment key; `values`: list of values | Defaults shown in signature | Nothing | Good for multi-valued keys such as repeated `include=` lines |
| `set_value(section='', key='', value='')` | Config write | Sets a single value for a key; **removes any earlier values** for that key in the section | `section`: section name (or `''`); `key`: assignment key; `value`: new value | Defaults shown in signature | Nothing | Use to enforce a single authoritative value for a setting |
| `set_values(section='', key='', values=[])` | Config write | Sets repeated values for a key; writes one `key=value` per value; **removes any earlier values** for that key | `section`: section name (or `''`); `key`: assignment key; `values`: list of new values | Defaults shown in signature | Nothing | Use when you want deterministic multi-valued settings |
| `remove(section='', keysOrLines=[])` | Config write | Removes assignments from a section by specifying **keys** and/or full **assignment lines** | `section`: section name (or `''`); `keysOrLines`: list of keys or full `key=value` strings | Defaults shown in signature | Nothing | Can remove by key (`'key1'`) or exact assignment (`'key2=beta'`), or both |

### Read / Query Operations
| API | Category | What it does | Required arguments | Optional arguments (defaults) | Returns | Notes / Typical use |
|---|---|---|---|---|---|---|
| `get_sections()` | Config read | Returns list of section names in the config file | — | — | list of section names | Useful for discovery/introspection of config structure |
| `get_value(section='', key='')` | Config read | Returns the value for a key in a section (single-value lookup) | `section`: section name (or `''`); `key`: assignment key | Defaults shown in signature | value string (or empty string) | Returns empty string if not found |
| `get_values(section='', key='')` | Config read | Returns **all values** assigned with a key in a section | `section`: section name (or `''`); `key`: assignment key | Defaults shown in signature | list of values (or empty list) | Use for repeated keys (multi-value settings) |
| `get_lines(section='', key='')` | Config read | Returns the **full assignment lines** matching a key in a section | `section`: section name (or `''`); `key`: assignment key | Defaults shown in signature | list of assignment strings | Useful when you need raw text lines rather than parsed values |

---

## Practical Notes (from the provided spec)

- **Top-level settings:** Pass `section=''` (empty string) to operate on settings not under any named section.
- **Uniqueness behavior differs by API:**
  - `add_lines()` and `add_values()` **do not remove** existing assignments.
  - `set_value()` and `set_values()` **remove earlier values** for that key before adding.
- **Removing assignments:** `remove()` supports removing by **key** and/or by full **`key=value`** line(s).
