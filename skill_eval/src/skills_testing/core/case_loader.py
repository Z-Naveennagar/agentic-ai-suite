"""
Loader for skill test cases on disk.

Two layouts are supported.

1. Legacy per-case layout (one directory == one case)::

    <skill_name>/<case_id>/
        manifest.yaml
        grading_spec.yaml
        inputs/                  (optional)

2. Suite layout (one directory == many cases; the "3-file" format)::

    <skill_name>/
        skill_spec.yaml          # test_cases: [ {id, input_files, expected} ]
        grader_spec.yaml         # output_schema (field -> grader) + scoring
        runner_spec.yaml         # skill identity, invocation, requirements
        inputs/                  # files referenced by test_cases[].input_files

The suite loader expands one suite directory into N ``CaseSpec`` objects
that are equivalent to what the runner would get from the legacy layout,
so nothing downstream (runner, workspace, graders, DB) needs to change.
``grader_spec.yaml`` holds a plain list of core graders (same shape as a
legacy ``grading_spec.yaml``); per-case ``expected`` values are
substituted into ``{token}`` placeholders in those graders.

The loader is deliberately strict on shape so misconfigured cases are
caught before we waste an LLM run on them.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from skills_testing.graders import GRADER_REGISTRY

# Suite filenames (the "3-file" format). The test-case list is read from
# ``test_cases.yaml`` when present, falling back to the older
# ``skill_spec.yaml`` name so both layouts load.
SKILL_SPEC = "skill_spec.yaml"
TEST_CASES_SPEC = "test_cases.yaml"
GRADER_SPEC = "grader_spec.yaml"
RUNNER_SPEC = "runner_spec.yaml"


def _skill_spec_path(suite_dir: Path) -> Path | None:
    """Return the suite's test-case spec path (test_cases.yaml preferred)."""
    for name in (TEST_CASES_SPEC, SKILL_SPEC):
        p = suite_dir / name
        if p.exists():
            return p
    return None


class CaseSchemaError(ValueError):
    """Raised when a case directory is missing or malformed."""


# The framework's closed, documented set of grader_spec.yaml placeholder
# names. Used only to detect a *known* placeholder left unsubstituted inline in a
# rubric/path string -- not a general `{\w+}` scan, so incidental curly
# braces in free-form rubric prose are never misread as placeholders.
#
# Split into two categories, since a single shared grader_spec.yaml can
# grade a MIX of case shapes within one suite (e.g. a pure-analysis case
# alongside a fix+verify case):
#   - always-required: every case's `expected:` block must define these,
#     no matter its shape. Missing one is a genuine data bug -> hard
#     CaseSchemaError, failing suite load (and thus `skills-test install`).
#   - conditional: only meaningful for *some* case shapes (log_path/
#     log_substring/tool_call_observed only apply to a case with a
#     run/verify step; expected_config/artifact_path only to a config-match
#     case). A case missing one isn't a bug -- that grader simply doesn't
#     apply to it, so it's dropped from that case's grading list rather
#     than raising or leaving broken placeholder data behind.
_ALWAYS_REQUIRED_PLACEHOLDER_NAMES = frozenset({"verdict", "answer", "skills"})
_CONDITIONAL_PLACEHOLDER_NAMES = frozenset({
    "log_path", "log_substring", "tool_call_observed",
    "expected_config", "artifact_path", "tool_sequence",
})
_KNOWN_PLACEHOLDER_NAMES = _ALWAYS_REQUIRED_PLACEHOLDER_NAMES | _CONDITIONAL_PLACEHOLDER_NAMES


#: Suffix marking a version-keyed variant of an ``expected`` field. See
#: :func:`_resolve_versioned_expected`.
_VERSIONED_SUFFIX = "_by_vivado_version"


def _resolve_versioned_expected(expected: dict) -> dict:
    """Collapse ``<field>_by_vivado_version`` variants into ``<field>``.

    A golden answer can be tool-version dependent: the same prompt has a
    different correct answer when the IP catalog changes between tool
    releases.

    So a case may write::

        expected:
          expected_output_by_vivado_version:
            "2026.1": {identified_ip: ps_wizard, ...}
            default:  {identified_ip: ps11, ...}

    Keys are matched as version *prefixes* against the installed tool
    version (``2026.1`` matches ``2026.1`` and ``2026.1.0``), longest first,
    with an optional ``default``. A resolved variant overwrites the plain
    field; when nothing matches, an already-present plain field is left
    untouched. Returns a new mapping -- the caller's data is not mutated.
    """
    versioned = [k for k in expected if k.endswith(_VERSIONED_SUFFIX)]
    if not versioned:
        return expected
    # Imported lazily: case loading must not pay the version-probe cost
    # unless a case actually asks for a version-keyed golden.
    from skills_testing.runtime.requirements_probe import _vivado_version
    installed = _vivado_version() or ""
    out = dict(expected)
    for vkey in versioned:
        variants = out.pop(vkey)
        if not isinstance(variants, dict):
            continue
        base = vkey[:-len(_VERSIONED_SUFFIX)]
        chosen = None
        for ver in sorted(
                (k for k in variants if str(k) != "default"),
                key=lambda s: len(str(s)), reverse=True):
            if installed.startswith(str(ver)):
                chosen = variants[ver]
                break
        if chosen is None and "default" in variants:
            chosen = variants["default"]
        if chosen is not None:
            out[base] = chosen
    return out


