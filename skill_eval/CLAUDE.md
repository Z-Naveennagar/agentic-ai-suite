# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A harness that **runs, grades, and benchmarks AI agent skills** against AMD EDA toolchains (Vivado, Vitis HLS). It launches an agent CLI (Claude Code, Cursor, Copilot, opencode) against a test case, captures its transcript/artifacts, grades the result, and records everything to a SQLite DB for a dashboard. This is a *signoff* framework: skill content is authored in `staging/`, test suites in `tests/`, and both only reach the agent-facing `.claude/skills/`/`.opencode/skills/` directories (and the runner's test-cases workspace) after passing `skills-test install`'s structural validation — see "Skill source of truth" below.

## Package identity (note the three-way naming)

| What | Value |
|------|-------|
| Distribution | `amd-skills-test` |
| Import name | `skills_testing` |
| CLI command | `skills-test` (entry point `skills_testing.cli.customer_cli:main`; also `python -m skills_testing`) |
| Layout | `src/` (setuptools `where = ["src"]`), Python 3.10+ |

## Repo layout: git root vs. harness root

The git repo root (`amd-skills-test/`) holds four things: `staging/` (skill
content), `tests/` (test suite content — both see "Skill source of
truth" below), `skill-signoffs/` (per-skill signoff snapshots — see "Reporting"
below), and `skill_eval/`. Everything else — `pyproject.toml`,
`src/skills_testing/`, `config.yaml`, `pricing.yaml`, `.claude/skills/`,
`.opencode/skills/`, `_runtime/`, `_workspace/`, `tools/`, and this file —
lives under `skill_eval/`, which is the harness's actual project root
(`PROJECT_ROOT`, `core/paths.py`). Every `skills-test <command>` resolves
paths relative to `skill_eval/` regardless of your shell's cwd, so no `cd`
is required to run them (see "Setup, run, test" below for the two commands,
`pip install -e` and `pytest`, that do need a path pointed at `skill_eval/`
instead). The harness's own pytest suite is nested one level deeper, at
`skill_eval/tests/`, so it doesn't collide with `skill_eval/` itself.

`staging/` and `tests/` are authored content, kept as siblings of
`skill_eval/` at the true git root rather than nested inside it, so a skill
or suite author can work entirely outside the harness's own internals —
they only ever touch `staging/<skill_name>/` and
`tests/<skill_name>/<suite_name>/`, never anything under `skill_eval/`.
They are reached from `skill_eval/config.yaml` via explicit `"../staging"`
and `"../tests"` path values (`skill_testing.staging_root` and
`skill_testing.test_suites`) rather than the bare relative names every
other `skill_testing:` config key uses, since those two cross the
`skill_eval/` boundary.

`skill-signoffs/` gets the same `"../skill-signoffs"` treatment
(`skill_testing.skill_signoffs_root`), but for the opposite reason: it isn't
authored, it's generated (see "Reporting" below) — kept as a git-root
sibling rather than gitignored under `skill_eval/_runtime/` like the
dashboard, because a per-skill signoff snapshot is meant to be committed
and reviewed, not treated as disposable scratch.

## Setup, run, test

```bash
# from amd-skills-test/ (the git root) -- no cd into skill_eval/ required, see below
pip install -e skill_eval          # REQUIRED before any CLI or test invocation
pip install pytest                 # test-only dep, NOT in pyproject.toml

pytest skill_eval/tests             # full suite (uses temp SQLite via conftest.py — never touches results.db)
pytest skill_eval/tests/test_graders.py::test_name   # single test

skills-test doctor                          # host readiness
skills-test install [--dry-run]             # validate + install skills (staging/) + suites (tests/)
skills-test list [--tags smoke] [--json]    # enumerate cases
skills-test run --skills rtl-assistant --dry-run     # validate manifests + plan, no execution
skills-test run --skills hls-array-to-stream --parallel 4   # actual run
skills-test run --skills hls-dataflow --reps 3       # repeated consistency evaluation
python -m skills_testing.reporting.generate_report --port 8080   # dashboard at localhost:8080
```

