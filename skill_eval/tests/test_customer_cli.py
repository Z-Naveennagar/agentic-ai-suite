from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from skills_testing.cli import customer_cli
from skills_testing.core.case_loader import load_suite
from skills_testing.runtime import requirements_probe


def test_scaffold_suite_creates_loadable_canonical_suite(tmp_path):
    tests_root = tmp_path / "tests"

    suite_dir = customer_cli.scaffold_suite(
        tests_root=tests_root,
        skill_name="my-skill",
        suite_name="my-suite",
        client="opencode",
        model="test-model",
    )

    assert suite_dir == tests_root / "my-skill" / "my-suite"
    assert {path.name for path in suite_dir.iterdir()} == {
        "runner_spec.yaml", "grader_spec.yaml", "test_cases.yaml", "inputs",
    }

    cases = load_suite(suite_dir)
    assert len(cases) == 1
    assert cases[0].skill_name == "my-skill"
    assert cases[0].suite_id == "my-suite"
    assert cases[0].case_id == "my-suite_01"
    assert cases[0].invocation["clients"] == [
        {"name": "opencode", "model": "test-model"},
    ]
    assert cases[0].grading[0]["id"] == "response_not_empty"


def test_scaffold_suite_requires_force_and_preserves_inputs(tmp_path):
    tests_root = tmp_path / "tests"
    suite_dir = customer_cli.scaffold_suite(
        tests_root=tests_root, skill_name="skill", suite_name="suite",
    )
    custom_input = suite_dir / "inputs" / "custom.cpp"
    custom_input.write_text("void top() {}\n")

    with pytest.raises(FileExistsError, match="suite already exists"):
        customer_cli.scaffold_suite(
            tests_root=tests_root, skill_name="skill", suite_name="suite",
        )

    customer_cli.scaffold_suite(
        tests_root=tests_root,
        skill_name="skill",
        suite_name="suite",
        model="new-model",
        force=True,
    )

    assert custom_input.read_text() == "void top() {}\n"
    runner = yaml.safe_load((suite_dir / "runner_spec.yaml").read_text())
    assert runner["invocation"]["coding_agent"][0]["model"] == "new-model"