class _GraderNotApplicable(Exception):
    """Internal signal: a grader references a conditionally-required
    placeholder that this case's `expected:` block doesn't define. The
    grader doesn't apply to this case and should be dropped from its
    grading list -- distinct from a genuinely missing always-required
    field (verdict/answer/skills), which is a hard load error."""


def _validate_clients(entries: Any, source: str) -> list[dict]:
    """Validate a ``clients``/``coding_agent`` list shape: non-empty list of
    ``{name, model}`` mappings. *source* is a path or config key used in the
    error message. Returns the validated list unchanged."""
    if not entries or not isinstance(entries, list):
        raise CaseSchemaError(f"{source}: must be a non-empty list")
    for entry in entries:
        if not isinstance(entry, dict) or "name" not in entry or "model" not in entry:
            raise CaseSchemaError(f"{source}: each entry needs 'name' and 'model'")
    return entries


_LIFECYCLE_ACTION_KINDS = ("prompt", "python", "bash")


def _parse_lifecycle_action(
    raw: Any, path: Path, field_name: str
) -> dict[str, Any] | None:
    """Parse a suite-level ``setup:``/``teardown:`` action (runner_spec.yaml).

    Runs once per (suite, client, model) group -- see
    ``runtime/suite_lifecycle.py`` -- rather than per case. Shape::

        setup:
          kind: prompt          # sent through the same cli.invoke() path
          prompt: "..."         # as a real case, in the shared workspace
        teardown:
          kind: bash            # or "python" (a script file) -- run
          command: "..."        # directly by the harness, no agent involved

    Returns None if *raw* is absent (the common case: most suites need no
    suite-level fixture at all).
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise CaseSchemaError(f"{path}: {field_name} must be a mapping")
    kind = raw.get("kind")
    if kind not in _LIFECYCLE_ACTION_KINDS:
        raise CaseSchemaError(
            f"{path}: {field_name}.kind must be one of "
            f"{_LIFECYCLE_ACTION_KINDS}, got {kind!r}")
    if kind == "python":
        # Either a script file (suite-local) or an importable module run with
        # -m. The module form exists so a shared helper such as
        # runtime/vivado_session_setup.py can back many suites' setup without
        # each one carrying a shim script -- and it runs under sys.executable,
        # so `skills_testing` is importable by construction (a bash `python -m`
        # would depend on whatever `python` resolves to on PATH).
        if not raw.get("script") and not raw.get("module"):
            raise CaseSchemaError(
                f"{path}: {field_name} needs either .script or .module for "
                f"kind='python'")
        if raw.get("script") and raw.get("module"):
            raise CaseSchemaError(
                f"{path}: {field_name} sets both .script and .module for "
                f"kind='python' -- pick one")
    else:
        required = {"prompt": "prompt", "bash": "command"}[kind]
        if not raw.get(required):
            raise CaseSchemaError(
                f"{path}: {field_name}.{required} is required for kind={kind!r}")

    # args: passed through to kind=python as argv after the script. Without it
    # a script action could only be parameterized by editing the script, so a
    # generic helper (e.g. runtime/vivado_session_setup.py) had no way to be
    # told the part / bd name / which TCL lib to source.
    raw_args = raw.get("args") or []
    if not isinstance(raw_args, list):
        raise CaseSchemaError(f"{path}: {field_name}.args must be a list")
    if raw_args and kind != "python":
        raise CaseSchemaError(
            f"{path}: {field_name}.args is only supported for kind='python' "
            f"(got kind={kind!r}); for kind='bash' put the arguments in "
            f"{field_name}.command")
    args = [str(a) for a in raw_args]

    # The runner executes lifecycle scripts with cwd=<group workspace>, which
    # is not where the suite's files live and (for suites with no input_files)
    # contains nothing at all. So resolve a relative script: against the suite
    # directory here, at load time, while we still know where that is.
    script = raw.get("script")
    if kind == "python" and script:
        script_path = Path(str(script))
        if not script_path.is_absolute():
            resolved = (path.parent / script_path).resolve()
            if not resolved.is_file():
                raise CaseSchemaError(
                    f"{path}: {field_name}.script {script!r} not found "
                    f"(looked for {resolved}). Give a path relative to the "
                    f"suite directory, or an absolute one")
            script = str(resolved)

    return {
        "kind": kind,
        "prompt": raw.get("prompt"),
        "script": script,
        "module": raw.get("module"),
        "args": args,
        "command": raw.get("command"),
        "timeout_seconds": int(raw.get("timeout_seconds", 1800)),
    }


@dataclass
class CaseSpec:
    skill_name: str
    skill_version: str
    case_id: str
    case_dir: Path
    description: str = ""
    invocation: dict[str, Any] = field(default_factory=dict)
    requirements: dict[str, Any] = field(default_factory=dict)
    cleanup: list[str] = field(default_factory=list)
    # Suite-level (once-per-suite-per-client-per-arm) fixture actions --
    # see runtime/suite_lifecycle.py. None for legacy manifest.yaml cases
    # and for suites that declare no shared-workspace fixture (the common
    # case). Shape: {"kind": "prompt"|"python"|"bash", ...}.
    setup_action: dict[str, Any] | None = None
    teardown_action: dict[str, Any] | None = None
    # Runs after EVERY case in the group (not just the last), restoring
    # the shared workspace/session to baseline before the next case's
    # turn -- e.g. ip-configurator's ipcfg::cleanup, which deletes the
    # throwaway cell the case just configured.
    reset_action: dict[str, Any] | None = None
    # Parallel actions for the no-skill A/B arm -- same infra (e.g. start
    # Vivado, open a block design), deliberately WITHOUT sourcing the
    # skill's own helper library/procs, so the no-skill arm gets the same
    # shared-workspace treatment without the skill's tooling leaking in.
    # The two arms always get separate groups/sessions (see suite_key_for
    # usage in suite_lifecycle.py) -- never shared with the with-skill
    # arm's session, even when both are declared.
    setup_action_without_skill: dict[str, Any] | None = None
    teardown_action_without_skill: dict[str, Any] | None = None
    reset_action_without_skill: dict[str, Any] | None = None
    grading: list[dict[str, Any]] = field(default_factory=list)
    # Optional Phase 2b: apply the skill's own fix artifact and rerun
    # implementation to verify the issue is actually resolved. Schema:
    #   verify_by_rerun:
    #     enabled: true
    #     apply_artifact: outputs/timing_fixes.xdc
    #     apply_via: { tool: vivado_mcp, tcl: "..." }
    #     success_criteria: [ <grader spec>, ... ]
    #     budget_seconds: 1800
    verify_by_rerun: dict[str, Any] | None = None
    pass_threshold: float = 1.0
    # How per-grader results combine into the case score:
    #   "fraction"     -> passed / total (default, legacy behaviour)
    #   "weighted_sum" -> sum(weight_i * score_i) / sum(weight_i)
    # ``pass_threshold`` is always compared on the 0-1 scale.
    scoring_aggregation: str = "fraction"
    # Suite provenance (new 3-file format). None for legacy manifest cases.
    suite_id: str | None = None
    # Explicit inputs-dir control. Legacy cases derive `inputs_dir` from
    # ``case_dir/inputs``. Suite cases stage per-case files via
    # ``invocation.external_inputs`` instead and set this flag so the
    # shared suite ``inputs/`` dir is NOT bulk-copied into every case.
    inputs_dir_is_set: bool = False
    inputs_dir_override: Path | None = None

    @property
    def tags(self) -> list[str]:
        return list(self.requirements.get("tags") or [])

    @property
    def inputs_dir(self) -> Path | None:
        if self.inputs_dir_is_set:
            return self.inputs_dir_override
        d = self.case_dir / "inputs"
        return d if d.is_dir() else None


# -- public API ------------------------------------------------------------


def load_case(case_dir: Path) -> CaseSpec:
    case_dir = Path(case_dir)
    manifest_path = case_dir / "manifest.yaml"
    grading_path = case_dir / "grading_spec.yaml"

    if not manifest_path.exists():
        raise CaseSchemaError(f"missing manifest.yaml in {case_dir}")
    if not grading_path.exists():
        raise CaseSchemaError(f"missing grading_spec.yaml in {case_dir}")

    manifest = _load_yaml(manifest_path)
    grading_doc = _load_yaml(grading_path)

    _require(manifest, "skill_name", manifest_path)
    _require(manifest, "skill_version", manifest_path)
    _require(manifest, "case_id", manifest_path)
    _require(manifest, "invocation", manifest_path)

    invocation = manifest["invocation"]
    if not isinstance(invocation, dict):
        raise CaseSchemaError(f"{manifest_path}: invocation must be a mapping")
    clients = _validate_clients(invocation.get("clients"), f"{manifest_path}: invocation.clients")

    requirements = manifest.get("requirements") or {}
    if not isinstance(requirements, dict):
        raise CaseSchemaError(f"{manifest_path}: requirements must be a mapping")

    cleanup = manifest.get("cleanup") or []
    if not isinstance(cleanup, list):
        raise CaseSchemaError(f"{manifest_path}: cleanup must be a list")

    graders = grading_doc.get("graders")
    if not isinstance(graders, list):
        raise CaseSchemaError(f"{grading_path}: 'graders' must be a list")

    # Expand grader families (`- family: <name>`) into core grader specs
    # before validation. Families are pure spec-expanders.
    from skills_testing.graders.families import expand_graders
    try:
        graders = expand_graders(
            graders,
            meta={"skill": manifest["skill_name"], "case": manifest["case_id"]},
        )
    except (KeyError, ValueError) as exc:
        raise CaseSchemaError(f"{grading_path}: {exc}")

    for g in graders:
        if not isinstance(g, dict) or "type" not in g:
            raise CaseSchemaError(
                f"{grading_path}: each grader needs a 'type' field"
            )
        if g["type"] not in GRADER_REGISTRY:
            raise CaseSchemaError(
                f"{grading_path}: unknown grader type {g['type']!r}"
            )

    verify = manifest.get("verify_by_rerun")
    if verify is not None and not isinstance(verify, dict):
        raise CaseSchemaError(
            f"{manifest_path}: verify_by_rerun must be a mapping if present"
        )
    if verify and verify.get("enabled"):
        if "apply_via" not in verify or not isinstance(verify["apply_via"], dict):
            raise CaseSchemaError(
                f"{manifest_path}: verify_by_rerun.apply_via must be a mapping"
            )
        if "tool" not in verify["apply_via"]:
            raise CaseSchemaError(
                f"{manifest_path}: verify_by_rerun.apply_via.tool is required"
            )
        criteria = verify.get("success_criteria") or []
        if not isinstance(criteria, list):
            raise CaseSchemaError(
                f"{manifest_path}: verify_by_rerun.success_criteria must be a list"
            )
        for c in criteria:
            if not isinstance(c, dict) or "type" not in c:
                raise CaseSchemaError(
                    f"{manifest_path}: each success_criteria entry needs 'type'"
                )
            if c["type"] not in GRADER_REGISTRY:
                raise CaseSchemaError(
                    f"{manifest_path}: unknown grader type in success_criteria: "
                    f"{c['type']!r}"
                )

    pass_threshold = float(grading_doc.get("pass_threshold", 1.0))

    return CaseSpec(
        skill_name=manifest["skill_name"],
        skill_version=str(manifest["skill_version"]),
        case_id=manifest["case_id"],
        case_dir=case_dir,
        description=manifest.get("description", ""),
        invocation=invocation,
        requirements=requirements,
        cleanup=list(cleanup),
        grading=list(graders),
        verify_by_rerun=verify,
        pass_threshold=pass_threshold,
    )


def is_suite_dir(path: Path) -> bool:
    """True if *path* holds the 3-file suite layout (skill + runner spec)."""
    path = Path(path)
    return _skill_spec_path(path) is not None and (path / RUNNER_SPEC).exists()


def load_suite(suite_dir: Path) -> list[CaseSpec]:
    """Expand a 3-file suite directory into one CaseSpec per test case.

    Reads ``runner_spec.yaml`` (skill identity, invocation, requirements),
    ``grader_spec.yaml`` (output_schema + scoring) and ``skill_spec.yaml``
    (the ``test_cases`` list), and produces CaseSpec objects equivalent to
    the legacy manifest layout.
    """
    suite_dir = Path(suite_dir)
    runner_path = suite_dir / RUNNER_SPEC
    grader_path = suite_dir / GRADER_SPEC
    skill_path = _skill_spec_path(suite_dir)
    if skill_path is None:
        raise CaseSchemaError(
            f"missing {TEST_CASES_SPEC} (or {SKILL_SPEC}) in {suite_dir}"
        )
    for p in (runner_path, grader_path):
        if not p.exists():
            raise CaseSchemaError(f"missing {p.name} in {suite_dir}")

    runner = _load_yaml(runner_path)
    grader = _load_yaml(grader_path)
    skill = _load_yaml(skill_path)

    # -- runner_spec: identity + invocation + requirements ----------------
    _require(runner, "skill_name", runner_path)
    skill_name = str(runner["skill_name"])
    skill_version = str(runner.get("skill_version", "1.0.0"))
    suite_id = runner.get("suite_id") or skill.get("suite_id")

    invocation_in = runner.get("invocation") or {}
    if not isinstance(invocation_in, dict):
        raise CaseSchemaError(f"{runner_path}: invocation must be a mapping")

    # `coding_agent` is the suite spelling; accept `clients` as an alias.
    agents = invocation_in.get("coding_agent")
    if agents is None:
        agents = invocation_in.get("clients")
    agents = _validate_clients(agents, f"{runner_path}: invocation.coding_agent")
    clients: list[dict] = [{"name": e["name"], "model": e["model"]} for e in agents]

    skills_allow = invocation_in.get("skills")
    if skills_allow is None:
        skills_allow = [skill_name]
    elif not isinstance(skills_allow, list):
        raise CaseSchemaError(f"{runner_path}: invocation.skills must be a list")

    requirements = runner.get("requirements") or {}
    if not isinstance(requirements, dict):
        raise CaseSchemaError(f"{runner_path}: requirements must be a mapping")
    cleanup = runner.get("cleanup") or []
    if not isinstance(cleanup, list):
        raise CaseSchemaError(f"{runner_path}: cleanup must be a list")
    setup_action = _parse_lifecycle_action(runner.get("setup"), runner_path, "setup")
    teardown_action = _parse_lifecycle_action(runner.get("teardown"), runner_path, "teardown")
    reset_action = _parse_lifecycle_action(runner.get("reset"), runner_path, "reset")
    setup_action_ns = _parse_lifecycle_action(
        runner.get("setup_without_skill"), runner_path, "setup_without_skill")
    teardown_action_ns = _parse_lifecycle_action(
        runner.get("teardown_without_skill"), runner_path, "teardown_without_skill")
    reset_action_ns = _parse_lifecycle_action(
        runner.get("reset_without_skill"), runner_path, "reset_without_skill")

    # Prepended to every case's prompt (both arms) -- a session-level
    # protocol (e.g. "log every result as one JSONL line to a shared
    # file") that has to be restated per case rather than said once in
    # setup:, because each case is its own separate, stateless agent
    # invocation with no memory of the setup step's own conversation.
    # {case_number} substitutes this case's 1-based position in
    # test_cases (alongside the {skill_name}/{input_file} prompt already
    # supports). It is concatenated into the *user* prompt, not sent on any
    # system-prompt channel -- hence "prompt prefix", not "system prompt".
    # `master_prompt` is the former key name, still accepted as a
    # deprecated alias.
    shared_prompt_prefix = runner.get("shared_prompt_prefix")
    if shared_prompt_prefix is None and runner.get("master_prompt") is not None:
        warnings.warn(
            f"{runner_path}: `master_prompt` is deprecated; rename it to "
            "`shared_prompt_prefix` (it is a user-prompt prefix, not a "
            "system prompt).",
            DeprecationWarning,
            stacklevel=2,
        )
        shared_prompt_prefix = runner.get("master_prompt")
    if shared_prompt_prefix is not None and not isinstance(shared_prompt_prefix, str):
        raise CaseSchemaError(
            f"{runner_path}: shared_prompt_prefix must be a string")

    # The output-contract half of the shared preamble: the mandated JSON result
    # shape the agent must emit (graded by the `output_contract_match` grader).
    # Kept separate from shared_prompt_prefix (basic requirement + instructions)
    # so the two concerns can be authored and reused independently. The final
    # per-case prompt is assembled as:
    #     shared_prompt_prefix + output_contract + <test case prompt>
    output_contract = runner.get("output_contract")
    if output_contract is not None and not isinstance(output_contract, str):
        raise CaseSchemaError(
            f"{runner_path}: output_contract must be a string")

    # timeout / token budget may sit under invocation or at the top level.
    timeout_seconds = invocation_in.get(
        "timeout_seconds", runner.get("timeout_seconds", 600)
    )
    max_tokens = invocation_in.get(
        "max_tokens_per_run", runner.get("max_tokens_per_run")
    )
    # Max re-attempts after a per-attempt timeout. 0 = single attempt (legacy
    # behaviour). May sit under invocation or at the top level.
    retries = int(invocation_in.get("retries", runner.get("retries", 0)))
    # Shared prompt(s) for every case. Preferred source is a top-level
    # `prompt` / `prompt_without_skill` in skill_spec.yaml (common to all
    # test cases); a runner_spec-level `*_template` is honoured as a
    # fallback. A test case may still override either arm individually.
    prompt_tmpl = (
        skill.get("prompt")
        or invocation_in.get("prompt_template")
        or runner.get("prompt_template")
    )
    prompt_ns_tmpl = (
        skill.get("prompt_without_skill")
        or invocation_in.get("prompt_without_skill_template")
        or runner.get("prompt_without_skill_template")
    )

    # -- grader_spec: shared grader templates + scoring -------------------
    # Two shapes are accepted:
    #   graders:       a plain list of core grader specs (legacy shape)
    #   output_schema: a field -> {grader, grader_args, weight, mandatory,
    #                  always} map (the richer format). Converted to the
    #                  same internal grader list here.
    # Per-case ``expected`` values are substituted into ``{placeholder}``
    # tokens in each grader before use.
    scoring = grader.get("scoring") or {}
    aggregation = str(scoring.get("aggregation", "fraction")).strip().lower()
    if "output_schema" in grader:
        graders_tmpl = _output_schema_to_graders(grader["output_schema"], grader_path)
        # weighted_sum on a 0-100 scale is the common companion of
        # output_schema; normalise a >1 threshold to the 0-1 space the
        # runner scores in.
        default_thr = 70.0 if aggregation == "weighted_sum" else 1.0
        pass_threshold = float(scoring.get("pass_threshold", default_thr))
        if pass_threshold > 1.0:
            pass_threshold = pass_threshold / 100.0
    else:
        graders_tmpl = grader.get("graders")
        if not isinstance(graders_tmpl, list) or not graders_tmpl:
            raise CaseSchemaError(
                f"{grader_path}: 'graders' or 'output_schema' must be provided"
            )
        pass_threshold = float(scoring.get("pass_threshold", 1.0))

    # -- skill_spec: the test cases ---------------------------------------
    test_cases = skill.get("test_cases")
    if not isinstance(test_cases, list) or not test_cases:
        raise CaseSchemaError(f"{skill_path}: 'test_cases' must be a non-empty list")

    inputs_root = suite_dir / "inputs"
    out: list[CaseSpec] = []
    for tc_number, tc in enumerate(test_cases, start=1):
        if not isinstance(tc, dict) or "id" not in tc:
            raise CaseSchemaError(f"{skill_path}: each test case needs an 'id'")
        case_id = str(tc["id"])
        expected = tc.get("expected") or {}
        if not isinstance(expected, dict):
            raise CaseSchemaError(
                f"{skill_path}: test case {case_id!r} 'expected' must be a mapping"
            )
        expected = _resolve_versioned_expected(expected)
        input_files = tc.get("input_files") or []
        if not isinstance(input_files, list):
            raise CaseSchemaError(
                f"{skill_path}: test case {case_id!r} 'input_files' must be a list"
            )

        # `cell_name` is an optional per-case field (e.g. "bench_cell_001"),
        # computed here (rather than down with the prompt rendering below)
        # so it's available as a {cell_name} substitution to BOTH the
        # prompt AND the grader templates -- a grader like harness_script
        # needs it too (e.g. `--cell={cell_name}` to know which block-design
        # cell to read back), not just the prompt that tells the agent what
        # to name the cell it creates.
        extra = {}
        if tc.get("cell_name"):
            extra["cell_name"] = str(tc["cell_name"])

        # Render the shared grader templates for this case, substituting
        # {field} placeholders (e.g. {verdict}, {opposite}, {cell_name}) from
        # the case's `expected` values plus the suite-specific `extra` above.
        grading = _render_graders(
            graders_tmpl, {**extra, **expected}, grader_path, case_id)
        for g in grading:
            if "type" not in g:
                raise CaseSchemaError(
                    f"{grader_path}: each grader needs a 'type' field "
                    f"(case {case_id!r})"
                )
            if g["type"] not in GRADER_REGISTRY:
                raise CaseSchemaError(
                    f"{grader_path}: unknown grader type {g['type']!r} "
                    f"(case {case_id!r})"
                )

        # Stage only this case's declared files (matches the legacy
        # inputs_dir behaviour: files land at the workspace root).
        external_inputs: list[dict] = []
        for fname in input_files:
            src = (inputs_root / fname).resolve()
            if not src.exists():
                raise CaseSchemaError(
                    f"{skill_path}: input file for case {case_id!r} not found: {src}"
                )
            external_inputs.append({"src": str(src), "dest": fname})

        # Prompts live per-case in skill_spec.yaml. A runner_spec-level
        # template is still honoured as a fallback. Either way {skill_name},
        # {input_file} and {case_number} are substituted so a prompt can
        # stay generic. `cell_name` (computed above, alongside `extra`) is
        # available as {cell_name} in prompt/prompt_ns/shared_prompt_prefix
        # -- suite-specific data, not a generic convention the loader
        # derives on its own.
        first_input = input_files[0] if input_files else ""
        prompt = _render_prompt(
            tc.get("prompt") or prompt_tmpl,
            skill_name=skill_name, input_file=first_input, case_number=tc_number,
            case_id=case_id, extra=extra,
        )
        prompt_ns = _render_prompt(
            tc.get("prompt_without_skill") or prompt_ns_tmpl,
            skill_name=skill_name, input_file=first_input, case_number=tc_number,
            case_id=case_id, extra=extra,
        )
        # Assemble the shared preamble in order: basic requirement/instructions
        # (shared_prompt_prefix) then the output contract, prepended to the
        # test-case prompt -> final = prefix + output_contract + case prompt.
        preamble_parts = []
        for shared in (shared_prompt_prefix, output_contract):
            if shared:
                preamble_parts.append(_render_prompt(
                    shared, skill_name=skill_name, input_file=first_input,
                    case_number=tc_number, case_id=case_id, extra=extra,
                ))
        if preamble_parts:
            preamble = "\n\n".join(preamble_parts)
            if prompt:
                prompt = f"{preamble}\n\n{prompt}"
            if prompt_ns:
                prompt_ns = f"{preamble}\n\n{prompt_ns}"

        invocation: dict[str, Any] = {
            "clients": clients,
            "skills": list(skills_allow),
            "timeout_seconds": timeout_seconds,
            "retries": retries,
            "external_inputs": external_inputs,
        }
        if max_tokens is not None:
            invocation["max_tokens_per_run"] = max_tokens
        if prompt:
            invocation["prompt"] = prompt
        if prompt_ns:
            invocation["prompt_without_skill"] = prompt_ns

        out.append(CaseSpec(
            skill_name=skill_name,
            skill_version=skill_version,
            case_id=case_id,
            case_dir=suite_dir,
            description=tc.get("description") or skill.get("description", ""),
            invocation=invocation,
            requirements=requirements,
            cleanup=list(cleanup),
            setup_action=setup_action,
            teardown_action=teardown_action,
            reset_action=reset_action,
            setup_action_without_skill=setup_action_ns,
            teardown_action_without_skill=teardown_action_ns,
            reset_action_without_skill=reset_action_ns,
            grading=grading,
            pass_threshold=pass_threshold,
            scoring_aggregation=aggregation,
            suite_id=suite_id,
            # Inputs staged per-case via external_inputs; do NOT bulk-copy
            # the shared suite inputs/ dir into every case.
            inputs_dir_is_set=True,
            inputs_dir_override=None,
        ))
    return out


def discover_cases(
    test_cases_root: Path,
    config: dict | None = None,
    *,
    cli_clients: list[dict] | None = None,
) -> list[CaseSpec]:
    """Load every case under *test_cases_root*.

    A skill directory using the 3-file suite layout is expanded via
    :func:`load_suite`; otherwise the directory is scanned one level deeper
    for legacy per-case ``manifest.yaml`` directories.

    If *config* is given and ``skill_testing.coding_agents`` is a non-empty
    list, it replaces ``invocation.clients`` on every returned case,
    regardless of what that case's own manifest.yaml/runner_spec.yaml
    declares. This is a signoff framework: the backends/models a skill is
    validated against are meant to be the fixed set a customer actually has,
    not whatever a suite author found convenient -- so this override is
    unconditional, with no per-case opt-out.

    *cli_clients*, when given, is a one-off ``--client``/``--model`` pair
    from a single ``skills-test run``/``run --dry-run`` invocation (see
    customer_cli.py/integration_runner.py) -- applied last, so it outranks
    both a suite's own declared clients and the persistent
    ``skill_testing.coding_agents`` config override. Scoped to that one
    invocation only, unlike ``coding_agents`` which affects every run until
    the config is edited back.
    """
    root = Path(test_cases_root)
    if not root.is_dir():
        return []
    found: list[CaseSpec] = []
    for skill_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        if is_suite_dir(skill_dir):
            found.extend(load_suite(skill_dir))
            continue
        for case_dir in sorted(p for p in skill_dir.iterdir() if p.is_dir()):
            if not (case_dir / "manifest.yaml").exists():
                continue
            found.append(load_case(case_dir))

    master_clients = ((config or {}).get("skill_testing") or {}).get("coding_agents")
    if master_clients:
        master_clients = _validate_clients(master_clients, "skill_testing.coding_agents")
        for case in found:
            case.invocation["clients"] = list(master_clients)

    if cli_clients:
        cli_clients = _validate_clients(cli_clients, "--client/--model")
        for case in found:
            case.invocation["clients"] = list(cli_clients)

    return found


def filter_cases(
    cases: list[CaseSpec],
    allowlist: list[str],
    denylist: list[str],
    tag_filter: list[str] | None = None,
) -> list[CaseSpec]:
    """
    Apply the policy from config:
      - denylist always blocks (even if allowlisted)
      - empty allowlist means 'allow everything not denied'
      - tag_filter (if given) keeps only cases with at least one matching tag
    """
    deny = set(denylist or [])
    allow = set(allowlist or [])
    tag_filter = set(tag_filter) if tag_filter else None

    out: list[CaseSpec] = []
    for c in cases:
        if c.skill_name in deny:
            continue
        if allow and c.skill_name not in allow:
            continue
        if tag_filter is not None and not (set(c.tags) & tag_filter):
            continue
        out.append(c)
    return out


# -- internals -------------------------------------------------------------


def _output_schema_to_graders(output_schema: Any, grader_path: Path) -> list[dict]:
    """Translate an ``output_schema`` map into the internal grader list.

    Each entry ``field: {grader, grader_args, weight, mandatory, always}``
    becomes a core grader spec dict ``{id, type, weight, mandatory, always,
    **grader_args}`` — i.e. the field name is the grader id, ``grader`` is
    the registry ``type``, and ``grader_args`` are flattened in as the
    grader's own keys (matching what the ``graders:`` list shape produces).
    """
    if not isinstance(output_schema, dict) or not output_schema:
        raise CaseSchemaError(
            f"{grader_path}: 'output_schema' must be a non-empty mapping"
        )
    out: list[dict] = []
    for field_name, entry in output_schema.items():
        if not isinstance(entry, dict):
            raise CaseSchemaError(
                f"{grader_path}: output_schema.{field_name} must be a mapping"
            )
        gtype = entry.get("grader")
        if not gtype:
            raise CaseSchemaError(
                f"{grader_path}: output_schema.{field_name} needs a 'grader'"
            )
        args = entry.get("grader_args") or {}
        if isinstance(args, str):
            # A bare placeholder like ``'{skills}'`` — the whole args block is
            # supplied per-case from ``expected``. Seed a same-named key
            # holding the placeholder so per-case rendering (``_render_graders``)
            # resolves ``{skills}`` -> the (possibly list) expected value.
            token = _sole_placeholder(args)
            if token is None:
                raise CaseSchemaError(
                    f"{grader_path}: output_schema.{field_name}.grader_args "
                    f"must be a mapping or a single '{{token}}' placeholder"
                )
            args = {token: args}
        elif not isinstance(args, dict):
            raise CaseSchemaError(
                f"{grader_path}: output_schema.{field_name}.grader_args "
                f"must be a mapping"
            )
        mandatory = bool(entry.get("mandatory", False))
        spec: dict[str, Any] = {
            "id": str(field_name),
            "type": str(gtype),
            "mandatory": mandatory,
            "always": bool(entry.get("always", True)),
        }
        # skill_only graders run only in the with-skill arm (e.g. a
        # skill-specific output-contract check): they are skipped in the
        # no-skill A/B arm, where the skill is hidden and the golden result
        # doesn't apply -- see runner._run_specs.
        if entry.get("skill_only"):
            spec["skill_only"] = True
        # Mandatory graders are pure Pass/Fail gates (the hallucination
        # contract): they do not carry a weight and do not contribute a
        # score to the aggregate. Only soft graders are weighted/scored.
        if not mandatory:
            spec["weight"] = float(entry.get("weight", 1.0))
        # grader_args are the grader's own keys; don't let them clobber the
        # structural fields above.
        for k, v in args.items():
            spec.setdefault(k, v)
        out.append(spec)
    return out


def _render_prompt(
    template: str | None, *, skill_name: str, input_file: str,
    case_number: int | None = None, case_id: str | None = None,
    extra: dict[str, str] | None = None,
) -> str:
    """Substitute {skill_name}/{input_file}/{case_number}/{case_id}, plus
    any {key} in *extra* (e.g. a suite-specific {cell_name}), in a suite
    prompt template.

    Uses str.replace (not .format) so literal braces elsewhere in the
    prompt are left untouched. Returns "" when *template* is falsy.
    """
    if not template:
        return ""
    out = (
        str(template)
        .replace("{skill_name}", skill_name)
        .replace("{input_file}", input_file)
    )
    if case_number is not None:
        out = out.replace("{case_number}", str(case_number))
    if case_id is not None:
        out = out.replace("{case_id}", case_id)
    for key, value in (extra or {}).items():
        out = out.replace("{" + key + "}", str(value))
    return out


def _lookup_dotted(subs: dict, token: str) -> tuple[bool, Any]:
    """Whole-value substitution lookup, supporting one or more ``.``-separated
    path segments, e.g. ``expected_output.as_configured`` ->
    ``subs["expected_output"]["as_configured"]``.

    Lets a grader reference a value nested inside another placeholder's dict
    (e.g. `config_match` pulling just the `as_configured` map out of a
    suite's larger `{expected_output}` golden) without the suite having to
    duplicate that nested value as its own top-level `expected:` key --
    duplication that would drift the moment one copy is updated and the
    other isn't. A bare (non-dotted) token behaves exactly as before.

    Returns ``(found, value)`` -- ``found`` is False on a missing key at any
    segment, letting the caller apply its usual missing-placeholder handling
    (hard error for an always-required token, drop-the-grader for a
    conditional one) instead of this helper deciding that itself.
    """
    cur: Any = subs
    for part in token.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return False, None
        cur = cur[part]
    return True, cur


def _sole_placeholder(s: str) -> str | None:
    """Return ``name`` if *s* is exactly ``"{name}"`` (nothing else), else None."""
    if not isinstance(s, str):
        return None
    t = s.strip()
    if (t.startswith("{") and t.endswith("}")
            and t.count("{") == 1 and t.count("}") == 1):
        return t[1:-1]
    return None


def _subst_placeholders(
    obj: Any, subs: dict[str, Any], *, case_id: str, grader_path: Path,
) -> Any:
    """Recursively substitute ``{key}`` tokens in every string within *obj*.

    Two substitution modes:

    * **Whole-value** -- when a string is *exactly* ``"{key}"``, the string is
      replaced by the raw value of ``subs[key]``. This preserves lists/dicts
      (e.g. ``grader_args: '{skills}'`` -> the ``skills`` list), which the
      inline mode below could not. If ``key`` has no entry in *subs*: for an
      always-required key (verdict/answer/skills) this raises rather than
      silently leaving the literal ``"{key}"`` string in place -- a grader
      receiving that raw string where it expects a list (e.g.
      ``action_sequence``'s ``tool_sequence``) would otherwise iterate it
      character-by-character and silently mis-grade instead of erroring (a
      real bug this guard was added to prevent). For a *conditional* key
      (log_path/log_substring/tool_call_observed/expected_config/
      artifact_path/tool_sequence -- only meaningful for some case shapes
      within a suite, e.g. a fix+verify case but not a pure-analysis one)
      this instead raises ``_GraderNotApplicable`` so ``_render_graders``
      can drop the whole grader for this case rather than erroring.
    * **Inline** -- every scalar ``{key}`` occurrence embedded in a larger
      string is replaced with ``str(value)`` (e.g. ``{verdict}`` -> ``YES``
      inside a rubric). Non-scalar values are skipped inline since they have
      no sensible string form.

    Non-string leaves pass through unchanged.
    """
    if isinstance(obj, str):
        token = _sole_placeholder(obj)
        if token is not None:
            found, val = _lookup_dotted(subs, token)
            if found:
                return val
            if token in _CONDITIONAL_PLACEHOLDER_NAMES:
                raise _GraderNotApplicable(token)
            raise CaseSchemaError(
                f"{grader_path}: case {case_id!r} is missing expected.{token}, "
                f"required by a grader_args: '{{{token}}}' placeholder"
            )
        for key, val in subs.items():
            if isinstance(val, (str, int, float, bool)):
                obj = obj.replace("{" + key + "}", str(val))
        # An always-required placeholder token (e.g. `{verdict}` inline in a
        # rubric) surviving substitution means that key was absent from
        # `expected` entirely (present-but-non-scalar values are a distinct,
        # allowed case -- a list-valued field embedded inline rather than
        # whole-value is simply not how it's meant to be referenced).
        # Conditional tokens are exempt here too, for the same reason as the
        # whole-value branch above; in practice they only ever appear as
        # whole-value entries in this codebase, not embedded inline, so this
        # is a belt-and-suspenders check, not the primary path. Checked
        # against the framework's own closed, documented set of placeholder
        # names (see grader-agent.md's Guidelines: "do not invent alternate
        # names") rather than a generic `{\\w+}` scan, so incidental curly
        # braces in free-form rubric prose aren't misread as placeholders.
        for known in _ALWAYS_REQUIRED_PLACEHOLDER_NAMES:
            if known not in subs and "{" + known + "}" in obj:
                raise CaseSchemaError(
                    f"{grader_path}: case {case_id!r} is missing expected.{known}, "
                    f"referenced inline as '{{{known}}}'"
                )
        return obj
    if isinstance(obj, dict):
        return {k: _subst_placeholders(v, subs, case_id=case_id, grader_path=grader_path)
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [_subst_placeholders(v, subs, case_id=case_id, grader_path=grader_path)
                for v in obj]
    return obj


def _render_graders(
    graders: list, expected: dict, grader_path: Path, case_id: str,
) -> list[dict]:
    """Specialise the suite's shared grader list for one test case.

    Each grader is a plain core grader spec (``type: ...``). Values from
    *expected* become ``{name}`` substitutions inside the grader specs, so a
    single template grades every case in the suite. Scalars substitute inline
    (inside rubrics/paths); list/dict values substitute whole (a grader arg
    that is exactly ``"{name}"`` becomes the list/dict itself).

    A grader referencing a conditional placeholder (see
    ``_CONDITIONAL_PLACEHOLDER_NAMES``) that this case's ``expected`` doesn't
    define is dropped from this case's grading list entirely -- it simply
    doesn't apply (e.g. a suite mixing a pure-analysis case with a
    fix+verify case: `log_contains`/`csynth_log_exists` apply to the latter
    only, not because the former is missing data it should have had).
    """
    subs = dict(expected or {})
    out: list[dict] = []
    for g in graders:
        if not isinstance(g, dict):
            raise CaseSchemaError(f"{grader_path}: each grader must be a mapping")
        try:
            out.append(_subst_placeholders(g, subs, case_id=case_id, grader_path=grader_path))
        except _GraderNotApplicable:
            continue
    return out


def _load_yaml(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise CaseSchemaError(f"{path}: invalid YAML: {exc}") from exc


def _require(d: dict, key: str, path: Path) -> None:
    if key not in d or d[key] is None:
        raise CaseSchemaError(f"{path}: missing required key {key!r}")
