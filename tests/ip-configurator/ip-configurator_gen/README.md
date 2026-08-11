# ip-configurator-test-kit — suite inputs

This directory holds files that would be **staged into the workspace** if a case
listed them in `input_files:`. Today every case has `input_files: []`, so this
directory is intentionally empty of stageable content — every case's prompt is
self-contained.

## Suite shape

- 31 cases, one per natural-language IP-configuration intent sourced from the
  RAVE2 SAPPHIRE Versal AI Edge Gen2 design (part `xc2ve3558-sfva1440-2MP-e-S`).
- Each case's `prompt` in `test_cases.yaml` is written the way a real customer
  would phrase it: target part, cell name, and the design intent. It does **not**
  name the skill under test, does not describe any two-tier / doc-driven /
  verification protocol, and does not select an operating mode. All of that is
  the responsibility of `SKILL.md` — the graders exist to check that the skill
  triggered on customer language and executed its own discipline.

## Grading gates (all mandatory)

- `skill_triggered` — the `ip-configurator` skill activated from customer intent.
- `no_tool_errors` — no `ERROR:` on stderr.
- `output_contract` — the agent's emitted JSON result (`identified_ip`,
  `vlnv`, `as_configured`, `tier1_success`, `tier2_success`, `notes`, etc.)
  matches this case's golden config. Comparison is tolerant (numeric fuzz,
  `true`/`false`↔`1`/`0`, comma-list element-wise, separator/case-insensitive
  names); `notes` is judged semantically by an LLM for factual consistency,
  not literal wording. A golden value of `null` is a don't-care wildcard.


## Blind-integrity notep

The RAVE2 answer key is **not** copied to the workspace directory and agent CLIs does not have
access to this. The values needed for grading are already inlined into each case's
`expected.expected_output` in `test_cases.yaml`. 

## Reference score

**Run:** 2026-07-26 · `opencode` · 2 models × 2 reps = 124 results

| Model          | Pass | Total | Rate  |
|----------------|:----:|:-----:|:-----:|
| `gpt-5.4`      | 36   | 62    | 58.1% |
| `gpt-5.4-mini` | 36   | 62    | 58.1% |
| **Combined**   | **72** | **124** | **58.1%** |

Lower than the standalone kit's historical 28/31 because `output_contract` also
grades `identified_ip`, `vlnv`, and the `tier1_success`/`tier2_success`/
`self_fidelity` self-report fields, not just `CONFIG.*`.

### Failure breakdown (31 cases)

**Failed on both models, all 4 runs — 9 cases**
- 16, 17 — `clk_wizard` unsupported on `xc2ve3558`; agent substitutes `clk_wiz`/`clkx5_wiz`
- 29, 30, 31 — resolve to `pcie_versal`/`ps_wizard` instead of `ps11`; params land nested under `PS11_CONFIG`
- 22, 28 — `CONFIG.*` all match, wrong IP version only (`visp_ss:1.0` vs `2.0`, `vcu2:2.0` vs `3.0`)
- 21 — `CMN_VC`, `C_PHY_MODE`
- 26 — LPDDR5 MC params gated behind device/board automation

**Failed on both models, some runs — 3 cases**
- 06, 20, 24 — `axi_noc2 CONFIG.DATA_WIDTH`, connection-derived

**Single-model flakes — 6 cases** (sampling variance, not suite gaps)
- 04, 18, 08 — `gpt-5.4` only
- 01, 13, 23 — `gpt-5.4-mini` only

**Clean on all 4 runs — 13 cases**
- 02, 03, 05, 07, 09–12, 14, 15, 19, 25, 27