def test_init_parser_uses_suite_terms_and_keeps_hidden_aliases():
    parser = customer_cli.build_parser()
    init_parser = next(
        action.choices["init"]
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    init_help = init_parser.format_help()

    assert "--suite" in init_help
    assert "--tests-root" in init_help
    assert "--case" not in init_help
    assert "--cases-root" not in init_help
    assert parser.parse_args([
        "init", "--skill", "skill", "--suite", "suite",
    ]).suite_name == "suite"
    assert parser.parse_args([
        "init", "--skill", "skill", "--case", "legacy-suite",
    ]).suite_name == "legacy-suite"
    assert parser.parse_args([
        "init", "--skill", "skill", "--suite", "suite",
        "--cases-root", "/legacy/tests",
    ]).tests_root == "/legacy/tests"


def test_init_uses_configured_test_suites_not_workspace(monkeypatch, tmp_path):
    authored_tests = tmp_path / "authored-tests"
    workspace = tmp_path / "workspace"
    monkeypatch.setattr(customer_cli, "load_config", lambda _=None: {
        "skill_testing": {
            "test_suites": str(authored_tests),
            "test_cases_root": str(workspace),
        },
    })

    assert customer_cli.main([
        "init", "--skill", "my-skill", "--suite", "my-suite",
    ]) == 0

    assert (authored_tests / "my-skill" / "my-suite" / "runner_spec.yaml").is_file()
    assert not workspace.exists()


def test_run_doctor_reports_vivado_version_memory_and_python_deps(monkeypatch, tmp_path):
    cases_root = tmp_path / "cases"
    skills_root = tmp_path / "skills"
    db_dir = tmp_path / "db"
    workspace_root = tmp_path / "ws"
    for path in (cases_root, skills_root, db_dir, workspace_root):
        path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("SKILL_TEST_VIVADO_VERSION", "2024.2")
    monkeypatch.setattr(requirements_probe, "_VIVADO_VERSION_CACHE", None)
    monkeypatch.setattr(requirements_probe, "_have", lambda cmd: cmd in {"vivado", "v++"})
    monkeypatch.setattr(
        customer_cli,
        "load_config",
        lambda _=None: {
            "skill_testing": {
                "workspace_root": str(workspace_root),
                "test_cases_root": str(cases_root),
                "skills_root": str(skills_root),
            },
            "database": {"path": str(db_dir / "results.db")},
        },
    )
    monkeypatch.setattr(customer_cli, "discover_cases", lambda _root, **_kw: [object()])
    monkeypatch.setattr(customer_cli, "probe_host", lambda **_: {
        "vivado": True,
        "vitis": True,
        "free_memory_gb": 64.0,
    })
    monkeypatch.setattr(customer_cli, "probe_workspace_root", lambda root: {
        "root": str(root),
        "free_bytes": 50 * 1024 ** 3,
    })
    monkeypatch.setattr(customer_cli.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")

    import socket
    monkeypatch.setattr(socket, "create_connection", lambda *args, **kwargs: SimpleNamespace(close=lambda: None))

    from skills_testing import cli_backends
    monkeypatch.setattr(cli_backends, "list_clients", lambda: [])

    from skills_testing.cli_backends import copilot_auth
    monkeypatch.setattr(copilot_auth, "diagnose_copilot_auth", lambda **_: (True, "ok"))
    monkeypatch.setattr(copilot_auth, "smoke_test_copilot_auth", lambda **_: (True, "ok"))

    exit_code, checks, rendered = customer_cli.run_doctor()

    by_name = {check.name: check for check in checks}
    assert exit_code == 0
    assert by_name["vivado_version"].status == "PASS"
    assert by_name["memory"].status == "PASS"
    assert by_name["python_deps"].status == "PASS"
    assert "vivado_version" in rendered
    assert "memory" in rendered
    assert "python_deps" in rendered


def _doctor_env(monkeypatch, tmp_path):
    """Shared minimal environment for the cli_<client> smoke-test tests
    below -- everything except list_clients/get_cli/the smoke-test
    functions themselves, which each test wires up for its own case."""
    cases_root = tmp_path / "cases"
    skills_root = tmp_path / "skills"
    db_dir = tmp_path / "db"
    workspace_root = tmp_path / "ws"
    for path in (cases_root, skills_root, db_dir, workspace_root):
        path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(requirements_probe, "_VIVADO_VERSION_CACHE", None)
    monkeypatch.setattr(requirements_probe, "_have", lambda cmd: False)
    monkeypatch.setattr(
        customer_cli, "load_config",
        lambda _=None: {
            "skill_testing": {
                "workspace_root": str(workspace_root),
                "test_cases_root": str(cases_root),
                "skills_root": str(skills_root),
            },
            "database": {"path": str(db_dir / "results.db")},
        },
    )
    monkeypatch.setattr(customer_cli, "discover_cases", lambda _root, **_kw: [object()])
    monkeypatch.setattr(customer_cli, "probe_host", lambda **_: {
        "vivado": False, "vitis": False, "free_memory_gb": 64.0,
    })
    monkeypatch.setattr(customer_cli, "probe_workspace_root", lambda root: {
        "root": str(root), "free_bytes": 50 * 1024 ** 3,
    })
    monkeypatch.setattr(customer_cli.shutil, "which", lambda cmd: None)

    import socket
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: (_ for _ in ()).throw(OSError()))

    from skills_testing.cli_backends import copilot_auth
    monkeypatch.setattr(copilot_auth, "diagnose_copilot_auth", lambda **_: (False, "n/a"))


def test_cli_check_fails_when_binary_cannot_execute(monkeypatch, tmp_path):
    """Regression test for the reported bug: a binary that merely exists on
    disk (is_available True) but can't actually run (e.g. Cursor's agent
    missing its companion node/index.js) must not read as a doctor PASS."""
    _doctor_env(monkeypatch, tmp_path)

    from skills_testing import cli_backends
    monkeypatch.setattr(cli_backends, "list_clients", lambda: ["cursor"])
    fake_cli = SimpleNamespace(is_available=True, binary="/usr/local/bin/agent")
    monkeypatch.setattr(cli_backends, "get", lambda *a, **k: fake_cli)

    from skills_testing.cli_backends import cli_smoke_test
    monkeypatch.setattr(
        cli_smoke_test, "version_check",
        lambda binary, **_: (False, f"{binary}: command not found"),
    )
    prompt_called = []
    monkeypatch.setattr(
        cli_smoke_test, "prompt_smoke_test",
        lambda cli, **_: prompt_called.append(1) or (True, "should not run"),
    )

    exit_code, checks, rendered = customer_cli.run_doctor()

    by_name = {check.name: check for check in checks}
    assert by_name["cli_cursor"].status == "FAIL"
    assert "command not found" in by_name["cli_cursor"].detail
    assert "cli_cursor_auth" not in by_name  # short-circuited, no LLM call spent
    assert not prompt_called
    assert exit_code == 0  # cli_* stays a soft check


def test_cli_check_fails_auth_when_binary_runs_but_prompt_fails(monkeypatch, tmp_path):
    """A CLI that runs (passes version_check) but can't complete a real
    prompt (e.g. no API key configured) must surface as its own failing
    row, distinct from -- and not masked by -- the binary-runs PASS."""
    _doctor_env(monkeypatch, tmp_path)

    from skills_testing import cli_backends
    monkeypatch.setattr(cli_backends, "list_clients", lambda: ["cursor"])
    fake_cli = SimpleNamespace(is_available=True, binary="/usr/local/bin/agent")
    monkeypatch.setattr(cli_backends, "get", lambda *a, **k: fake_cli)

    from skills_testing.cli_backends import cli_smoke_test
    monkeypatch.setattr(
        cli_smoke_test, "version_check", lambda binary, **_: (True, "agent 1.0.0"),
    )
    monkeypatch.setattr(
        cli_smoke_test, "prompt_smoke_test",
        lambda cli, **_: (False, "prompt smoke test exited 1: not authenticated"),
    )

    exit_code, checks, rendered = customer_cli.run_doctor()

    by_name = {check.name: check for check in checks}
    assert by_name["cli_cursor"].status == "PASS"
    assert by_name["cli_cursor_auth"].status == "FAIL"
    assert "not authenticated" in by_name["cli_cursor_auth"].detail
    assert exit_code == 0  # cli_*/cli_*_auth both stay soft checks


def test_cli_check_passes_fully_when_binary_and_prompt_both_work(monkeypatch, tmp_path):
    _doctor_env(monkeypatch, tmp_path)

    from skills_testing import cli_backends
    monkeypatch.setattr(cli_backends, "list_clients", lambda: ["cursor"])
    fake_cli = SimpleNamespace(is_available=True, binary="/usr/local/bin/agent")
    monkeypatch.setattr(cli_backends, "get", lambda *a, **k: fake_cli)

    from skills_testing.cli_backends import cli_smoke_test
    monkeypatch.setattr(
        cli_smoke_test, "version_check", lambda binary, **_: (True, "agent 1.0.0"),
    )
    monkeypatch.setattr(
        cli_smoke_test, "prompt_smoke_test", lambda cli, **_: (True, "prompt smoke test OK"),
    )

    exit_code, checks, rendered = customer_cli.run_doctor()

    by_name = {check.name: check for check in checks}
    assert by_name["cli_cursor"].status == "PASS"
    assert by_name["cli_cursor_auth"].status == "PASS"
    assert exit_code == 0


def test_dry_run_expands_workspace_root_from_config(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))

    case_dir = tmp_path / "cases" / "rtl-assistant" / "rtl-lint"
    inputs_dir = case_dir / "inputs"
    inputs_dir.mkdir(parents=True)
    (case_dir / "grading_spec.yaml").write_text("graders: []\n")
    (inputs_dir / "top.sv").write_text("module top; endmodule\n")

    fake_case = SimpleNamespace(
        skill_name="rtl-assistant",
        case_id="rtl-lint",
        skill_version="1.0.0",
        grading=[],
        case_dir=case_dir,
        inputs_dir=inputs_dir,
        requirements={"min_disk_gb": 1, "tags": ["smoke"]},
        invocation={
            "clients": [{"name": "claude_code", "model": "sonnet"}],
            "timeout_seconds": 30,
        },
    )

    seen = {}
    monkeypatch.setattr(
        customer_cli,
        "load_config",
        lambda _=None: {"skill_testing": {"workspace_root": "~/doctor-ws", "test_cases_root": str(tmp_path / "cases")}},
    )
    monkeypatch.setattr(customer_cli, "discover_cases", lambda _root, **_kw: [fake_case])

    def fake_probe(root):
        seen["root"] = Path(root)
        return {"free_bytes": 5 * 1024 ** 3}

    monkeypatch.setattr(customer_cli, "probe_workspace_root", fake_probe)

    exit_code, rendered = customer_cli.dry_run()

    assert exit_code == 0
    assert seen["root"] == (tmp_path / "doctor-ws")
    assert "Workspace disk: OK" in rendered


