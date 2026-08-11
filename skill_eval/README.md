# amd-skills-test

AMD Agent Skills Testing Infrastructure — run, grade, and benchmark AI agent skills against Vivado, Vitis, and other AMD EDA toolchains.

## Installation

```bash
# From source (development)
git clone <repo-url> amd-skills-test
cd amd-skills-test        # git root -- holds staging/ + test_suites/ + skill_eval/ (the harness's project root)
python3.10 -m venv .venv
source .venv/bin/activate
pip install -e skill_eval   # points pip at skill_eval/pyproject.toml without cd-ing into it

# From published package
pip install amd-skills-test
```

Every `skills-test <command>` (and `pip install -e skill_eval` above) can be run from anywhere — they resolve `config.yaml`, the skills root, and the workspace relative to where the package is installed on disk, not your shell's current directory. The only commands that need a path argument instead of a `cd` are the one above and `pytest skill_eval/tests` (see "Testing" below).

Requires Python 3.10+.

## Quick Start

```bash
# Check host readiness
skills-test doctor

# List shipped test cases
skills-test list

# Validate a run without executing
skills-test run --dry-run

# Scaffold a canonical test suite under tests/my-skill/my-suite/
skills-test init --skill my-skill --suite my-suite

# Run test cases
skills-test run --skills ip-configurator --tags smoke

# Run the ip-configurator
skills-test run --skills ip-configurator 

# Launch the full results dashboard (http://localhost:8080/)
python -m skills_testing.reporting.generate_report --port 8080

# Generate a report bundle
skills-test report --output results.zip
```

## Dashboard

The HTML dashboard (Skill Testing results, grading, LLM-judge scores, and
full session transcripts) is served by `generate_report`:

```bash
python -m skills_testing.reporting.generate_report --port 8080
# then open http://localhost:8080/
```

- `--port <N>` — HTTP port (default `8080`).
- `--db <path>` — point at a specific results DB (defaults to the harness DB
  used by `skills-test run`, i.e. `_runtime/results.db` under `skill_eval/`).

Every `skills-test run` also auto-regenerates a static dashboard at
`_runtime/reports/index.html` (under `skill_eval/`) — just hard-reload the
browser after a run (pass `--no-refresh-dashboard` to skip).

Separately, it writes a per-skill signoff snapshot to
`eval-output/<skill_name>_summary/` for every skill in that run (pass
`--no-eval-output` to skip): the installed skill content as actually
tested is copied into a `<skill_name>/` subfolder, alongside a `report/`
subfolder holding everything generated -- `report.html` (versioned
`report_v2.html`, `report_v3.html`, ... on repeat runs of the same skill)
and a `README.md` with an environment summary and a run-history table
that gains one row per run.

## Running the IP Configurator Skill

`ip-configurator` configures Vivado IP blocks from natural language and **needs a working, licensed Vivado install**, along with the Vivado MCP server (check both with `doctor`). Its suite (31 blind-benchmark cases) shares one live Vivado session per `(client, model)` across every case
in a run — a `setup:` action opens the session and a shared block design once,
`reset:` restores it to baseline between cases, and `teardown:`/cleanup close
it after the last case (see `test_suites/ip-configurator/runner_spec.yaml`).

```bash
# Install the skill (from staging/) + its suite (from test_suites/) first
skills-test install

# Run the full 31-case blind benchmark
skills-test run --skills ip-configurator

# A single case, or a handful by id
skills-test run --cases ip-configurator-test-kit_01
skills-test run --cases ip-configurator-test-kit_01 ip-configurator-test-kit_02

# Repeat the same case N times to check run-to-run consistency
# (the priority over one-off pass/fail — see CLAUDE.md)
skills-test run --cases ip-configurator-test-kit_01 --reps 3

# Filter by tag (vivado, blind-benchmark, ip-configurator)
skills-test run --tags blind-benchmark
```

Then view results in the dashboard (above). Additional models are enabled by
uncommenting entries under `invocation.coding_agent` in that suite's
`runner_spec.yaml`; each extra `(client, model)` pair opens its own concurrent
Vivado MCP session, so watch the server's concurrent-session cap (7) if other
suites are running at the same time.

## Commands

