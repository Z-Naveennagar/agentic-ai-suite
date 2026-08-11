"""Customer-facing command line entry points for the skill-test harness.

The internal harness already has the primitives for workspaces, case loading,
grading, and dashboards. This module wraps those primitives in stable commands
that are easier to document and hand to external skill authors:

    python -m skills_testing init --skill my-skill --suite my-suite
    python -m skills_testing doctor ...
    python -m skills_testing run ...
    python -m skills_testing package-report ...
"""

from __future__ import annotations

import argparse
from importlib import import_module, metadata as importlib_metadata
import json
import os
import platform
import shutil
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import yaml

from ..core.case_loader import CaseSchemaError, discover_cases, load_case
from ..core.paths import (
    DEFAULT_CONFIG, DEFAULT_PRICING_CONFIG, PROJECT_ROOT, REPO_ROOT, REPORTS_DIR,
    default_workspace_root, resolve_project_path, resolve_repo_path,
)
from ..core import skill_repo
from ..runtime.requirements_probe import probe_host, vivado_satisfies, vivado_version
from ..runtime.workspace import probe_workspace_root


@dataclass
class DoctorCheck:
    name: str
    status: str
    detail: str


def load_config(
    config_path: str | os.PathLike | None = None,
    pricing_path: str | os.PathLike | None = None,
) -> dict:
    path = Path(config_path or DEFAULT_CONFIG)
    if not path.exists():
        return {}
    cfg = yaml.safe_load(path.read_text()) or {}

    # Validate against JSON schema
    from jsonschema import validate, ValidationError
    from ..schemas import CONFIG_SCHEMA_PATH, PRICING_SCHEMA_PATH
    import json as _json
    with open(CONFIG_SCHEMA_PATH) as f:
        schema = _json.load(f)
    try:
        validate(instance=cfg, schema=schema)
    except ValidationError as exc:
        print(f"config error: {exc.message}", file=sys.stderr)
        print(f"  path: {' -> '.join(str(p) for p in exc.absolute_path)}", file=sys.stderr)
        sys.exit(1)

    # model_pricing lives in its own file (pricing.yaml) -- see config.yaml's
    # header comment. Merge it back in under the same key so any caller of
    # this function still sees a "complete" effective config; a missing
    # pricing file degrades to no pricing data, same as a missing config.yaml
    # degrades to {} above, rather than a hard error.
    pricing_file = Path(pricing_path or DEFAULT_PRICING_CONFIG)
    if pricing_file.exists():
        pricing_cfg = yaml.safe_load(pricing_file.read_text()) or {}
        with open(PRICING_SCHEMA_PATH) as f:
            pricing_schema = _json.load(f)
        try:
            validate(instance=pricing_cfg, schema=pricing_schema)
        except ValidationError as exc:
            print(f"pricing config error: {exc.message}", file=sys.stderr)
            print(f"  path: {' -> '.join(str(p) for p in exc.absolute_path)}", file=sys.stderr)
            sys.exit(1)
        cfg["model_pricing"] = pricing_cfg.get("model_pricing", {})
    else:
        cfg.setdefault("model_pricing", {})
    return cfg


def scaffold_suite(
    *,
    tests_root: Path,
    skill_name: str,
    suite_name: str,
    client: str = "claude_code",
    model: str = "sonnet",
    force: bool = False,
) -> Path:
    """Create a canonical three-file starter suite in the authored tests tree."""
    suite_dir = tests_root / skill_name / suite_name
    if suite_dir.exists() and any(suite_dir.iterdir()) and not force:
        raise FileExistsError(
            f"suite already exists and is not empty: {suite_dir}. "
            "Use --force to overwrite generated stubs."
        )
    suite_dir.mkdir(parents=True, exist_ok=True)
    (suite_dir / "inputs").mkdir(exist_ok=True)

    runner = {
        "skill_name": skill_name,
        "skill_version": "0.1.0",
        "suite_id": suite_name,
        "invocation": {
            "coding_agent": [{"name": client, "model": model}],
            "skills": [skill_name],
            "timeout_seconds": 600,
        },
        "requirements": {
            "vivado": False,
            "vitis": False,
            "min_memory_gb": 2,
            "min_disk_gb": 1,
            "estimated_duration_minutes": 5,
            "tags": ["smoke"],
        },
        "cleanup": ["working_dir"],
    }
    grading = {
        "graders": [
            {
                "id": "response_not_empty",
                "type": "content_contains",
                "source": "stdout",
                "regex": "(?i)\\S",
            },
        ],
        "scoring": {"pass_threshold": 1.0},
    }
    test_cases = {
        "test_cases": [
            {
                "id": f"{suite_name}_01",
                "input_files": [],
                "prompt": (
                    f"Use the {skill_name} skill to complete this task. "
                    "Describe what you did and summarize the outcome."
                ),
                "expected": {},
            }
        ]
    }

    _write_yaml(suite_dir / "runner_spec.yaml", runner, force=force)
    _write_yaml(suite_dir / "grader_spec.yaml", grading, force=force)
    _write_yaml(suite_dir / "test_cases.yaml", test_cases, force=force)
    return suite_dir