def test_dry_run_repetitions_default_to_one(monkeypatch, tmp_path):
    """A plain run stays cheap; explicit --reps expands consistency work."""
    case_dir = tmp_path / "cases" / "ip-configurator" / "case_01"
    inputs_dir = case_dir / "inputs"
    inputs_dir.mkdir(parents=True)
    (case_dir / "grading_spec.yaml").write_text("graders: []\n")

    fake_case = SimpleNamespace(
        skill_name="ip-configurator",
        case_id="case_01",
        skill_version="1.0.0",
        grading=[],
        case_dir=case_dir,
        inputs_dir=None,
        requirements={"min_disk_gb": 1, "tags": []},
        invocation={
            "clients": [{"name": "opencode", "model": "azure/gpt-5.4"}],
            "timeout_seconds": 30,
        },
    )
    monkeypatch.setattr(
        customer_cli,
        "load_config",
        lambda _=None: {"skill_testing": {"workspace_root": str(tmp_path / "ws"),
                                           "test_cases_root": str(tmp_path / "cases")}},
    )
    monkeypatch.setattr(customer_cli, "discover_cases", lambda _root, **_kw: [fake_case])
    monkeypatch.setattr(customer_cli, "probe_workspace_root", lambda root: {"free_bytes": 5 * 1024 ** 3})

    exit_code, rendered = customer_cli.dry_run()
    assert exit_code == 0
    assert "1 repetition(s)" in rendered
    assert "Total planned runs: 1" in rendered

    exit_code, rendered = customer_cli.dry_run(reps=3)
    assert exit_code == 0
    assert "3 repetition(s)" in rendered
    assert "Total planned runs: 3" in rendered


