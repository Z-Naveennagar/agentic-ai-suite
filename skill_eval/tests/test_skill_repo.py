"""
Tests for core/skill_repo.py -- discovery, validation, and install of skills
from staging/ plus suites from the canonical nested tests/ layout (while
retaining support for direct suites):

    staging/<skill_name>/SKILL.md

    tests/<skill_name>/<suite_name>/{grader_spec.yaml,test_cases.yaml,runner_spec.yaml}

Validation reuses case_loader.is_suite_dir/load_suite, so these tests focus
on the discovery/reporting/install layer, not re-testing suite-file shape
rules already covered by test_suite_loader.py.

Each test keeps staging/ (tmp_path / "staging") separate from the
tests-shaped tree passed to discover_components, since in the real
repo they're siblings at the true git root, both one level above
PROJECT_ROOT (skill_eval/), not nested under it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from skills_testing.core.skill_repo import (
    dependency_installs,
    discover_components,
    install_reports,
    unmatched_suite_warnings,
)


def _write_skill(staging_root: Path, skill_name: str) -> Path:
    skill_dir = staging_root / skill_name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(f"# {skill_name}\n")
    return skill_dir


def _write_suite(
    src_root: Path,
    suite_name: str,
    *,
    skill_name: str,
    requires: list[str] | None = None,
) -> Path:
    """*requires* becomes ``invocation.skills`` (default: just the skill).
    Writes directly at src_root/<suite_name>/. Callers choose whether
    *src_root* is the tests root (direct layout) or tests/<skill> (nested)."""
    suite_dir = src_root / suite_name
    suite_dir.mkdir(parents=True)
    (suite_dir / "runner_spec.yaml").write_text(yaml.safe_dump({
        "skill_name": skill_name,
        "skill_version": "1.0.0",
        "suite_id": f"{suite_name}-suite",
        "invocation": {
            "coding_agent": [{"name": "opencode", "model": "azure/gpt-5.4"}],
            "skills": requires if requires is not None else [skill_name],
            "timeout_seconds": 60,
        },
        "requirements": {"vivado": False, "vitis": False,
                         "min_memory_gb": 1, "min_disk_gb": 1, "tags": ["smoke"]},
        "cleanup": ["working_dir"],
    }))
    (suite_dir / "grader_spec.yaml").write_text(yaml.safe_dump({
        "graders": [
            {"id": "present", "type": "content_contains", "source": "stdout",
             "regex": r"(?i)VERDICT:\s*{verdict}\b"},
        ],
        "scoring": {"pass_threshold": 1.0},
    }))
    (suite_dir / "test_cases.yaml").write_text(yaml.safe_dump({
        "suite_id": f"{suite_name}-suite",
        "test_cases": [
            {"id": "case_1", "input_files": [], "expected": {"verdict": "YES"},
             "prompt": f"Analyze with {skill_name}."},
        ],
    }))
    return suite_dir


class TestDiscoverComponents:
    def test_valid_flat_suite_passes(self, tmp_path):
        staging = tmp_path / "staging"
        src_root = tmp_path / "test_suites"
        _write_skill(staging, "skill-a")
        _write_suite(src_root, "skill-a", skill_name="skill-a")

        reports = discover_components(src_root, staging_root=staging)
        assert len(reports) == 1
        r = reports[0]
        assert r.passed
        assert r.skill_name == "skill-a"
        assert [s.name for s in r.suites] == ["skill-a"]
        assert not r.issues

    def test_orphan_suite_with_no_matching_skill_is_only_a_warning(self, tmp_path):
        """A suite exists but staging/ has no skill by that name (or matching
        declared skill_name) -- there's no skill to attach a FAIL report to
        in the flat model, so this surfaces only via
        unmatched_suite_warnings(), not as a discover_components() report."""
        staging = tmp_path / "staging"
        src_root = tmp_path / "test_suites"
        staging.mkdir(parents=True)
        _write_suite(src_root, "skill-a", skill_name="skill-a")

        reports = discover_components(src_root, staging_root=staging)
        assert reports == []

        warnings = unmatched_suite_warnings(src_root, staging)
        assert len(warnings) == 1
        assert "skill-a" in warnings[0]

    def test_suite_missing_required_file_is_issue(self, tmp_path):
        staging = tmp_path / "staging"
        src_root = tmp_path / "test_suites"
        _write_skill(staging, "skill-a")
        suite_dir = _write_suite(src_root, "skill-a", skill_name="skill-a")
        (suite_dir / "grader_spec.yaml").unlink()

        reports = discover_components(src_root, staging_root=staging)
        assert len(reports) == 1
        assert not reports[0].passed
        assert "grader_spec.yaml" in reports[0].issues[0]

    def test_invalid_yaml_is_issue(self, tmp_path):
        staging = tmp_path / "staging"
        src_root = tmp_path / "test_suites"
        _write_skill(staging, "skill-a")
        suite_dir = _write_suite(src_root, "skill-a", skill_name="skill-a")
        (suite_dir / "runner_spec.yaml").write_text("skill_name: [unterminated\n")

        reports = discover_components(src_root, staging_root=staging)
        assert len(reports) == 1
        assert not reports[0].passed

    def test_missing_always_required_placeholder_fails_install(self, tmp_path):
        """A suite whose grader_spec.yaml references an always-required
        whole-value placeholder (e.g. `skill_triggered`'s `{skills}`) that
        some case's `expected:` block omits must fail validation --
        `skills-test install` should refuse to install it, not silently
        install a suite that will mis-grade at runtime."""
        staging = tmp_path / "staging"
        src_root = tmp_path / "test_suites"
        _write_skill(staging, "skill-a")
        suite_dir = src_root / "skill-a"
        suite_dir.mkdir(parents=True)
        (suite_dir / "runner_spec.yaml").write_text(yaml.safe_dump({
            "skill_name": "skill-a", "skill_version": "1.0.0",
            "suite_id": "skill-a-suite",
            "invocation": {"coding_agent": [{"name": "opencode", "model": "m"}],
                          "skills": ["skill-a"], "timeout_seconds": 60},
            "requirements": {"vivado": False, "vitis": False,
                             "min_memory_gb": 1, "min_disk_gb": 1, "tags": []},
            "cleanup": ["working_dir"],
        }))
        (suite_dir / "grader_spec.yaml").write_text(yaml.safe_dump({
            "output_schema": {
                "skill_triggered": {
                    "grader": "trigger", "mandatory": True,
                    "grader_args": "{skills}",
                },
            },
            "scoring": {"aggregation": "weighted_sum", "pass_threshold": 70.0},
        }))
        (suite_dir / "test_cases.yaml").write_text(yaml.safe_dump({
            "suite_id": "skill-a-suite",
            "test_cases": [
                {"id": "case_1", "input_files": [], "expected": {}, "prompt": "p"},
            ],
        }))

        reports = discover_components(src_root, staging_root=staging)
        assert len(reports) == 1
        assert not reports[0].passed
        assert "missing expected.skills" in reports[0].issues[0]

    def test_nested_multi_suite_layout(self, tmp_path):
        staging = tmp_path / "staging"
        src_root = tmp_path / "test_suites"
        _write_skill(staging, "skill-a")
        (src_root / "skill-a").mkdir(parents=True)

        def _write_suite_at(suite_dir, suite_name, skill_name):
            suite_dir.mkdir(parents=True)
            (suite_dir / "runner_spec.yaml").write_text(yaml.safe_dump({
                "skill_name": skill_name, "skill_version": "1.0.0",
                "invocation": {"coding_agent": [{"name": "opencode", "model": "m"}],
                              "skills": [skill_name], "timeout_seconds": 60},
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
            return suite_dir

        _write_suite_at(src_root / "skill-a" / "suite_a", "suite_a", "skill-a")
        _write_suite_at(src_root / "skill-a" / "suite_b", "suite_b", "skill-a")

        reports = discover_components(src_root, staging_root=staging)
        assert len(reports) == 1
        assert reports[0].passed
        assert {s.name for s in reports[0].suites} == {"suite_a", "suite_b"}

    def test_content_match_fallback_and_warning(self, tmp_path):
        # tests/skill-a-variant declares skill_name: skill-a but the
        # dir itself doesn't match any skill in staging/ -- should still
        # count as a suite for skill-a, with a warning about the name
        # mismatch.
        staging = tmp_path / "staging"
        src_root = tmp_path / "test_suites"
        _write_skill(staging, "skill-a")
        _write_suite(src_root, "skill-a", skill_name="skill-a")
        _write_suite(src_root, "skill-a-variant", skill_name="skill-a")

        reports = discover_components(src_root, staging_root=staging)
        assert len(reports) == 1
        r = reports[0]
        assert r.passed
        assert {s.name for s in r.suites} == {"skill-a", "skill-a-variant"}
        assert any("skill-a-variant" in w for w in r.warnings)

    def test_non_skill_dir_without_SKILL_md_is_ignored(self, tmp_path):
        staging = tmp_path / "staging"
        src_root = tmp_path / "test_suites"
        _write_skill(staging, "skill-a")
        _write_suite(src_root, "skill-a", skill_name="skill-a")
        (staging / "scripts").mkdir(parents=True)
        (staging / "scripts" / "helper.py").write_text("# not a skill\n")

        reports = discover_components(src_root, staging_root=staging)
        assert {r.skill_name for r in reports} == {"skill-a"}

    def test_unreferenced_staging_skill_is_reported(self, tmp_path):
        """A skill in staging/ with no matching suite anywhere still shows
        up (still not .passed, so it isn't silently dropped), but as
        `no_suite` -- a warning, not a hard issue, since most of staging/
        has no tests/ counterpart yet (see skill_eval/CLAUDE.md's "Known
        gap"). Real validation problems still land in `.issues`."""
        staging = tmp_path / "staging"
        src_root = tmp_path / "test_suites"
        _write_skill(staging, "skill-a")
        _write_suite(src_root, "skill-a", skill_name="skill-a")
        _write_skill(staging, "orphan-skill")

        reports = discover_components(src_root, staging_root=staging)
        orphan = next(r for r in reports if r.skill_name == "orphan-skill")
        assert not orphan.passed
        assert orphan.no_suite
        assert not orphan.issues
        assert "not referenced by any valid test suite" in orphan.warnings[0]

    def test_unmatched_suite_warning(self, tmp_path):
        staging = tmp_path / "staging"
        src_root = tmp_path / "test_suites"
        _write_skill(staging, "skill-a")
        _write_suite(src_root, "skill-a", skill_name="skill-a")
        _write_suite(src_root, "orphan-suite", skill_name="no-such-skill")

        warnings = unmatched_suite_warnings(src_root, staging)
        assert len(warnings) == 1
        assert "orphan-suite" in warnings[0]
        assert "no-such-skill" in warnings[0]

    def test_nested_tests_layout_is_discovered_and_installed(self, tmp_path):
        """The canonical tests/<skill>/<suite>/ layout installs normally."""
        staging = tmp_path / "staging"
        src_root = tmp_path / "tests"
        _write_skill(staging, "skill-a")
        _write_suite(src_root / "skill-a", "suite-a", skill_name="skill-a")

        reports = discover_components(src_root, staging_root=staging)

        assert len(reports) == 1
        assert reports[0].passed
        assert [suite.name for suite in reports[0].suites] == ["suite-a"]

        claude_dir = tmp_path / ".claude" / "skills"
        workspace_dir = tmp_path / "_workspace"
        install_reports(
            reports,
            claude_skills_dir=claude_dir,
            opencode_skills_dir=tmp_path / ".opencode" / "skills",
            workspace_root=workspace_dir,
        )
        assert (claude_dir / "skill-a" / "SKILL.md").is_file()
        assert (workspace_dir / "suite-a" / "runner_spec.yaml").is_file()

    def test_nested_suite_without_staging_skill_warns(self, tmp_path):
        """Nested suites must not disappear when their source skill is absent."""
        staging = tmp_path / "staging"
        src_root = tmp_path / "tests"
        staging.mkdir()
        _write_suite(
            src_root / "orphan-skill", "orphan-suite",
            skill_name="orphan-skill",
        )

        warnings = unmatched_suite_warnings(src_root, staging)

        assert len(warnings) == 1
        assert "orphan-skill/orphan-suite" in warnings[0]
        assert "orphan-skill" in warnings[0]


class TestSuiteDependencies:
    """A suite's ``invocation.skills`` names every skill the runner stages
    into the workspace. Install has to honour that list, not just each
    skill's own suite -- otherwise a chain-style suite (hls-architect ->
    hls-optimize -> hls-run-flow) installs cleanly and then ERRORs at
    workspace setup on the first suite-less link in the chain."""

    def test_suiteless_dependency_is_recorded_and_installed(self, tmp_path):
        staging = tmp_path / "staging"
        src_root = tmp_path / "test_suites"
        _write_skill(staging, "skill-a")
        _write_skill(staging, "helper")  # no suite of its own
        _write_suite(src_root, "skill-a", skill_name="skill-a",
                     requires=["skill-a", "helper"])

        reports = discover_components(src_root, staging_root=staging)
        owner = next(r for r in reports if r.skill_name == "skill-a")
        assert owner.passed
        assert set(owner.dependencies) == {"helper"}

        deps = dependency_installs(reports)
        assert set(deps) == {"helper"}
        assert deps["helper"][1] == ["skill-a"]

        claude_dir = tmp_path / ".claude" / "skills"
        opencode_dir = tmp_path / ".opencode" / "skills"
        log = install_reports(
            reports, claude_skills_dir=claude_dir,
            opencode_skills_dir=opencode_dir,
            workspace_root=tmp_path / "_workspace",
        )
        # The whole point: installed despite having no suite.
        assert (claude_dir / "helper" / "SKILL.md").is_file()
        assert (opencode_dir / "helper" / "SKILL.md").is_file()
        assert any(line.startswith("dep helper ") for line in log)

    def test_dependency_that_passes_on_its_own_is_not_double_installed(self, tmp_path):
        staging = tmp_path / "staging"
        src_root = tmp_path / "test_suites"
        _write_skill(staging, "skill-a")
        _write_skill(staging, "skill-b")
        _write_suite(src_root, "skill-a", skill_name="skill-a",
                     requires=["skill-a", "skill-b"])
        _write_suite(src_root, "skill-b", skill_name="skill-b")

        reports = discover_components(src_root, staging_root=staging)
        assert dependency_installs(reports) == {}
        log = install_reports(
            reports,
            claude_skills_dir=tmp_path / ".claude" / "skills",
            opencode_skills_dir=tmp_path / ".opencode" / "skills",
            workspace_root=tmp_path / "_workspace",
        )
        assert not [line for line in log if line.startswith("dep ")]

    def test_unresolvable_dependency_fails_the_owning_skill(self, tmp_path):
        """The suite loads fine, so only this check stops it -- without it
        install reports PASS and every case ERRORs at workspace setup."""
        staging = tmp_path / "staging"
        src_root = tmp_path / "test_suites"
        _write_skill(staging, "skill-a")
        _write_suite(src_root, "skill-a", skill_name="skill-a",
                     requires=["skill-a", "no-such-skill"])

        reports = discover_components(src_root, staging_root=staging)
        owner = next(r for r in reports if r.skill_name == "skill-a")
        assert not owner.passed
        assert "no-such-skill" in "; ".join(owner.issues)

        # ...and nothing is installed for it.
        claude_dir = tmp_path / ".claude" / "skills"
        install_reports(
            reports, claude_skills_dir=claude_dir,
            opencode_skills_dir=tmp_path / ".opencode" / "skills",
            workspace_root=tmp_path / "_workspace",
        )
        assert not (claude_dir / "skill-a").exists()

    def test_dependency_already_in_skills_root_is_satisfied(self, tmp_path):
        """Hand-authored skills that aren't sourced from staging/
        (rtl-assistant, baselining, ...) count as resolved."""
        staging = tmp_path / "staging"
        src_root = tmp_path / "test_suites"
        _write_skill(staging, "skill-a")
        _write_suite(src_root, "skill-a", skill_name="skill-a",
                     requires=["skill-a", "hand-authored"])
        claude_dir = tmp_path / ".claude" / "skills"
        (claude_dir / "hand-authored").mkdir(parents=True)
        (claude_dir / "hand-authored" / "SKILL.md").write_text("# pre-existing\n")

        reports = discover_components(
            src_root, staging_root=staging, installed_skill_roots=(claude_dir,),
        )
        owner = next(r for r in reports if r.skill_name == "skill-a")
        assert owner.passed
        # Not in staging/, so nothing to copy -- just not an error.
        assert "hand-authored" not in owner.dependencies

        # Without that root it's indistinguishable from a typo, so it fails.
        reports_no_root = discover_components(src_root, staging_root=staging)
        owner_no_root = next(r for r in reports_no_root if r.skill_name == "skill-a")
        assert not owner_no_root.passed

    def test_subskill_dependency_resolves_to_parent(self, tmp_path):
        """`parent/child` entries stage the parent tree, so the parent is
        what has to exist on disk."""
        staging = tmp_path / "staging"
        src_root = tmp_path / "test_suites"
        _write_skill(staging, "skill-a")
        _write_skill(staging, "parent")
        _write_suite(src_root, "skill-a", skill_name="skill-a",
                     requires=["skill-a", "parent/child"])

        reports = discover_components(src_root, staging_root=staging)
        owner = next(r for r in reports if r.skill_name == "skill-a")
        assert owner.passed
        assert set(owner.dependencies) == {"parent"}

    def test_dependency_with_no_suite_of_its_own_resolves(self, tmp_path):
        staging = tmp_path / "staging"
        src_root = tmp_path / "test_suites"
        _write_skill(staging, "skill-a")
        _write_suite(src_root, "skill-a", skill_name="skill-a",
                     requires=["skill-a", "far-helper"])
        _write_skill(staging, "far-helper")

        reports = discover_components(src_root, staging_root=staging)
        owner = next(r for r in reports if r.skill_name == "skill-a")
        assert owner.passed
        assert set(owner.dependencies) == {"far-helper"}

    def test_absent_skills_key_needs_no_dependencies(self, tmp_path):
        """case_loader defaults the allowlist to [skill_name], which the
        skill's own install already satisfies."""
        staging = tmp_path / "staging"
        src_root = tmp_path / "test_suites"
        _write_skill(staging, "skill-a")
        suite_dir = _write_suite(src_root, "skill-a", skill_name="skill-a")
        spec = yaml.safe_load((suite_dir / "runner_spec.yaml").read_text())
        del spec["invocation"]["skills"]
        (suite_dir / "runner_spec.yaml").write_text(yaml.safe_dump(spec))

        reports = discover_components(src_root, staging_root=staging)
        assert reports[0].passed
        assert reports[0].dependencies == {}


class TestInstallReports:
    def test_install_copies_passing_skills_and_suites_only(self, tmp_path):
        staging = tmp_path / "staging"
        src_root = tmp_path / "test_suites"
        _write_skill(staging, "skill-a")
        _write_suite(src_root, "skill-a", skill_name="skill-a")
        _write_skill(staging, "skill-b")  # no suite -> fails, must not be installed

        reports = discover_components(src_root, staging_root=staging)

        claude_dir = tmp_path / ".claude" / "skills"
        opencode_dir = tmp_path / ".opencode" / "skills"
        workspace_dir = tmp_path / "_workspace"
        # Pre-existing, unrelated skill that must survive untouched.
        (claude_dir / "unrelated-skill").mkdir(parents=True)
        (claude_dir / "unrelated-skill" / "SKILL.md").write_text("# pre-existing\n")

        log = install_reports(
            reports, claude_skills_dir=claude_dir,
            opencode_skills_dir=opencode_dir, workspace_root=workspace_dir,
        )

        assert (claude_dir / "skill-a" / "SKILL.md").is_file()
        assert (opencode_dir / "skill-a" / "SKILL.md").is_file()
        assert not (claude_dir / "skill-b").exists()
        assert (workspace_dir / "skill-a" / "runner_spec.yaml").is_file()
        assert (claude_dir / "unrelated-skill" / "SKILL.md").is_file()
        assert any("skill-a" in line for line in log)

    def test_install_avoids_suite_name_collision_across_skills(self, tmp_path):
        """Two different skills can each nest a sub-suite with the same leaf
        name (tests/<skill>/<suite_name>/, the multi-suite shape) --
        their destination names in the flat install workspace must be
        disambiguated by skill_name, not silently overwrite each other."""
        staging = tmp_path / "staging"
        src_root = tmp_path / "test_suites"
        _write_skill(staging, "skill-a")
        _write_skill(staging, "skill-b")

        def _write_nested_suite(skill_name: str) -> Path:
            suite_dir = src_root / skill_name / "shared-name"
            suite_dir.mkdir(parents=True)
            (suite_dir / "runner_spec.yaml").write_text(yaml.safe_dump({
                "skill_name": skill_name, "skill_version": "1.0.0",
                "invocation": {"coding_agent": [{"name": "opencode", "model": "m"}],
                              "skills": [skill_name], "timeout_seconds": 60},
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
            return suite_dir

        _write_nested_suite("skill-a")
        _write_nested_suite("skill-b")

        reports = discover_components(src_root, staging_root=staging)
        workspace_dir = tmp_path / "_workspace"
        install_reports(
            reports,
            claude_skills_dir=tmp_path / ".claude" / "skills",
            opencode_skills_dir=tmp_path / ".opencode" / "skills",
            workspace_root=workspace_dir,
        )

        installed = {p.name for p in workspace_dir.iterdir()}
        assert "shared-name" in installed
        assert any(name.startswith("skill-a__") or name.startswith("skill-b__") for name in installed)
        assert len(installed) == 2