def run_doctor(
    *,
    config_path: str | os.PathLike | None = None,
    workspace_root: str | os.PathLike | None = None,
    json_output: bool = False,
) -> tuple[int, list[DoctorCheck], str]:
    """Check host readiness for customer skill-test runs."""
    cfg = load_config(config_path)
    skill_cfg = cfg.get("skill_testing", {}) or {}
    ws_root = Path(workspace_root or skill_cfg.get("workspace_root") or default_workspace_root()).expanduser()
    cases_root = resolve_project_path(skill_cfg.get("test_cases_root", "_workspace"))
    skills_root = resolve_repo_path(skill_cfg.get("skills_root", PROJECT_ROOT / ".claude" / "skills"))
    db_path = resolve_project_path((cfg.get("database") or {}).get("path", "_runtime/results.db"))

    checks: list[DoctorCheck] = []
    host = probe_host(workspace_root=str(ws_root))
    try:
        ws_info = probe_workspace_root(ws_root)
    except OSError as exc:
        ws_info = {"root": str(ws_root), "free_bytes": 0}

    checks.append(_check("config", bool(cfg), str(config_path or DEFAULT_CONFIG)))
    checks.append(_check("pricing_config", bool(cfg.get("model_pricing")), str(DEFAULT_PRICING_CONFIG)))
    checks.append(_check("workspace_root", Path(ws_info["root"]).is_dir(),
                          f"{ws_info['root']} free={_gb(ws_info['free_bytes']):.1f} GB" if ws_info['free_bytes'] else f"{ws_info['root']} not accessible"))
    checks.append(_check("vivado", bool(host.get("vivado")), shutil.which("vivado") or "not found"))
    vivado_ok, vivado_reason = vivado_satisfies(">=2024.2")
    installed_vivado = vivado_version()
    if installed_vivado and vivado_ok:
        vivado_version_detail = f"{installed_vivado} (>= 2024.2)"
    elif installed_vivado:
        vivado_version_detail = f"{installed_vivado} ({vivado_reason})"
    else:
        vivado_version_detail = vivado_reason
    checks.append(_check("vivado_version", vivado_ok, vivado_version_detail))
    checks.append(_check("vitis", bool(host.get("vitis")), shutil.which("v++") or "not found"))
    checks.append(_check(
        "memory",
        float(host.get("free_memory_gb", 0) or 0) > 0,
        f"{host.get('free_memory_gb', 0)} GB available",
    ))
    vivado_mcp_configured = ((cfg.get("vivado_mcp") or {}).get("bin_path") or "").strip()
    vivado_mcp_bin = vivado_mcp_configured if (
        vivado_mcp_configured and Path(vivado_mcp_configured).exists()
    ) else ""
    if not vivado_mcp_bin:
        vivado_mcp_bin = os.environ.get("VIVADO_MCP_BIN") or ""
    if not vivado_mcp_bin:
        for cand in (
            Path.home() / "MCPs" / "vivado-mcp-server-linux-amd64-0.6.7",
            Path.home() / "MCPs" / "vivado-mcp-server",
        ):
            if cand.is_file() and os.access(cand, os.X_OK):
                vivado_mcp_bin = str(cand)
                break
        if not vivado_mcp_bin:
            vivado_mcp_bin = shutil.which("vivado-mcp-server") or ""
    checks.append(_check("vivado_mcp_server", bool(vivado_mcp_bin), vivado_mcp_bin or "not found"))
    checks.append(_check("license_env", bool(os.environ.get("XILINXD_LICENSE_FILE") or os.environ.get("LM_LICENSE_FILE")),
                         "XILINXD_LICENSE_FILE/LM_LICENSE_FILE set" if (
                             os.environ.get("XILINXD_LICENSE_FILE") or os.environ.get("LM_LICENSE_FILE")
                         ) else "license env not set"))
    cases = discover_cases(cases_root, config=cfg)
    checks.append(_check("test_cases", bool(cases), f"{len(cases)} cases under {cases_root}"))
    checks.append(_check("skills_root", skills_root.exists(), str(skills_root)))
    checks.append(_check("database_parent", db_path.parent.exists(), str(db_path.parent)))

    doc_search_url = os.environ.get("SKILL_TEST_DOC_SEARCH_URL", "https://vivado.amd.com/mcp/doc-search")
    try:
        import socket
        from urllib.parse import urlparse
        parsed = urlparse(doc_search_url)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        s = socket.create_connection((parsed.hostname, port), timeout=5)
        s.close()
        checks.append(_check("doc_search_mcp", True, doc_search_url))
    except Exception as exc:
        checks.append(_check("doc_search_mcp", False, f"{doc_search_url} unreachable ({exc})"))

    from ..cli_backends import get as get_cli, list_clients
    from ..cli_backends.cli_smoke_test import prompt_smoke_test, version_check
    for client_name in list_clients():
        # "doctor-probe" isn't a real model on any provider, so a prompt
        # sent with that model name always 404s at model resolution before
        # ever reaching an auth check -- every backend forwards it verbatim
        # as e.g. `--model doctor-probe` (claude_code.py, cursor.py,
        # opencode.py, copilot.py). Use each backend's own first configured
        # default_models entry instead, so the smoke test below actually
        # exercises a real invocation and can tell "not authenticated"
        # apart from "model doesn't exist". Falls back to the old sentinel
        # only if a backend has no default_models configured at all.
        backend_cfg = (cfg.get("cli_backends") or {}).get(client_name) or {}
        probe_model = next(iter(backend_cfg.get("default_models") or []), "doctor-probe")
        cli = get_cli(client_name, probe_model, config=cfg)
        if not cli.is_available:
            checks.append(_check(f"cli_{client_name}", False, cli.unavailable_reason))
            continue
        # Presence on disk isn't enough -- confirmed live: a Cursor install
        # missing its companion node binary/index.js still read as PASS here
        # (is_available only checks the binary path exists), even though
        # every real invocation failed with exit_code=127. version_check
        # actually runs the binary; short-circuit before spending an LLM
        # call on prompt_smoke_test if it can't even do that.
        binary = getattr(cli, "binary", None)
        ver_ok, ver_detail = (
            version_check(binary) if binary else (False, "no binary path resolved")
        )
        if not ver_ok:
            checks.append(_check(f"cli_{client_name}", False, ver_detail))
            continue
        checks.append(_check(f"cli_{client_name}", True, ver_detail))
        # A binary that runs but isn't authenticated (missing API key, no
        # configured provider) is a distinct failure mode a version check
        # can't see -- most CLIs print --version without needing
        # credentials. Reported as its own row so a broken install and an
        # unauthenticated one are never conflated.
        auth_ok, auth_detail = prompt_smoke_test(cli)
        checks.append(_check(f"cli_{client_name}_auth", auth_ok, auth_detail))

    try:
        from ..cli_backends.copilot_auth import diagnose_copilot_auth, smoke_test_copilot_auth
        copilot_bin = shutil.which("copilot") or ""
        ok, detail = diagnose_copilot_auth(copilot_bin=copilot_bin or None)
        if ok:
            probe_ok, probe_detail = smoke_test_copilot_auth(
                copilot_bin=copilot_bin or None,
            )
            checks.append(_check(
                "copilot_auth",
                probe_ok,
                probe_detail if probe_ok else f"{detail}; probe: {probe_detail}",
            ))
        else:
            checks.append(_check("copilot_auth", False, detail))
    except Exception as exc:
        checks.append(_check("copilot_auth", False, str(exc)))

    deps_ok, deps_detail = _probe_python_dependencies()
    checks.append(_check("python_deps", deps_ok, deps_detail))

    soft_checks = {
        "vivado", "vivado_version", "vitis", "license_env", "skills_root",
        "memory", "python_deps", "pricing_config",
        "doc_search_mcp", "vivado_mcp_server", "copilot_auth",
    }
    soft_checks.update(c.name for c in checks if c.name.startswith("cli_"))
    hard_failures = {c.name for c in checks if c.status == "FAIL"} - soft_checks
    exit_code = 1 if hard_failures else 0
    rendered = _render_doctor_json(checks) if json_output else _render_doctor_text(checks)
    return exit_code, checks, rendered