def test_dry_run_client_model_override_forwarded_and_reported(monkeypatch, tmp_path):
    """--client/--model must reach discover_cases as cli_clients and be
    called out in the rendered plan, same as the coding_agents notice."""
    case_dir = tmp_path / "cases" / "ip-configurator" / "case_01"
    case_dir.mkdir(parents=True)
    (case_dir / "grading_spec.yaml").write_text("graders: []\n")

    fake_case = SimpleNamespace(
        skill_name="ip-configurator",
        case_id="case_01",
        skill_version="1.0.0",
        grading=[],
        case_dir=case_dir,
        inputs_dir=None,
        requirements={"min_disk_gb": 1, "tags": []},
        invocation={
            "clients": [{"name": "cursor", "model": "auto"}],
            "timeout_seconds": 30,
        },
    )
    monkeypatch.setattr(
        customer_cli, "load_config",
        lambda _=None: {"skill_testing": {"workspace_root": str(tmp_path / "ws"),
                                           "test_cases_root": str(tmp_path / "cases")}},
    )
    seen = {}

    def fake_discover(_root, config=None, cli_clients=None):
        seen["cli_clients"] = cli_clients
        return [fake_case]

    monkeypatch.setattr(customer_cli, "discover_cases", fake_discover)
    monkeypatch.setattr(customer_cli, "probe_workspace_root", lambda root: {"free_bytes": 5 * 1024 ** 3})

    exit_code, rendered = customer_cli.dry_run(client="cursor", model="auto")

    assert exit_code == 0
    assert seen["cli_clients"] == [{"name": "cursor", "model": "auto"}]
    assert "CLI override: --client/--model" in rendered
    assert "cursor(auto)" in rendered


def test_run_client_and_model_must_be_given_together(capsys):
    with pytest.raises(SystemExit):
        customer_cli.main(["run", "--dry-run", "--client", "cursor"])
    assert "--client and --model must be given together" in capsys.readouterr().err

    with pytest.raises(SystemExit):
        customer_cli.main(["run", "--dry-run", "--model", "auto"])
    assert "--client and --model must be given together" in capsys.readouterr().err


def test_run_unknown_client_rejected(monkeypatch, capsys):
    from skills_testing import cli_backends
    monkeypatch.setattr(cli_backends, "list_clients", lambda: ["claude_code", "cursor"])

    with pytest.raises(SystemExit):
        customer_cli.main(["run", "--dry-run", "--client", "bogus", "--model", "x"])
    assert "not a known backend" in capsys.readouterr().err


