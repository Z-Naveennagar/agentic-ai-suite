<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Closure Routing

| Evidence | Owner | Response |
|---|---|---|
| Syntax, elaboration, inference, or incorrect XDC object | `vivado_rtl_engineer` | return source evidence |
| Deep logic, insufficient pipeline, memory topology, CDC architecture | `amd_soc_architect` | request architecture revision |
| Clock, latency, area, or power target conflicts | `amd_soc_intent_to_spec` | request requirement decision |
| Test failure or missing verification obligation | `amd_soc_verifier` | return verification evidence |
| Directive, placement, routing, congestion, physical optimization | `vivado_impl_closure` | iterate locally |
| License, host, device database, session, or tool crash | infrastructure | recover or return `ERROR` |

Local implementation remedies must preserve behavior and constraints intent. Stop after two repeats of the same failure class without new evidence.