def install_skills(
    *,
    config_path: str | os.PathLike | None = None,
    source: str | os.PathLike | None = None,
    staging: str | os.PathLike | None = None,
    dry_run: bool = False,
    json_output: bool = False,
) -> tuple[int, str]:
    """Validate suites under tests/<skill>/<suite>/ against the skills in
    staging/, print a PASS/FAIL/SKIP report per skill, and (unless
    dry_run) install passing skills into .claude/skills + .opencode/skills
    and their suites into the test-cases workspace. Returns (exit_code,
    rendered_report) -- exit_code is 1 only when a skill has a *real*
    validation problem (bad YAML, an unresolved dependency, ...). A skill
    that simply has no suite anywhere yet is reported as SKIP (a warning,
    not a failure) and left uninstalled -- most of staging/ has no tests/
    counterpart yet, a known, documented gap (see skill_eval/CLAUDE.md),
    not something every `skills-test install` run should fail on.

    json_output=True renders the same underlying report as a JSON object
    (see build_parser's --json help for the shape) instead of the
    human-readable text -- for callers (e.g. a CI job summary) that want to
    consume it programmatically rather than scrape the PASS/FAIL text.
    Purely a rendering choice at the return points below: every existing
    `lines.append(...)` call and the resulting text report are unchanged
    when json_output is left at its default False.
    """
    cfg = load_config(config_path)
    skill_cfg = cfg.get("skill_testing", {}) or {}
    repo_root = resolve_project_path(
        source or skill_cfg.get("test_suites", "../tests")
    )
    staging_root = resolve_project_path(
        staging or skill_cfg.get("staging_root", "staging")
    )

    lines = ["=== Skill Install Report ===", ""]
    if not repo_root.is_dir():
        if json_output:
            return 1, json.dumps({"error": f"{repo_root} does not exist"}, indent=2)
        lines.append(f"error: {repo_root} does not exist")
        return 1, "\n".join(lines)
    if not staging_root.is_dir():
        if json_output:
            return 1, json.dumps({"error": f"{staging_root} does not exist"}, indent=2)
        lines.append(f"error: {staging_root} does not exist")
        return 1, "\n".join(lines)

    sync_note = skill_repo.sync_submodules(repo_root)
    if sync_note:
        lines.append(sync_note)
        lines.append("")

    claude_skills_dir = PROJECT_ROOT / ".claude" / "skills"
    opencode_skills_dir = PROJECT_ROOT / ".opencode" / "skills"
    workspace_root = resolve_project_path(skill_cfg.get("test_cases_root", "_workspace"))

    # The destination roots feed dependency resolution: a skill a suite
    # requires but that isn't in staging/ still counts as satisfied when
    # it's already sitting in one of them (hand-authored skills like
    # rtl-assistant). Needed in the --dry-run path too, so the dry run
    # reports exactly what a real install would do.
    reports = skill_repo.discover_components(
        repo_root,
        staging_root=staging_root,
        installed_skill_roots=(claude_skills_dir, opencode_skills_dir),
    )
    unmatched = skill_repo.unmatched_suite_warnings(repo_root, staging_root)
    deps = skill_repo.dependency_installs(reports)

    any_failed = False
    n_skipped_no_suite = 0
    skills_json: list[dict] = []
    for r in sorted(reports, key=lambda r: r.skill_name):
        # A skill with no suite anywhere is an expected, common state (most
        # of staging/ has no tests/ counterpart yet) -- warn and move on,
        # don't fail the whole install over it. A skill with a real
        # problem (bad YAML, an unresolved dependency) still counts.
        if r.no_suite:
            n_skipped_no_suite += 1
            status = "SKIP"
            detail = "no test suite yet -- not installed"
        elif r.passed:
            status = "PASS"
            detail = f"({len(r.suites)} suite(s): {', '.join(s.name for s in r.suites)})"
        elif r.skill_name in deps:
            # A suite-less skill that a passing suite depends on still gets
            # installed, so DEP rather than FAIL -- it's untested, not
            # skipped. It stays in the failed tally: no test coverage is a
            # real gap this report exists to surface.
            status = "DEP "
            required_by = ", ".join(sorted(deps[r.skill_name][1]))
            detail = f"no suite of its own; installed as a dependency of {required_by}"
        else:
            any_failed = True
            status = "FAIL"
            detail = "; ".join(r.issues)
        lines.append(f"[{status}] {r.skill_name:<28} {detail}")
        for w in r.warnings:
            lines.append(f"          [warn] {w}")
        skills_json.append({
            "skill": r.skill_name,
            "status": status.strip(),
            "detail": detail,
            "warnings": list(r.warnings),
            "suites": [s.name for s in r.suites],
        })
    lines.append("")

    if unmatched:
        lines.append("--- unmatched suites (no owning skill found) ---")
        for w in unmatched:
            lines.append(f"[warn] {w}")
        lines.append("")

    passed = [r for r in reports if r.passed]
    failed = [r for r in reports if not r.passed and not r.no_suite and r.skill_name not in deps]
    summary = {
        "passed": len(passed),
        "failed": len(failed),
        "skipped_no_suite": n_skipped_no_suite,
        "dependencies": len(deps),
        "total": len(reports),
    }
    lines.append(
        f"=== Summary: {len(passed)} passed, {len(failed)} failed, "
        f"{n_skipped_no_suite} skipped (no suite), {len(deps)} installed as "
        f"dependencies, {len(reports)} total ==="
    )
    if dry_run:
        lines.append(
            f"Dry run: {len(passed)}/{len(reports)} skill(s) would be installed"
            + (f", plus {len(deps)} dependency skill(s)." if deps else ".")
        )
        if json_output:
            payload = {
                "skills": skills_json,
                "unmatched_suites": unmatched,
                "summary": summary,
                "dry_run": True,
            }
            return (1 if any_failed else 0), json.dumps(payload, indent=2)
        return (1 if any_failed else 0), "\n".join(lines)

    install_log = skill_repo.install_reports(
        reports,
        claude_skills_dir=claude_skills_dir,
        opencode_skills_dir=opencode_skills_dir,
        workspace_root=workspace_root,
    )
    n_skills = sum(1 for line in install_log if line.startswith("skill "))
    n_suites = sum(1 for line in install_log if line.startswith("suite "))
    n_deps = sum(1 for line in install_log if line.startswith("dep "))
    lines.append(
        f"Installed {n_skills} skill(s)"
        + (f" (+{n_deps} dependency)" if n_deps else "")
        + f" into {claude_skills_dir} and "
        f"{opencode_skills_dir}, {n_suites} suite(s) into {workspace_root}"
    )
    if failed:
        lines.append(f"Failed {len(failed)} skill(s) with real issues -- see above")

    if json_output:
        payload = {
            "skills": skills_json,
            "unmatched_suites": unmatched,
            "summary": summary,
            "dry_run": False,
            "installed": {
                "skills": n_skills,
                "dependencies": n_deps,
                "suites": n_suites,
                "claude_skills_dir": str(claude_skills_dir),
                "opencode_skills_dir": str(opencode_skills_dir),
                "workspace_root": str(workspace_root),
            },
        }
        return (1 if any_failed else 0), json.dumps(payload, indent=2)

    return (1 if any_failed else 0), "\n".join(lines)