def test_package_report_output_inside_reports_dir_does_not_self_include(monkeypatch, tmp_path):
    """Regression test: pointing --output at a path inside reports_dir (a
    natural place to put it) must not make the zip include itself mid-write.
    package_report() opens the zip for writing, then rglob()s reports_dir --
    if the (still-growing) output file lives in that same directory, it gets
    picked up and written into itself, ballooning exponentially. Observed in
    practice: an 11+ GB zip before the process was killed."""
    import zipfile

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    (reports_dir / "index.html").write_text("<html>report</html>")

    monkeypatch.setattr(customer_cli, "REPORTS_DIR", reports_dir)
    monkeypatch.setattr(customer_cli, "load_config", lambda _=None: {
        "skill_testing": {}, "database": {"path": str(tmp_path / "results.db")},
    })

    output_path = reports_dir / "bundle.zip"
    result = customer_cli.package_report(output_path=output_path, include_workspace_summary=False)

    assert result == output_path
    with zipfile.ZipFile(output_path) as zf:
        names = zf.namelist()
        assert "reports/bundle.zip" not in names
        assert "reports/index.html" in names
    # A tiny fixture must produce a tiny zip -- guards against any regression
    # of the runaway self-inclusion growth (observed: 11+ GB). The ceiling
    # has generous headroom above the fixture's own size since the bundle
    # also pulls in the real repo-root config.yaml/pricing.yaml, which grow
    # over time independently of this test.
    assert output_path.stat().st_size < 200_000


def test_package_report_bundles_pricing_yaml_alongside_config(monkeypatch, tmp_path):
    """model_pricing lives in its own sibling file (pricing.yaml) since the
    config.yaml/pricing.yaml split -- the bundle must include it too, so the
    cost_usd figures already in the DB can be audited against the vendor
    rates that produced them, not just the harness behavior config."""
    import zipfile

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    pricing_file = tmp_path / "pricing.yaml"
    pricing_file.write_text("model_pricing:\n  default_currency: usd\n")

    monkeypatch.setattr(customer_cli, "REPORTS_DIR", reports_dir)
    monkeypatch.setattr(customer_cli, "DEFAULT_PRICING_CONFIG", pricing_file)
    monkeypatch.setattr(customer_cli, "load_config", lambda _=None: {
        "skill_testing": {}, "database": {"path": str(tmp_path / "results.db")},
    })

    output_path = tmp_path / "bundle.zip"
    customer_cli.package_report(output_path=output_path, include_workspace_summary=False)

    with zipfile.ZipFile(output_path) as zf:
        assert "pricing.yaml" in zf.namelist()
        assert zf.read("pricing.yaml").decode() == pricing_file.read_text()


def _write_minimal_suite(
    root, skill, *, staging_root, with_suite=True, suite_name=None,
):
    import yaml

    skill_dir = staging_root / skill
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(f"# {skill}\n")
    if not with_suite:
        return
    suite_dir = root / (suite_name or skill)
    suite_dir.mkdir(parents=True)
    (suite_dir / "runner_spec.yaml").write_text(yaml.safe_dump({
        "skill_name": skill, "skill_version": "1.0.0",
        "invocation": {"coding_agent": [{"name": "opencode", "model": "m"}],
                      "skills": [skill], "timeout_seconds": 60},
        "requirements": {"vivado": False, "vitis": False,
                         "min_memory_gb": 1, "min_disk_gb": 1, "tags": []},
        "cleanup": ["working_dir"],
    }))
    (suite_dir / "grader_spec.yaml").write_text(yaml.safe_dump({
        "graders": [{"id": "x", "type": "content_contains", "source": "stdout", "regex": "x"}],
        "scoring": {"pass_threshold": 1.0},
    }))
    (suite_dir / "test_cases.yaml").write_text(yaml.safe_dump({
        "test_cases": [{"id": "c1", "input_files": [], "expected": {}, "prompt": "p"}],
    }))


def test_install_skills_dry_run_reports_without_copying(monkeypatch, tmp_path):
    repo_root = tmp_path / "test_suites"
    staging_root = tmp_path / "staging"
    _write_minimal_suite(repo_root, "good-skill", staging_root=staging_root, with_suite=True)
    # A skill with no suite at all is a SKIP, not a FAIL -- see
    # test_install_skills_no_suite_is_skip_not_fail for the exit-code case.
    _write_minimal_suite(repo_root, "no-suite-skill", staging_root=staging_root, with_suite=False)

    monkeypatch.setattr(
        customer_cli, "load_config",
        lambda _=None: {"skill_testing": {
            "test_suites": str(repo_root), "staging_root": str(staging_root),
        }},
    )

    exit_code, rendered = customer_cli.install_skills(dry_run=True)

    assert exit_code == 0  # no real validation failures, only a no-suite skip
    assert "[PASS] good-skill" in rendered
    assert "[SKIP] no-suite-skill" in rendered
    assert "Dry run:" in rendered
    assert "1 skipped (no suite)" in rendered
    assert not (tmp_path / ".claude").exists()
    assert not (tmp_path / "_workspace").exists()