| Command | Description |
|---------|-------------|
| `doctor` | Check host readiness: tools, licenses, CLI binaries, disk, MCP connectivity |
| `install` | Validate skills from `staging/` + test suites from `test_suites/` and install passing ones into `.claude/skills`, `.opencode/skills`, and the test-cases workspace |
| `install --dry-run` | Print the validation report only, without installing anything |
| `run` | Execute skill test cases against configured AI agents; refreshes the dashboard and writes `eval-output/` signoff snapshots when done |
| `run --dry-run` | Validate manifests, resolve inputs, print execution plan without running |
| `run --no-eval-output` | Skip writing `eval-output/<skill_name>_summary/` signoff snapshots after this run |
| `list` | Enumerate test cases with tags, requirements, and estimated durations |
| `list --tags <tag>` | Filter cases by tag |
| `list --json` | Output as JSON |
| `report` | Generate a reviewable ZIP bundle of results |
| `package-report` | Alias for `report` |


## Configuration

The bundled default config is at `config.yaml` (repo root). Override with `--config`:

```bash
skills-test --config /path/to/my-config.yaml doctor
```

The config is validated against a JSON Schema on every CLI invocation. Invalid configs exit with a field path and error message.

### Config Sections

| Section | Purpose |
|---------|---------|
| `skill_testing` | Test harness: workspace, parallelism, allow/deny lists, `llm_judge` (per-case semantic-field grading) |
| `model_pricing` | Per-model token pricing + hardware cost models (in `pricing.yaml`) |
| `cli_backends` | Per-agent CLI settings (models, MCP URLs) |
| `database` | SQLite results DB path |
| `grading` | `mcp_server_aliases` for tool-call graders |

## Cloud API Configuration

For cloud-hosted models (Anthropic, OpenAI, Google), set the appropriate API key environment variables before running tests.

### Anthropic (Claude Code)

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

Claude Code will pick up the key automatically. The `config.yaml` `model_pricing.models` section already contains pricing for all Claude variants (Opus, Sonnet, Haiku).

### OpenAI (Cursor, Copilot)

```bash
export OPENAI_API_KEY="sk-..."
```

Or use Cursor's API usage pool — no separate key needed if you have a Cursor subscription.

### Azure OpenAI

```bash
export AZURE_OPENAI_API_KEY="..."
export AZURE_OPENAI_ENDPOINT="https://<resource>.openai.azure.com/"
```

### GitHub Copilot CLI

Copilot uses GitHub authentication. Two paths:

1. **OAuth token** (interactive): Run `copilot auth login` once, token stored in `~/.copilot/config.json`.
2. **Fine-grained PAT** (headless): Create a GitHub PAT with `Copilot Requests` scope, export as:
   ```bash
   export GH_TOKEN="ghp_..."
   # or
   export GITHUB_TOKEN="ghp_..."
   # or
   export COPILOT_GITHUB_TOKEN="ghp_..."
   ```

The test harness strips BYOK env vars (`COPILOT_PROVIDER_BASE_URL`, etc.) so runs use GitHub-hosted models, not a local server. Set `SKILL_TEST_COPILOT_STRIP_GH_TOKEN=1` to also strip ambient PATs (falls back to stored OAuth token).

### LLM Judge

The per-case LLM-as-judge (`skill_testing.llm_judge`, feeding the `semantic_fields` comparison in `output_contract_match.py`) grades runs via a **gateway-first, CLI-fallback** pathway: it calls an Anthropic-compatible API when one is configured, and otherwise falls back to a local CLI agent (opencode → copilot → Cursor `agent`).

The gateway can be enabled and fully configured from the environment — no `config.yaml` edit required. Each variable overrides the matching `skill_testing.llm_judge.gateway` config key:

```bash
# Direct Anthropic API — presence of this key alone enables the gateway
export ANTHROPIC_API_KEY="sk-ant-..."

# Corporate / Azure gateway (Ocp-Apim-Subscription-Key auth)
export LLM_GATEWAY_SUBSCRIPTION_KEY="..."   # also auto-enables the gateway
export LLM_GATEWAY_BASE_URL="https://<gateway-host>/..."
export LLM_GATEWAY_API_KEY="..."            # optional; defaults to "dummy"
export LLM_GATEWAY_MODEL="azure/gpt-5.4"    # override the judge model
export LLM_GATEWAY_MAX_TOKENS="1024"        # override max_tokens

# Explicitly force the gateway on or off (overrides the auto-enable above)
export LLM_GATEWAY_ENABLED=1                # 1/true/yes/on — or 0/false/no/off
```