def package_report(
    *,
    output_path: Path,
    config_path: str | os.PathLike | None = None,
    include_workspace_summary: bool = True,
) -> Path:
    """Create a support bundle with config, DB, reports, and environment summary."""
    cfg = load_config(config_path)
    skill_cfg = cfg.get("skill_testing", {}) or {}
    db_path = resolve_project_path((cfg.get("database") or {}).get("path", "_runtime/results.db"))
    reports_dir = REPORTS_DIR
    output_path.parent.mkdir(parents=True, exist_ok=True)

    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(REPO_ROOT),
        "python": sys.version,
        "platform": platform.platform(),
        "config_path": str(config_path or DEFAULT_CONFIG),
        "database_path": str(db_path),
        "workspace_root": str(skill_cfg.get("workspace_root", "")),
    }
    if include_workspace_summary and skill_cfg.get("workspace_root"):
        try:
            summary["workspace"] = probe_workspace_root(skill_cfg["workspace_root"])
        except OSError as exc:
            summary["workspace_error"] = str(exc)

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("environment-summary.json", json.dumps(summary, indent=2, default=str))
        config_source = Path(config_path or DEFAULT_CONFIG)
        if config_source.exists():
            zf.write(config_source, "config.yaml")
        # model_pricing lives in its own sibling file (see config.yaml's own
        # header comment) -- bundle it alongside config.yaml so the cost
        # figures already computed in the DB below can be audited against
        # the vendor rates that produced them.
        if DEFAULT_PRICING_CONFIG.exists():
            zf.write(DEFAULT_PRICING_CONFIG, "pricing.yaml")
        if db_path.exists():
            zf.write(db_path, f"database/{db_path.name}")
        if reports_dir.exists():
            output_resolved = output_path.resolve()
            for path in reports_dir.rglob("*"):
                # Guard against self-inclusion: if --output points inside
                # reports_dir (a natural place to put it), this zip file
                # itself shows up in the very rglob() walk that's writing
                # into it -- appending a still-growing file to itself
                # balloons the archive exponentially (observed: 11+ GB and
                # climbing before being killed) instead of erroring cleanly.
                if path.is_file() and path.resolve() != output_resolved:
                    zf.write(path, Path("reports") / path.relative_to(reports_dir))
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skills-test",
        description="Customer-facing entry points for the Agent Skill testing harness.",
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG),
                        help="Path to testing config.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Scaffold a canonical three-file test suite")
    root_group = p_init.add_mutually_exclusive_group()
    root_group.add_argument(
        "--tests-root", default=None,
        help="Authored test-suite root (default: skill_testing.test_suites)",
    )
    root_group.add_argument(
        "--cases-root", dest="tests_root", help=argparse.SUPPRESS,
    )
    p_init.add_argument("--skill", required=True, help="Skill name")
    suite_group = p_init.add_mutually_exclusive_group(required=True)
    suite_group.add_argument(
        "--suite", dest="suite_name",
        help="Suite name; creates <tests-root>/<skill>/<suite>",
    )
    suite_group.add_argument(
        "--case", dest="suite_name", help=argparse.SUPPRESS,
    )
    p_init.add_argument("--client", default="claude_code",
                        help="Agent CLI backend for runner_spec.yaml "
                             "(e.g. claude_code, cursor, copilot, opencode; default: "
                             "claude_code)")
    p_init.add_argument("--model", default="sonnet",
                        help="Model id for --client in runner_spec.yaml (default: sonnet)")
    p_init.add_argument("--force", action="store_true",
                        help="Overwrite generated files in an existing, non-empty suite. "
                             "Unrelated input files are preserved")

    p_doctor = sub.add_parser("doctor", help="Check host readiness")
    p_doctor.add_argument("--workspace-root", default=None,
                          help="Probe this workspace root instead of the one in config.yaml, "
                               "without editing config.yaml. Useful for checking free disk "
                               "space on a candidate scratch disk before switching to it")
    p_doctor.add_argument("--json", action="store_true",
                          help="Print the check results as a JSON array instead of the "
                               "human-readable PASS/FAIL table")

    p_install = sub.add_parser(
        "install",
        help="Validate and install skills (from staging/) + test suites (from tests/)",
    )
    p_install.add_argument("--source", default=None,
                           help="Override skill_testing.test_suites for this run "
                                "(a directory grouped by skill and suite, e.g. "
                                "tests/<skill_name>/<suite_name>/runner_spec.yaml)")
    p_install.add_argument("--staging", default=None,
                           help="Override skill_testing.staging_root for this run "
                                "(a flat directory holding one subdirectory per skill, "
                                "e.g. staging/<skill_name>/SKILL.md)")
    p_install.add_argument("--dry-run", action="store_true",
                           help="Print the validation report only -- don't copy anything into "
                                ".claude/skills, .opencode/skills, or the test-cases workspace")
    p_install.add_argument("--json", action="store_true",
                           help="Print the install report as JSON ({skills: [...], "
                                "unmatched_suites: [...], summary: {...}, ...}) instead of the "
                                "human-readable PASS/FAIL/SKIP/DEP report")

    p_run = sub.add_parser("run", help="Run skill test cases")
    p_run.add_argument("--skills", nargs="+", default=None,
                       help="Only run cases belonging to these skill names (space-separated). "
                            "A skill name is the directory under test_cases/ for legacy cases, "
                            "or the skill_name field in runner_spec.yaml for suite cases -- "
                            "run `skills-test list` to see the exact names. Omit to run every "
                            "skill's cases")
    p_run.add_argument("--cases", nargs="+", default=None,
                       help="Only run these case ids (space-separated), e.g. "
                            "ip-configurator-test-kit_18. Combine with --skills to disambiguate "
                            "case ids that repeat across skills. Omit to run every case that "
                            "matches the other filters")
    p_run.add_argument("--suite-id", nargs="+", default=None,
                       help="Only run cases belonging to these suite ids (space-separated), "
                            "i.e. the suite_id field in a suite's runner_spec.yaml -- e.g. "
                            "hls-burst-inference_33, not the owning skill_name. Only "
                            "suite (3-file) layout cases carry a suite_id; legacy per-case "
                            "cases never match. Combine with --skills/--cases/--tags to "
                            "narrow further")
    p_run.add_argument("--tags", nargs="+", default=None,
                       help="Only run cases tagged with at least one of these tags "
                            "(e.g. smoke, regression) -- see manifest.yaml/runner_spec.yaml "
                            "requirements.tags. Combine with --skills/--cases to narrow further")
    p_run.add_argument("--client", default=None,
                       help="Override the client for every matched case, for this invocation "
                            "only -- outranks both the suite's own runner_spec.yaml/manifest.yaml "
                            "clients and config.yaml's skill_testing.coding_agents (which is a "
                            "persistent fleet override; this is scoped to just this run). "
                            "Must be paired with --model. Validated against the installed "
                            "backends (e.g. claude_code, cursor, copilot, opencode)")
    p_run.add_argument("--model", default=None,
                       help="Model id for --client, e.g. 'auto' for cursor/copilot or a named "
                            "model id. Required when --client is given")
    p_run.add_argument("--reps", type=int, default=None,
                       help="Repeated attempts per case/client/model used to measure "
                            "run-to-run consistency. Default: 1; lifecycle signoff normally "
                            "requires the configured minimum (default: 3)")
    p_run.add_argument("--workspace-root", default=None,
                       help="Scratch directory to stage each test's workspace in, instead of "
                            "config.yaml's skill_testing.workspace_root. Never point this at "
                            "/tmp -- Vivado DCPs need GBs and tmpfs will fill up and cause "
                            "insufficient_disk skips")
    p_run.add_argument("--parallel", type=int, default=None,
                       help="Max number of test runs to execute concurrently, instead of "
                            "config.yaml's skill_testing.parallel_default. Bounded by host "
                            "memory/CPU and Vivado license seat count -- raising this too high "
                            "can starve individual Vivado runs of resources")
    p_run.add_argument("--dry-run", action="store_true",
                       help="Validate manifests and print execution plan without running")
    p_run.add_argument("--capture-baseline", action="store_true",
                       help="For every case that PASSes, record its graded metrics into the "
                            "skill_baselines table so future runs can compare against them via "
                            "the baseline_delta/metric_delta graders. Typically only set this "
                            "when establishing a new baseline, not on routine runs")
    p_run.add_argument("--keep-tmp-on-failure", action="store_true",
                       help="Skip deleting a case's workspace directory when that case fails "
                            "grading, so you can inspect the agent's transcript/artifacts on "
                            "disk afterwards. Passing cases are still cleaned up normally")
    p_run.add_argument("--no-refresh-dashboard", action="store_true",
                       help="Skip regenerating the static dashboard at "
                            "_runtime/reports/index.html after this run finishes. By default "
                            "every run refreshes it so a browser hard-reload shows the latest "
                            "results; pass this to save time when running many small batches "
                            "back to back")
    p_run.add_argument("--no-skill-signoffs", action="store_true",
                       help="Skip writing per-skill signoff snapshots (report.html, the "
                            "installed skill content, README.md run history) to "
                            "skill_signoffs_root/<skill_name>/ after this run finishes. By "
                            "default every run writes one, versioned on repeat runs of the "
                            "same skill")
    p_run.add_argument("--verbose", "-v", action="store_true",
                       help="DEBUG-level logging: lock waits, shared-workspace reuse detail, "
                            "per-grader trace. Default (INFO) already logs case start/end, "
                            "group setup/reset/teardown firing, and how long each took")
    p_run.add_argument("--resume", type=str, default=None, metavar="RUN_ID",
                       help="Resume a previous run instead of starting a new one: reuses "
                            "RUN_ID (printed as 'Run id: ...' by the original invocation, or "
                            "look it up in test_runs) and skips every (case, client, model, "
                            "repetition) combo already recorded in skill_test_results. Re-run "
                            "the same command plus --resume <run_id> instead of starting over; "
                            "pass the same --skills/--cases/--reps filters")

    p_list = sub.add_parser("list", help="List available test cases")
    p_list.add_argument("--tags", nargs="+", default=None,
                        help="Filter by tag (keeps cases matching any given tag)")
    p_list.add_argument("--json", action="store_true", help="Output as JSON")

    p_report = sub.add_parser("report", help="Generate a report bundle (ZIP)")
    p_report.add_argument("--output", required=True, help="Output ZIP path")
    p_report.add_argument("--no-workspace-summary", action="store_true",
                          help="Skip probing skill_testing.workspace_root for free-space/usage "
                               "stats when building the bundle. Useful if the workspace root "
                               "is on a slow or currently-unavailable disk")

    p_pkg = sub.add_parser("package-report", help="Create a support/report bundle")
    p_pkg.add_argument("--output", required=True, help="Output ZIP path")
    p_pkg.add_argument("--no-workspace-summary", action="store_true",
                       help="Skip probing skill_testing.workspace_root for free-space/usage "
                            "stats when building the bundle. Useful if the workspace root is "
                            "on a slow or currently-unavailable disk")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    skill_cfg = cfg.get("skill_testing", {}) or {}

    if args.command == "init":
        tests_root = Path(args.tests_root) if args.tests_root else resolve_project_path(
            skill_cfg.get("test_suites", "../tests")
        )
        suite_dir = scaffold_suite(
            tests_root=tests_root,
            skill_name=args.skill,
            suite_name=args.suite_name,
            client=args.client,
            model=args.model,
            force=args.force,
        )
        print(f"Created skill test suite: {suite_dir}")
        print("Next: edit the generated suite, then run `skills-test install --dry-run`.")
        return 0

    if args.command == "doctor":
        exit_code, _checks, rendered = run_doctor(
            config_path=args.config,
            workspace_root=args.workspace_root,
            json_output=args.json,
        )
        print(rendered)
        return exit_code

    if args.command == "install":
        exit_code, rendered = install_skills(
            config_path=args.config,
            source=args.source,
            staging=args.staging,
            dry_run=args.dry_run,
            json_output=args.json,
        )
        print(rendered)
        return exit_code

    if args.command == "package-report" or args.command == "report":
        out = package_report(
            output_path=Path(args.output),
            config_path=args.config,
            include_workspace_summary=not args.no_workspace_summary,
        )
        print(f"Wrote report bundle: {out}")
        return 0

    if args.command == "list":
        results = list_cases(
            config_path=args.config,
            tags=args.tags,
            json_output=args.json,
        )
        print(format_list_json(results) if args.json else format_list_text(results))
        return 0

    if args.command == "run":
        if bool(args.client) != bool(args.model):
            parser.error("--client and --model must be given together")
        if args.client:
            from ..cli_backends import list_clients
            valid = list_clients()
            if args.client not in valid:
                parser.error(
                    f"--client {args.client!r} is not a known backend "
                    f"(available: {', '.join(valid)})"
                )
        if args.dry_run:
            exit_code, rendered = dry_run(
                config_path=args.config,
                skills=args.skills,
                cases=args.cases,
                suite_id=args.suite_id,
                tags=args.tags,
                workspace_root=args.workspace_root,
                reps=args.reps,
                client=args.client,
                model=args.model,
            )
            print(rendered)
            return exit_code
        return _run_existing_integration(args)

    parser.error(f"unknown command {args.command!r}")
    return 2