def test_install_skills_no_suite_is_skip_not_fail(monkeypatch, tmp_path):
    """A skill with no suite anywhere is an expected, common state (most of
    staging/ has no tests/ counterpart yet) -- it must not fail the whole
    install. A skill with a real validation problem still does."""
    repo_root = tmp_path / "test_suites"
    staging_root = tmp_path / "staging"
    repo_root.mkdir(parents=True)  # no-suite skills leave repo_root untouched
    _write_minimal_suite(repo_root, "no-suite-skill", staging_root=staging_root, with_suite=False)

    monkeypatch.setattr(
        customer_cli, "load_config",
        lambda _=None: {"skill_testing": {
            "test_suites": str(repo_root), "staging_root": str(staging_root),
        }},
    )

    exit_code, rendered = customer_cli.install_skills(dry_run=True)

    assert exit_code == 0
    assert "[SKIP] no-suite-skill" in rendered
    assert "0 failed" in rendered


def test_install_skills_real_validation_issue_still_fails(monkeypatch, tmp_path):
    """A suite that exists but is broken (missing a required file) is a
    real FAIL and still exits 1 -- only the no-suite-at-all case is a
    SKIP."""
    repo_root = tmp_path / "test_suites"
    staging_root = tmp_path / "staging"
    _write_minimal_suite(repo_root, "bad-skill", staging_root=staging_root, with_suite=True)
    (repo_root / "bad-skill" / "grader_spec.yaml").unlink()

    monkeypatch.setattr(
        customer_cli, "load_config",
        lambda _=None: {"skill_testing": {
            "test_suites": str(repo_root), "staging_root": str(staging_root),
        }},
    )

    exit_code, rendered = customer_cli.install_skills(dry_run=True)

    assert exit_code == 1
    assert "[FAIL] bad-skill" in rendered


def test_install_skills_dry_run_json_shape(monkeypatch, tmp_path):
    """--json's dry-run payload mirrors the text report's own numbers, just
    structured -- summary counts, one entry per skill, dry_run: true."""
    import json

    repo_root = tmp_path / "test_suites"
    staging_root = tmp_path / "staging"
    _write_minimal_suite(repo_root, "good-skill", staging_root=staging_root, with_suite=True)
    _write_minimal_suite(repo_root, "no-suite-skill", staging_root=staging_root, with_suite=False)

    monkeypatch.setattr(
        customer_cli, "load_config",
        lambda _=None: {"skill_testing": {
            "test_suites": str(repo_root), "staging_root": str(staging_root),
        }},
    )

    exit_code, rendered = customer_cli.install_skills(dry_run=True, json_output=True)

    assert exit_code == 0
    payload = json.loads(rendered)
    assert payload["dry_run"] is True
    assert payload["summary"] == {
        "passed": 1, "failed": 0, "skipped_no_suite": 1,
        "dependencies": 0, "total": 2,
    }
    by_skill = {s["skill"]: s for s in payload["skills"]}
    assert by_skill["good-skill"]["status"] == "PASS"
    assert by_skill["no-suite-skill"]["status"] == "SKIP"


