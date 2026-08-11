<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# v0.1 Codex Runtime Instructions

For AMD FPGA or Adaptive SoC design requests in this directory:

1. Use `amd_soc_orchestrator` as the entry role. In runner-launched workflows, the parent invocation reads `.codex/agents/amd_soc_orchestrator.toml` and acts as that role directly.
2. Preserve the user's request verbatim under `runs/<request_id>/`.
3. Follow `AGENT_ARCHITECTURE_v0.1.md`, `ARTIFACT_OWNERSHIP_v0.1.md`,
   `workflow.json`, and the schemas in `contracts/`. Enforce one writer per
   mutable artifact; consumers return findings to the owner.
4. Use the six-agent direct RTL-to-Vivado design path by default. Append `amd_soc_hardware_validator` for a hardware-qualified run.
5. Invoke `amd_soc_platform_integrator`, `vitis_hls_engineer`, `vitis_aie_engineer`, or `vitis_sw_engineer` only when selected by the approved architecture.
6. Use the bundled flow skills and discover published or staging suite skills read-only through `registry/skills.json`. Do not modify shared suite skills during a design run.
7. Use Vivado MCP throughout the flow where Vivado evidence or actions are required.
8. Do not report design success without functional verification, Vivado signoff, and an existing `.bit` or `.pdi`. Do not report hardware-qualified success without a PASS `hardware-validation-result.json`.
9. Use `contracts/examples/direct-rtl/` only to learn the exact contract shape; all values must come from the active request and tool evidence.
10. Before each handoff, run `python3 scripts/v0_1_runner.py finalize --run
    runs/<request_id> --stage <stage> --write`. Only the orchestrator runs
    whole-flow validation; before final success it runs `python3
    scripts/v0_1_runner.py validate --run runs/<request_id>`.
    For assurance-enabled runs, finalization also closes the pre-opened gate,
    writes JSON plus generated Markdown under `gates/`, and opens the next
    default gate only after PASS. Treat the agent status as a claim and the
    deterministic receipt as the transition verdict. Never advance on a
    non-PASS gate.
11. When spawning a named custom-agent type, use `fork_turns="none"` and put the artifact paths and exact work package in its prompt. This runtime does not allow an explicit custom-agent type with a full-history fork.
12. Require explicit user authorization before programming hardware, resetting a target, or driving VIO.
13. When Vitis is selected, require schema-valid `vitis-execution-plan.json`
    and invoke it only through `python3 scripts/v0_1_runner.py vitis --run
    runs/<request_id>`. Never execute free-form commands supplied by an agent.
14. Require PASS `vitis-result.json` and existing selected outputs before
    claiming a Vitis platform, accelerator, application, or ELF was built.
15. Run isolated requests in parallel only within the configured pools.
    Serialize Tcl per Vivado session and allow only one hardware-validation
    writer per target profile and JTAG cable.
16. Each specialist must disclose exact input revisions, actions, decisions,
    outputs, side effects, assumptions, waivers, and unverified boundaries in
    its owned artifacts and return. Specialists must not create or edit gate
    receipts.
17. Customer-facing runs must follow `CUSTOMER_GUIDANCE_STANDARD_v0.1.md`.
    Give an intake brief, evidence-backed gate updates, actionable failure and
    retry explanations, and a standalone final handoff that distinguishes
    design-complete, hardware-ready, and hardware-qualified.

Run `python3 scripts/validate_prototype.py` after changing bundle configuration.