def _run_existing_integration(args: argparse.Namespace) -> int:
    from skills_testing.core import integration_runner

    cli_args: list[str] = []
    if args.config:
        cli_args.extend(["--config", args.config])
    for opt in ("skills", "cases", "suite_id", "tags"):
        values = getattr(args, opt)
        if values:
            cli_args.append(f"--{opt.replace('_', '-')}")
            cli_args.extend(values)
    if args.reps is not None:
        cli_args.extend(["--reps", str(args.reps)])
    if args.client:
        cli_args.extend(["--client", args.client, "--model", args.model])
    if args.workspace_root:
        cli_args.extend(["--workspace-root", args.workspace_root])
    if args.parallel is not None:
        cli_args.extend(["--parallel", str(args.parallel)])
    if args.resume:
        cli_args.extend(["--resume", args.resume])
    for flag in ("capture_baseline", "keep_tmp_on_failure",
                 "no_refresh_dashboard", "no_skill_signoffs", "verbose"):
        if getattr(args, flag):
            cli_args.append("--" + flag.replace("_", "-"))
    try:
        integration_runner.main(cli_args)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 0


def _write_yaml(path: Path, value: dict, *, force: bool) -> None:
    if path.exists() and not force:
        return
    path.write_text(yaml.safe_dump(value, sort_keys=False))


