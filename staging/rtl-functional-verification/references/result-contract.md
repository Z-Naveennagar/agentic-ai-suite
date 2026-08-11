<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Result Contract

Emit one JSON object per regression and validate it with `scripts/verify_result.py`.

```json
{
  "schema_version": 1,
  "backend": "cocotb-verilator",
  "status": "PASS",
  "tool_versions": {"verilator": "5.x", "cocotb": "2.x"},
  "tests": {"required": 12, "run": 12, "passed": 12, "failed": 0, "skipped": 0},
  "checks": {
    "compile_ok": true,
    "elaboration_ok": true,
    "simulator_exit_code": 0,
    "terminal_pass": true,
    "assertion_failures": 0,
    "checker_failures": 0,
    "timeouts": 0
  },
  "seeds": [1, 2, 3],
  "coverage_reviewed": true,
  "exclusions": [],
  "unverified_boundaries": [],
  "artifacts": {"log": "results/sim.log", "junit": "results/results.xml"}
}
```

## PASS invariants

A PASS result requires:

- `required == run == passed`;
- `failed == 0`;
- compile and elaboration true;
- simulator exit code zero;
- terminal pass true;
- zero assertion failures, checker failures, and timeouts;
- coverage reviewed when the verification plan requires it.

Skipped tests do not count as passed. A test expected to fail must prove the expected failure and be
reported separately by the test framework; do not hide it in `skipped`.

Use `status: "FAIL"` for a verified DUT or test failure. Use `status: "ERROR"` for infrastructure,
unsupported backend, malformed result, crash, or incomplete execution. Never emit PASS in an
exception or cleanup path.

Store paths relative to the regression root when practical. Preserve raw logs and databases; the
JSON summary is evidence indexing, not a replacement for raw artifacts.

## Multi-tier regressions

Emit one independently validated result object per backend or tier. Keep its `backend`, tool
versions, tests, checks, coverage review, exclusions, and boundaries local to that execution.

A separate rollup may reference the per-tier result paths. It must list which tiers are required
and may report PASS only when every required result exists, validates, and reports PASS. Never
average test or coverage counts across simulators, and never let a fast portable-RTL tier waive an
XSim tier required for AMD models, X/Z behavior, or mixed-language integration.