Every `skills-test <command>` above resolves `config.yaml`, `skills_root`, and the workspace relative to where the `skills_testing` package is installed on disk (`PROJECT_ROOT`, computed from `__file__` — see "Non-obvious gotchas" below), not the shell's current directory, so none of them need a `cd` into `skill_eval/` first. Only `pip install -e` and `pytest` are inherently path-relative-to-cwd — point them at `skill_eval` / `skill_eval/tests` explicitly (as above) instead of `cd`-ing in, if you'd rather stay at the git root.

Every command takes `--config <path>` to override the bundled default at `config.yaml` (`skill_eval/` — deliberately outside `src/skills_testing/`, since it's project config rather than package data); config is JSON-Schema-validated (`src/skills_testing/schemas/config_schema.json`) on every invocation — invalid config exits with the field path. Model & hardware pricing (`model_pricing:`) lives in a separate sibling file, `pricing.yaml` — externally-sourced vendor $/Mtok rates and self-hosted machine capex/power on a different maintenance cadence than the rest of config.yaml, validated against `schemas/pricing_schema.json` and merged back into the config dict under the same `model_pricing` key by `core/cost_model.py:load_config()`. A missing `pricing.yaml` degrades to no pricing data (costs come back `None`/`unknown`) rather than a hard error.

## Architecture (the big picture)

The flow is **case → run → grade → record → report**.

- **CLI (`core`/`cli/customer_cli.py`)** — `run` has two code paths: `--dry-run` is handled entirely in `customer_cli.py`; actual execution delegates to `core/integration_runner.py` (the real driver — discovers cases, gates on host capabilities, schedules with resource awareness, runs each through `SkillRunner`, writes to DB).

- **CLI backends (`cli_backends/`)** — one adapter per agent: `claude_code`, `cursor`, `copilot`, `opencode`, looked up via the `_REGISTRY` in `cli_backends/__init__.py`. Two layers, don't conflate them:
  - `interface.py:SkillBackend` — **the contract**, and the only surface the runner/graders/workspace stager may rely on: identity attrs (`name`, `transcript_format`, `workspace_skills_dir`, `binary_env_var`, all read off the *class* so grading works on a host with no CLI binary), availability (`is_available`/`unavailable_reason`), execution (`build_command`, `invoke` → `InvokeResult.as_dict()`), token stats (`parse_token_usage` → `TokenUsage`, resolved via `token_usage`), and the observability/A-B hooks (`detect_skill_invocation`, `hide_skills_env_overrides`, `extract_vivado_session_ids`, `preflight_skip`). Only `invoke` is abstract; everything else ships a working default, so `NullSkillCLI` and test doubles implement the same interface instead of duck-typing a subset.
  - `base.py:SkillCLIBackend` — the shared **implementation** for everything that drives a real CLI subprocess: binary discovery (config `bin_path` > env var > PATH), streamed capture with per-line timestamps, timeout → `exit_code 124` plus partial output, tool-call timeline, final-response extraction. A concrete backend declares only what differs.

  Backends are **workspace-aware**: they `cd` into the workspace so a `.claude/`/`.cursor/` subdir there is discovered as the skill/MCP root. Missing binary → `NullSkillCLI` (`is_available` False; the case records a SKIPPED row).

  **Token stats have exactly one override point: `parse_token_usage`.** Return `None`/empty for "no signal" and the interface applies the shared fallback (generic `input_tokens`/`prompt_tokens` envelope, then a char-count estimate flagged `TokenUsage.estimated`). Never call the fallback or `token_usage` from inside it. `_parse_usage`/`_parse_usage_extended` are deprecated shims kept for external callers — the pair used to be mutually recursive, which forced every backend to inline a duplicate of its own parser.

- **Graders (`graders/`)** — a grader takes a spec dict from `grading_spec.yaml`/`grader_spec.yaml` + a `GraderContext` (workspace, stdout/stderr, lookups) and returns `GraderResult(passed, score, details)`. Core grader types registered in the `GRADER_REGISTRY`: `content_contains`, `artifact_exists`, `artifact_valid`, `metric_threshold`, `baseline_delta`, `metric_delta`, `llm_judge`, `report_schema`, `oracle_match`, `artifact_signature`, `tool_call_observed` (`_builtins.py`), plus `trigger`, `diff`, `program`, `action_sequence`, `config_match` (own modules). **Grader families** (`violation`, `linter`, `coder`, `tool-execution`) are *expanders* — a family entry in a `grading_spec.yaml` expands at case-load time into several core graders.

- **Runtime (`runtime/`)** — workspace management, host `requirements_probe`, `cleanup_manager`, power metering, and shared suite setup/reset/teardown lifecycle.

- **Lifecycle (`core/lifecycle.py`)** — consistency policy over repeated skill-enabled runs. It evaluates coverage, status rates, per-case `aggregate_score` spread, and mandatory/weighted grader failure rates, then writes run-scoped history to `skill_lifecycle_evaluations`.

- **Reporting (`reporting/`)** — `generate_report.py` serves the dashboard and every `skills-test run` also refreshes a static `_runtime/reports/index.html` (under `skill_eval/` — every generated artifact lives under `_runtime/`, alongside `_workspace/`, not under `src/skills_testing/`) (`--no-refresh-dashboard` to skip). Separately, `skill_signoffs.py` writes a per-skill signoff snapshot to `skill-signoffs/<skill_name>_summary/` for every skill in that run that has at least one row in `skill_test_results` (`--no-skill-signoffs` to skip): the installed skill content from `.claude/skills/<skill_name>/` (always the latest snapshot, never versioned) is copied into a `<skill_name>/` subfolder; everything *generated* lives in a sibling `report/` subfolder, kept out of the skill-content directory: `report.html` reusing `dashboard.py:render_skill_run_report` (the same headline/consistency-tree/heatmap rendering as the main dashboard, scoped to one skill's one run instead of everything) — versioned `report_v2.html`, `report_v3.html`, ... on repeat runs of the same skill, derived by scanning `report/` rather than a stored counter — and `README.md`, whose environment block reflects the latest run while its run-history table gains one row per run, with prior rows preserved verbatim.

## Skill source of truth: `staging/` + `tests/` → `skills-test install` → `.claude/skills/` + `_workspace/`

Skill content and test suites are authored in separate trees, joined by skill name at install time:

```
staging/<skill_name>/SKILL.md, ...             # one source directory per skill

tests/<skill_name>/<suite_name>/               # one or more 3-file suites
    grader_spec.yaml
    test_cases.yaml
    runner_spec.yaml
```

A skill with one suite may also place the three suite files directly under
`tests/<skill_name>/`; the nested form is canonical and supports multiple
suites per skill. `tests/` replaces the old `vivado_skills_repo/` layout.
**Never hand-edit `.claude/skills/`, `.opencode/skills/`, or `_workspace/`
directly** — edit the skill under `staging/<skill_name>/` or its suite under
`tests/<skill_name>/<suite_name>/` and re-run install.

`skills-test install [--dry-run] [--source PATH] [--staging PATH]` (`core/skill_repo.py`) matches every suite under `tests/` to a skill in `staging/` and prints a PASS/FAIL report per skill (a skill needs ≥1 structurally-valid suite — reuses `case_loader.is_suite_dir`/`load_suite`, so the pass bar is identical to what the runner enforces at load time). A skill in `staging/` that no suite anywhere references still gets a report, so it shows up as a FAIL rather than silently vanishing. A suite that matches no skill at all in `staging/` surfaces only as a warning (`unmatched_suite_warnings`), not a report of its own — there's no skill to attach a FAIL to. Only **passing** skills get installed:
- the skill dir → `.claude/skills/<skill_name>/` **and** `.opencode/skills/<skill_name>/` (only that subdirectory is touched — hand-authored skills already there that aren't sourced from `staging/` are left alone)
- each valid suite → `skill_testing.test_cases_root` (default `_workspace/`, gitignored, always empty until install runs)

A suite's owning skill is matched either by directory name or, when that doesn't line up (see `hls-burst-inference_33` matching skill `hls-burst-inference` by content), by the suite's own `runner_spec.yaml:skill_name` field — mismatches print as warnings, not failures. Directory names are never load-bearing for `discover_cases()` itself (see below), only for this install-time association.

**Known gap:** `rtl-assistant`, `timing-closure-optimized`, `timing-closure-prototype`, `vivado-revision-control` have no suite under `tests/` yet (legacy `manifest.yaml` format doesn't fit the 3-file-only contract) — they're currently untested; the corresponding seed-case tests are skipped with a reason pointing here.

## Test case anatomy

`core/case_loader.py` supports two on-disk layouts, both expanded into the same `CaseSpec` before reaching the runner/graders/DB — nothing downstream cares which one a case uses, and neither cares what directory name it was discovered under (identity comes from `manifest.yaml`/`runner_spec.yaml` content, e.g. `skill_name:`):

- **Legacy per-case layout** — one directory is one case:
  - `manifest.yaml` — `invocation` (clients+models, prompt, inputs_dir, timeout), `requirements` (vivado/vitis, memory, disk, tags, est. duration), `cleanup`.
  - `grading_spec.yaml` — `pass_threshold` + list of graders (core `type:` or `family:`).
  - `inputs/` — files staged into the workspace; `expected_answer.txt` for answer-quality cases.

- **Suite ("3-file") layout** — one directory expands into *N* cases (e.g. `tests/ip-configurator/ip-configurator_gen/` or `tests/hls-burst-inference/hls-burst-inference_08/`):
  - `test_cases.yaml` — the list of test cases (`id`, `input_files`, per-case `expected` values); `skill_spec.yaml` is the older name for this file and still loads.
  - `grader_spec.yaml` — one shared `output_schema` (field → grader + `mandatory`/`always`/weight) grading every case; per-case `expected` values are substituted into `{token}` placeholders in `grader_args`.
  - `runner_spec.yaml` — shared `skill_name`, `suite_id`, `invocation` (multi-backend `coding_agent` list, skill allowlist, `timeout_seconds`, `retries`), and `requirements` for the whole suite.
  - `inputs/` — shared pool referenced by each case's `input_files` (not bulk-copied into every workspace, unlike legacy `inputs_dir`).

  Scaffold a canonical authored suite with `skills-test init --skill <name> --suite <suite>`.
  It creates `tests/<name>/<suite>/` with the three YAML files and an `inputs/`
  directory; edit those sources and run `skills-test install` to validate and copy
  them into the generated `_workspace/` tree.

  **Suite-level fixtures (`setup:`/`reset:`/`teardown:` in `runner_spec.yaml`)** run once per `(suite, client, model, arm)` group, not per case (`runtime/suite_lifecycle.py`), in the shared workspace every case in that group reuses. Three `kind`s: `prompt` (goes through `cli.invoke()`, so the *agent* does the work), and `python`/`bash` (run directly by the harness — no agent, no tokens, no LLM variance).

  Prefer `python` for environment prep. A `prompt` setup makes one LLM turn the gate on every case in the suite, and when it improvises the failures look like skill failures. `kind: python` takes either `script:` (resolved against the **suite dir** at load time, since the runner runs it with `cwd=<workspace>`) or `module:` (run with `-m` under `sys.executable`, so `skills_testing` is importable by construction — a bash `python -m` would depend on whatever `python` resolves to, and this host has no bare `python`), plus `args:`.

  Two things make a script fixture able to hand a live Vivado session to the cases:
  - **Print `VIVADO_SESSION_ID:<id>` on stdout.** `runner._parse_session_id_sentinels` reads it into `group.session_ids`, which seeds `carried_session_ids` so every case's prompt is told to reuse that session (`_augment_prompt_reuse_session`, whose neutral `[HARNESS SESSION NOTICE]` variant is used on first attempts and the `[HARNESS RETRY NOTICE]` one only after a real timeout).
  - **`{skills_dir}` / `{workspace}` / `{session_id}` tokens in `args:` are substituted per client.** The staged skills tree is backend-specific — opencode uses `.opencode/skills`, Claude Code and Copilot `.claude/skills` (`create_workspace(skills_dest=skills_dir_for(client))`) — so a hardcoded path is right for one backend and silently wrong for the rest. `{session_id}` resolves to `group.session_ids[0]` (empty string when the group has none), which is how a `reset:` action targets the live session `setup:` created instead of starting its own.

  **`reset:` runs after every group member *except the last*, and a failure is fatal to the group.** There is no next case after the last member — teardown wipes the workspace moments later — so a reset there is pure waste (for `ip-configurator`, a whole Vivado close/reopen cycle per group); `runner.py` detects it as `group.remaining <= 1`, still pre-decrement and under `group.lock`. A failed reset sets `GroupState.reset_error`, and every remaining member is then recorded `ERROR` without spending an agent invocation, alongside the existing `setup_error` gate. It used to be a `logger.warning`, which meant a dirty shared design (leftover cells, or a part a case swapped and never restored) silently failed *later*, innocent cases and blamed them for it.

  `runtime/vivado_session_reset.py` is the ready-made reset (used by `ip-configurator`): deletes cells/ports by **pattern** (`--cell-pattern=bench_cell_*`), then restores `--part` in the group's existing session — it never starts or stops Vivado. Two non-obvious ordering rules it encodes, both found by live smoke tests, and both of which `ipcfg::cleanup` in the skill's own `lib/ipcfg.tcl` still gets wrong: **`save_bd_design` must run before the part restore's `close_bd_design`** (the deletes are in-memory, `close_bd_design` discards unsaved changes, and `open_bd_design` then resurrects every cell you just deleted while the reset reports success), and **cells must be deleted before the part is restored** (a case may have swapped to a part whose IP the baseline part cannot host — `clk_wizard` on `xcvc1902` vs `xc2ve3558`). It takes the baseline part as an argument rather than recovering it from session state, because the `kind: prompt` reset it replaced passed `$orig_part` — a Tcl variable a fresh, stateless agent could only inherit by luck, which `ipcfg::cleanup` reads as "don't restore the part" when empty.

  `runtime/vivado_session_setup.py` is the ready-made one (used by `ip-configurator`): starts one session, sets the part, creates the BD, sources a skill's TCL lib, leaves the session running. Two Vivado-MCP realities it encodes, both learned the hard way — a `[REJECTED] ... already running` or dropped-connection reply means the command may still be *running*, so recover the result from `vivado_status` rather than re-sending the TCL (which would double-apply it), and back off geometrically because that tool throttles tight pollers; and concurrent `vivado_start`s trip the server's webserver thread-handling, so session creation is serialized behind a `flock` keyed on the MCP URL (`--no-serialize` opts out).

  These three files are hand-authored per suite (there is no generator for them).

## Development priorities (as of 2026-08-07)

The harness has one execution model: run the installed skill repeatedly and assess consistency. A/B/no-skill execution was removed.

- `--reps N` repeats each case/client/model within one `test_runs` record. Use it instead of launching N separate commands so score spread and PASS/FAIL disagreement are measured correctly.
- Lifecycle snapshots are automatic. Runs below `consistency_lifecycle.min_reps` or coverage requirements are recorded as `UNASSESSED` (or preserve an established prior state) rather than producing a weak signoff decision.
- Lifecycle gates use status rates, per-case `aggregate_score` spread, and mandatory/weighted grader failure percentages. Diagnostic grader failures are reported but do not gate.
- Dashboard and `skill-signoffs` are presentations of the same SQLite evidence; do not implement separate report-only lifecycle math. A signoff package is durable inspection evidence for approving a skill's promotion from `staging/` to production.

## Non-obvious gotchas

- **Never use `/tmp` for workspace.** Vivado DCPs need GBs; tmpfs fills → `insufficient_disk` skips. Set `skill_testing.workspace_root` in config, or `--workspace-root`, or `SKILL_TEST_WORKSPACE_ROOT`. Default is `~/.cache/amd-skills-test/workspaces`.
- **Two path roots, don't confuse them:** `core/paths.py:REPO_ROOT` is `src/skills_testing/` (the *package* root — source code and schemas only, nothing generated lives here anymore) while `PROJECT_ROOT` (`REPO_ROOT.parent.parent`) is `skill_eval/` — the harness's project root, used for `config.yaml`, `pricing.yaml`, `_workspace/` (installed test-case definitions), `skills_root` (`.claude/skills`), and `_runtime/` (every generated artifact: `database.path`, `results_dir`, `session_log.dir`, and the dashboard's `reports/`). **`PROJECT_ROOT` is *not* the actual git repo root** — since the `staging/` + `tests/` + `skill_eval/` split (see "Repo layout" above), the true git top-level is one level above `PROJECT_ROOT` and holds `staging/` and `tests/` as `skill_eval/`'s siblings. `staging_root` and `test_suites` are the two config keys that have to reach across that boundary, hence their explicit `"../staging"` / `"../tests"` values in `config.yaml` rather than the bare relative name every other key under `skill_testing:` uses. `resolve_repo_path()` anchors at `REPO_ROOT`; `resolve_project_path()` anchors at `PROJECT_ROOT` — pick the one matching the config key you're resolving. Since the `_runtime/` move, `database.path`/`results_dir`/`session_log.dir` are all `PROJECT_ROOT`-relative like `test_cases_root`, not `REPO_ROOT`-relative — `REPO_ROOT` no longer has any config key resolving against it at all.
- **`doctor` exits 0 unless a *hard* check fails.** Hard: config, test_cases, skills_root, database_parent, workspace_root. Everything else (vivado, vitis, license, MCP, CLI binaries, copilot auth) reports FAIL but doesn't change exit code.
- **Copilot must hit GitHub-hosted models**, not a local BYOK server. The harness strips `COPILOT_PROVIDER_*` env vars; set `USE_COPILOT_BYOK=1` to opt into local routing, `SKILL_TEST_COPILOT_STRIP_GH_TOKEN=1` to also strip ambient PATs.
- **DB cleanup:** only clear `skill_*` tables in `results.db` (now at `_runtime/results.db`) — it also holds Q&A doc-search history. Back up first (`cp _runtime/results.db _runtime/results.db.bak.$(date +%s)`).
- **Self-hosted model cost** uses `model_pricing.machines` (calendar-hour amortization), not per-token rates. `model_pricing` itself lives in `pricing.yaml`, not `config.yaml` — see "Setup, run, test" above.

## Skill libraries under test

- `.claude/skills/` / `.opencode/skills/` — installed, agent-facing skill directories, both gitignored and untracked: they are generated output, so a fresh clone has neither until `skills-test install` runs. Populated from `staging/` (see above) for skills that pass validation; anything hand-authored there is untouched by install — and, being untracked, exists only on the machine that authored it.
- `staging/` — flat skill-content source, one directory per skill. Not gitignored — this is authored source, same as `tests/`.
- `tests/` — test-suite source grouped by skill, with suites under `tests/<skill_name>/<suite_name>/` (for example `tests/hls-array-to-stream/hls-array2stream-12/`). Skill content itself lives in `staging/`, not here.