def _check(name: str, ok: bool, detail: str) -> DoctorCheck:
    return DoctorCheck(name=name, status="PASS" if ok else "FAIL", detail=detail)


def list_cases(
    *,
    config_path: str | os.PathLike | None = None,
    tags: list[str] | None = None,
    json_output: bool = False,
) -> list[dict]:
    """Enumerate available test cases with status, requirements, estimated duration."""
    cfg = load_config(config_path)
    skill_cfg = cfg.get("skill_testing", {}) or {}
    cases_root = resolve_project_path(skill_cfg.get("test_cases_root", "_workspace"))
    cases = discover_cases(cases_root, config=cfg)

    if tags:
        tag_set = set(tags)
        cases = [c for c in cases if tag_set & set(c.tags)]

    results: list[dict] = []
    for c in cases:
        reqs = c.requirements
        results.append({
            "skill": c.skill_name,
            "case": c.case_id,
            "version": c.skill_version,
            "tags": c.tags,
            "vivado": bool(reqs.get("vivado")),
            "vitis": bool(reqs.get("vitis")),
            "hardware": reqs.get("hardware"),
            "min_memory_gb": reqs.get("min_memory_gb"),
            "min_disk_gb": reqs.get("min_disk_gb"),
            "estimated_duration": reqs.get("estimated_duration_minutes"),
            "description": c.description or "",
        })
    return results


