<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Architecture Decisions

For every decision record:

- requirement IDs served;
- selected option and alternatives;
- measurable effect on latency, throughput, area, clocks, and verification;
- evidence source and confidence;
- whether the decision changes observable behavior.

The plan must cover module hierarchy, external and internal interfaces, clock/reset domains, CDC, buffering, backpressure, pipeline latency, memory mapping, arithmetic resources, IP selection, source artifacts, and verification obligations.

Return to `amd_soc_intent_to_spec` instead of deciding when a choice changes a hard requirement. Use `vivado_doc_search` for device-family, primitive, XPM, hard-block, and IP facts.
