<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Source Ownership

`vivado_rtl_engineer` owns RTL, HDL packages, XDC, project Tcl, IP configuration, and PL-only integration scripts. It may repair elaboration and source-owned lint findings.

It does not own:

- specification changes;
- module partition, interface, CDC, or latency architecture;
- test expectations;
- implementation directives that do not belong in source or constraints;
- waivers that weaken signoff.

When feedback exceeds source ownership, return a handoff that identifies the affected contract field and evidence. Do not apply a speculative workaround.