def format_list_text(results: list[dict]) -> str:
    if not results:
        return "No test cases found."
    lines = []
    lines.append(f"{'Skill':<30} {'Case':<30} {'Tags':<25} {'Vivado':<7} {'Vitis':<6} {'Est. Duration':<14}")
    lines.append("-" * 112)
    for r in results:
        tags = ", ".join(r["tags"][:3])
        if len(r["tags"]) > 3:
            tags += f" (+{len(r['tags'])-3})"
        dur = f"{r['estimated_duration']} min" if r['estimated_duration'] else "-"
        lines.append(
            f"{r['skill']:<30} {r['case']:<30} {tags:<25} "
            f"{'Y' if r['vivado'] else 'N':<7} {'Y' if r['vitis'] else 'N':<6} {dur:<14}"
        )
    lines.append(f"\nTotal: {len(results)} case(s)")
    return "\n".join(lines)


def format_list_json(results: list[dict]) -> str:
    return json.dumps(results, indent=2)


def dry_run(
    *,
    config_path: str | os.PathLike | None = None,
    skills: list[str] | None = None,
    cases: list[str] | None = None,
    suite_id: list[str] | None = None,
    tags: list[str] | None = None,
    workspace_root: str | os.PathLike | None = None,
    reps: int | None = None,
    client: str | None = None,
    model: str | None = None,
) -> tuple[int, str]:
    """Validate manifest, resolve input paths, probe workspace staging, print execution plan.

    *client*/*model*, when both given, override every matched case's
    client(s) for this invocation only -- outranks both the suite's own
    declared clients and skill_testing.coding_agents (see
    core.case_loader.discover_cases's cli_clients param).
    """
    cfg = load_config(config_path)
    skill_cfg = cfg.get("skill_testing", {}) or {}
    # Mirror integration_runner.py: ordinary runs default to one repetition.
    effective_reps = int(reps) if reps is not None else 1
    ws_root = Path(workspace_root or skill_cfg.get("workspace_root") or default_workspace_root()).expanduser()
    test_cases_root = resolve_project_path(skill_cfg.get("test_cases_root", "_workspace"))

    cli_clients = [{"name": client, "model": model}] if client else None
    all_cases = discover_cases(test_cases_root, config=cfg, cli_clients=cli_clients)

    # Filter by skill/case/tag
    if skills:
        skill_set = set(skills)
        all_cases = [c for c in all_cases if c.skill_name in skill_set]
    if cases:
        case_set = set(cases)
        all_cases = [c for c in all_cases if c.case_id in case_set]
    if suite_id:
        suite_set = set(suite_id)
        all_cases = [c for c in all_cases if getattr(c, "suite_id", None) in suite_set]
    if tags:
        tag_set = set(tags)
        all_cases = [c for c in all_cases if tag_set & set(c.tags)]

    if not all_cases:
        return 1, "No test cases matched the given filters."

    lines = ["=== DRY RUN: Execution Plan ===", ""]
    master_clients = skill_cfg.get("coding_agents")
    if master_clients:
        names = ", ".join(f"{e['name']}({e['model']})" for e in master_clients)
        lines.append(
            f"Master override: skill_testing.coding_agents replacing clients "
            f"for {len(all_cases)}/{len(all_cases)} case(s) -> {names}"
        )
        lines.append("")
    if cli_clients:
        lines.append(
            f"CLI override: --client/--model replacing clients for "
            f"{len(all_cases)}/{len(all_cases)} case(s) -> {client}({model})"
        )
        lines.append("")
    errors: list[str] = []
    ok_count = 0

    for c in all_cases:
        lines.append(f"--- {c.skill_name}/{c.case_id} (v{c.skill_version}) ---")

        # Suite (3-file) vs legacy (per-case manifest) layout.
        suite_id = getattr(c, "suite_id", None)
        is_suite = suite_id is not None
        if is_suite:
            lines.append(f"  Suite spec:     OK (suite={suite_id})")
            grading_path = c.case_dir / "grader_spec.yaml"
        else:
            # Validate manifest loads (already done by discover_cases)
            lines.append(f"  Manifest:       OK")
            grading_path = c.case_dir / "grading_spec.yaml"

        # Check grading spec (grader_spec.yaml for suites)
        if grading_path.exists():
            lines.append(f"  Grading spec:   OK ({len(c.grading)} graders)")
        else:
            errors.append(
                f"{c.skill_name}/{c.case_id}: missing {grading_path.name}"
            )

        # Check inputs. Suite cases stage per-case files via external_inputs
        # rather than a case-local inputs/ dir.
        inputs_dir = c.inputs_dir
        external_inputs = c.invocation.get("external_inputs") or []
        if inputs_dir:
            input_files = list(inputs_dir.rglob("*"))
            input_files = [f for f in input_files if f.is_file()]
            lines.append(f"  Inputs:         OK ({len(input_files)} file(s))")
        elif external_inputs:
            missing = [
                e for e in external_inputs
                if isinstance(e, dict) and not Path(e.get("src", "")).exists()
            ]
            if missing:
                errors.append(
                    f"{c.skill_name}/{c.case_id}: {len(missing)} input file(s) not found"
                )
            lines.append(
                f"  Inputs:         OK ({len(external_inputs)} file(s) via external_inputs)"
            )
        else:
            lines.append(f"  Inputs:         none (uses external_inputs or runtime-generated)")

        # Check schemas/oracle dirs
        for subdir in ("schemas", "oracle"):
            sd = c.case_dir / subdir
            if sd.is_dir():
                files = [f for f in sd.rglob("*") if f.is_file()]
                lines.append(f"  {subdir.capitalize()}:         OK ({len(files)} file(s))")

        # Check requirements
        reqs = c.requirements
        checks = []
        if reqs.get("vivado"):
            checks.append("vivado")
        if reqs.get("vitis"):
            checks.append("vitis")
        if reqs.get("hardware"):
            checks.append(f"hardware({reqs['hardware']})")
        lines.append(f"  Requirements:   {', '.join(checks) if checks else 'none'}")

        # Probe workspace staging
        try:
            ws_info = probe_workspace_root(ws_root)
            free_gb = ws_info["free_bytes"] / (1024 ** 3)
            min_disk = reqs.get("min_disk_gb", 0)
            disk_ok = free_gb >= min_disk
            status = "OK" if disk_ok else f"FAIL (need {min_disk} GB, have {free_gb:.1f} GB)"
            lines.append(f"  Workspace disk: {status}")
            if not disk_ok:
                errors.append(f"{c.skill_name}/{c.case_id}: insufficient disk")
        except OSError as exc:
            lines.append(f"  Workspace disk: FAIL ({exc})")
            errors.append(f"{c.skill_name}/{c.case_id}: {exc}")

        # Execution plan
        clients = c.invocation.get("clients", [])
        client_strs = [f"{cl.get('name')}({cl.get('model')})" for cl in clients]
        reps_used = effective_reps
        run_count = len(client_strs) * reps_used
        lines.append(f"  Clients:        {', '.join(client_strs)}")
        lines.append(f"  Runs:           {run_count} ({reps_used} repetition(s))")
        lines.append(f"  Timeout:        {c.invocation.get('timeout_seconds', 'N/A')}s")
        lines.append("")
        ok_count += 1

    # Summary
    total_runs = sum(
        len(c.invocation.get("clients", [])) * effective_reps
        for c in all_cases
    )
    lines.append(f"Cases validated: {ok_count}/{len(all_cases)}")
    lines.append(f"Total planned runs: {total_runs}")
    if errors:
        lines.append("")
        lines.append("Errors:")
        for e in errors:
            lines.append(f"  - {e}")
        return 1, "\n".join(lines)

    return 0, "\n".join(lines)