| Variable | Effect |
|----------|--------|
| `ANTHROPIC_API_KEY` | Use the direct Anthropic endpoint; its presence auto-enables the gateway |
| `LLM_GATEWAY_SUBSCRIPTION_KEY` | Subscription key for a corporate gateway; its presence auto-enables the gateway |
| `LLM_GATEWAY_BASE_URL` | Gateway base URL |
| `LLM_GATEWAY_API_KEY` | Gateway API key (default `dummy`) |
| `LLM_GATEWAY_MODEL` | Judge model id |
| `LLM_GATEWAY_MAX_TOKENS` | Judge response token cap |
| `LLM_GATEWAY_ENABLED` | Force enable/disable; an explicit value wins over the credential auto-enable |

If no gateway is configured, the judge uses the local CLI agent found by `_find_judge_bin` (override its binary via `AGENT_BIN` for Cursor). Transient failures **and** unparseable judge responses are retried with backoff before a run is scored `F`.

## On-Premises / Air-Gapped Configuration

For self-hosted models via Lemonade (or any OpenAI-compatible local inference server):

### Lemonade Setup

```bash
# Install Lemonade snap
sudo snap install lemonade --classic

# Start the server (example: Gemma-4-26B)
lemonade serve /path/to/Gemma-4-26B-A4B-it-GGUF --port 8000
```

Then configure the CLI backend in `config.yaml`:

```yaml
cli_backends:
  opencode:
    lemonade_base_url: "http://localhost:8000/api/v1"
    default_models:
      - "lemonade/Gemma-4-26B-A4B-it-GGUF"
```

### Ollama Setup

```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Pull a model
ollama pull qwen3:35b

# Start (default port 11434)
ollama serve
```

Configure the backend to point at Ollama's OpenAI-compatible endpoint:

```yaml
cli_backends:
  opencode:
    lemonade_base_url: "http://localhost:11434/v1"
    default_models:
      - "qwen3:35b"
```

### Air-Gapped Considerations

- **No cloud API keys needed** — all inference runs locally.
- **Pricing**: Self-hosted models use the `model_pricing.machines` section for cost estimation (capex amortization + power). See `config.yaml` for the `strix_halo` machine definition.
- **Disk**: Use a large scratch volume for `skill_testing.workspace_root`. The bundled default is `~/.cache/amd-skills-test/workspaces`; override it for larger Vivado jobs. Avoid `/tmp` (too small for Vivado DCPs).
- **Workspace**: Set `skill_testing.workspace_root` in config or pass `--workspace-root` to `skills-test run`.

## Post-Install Steps

1. **Verify installation**: `skills-test doctor`
2. **Set workspace root**: Optionally edit `config.yaml` → `skill_testing.workspace_root` to a larger disk for Vivado-heavy runs (the default is `~/.cache/amd-skills-test/workspaces`).
3. **Configure API keys** (cloud) or **start local server** (on-prem) per sections above.
4. **Run a smoke test**: `skills-test run --dry-run --tags smoke`

## Testing

```bash
pip install pytest
pytest skill_eval/tests   # from the git root; or `pytest tests/` if you cd'd into skill_eval/
```

## Tool-call grading (`tool_sequence`) and MCP tool names

