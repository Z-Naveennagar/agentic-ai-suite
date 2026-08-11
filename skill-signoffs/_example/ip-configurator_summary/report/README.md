# IP-configurator inspection example

This package captures the completed 10-case consistency evaluation used to demonstrate staging-to-production review.

## Run

- **Run ID:** `437ff984`
- **Vivado:** 2026.1
- **Cases:** `ip-configurator-test-kit_01` through `_10`
- **Clients/models:** Claude Code / Sonnet and OpenCode / `azure/gpt-5.4-mini`
- **Repetitions:** 3 per case/client/model
- **Total attempts:** 60
- **Outcomes:** 58 PASS, 2 FAIL, 0 ERROR, 0 SKIP
- **Pass rate:** 96.7%
- **Recorded cost:** $27.9095
- **Recorded prompt + output tokens:** 200,871

## Lifecycle conclusions

| Client / model | Outcome | Pass rate | Lifecycle | Why |
|---|---:|---:|---|---|
| OpenCode / `azure/gpt-5.4-mini` | 30/30 PASS | 100% | **KEEP** | Full coverage, no failed or flaky cases, and no mandatory grader failures. |
| Claude Code / Sonnet | 28/30 PASS | 93.3% | **WATCH** | One failure in case 07 and one in case 08 produced a 20% flaky-case rate and a 3.3% mandatory grader failure rate. |

## Inspection

Open [`report.html`](report.html) in a browser. The report is self-contained and provides:

- filters for case, CLI, model, consistency, and outcome;
- expandable test cases and individual repetition evidence;
- cost and token-consumption summaries;
- configurable column visibility, order, and width;
- lifecycle disclosures explaining how each conclusion was reached.

This is a committed format example, not a production-promotion approval.