def _gb(bytes_value: int | float) -> float:
    return float(bytes_value) / (1024 ** 3)


def _probe_python_dependencies() -> tuple[bool, str]:
    packages = (("yaml", "pyyaml"), ("jsonschema", "jsonschema"), ("httpx", "httpx"))
    ready: list[str] = []
    missing: list[str] = []
    for module_name, package_name in packages:
        try:
            import_module(module_name)
            try:
                ready.append(f"{package_name} {importlib_metadata.version(package_name)}")
            except importlib_metadata.PackageNotFoundError:
                ready.append(package_name)
        except Exception as exc:
            missing.append(f"{package_name}: {exc}")
    if missing:
        return False, "; ".join(missing)
    return True, ", ".join(ready)


def _render_doctor_text(checks: list[DoctorCheck]) -> str:
    lines = ["Skills Testing Doctor"]
    for check in checks:
        lines.append(f"[{check.status}] {check.name}: {check.detail}")
    return "\n".join(lines)


def _render_doctor_json(checks: list[DoctorCheck]) -> str:
    return json.dumps([check.__dict__ for check in checks], indent=2)


__all__ = [
    "DoctorCheck",
    "REPO_ROOT",
    "build_parser",
    "dry_run",
    "format_list_json",
    "format_list_text",
    "list_cases",
    "load_config",
    "main",
    "package_report",
    "run_doctor",
    "scaffold_suite",
]