The `action_sequence` grader (and the `tool-execution` family's `sequence:`)
checks the tools an agent actually called against an expected list. In a suite
`test_cases.yaml` this is the per-case `expected.tool_sequence`; in a
`grading_spec.yaml` it is the `action_sequence` grader's `tool_sequence` /
`expected_actions`. Each entry is matched as an exact tool name (or a
`"<tool>: <command>"` pattern that also checks the executed command).

### Per-backend transcript dialects

Tool calls are recovered from the agent transcript by
`skills_testing.graders.trace`. Each CLI backend emits a different transcript
format, declared on the backend class as `transcript_format` (in
`src/skills_testing/cli_backends/`) and dispatched by the `client` recorded in
the run's `run_meta`:

| Client | `transcript_format` | Set by | Tool-call encoding |
|--------|---------------------|--------|--------------------|
| `claude_code` | `anthropic_stream_json` | `--output-format stream-json` | line-delimited JSON `tool_use` blocks |
| `opencode` | `opencode_logs` | `--print-logs` | `→` arrow (built-ins), **`⚙` gear (MCP)**, `$` shell |
| `copilot` | `copilot_bullets` | bullet output | `● Read …`, `● skill(…)` |
| `cursor` | `cursor_json` | `--output-format stream-json` | JSONL: assistant + `tool_call` events + terminal `result` |

When the client is known, `trace` uses that backend's parser directly; when it
is unknown/absent it falls back to format auto-detection. The
`transcript_format` is read off the backend *class* (never instantiated), so
grading works on a host without the CLI binary installed.

### Canonical MCP tool names (portable across backends)

The same MCP call is spelled differently per backend — Claude Code uses
`mcp__<server>__<tool>` while OpenCode uses `<server>_<tool>`. `trace`
**normalizes every backend to the canonical `mcp__<server>__<tool>` form**, so
one `tool_sequence` value matches regardless of which client ran the case.
(The canonical form deliberately contains no `:`, so it never collides with the
`"<tool>: <command>"` command-pattern syntax.)

Author MCP assertions using the canonical name:

```yaml
expected:
  tool_sequence:
  - mcp__vivado-mcp-server__vivado_execute   # runs all TCL (create_bd_cell, set_property, …)
  - mcp__vivado-mcp-server__vivado_doc_search
```

Notes:
- The `<server>` segment is the MCP server key from the backend config, e.g.
  `vivado-mcp-server` and `vivado-doc-search` (both written by the
  `claude_code`/`opencode` backends).
- The `ip-configurator` skill wraps all Vivado TCL inside `vivado_execute`, so
  `create_bd_cell`/`set_property` are **not** separate MCP calls —
  `mcp__vivado-mcp-server__vivado_execute` is the tool that always fires
  (`vivado_doc_search` is skipped on a learned-cache hit, so don't require it if
  you want robustness).
- Default matching is `any_order_match` (each listed tool must appear at least
  once). To inspect what a run actually invoked, read `actual_actions` in the
  grader details.

## Project Structure

```
amd-skills-test/                        # git root -- staging/, test_suites/, eval-output/, and skill_eval/ live here
├── staging/                            # Skill content SOURCE, flat (staging/<skill_name>/)
│   └── ip-configurator/               # SKILL.md + lib/ipcfg.tcl (what `install` ships)
├── test_suites/                        # Test-suite SOURCE, flat (test_suites/<suite_dir>/)
│   └── ip-configurator/               # 3-file suite: test_cases/grader_spec/runner_spec.yaml
├── eval-output/                        # Per-skill signoff snapshots (generated; committed, not gitignored)
│   └── ip-configurator_summary/       # One "_summary" container per skill
│       ├── ip-configurator/          #   Installed skill content (SKILL.md, ...) as actually tested
│       └── report/                   #   report.html (+ versioned report_v2.html, ...) and
│                                      #     README.md with a run-history table
└── skill_eval/                          # The harness's project root -- no cd needed, see CLAUDE.md
    ├── pyproject.toml
    ├── config.yaml                    # Bundled default config (staging_root: "../staging", test_suites: "../test_suites")
    ├── pricing.yaml                   # Model & hardware pricing (split from config.yaml)
    ├── CLAUDE.md                      # Guidance for AI coding agents in this repo
    ├── AGENTS.md                      # Symlink -> CLAUDE.md
    ├── _workspace/                    # Installed test cases (gitignored; `install` output)
    ├── _runtime/                      # Generated artifacts (gitignored): results.db, results/,
    │                                  #   logs/, reports/ — see core/paths.py:RUNTIME_DIR
    ├── .claude/skills/, .opencode/skills/  # Installed skills (also `install` output)
    ├── tools/
    │   └── analyze_failures.py
    ├── src/skills_testing/
    │   ├── cli/
    │   │   └── customer_cli.py        # CLI entry points
    │   ├── cli_backends/              # Per-agent adapters: claude_code, opencode, copilot, cursor
    │   ├── core/                      # Case loading, running (runner.py), scheduling, skill_repo.py
    │   ├── graders/                   # Grader implementations + families/, validators/
    │   ├── runtime/                   # Workspace, cleanup_manager.py, suite_lifecycle.py,
    │   │                              #   vivado_session_setup.py / vivado_session_reset.py
    │   ├── reporting/                 # Dashboard, report generation
    │   ├── schemas/                   # config_schema.json + pricing_schema.json
    │   └── verifiers/                 # Tool-call verification (vivado_mcp.py)
    └── tests/                         # The harness's OWN unit-test suite (pytest)
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `No module named 'jsonschema'` | `pip install jsonschema` |
| `config error: ...` | Run `skills-test --config <path> doctor` to validate; check field path in error |
| `workspace_root ... not accessible` | Set `skill_testing.workspace_root` to an accessible path or pass `--workspace-root` |
| `copilot binary not found` | Install GitHub Copilot CLI or set `COPILOT_BIN` |
| `cursor binary not found` | Install Cursor CLI or set `AGENT_BIN` |
| Vivado/Vitis not found | Add to PATH or install AMD EDA tools |
| `insufficient_disk` during run | Use a larger scratch volume; avoid `/tmp` |

## License

Proprietary — AMD Internal Use Only.