def test_install_skills_real_run_json_includes_installed_counts(monkeypatch, tmp_path):
    import json

    repo_root = tmp_path / "tests"
    staging_root = tmp_path / "staging"
    family_root = repo_root / "good-skill"
    _write_minimal_suite(
        family_root, "good-skill", staging_root=staging_root,
        with_suite=True, suite_name="good-skill-suite",
    )

    monkeypatch.setattr(
        customer_cli, "load_config",
        lambda _=None: {"skill_testing": {
            "test_suites": str(repo_root), "staging_root": str(staging_root),
        }},
    )
    from skills_testing.core import paths as core_paths
    monkeypatch.setattr(customer_cli, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(core_paths, "PROJECT_ROOT", tmp_path)

    exit_code, rendered = customer_cli.install_skills(dry_run=False, json_output=True)

    assert exit_code == 0
    payload = json.loads(rendered)
    assert payload["dry_run"] is False
    assert payload["installed"]["skills"] == 1


def test_install_skills_bad_skill_json_status_fail(monkeypatch, tmp_path):
    import json

    repo_root = tmp_path / "test_suites"
    staging_root = tmp_path / "staging"
    _write_minimal_suite(repo_root, "bad-skill", staging_root=staging_root, with_suite=True)
    (repo_root / "bad-skill" / "grader_spec.yaml").unlink()

    monkeypatch.setattr(
        customer_cli, "load_config",
        lambda _=None: {"skill_testing": {
            "test_suites": str(repo_root), "staging_root": str(staging_root),
        }},
    )

    exit_code, rendered = customer_cli.install_skills(dry_run=True, json_output=True)

    assert exit_code == 1
    payload = json.loads(rendered)
    assert payload["summary"]["failed"] == 1
    by_skill = {s["skill"]: s for s in payload["skills"]}
    assert by_skill["bad-skill"]["status"] == "FAIL"


def test_install_skills_missing_source_dir_json_error(monkeypatch, tmp_path):
    import json

    monkeypatch.setattr(
        customer_cli, "load_config",
        lambda _=None: {"skill_testing": {
            "test_suites": str(tmp_path / "does-not-exist"),
            "staging_root": str(tmp_path / "staging"),
        }},
    )

    exit_code, rendered = customer_cli.install_skills(json_output=True)

    assert exit_code == 1
    payload = json.loads(rendered)
    assert "error" in payload


def test_install_skills_json_default_false_unchanged(monkeypatch, tmp_path):
    """The default (json_output unset) must stay byte-identical to the
    original text report -- this is the regression guard for every existing
    text-mode assertion elsewhere in this file."""
    repo_root = tmp_path / "test_suites"
    staging_root = tmp_path / "staging"
    _write_minimal_suite(repo_root, "good-skill", staging_root=staging_root, with_suite=True)

    monkeypatch.setattr(
        customer_cli, "load_config",
        lambda _=None: {"skill_testing": {
            "test_suites": str(repo_root), "staging_root": str(staging_root),
        }},
    )

    exit_code, rendered = customer_cli.install_skills(dry_run=True)

    assert exit_code == 0
    assert rendered.startswith("=== Skill Install Report ===")


def test_install_json_wired_through_main(monkeypatch, tmp_path, capsys):
    repo_root = tmp_path / "test_suites"
    staging_root = tmp_path / "staging"
    _write_minimal_suite(repo_root, "good-skill", staging_root=staging_root, with_suite=True)

    monkeypatch.setattr(
        customer_cli, "load_config",
        lambda _=None: {"skill_testing": {
            "test_suites": str(repo_root), "staging_root": str(staging_root),
        }},
    )

    exit_code = customer_cli.main(["install", "--dry-run", "--json"])

    assert exit_code == 0
    import json
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True


def test_install_skills_real_run_copies_passing_skill(monkeypatch, tmp_path):
    repo_root = tmp_path / "tests"
    staging_root = tmp_path / "staging"
    family_root = repo_root / "good-skill"
    _write_minimal_suite(
        family_root, "good-skill", staging_root=staging_root,
        with_suite=True, suite_name="good-skill-suite",
    )

    monkeypatch.setattr(
        customer_cli, "load_config",
        lambda _=None: {"skill_testing": {
            "test_suites": str(repo_root), "staging_root": str(staging_root),
        }},
    )
    # install_skills() resolves both directly (customer_cli.PROJECT_ROOT for
    # the .claude/.opencode skill dirs) and via resolve_project_path() (which
    # reads core.paths.PROJECT_ROOT internally for the workspace) -- patch
    # both so nothing leaks into the real repo's own .claude/_workspace.
    from skills_testing.core import paths as core_paths
    monkeypatch.setattr(customer_cli, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(core_paths, "PROJECT_ROOT", tmp_path)

    exit_code, rendered = customer_cli.install_skills(dry_run=False)

    assert exit_code == 0
    assert (tmp_path / ".claude" / "skills" / "good-skill" / "SKILL.md").is_file()
    assert (tmp_path / ".opencode" / "skills" / "good-skill" / "SKILL.md").is_file()
    assert (tmp_path / "_workspace" / "good-skill-suite" / "runner_spec.yaml").is_file()
    assert "Installed 1 skill(s)" in rendered
