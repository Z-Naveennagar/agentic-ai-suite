"""
Discover, validate, and install skills from staging/ plus test suites
from tests/.

Skill content (SKILL.md, ...) and test suites are sourced from two trees,
joined by skill name at install time:

    staging/<skill_name>/                 # agent skill definition (SKILL.md, ...)

    tests/<skill_name>/<suite_name>/      # canonical 3-file suite
                                          # (grader_spec.yaml, test_cases.yaml,
                                          # runner_spec.yaml). A single suite
                                          # may also live directly under
                                          # tests/<skill_name>/.

A suite is associated with a skill either by its own directory name
matching a skill in staging/, or (when that doesn't line up, e.g.
`hls-burst-inference_33`) by its own runner_spec.yaml:skill_name field.

Validation reuses case_loader's suite-shape checks (is_suite_dir/load_suite)
so the rules are identical to what the runner actually enforces at load
time -- this module is a discovery + reporting + install layer on top, not
a second validator.

`skills-test install` (customer_cli.py) is the only caller; see there for
the CLI surface and printed report format.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .case_loader import CaseSchemaError, RUNNER_SPEC, is_suite_dir, load_suite
from .paths import PROJECT_ROOT, resolve_project_path


@dataclass
class SkillReport:
    skill_name: str
    skill_dir: Path
    suites: list[Path] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # Skills this one's suites declare in ``invocation.skills`` and that
    # resolve to a skill dir in the repo: name -> that dir. Installed
    # alongside the skill even when they have no suite of their own (see
    # dependency_installs).
    dependencies: dict[str, Path] = field(default_factory=dict)
    # True when this skill simply has no suite anywhere yet -- a common,
    # expected state (most of staging/ has no tests/ counterpart, see
    # skill_eval/CLAUDE.md's "Known gap"), not a validation failure. Kept
    # separate from `issues` so `install_skills` can WARN-and-skip it
    # instead of failing the whole run; a skill with a real problem (bad
    # YAML, an unresolved dependency) still lands in `issues` and still
    # fails.
    no_suite: bool = False

    @property
    def passed(self) -> bool:
        return not self.issues and bool(self.suites)


def _load_suite_skill_name(suite_dir: Path) -> str | None:
    """Best-effort read of a suite's declared skill_name, without raising."""
    try:
        import yaml
        doc = yaml.safe_load((suite_dir / RUNNER_SPEC).read_text()) or {}
        name = doc.get("skill_name")
        return str(name) if name else None
    except Exception:
        return None


def _suite_required_skills(suite_dir: Path) -> list[str]:
    """Top-level skill names from a suite's ``invocation.skills`` allowlist.

    This is the list the runner stages into each workspace's
    ``.claude/skills`` (runner.py -> workspace.py:_stage_skills_subset), so
    every entry must exist in the skills root or the case ERRORs at setup
    before the agent starts. Sub-skill entries (``"parent/child"``) resolve
    to their top-level ``parent``, matching what staging requires on disk.

    Returns [] when the key is absent -- case_loader then defaults the
    allowlist to ``[skill_name]``, which the skill's own install satisfies.
    """
    try:
        import yaml
        doc = yaml.safe_load((suite_dir / RUNNER_SPEC).read_text()) or {}
        entries = ((doc.get("invocation") or {}) or {}).get("skills")
    except Exception:
        return []
    if not isinstance(entries, list):
        return []
    out: list[str] = []
    for entry in entries:
        top = str(entry).strip("/").split("/")[0]
        if top and top not in out:
            out.append(top)
    return out


def index_skill_dirs(staging_root: Path) -> dict[str, Path]:
    """Map skill_name -> skill dir for every skill in *staging_root*.

    staging_root is flat: one directory per skill (``staging/<skill_name>/
    SKILL.md``), not nested under any component -- skill content is global
    across the whole repo, independent of which component(s) test it.
    """
    root = Path(staging_root)
    index: dict[str, Path] = {}
    if not root.is_dir():
        return index
    for skill_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        if (skill_dir / "SKILL.md").is_file():
            index[skill_dir.name] = skill_dir
    return index


def _validate_suite(suite_dir: Path) -> list[str]:
    """Return a list of issue strings for *suite_dir* (empty = valid)."""
    try:
        load_suite(suite_dir)
        return []
    except CaseSchemaError as exc:
        return [f"{suite_dir}: {exc}"]


def _find_suites_for_skill(test_suites_root: Path, skill_name: str) -> tuple[list[Path], list[str], list[str]]:
    """Return (valid_suite_dirs, issues, warnings) for one skill.

    Tries, in order: a suite directly at tests/<skill_name>/ (supported
    single-suite shape); suites nested at tests/<skill_name>/<suite>/
    (the canonical multi-suite shape); falls through to nothing here --
    the content-match fallback across *all* of test_suites_root happens once
    in discover_components, since
    it isn't skill-directory-scoped.
    """
    issues: list[str] = []
    warnings: list[str] = []
    suites: list[Path] = []

    flat = test_suites_root / skill_name
    if flat.is_dir() and is_suite_dir(flat):
        flat_issues = _validate_suite(flat)
        if flat_issues:
            issues.extend(flat_issues)
        else:
            suites.append(flat)
        return suites, issues, warnings

    if flat.is_dir():
        nested_any = False
        for child in sorted(p for p in flat.iterdir() if p.is_dir()):
            if is_suite_dir(child):
                nested_any = True
                child_issues = _validate_suite(child)
                if child_issues:
                    issues.extend(child_issues)
                else:
                    suites.append(child)
        if nested_any:
            return suites, issues, warnings

    return suites, issues, warnings


def _resolve_dependencies(
    suites: list[Path],
    skill_name: str,
    skill_index: dict[str, Path],
    installed_skill_roots: tuple[Path, ...],
) -> tuple[dict[str, Path], list[str]]:
    """Resolve every skill a skill's suites declare in ``invocation.skills``.

    Returns (name -> skill dir to install, issues). A required skill is
    satisfied by, in order: being the skill itself; a skill dir in staging/
    (installed as a dependency); or already existing in one of
    *installed_skill_roots* (hand-authored skills not sourced from
    staging/, e.g. rtl-assistant). Anything left is an issue -- the suite
    would load fine but ERROR at workspace setup, so failing it here is
    what makes `install --dry-run` catch it.

    Not recursive: only suites declare dependencies, and any dependency
    that itself has a suite gets its own SkillReport with its own
    dependencies resolved.
    """
    deps: dict[str, Path] = {}
    issues: list[str] = []
    for suite_dir in suites:
        for required in _suite_required_skills(suite_dir):
            if required == skill_name or required in deps:
                continue
            if required in skill_index:
                deps[required] = skill_index[required]
            elif any((root / required).is_dir() for root in installed_skill_roots):
                continue  # hand-authored skill already in the skills root
            else:
                issues.append(
                    f"{suite_dir}: invocation.skills requires skill "
                    f"{required!r}, which has no directory in staging/ "
                    f"and is not already installed -- every case in this "
                    f"suite would fail workspace setup"
                )
    return deps, issues


def discover_components(
    test_suites_root: Path,
    *,
    staging_root: Path,
    installed_skill_roots: tuple[Path, ...] | list[Path] = (),
) -> list[SkillReport]:
    """Match suites under *test_suites_root* to skills in *staging_root*.

    Supports direct ``tests/<skill>/`` suites and the canonical nested
    ``tests/<skill>/<suite>/`` layout, returning one SkillReport per skill
    in staging_root
    (issues/warnings populated for skills that fail validation; `.passed`
    is False for those).

    Every skill in staging_root gets a report, including one with zero
    suites anywhere -- so an orphaned skill shows up as a FAIL, not
    silently absent from the report. Which suite(s) a skill "owns" is
    derived from suite directory names and, when those don't match, each
    suite's own runner_spec.yaml skill_name field (see
    _load_suite_skill_name).

    *installed_skill_roots* are the destination skill roots (.claude/skills,
    .opencode/skills). They only matter for dependency resolution: a skill
    required by a suite but absent from the repo is still satisfied if it
    already exists there. Pass them so hand-authored skills don't read as
    missing dependencies.
    """
    root = Path(test_suites_root)
    staging_root = Path(staging_root)
    installed_roots = tuple(Path(p) for p in installed_skill_roots)
    skill_index = index_skill_dirs(staging_root)
    reports: list[SkillReport] = []

    # Content-match fallback: suites whose declared skill_name matches a
    # known skill but whose own directory name doesn't (today's real
    # direct layout, e.g. tests/hls-burst-inference_33 -> skill_name:
    # hls-burst-inference). Also the source of skill_name/dir-name
    # mismatch warnings. Suites whose declared skill_name matches no
    # known skill at all are surfaced separately by
    # unmatched_suite_warnings() -- not tied to any single SkillReport.
    content_matches: dict[str, list[Path]] = {}
    if root.is_dir():
        for suite_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            if suite_dir.name in skill_index:
                continue  # already handled by direct/nested lookup below
            if not is_suite_dir(suite_dir):
                continue
            declared = _load_suite_skill_name(suite_dir)
            if declared in skill_index:
                content_matches.setdefault(declared, []).append(suite_dir)

    for skill_name in sorted(skill_index):
        skill_dir = skill_index[skill_name]
        suites, issues, warnings = (
            _find_suites_for_skill(root, skill_name) if root.is_dir() else ([], [], [])
        )

        for extra in content_matches.get(skill_name, []):
            extra_issues = _validate_suite(extra)
            if extra_issues:
                issues.extend(extra_issues)
            else:
                suites.append(extra)
                if extra.name != skill_name:
                    warnings.append(
                        f"{extra}: matched to skill '{skill_name}' via runner_spec.yaml "
                        f"skill_name (directory name differs)"
                    )

        no_suite = not suites and not issues
        if no_suite:
            warnings.append(f"{skill_name}: not referenced by any valid test suite under {root} -- skipped, not installed")

        # Only meaningful for a skill that has valid suites; a failing
        # skill installs nothing, so its declared deps are moot.
        dependencies: dict[str, Path] = {}
        if suites and not issues:
            dependencies, dep_issues = _resolve_dependencies(
                suites, skill_name, skill_index, installed_roots,
            )
            issues.extend(dep_issues)

        reports.append(SkillReport(
            skill_name=skill_name, skill_dir=skill_dir,
            suites=suites, issues=issues, warnings=warnings,
            dependencies=dependencies, no_suite=no_suite,
        ))

    return reports


def unmatched_suite_warnings(test_suites_root: Path, staging_root: Path) -> list[str]:
    """Collect suites whose declared skill name has no source in staging/.

    Supports both a suite directly under *test_suites_root* and the canonical
    ``tests/<skill>/<suite>/`` layout. These warnings are separate because an
    unmatched suite has no SkillReport to attach to.
    """
    root = Path(test_suites_root)
    out: list[str] = []
    if not root.is_dir():
        return out
    skill_names = set(index_skill_dirs(staging_root))
    suite_dirs: list[Path] = []
    for child in sorted(p for p in root.iterdir() if p.is_dir()):
        if is_suite_dir(child):
            suite_dirs.append(child)
        else:
            suite_dirs.extend(
                nested for nested in sorted(p for p in child.iterdir() if p.is_dir())
                if is_suite_dir(nested)
            )

    for suite_dir in suite_dirs:
        declared = _load_suite_skill_name(suite_dir)
        if declared not in skill_names:
            out.append(
                f"{suite_dir.relative_to(root)} declares skill_name={declared!r} "
                f"but no matching skill directory exists in {Path(staging_root)}"
            )
    return out


def sync_submodules(test_suites_root: Path, *, project_root: Path | None = None) -> str | None:
    """Best-effort `git submodule update --init` scoped to paths under
    the configured tests root, if any are registered in .gitmodules. No
    submodules exist yet, so this is a no-op today -- it's here so the
    command is ready once components are converted to real submodules.
    Returns a status line, or None if there was nothing to do.
    """
    project_root = project_root or PROJECT_ROOT
    gitmodules = project_root / ".gitmodules"
    if not gitmodules.is_file():
        return None
    try:
        rel_prefix = Path(test_suites_root).resolve().relative_to(project_root.resolve())
    except ValueError:
        return None
    text = gitmodules.read_text()
    paths = [
        line.split("=", 1)[1].strip()
        for line in text.splitlines()
        if line.strip().startswith("path =") or line.strip().startswith("path=")
    ]
    scoped = [p for p in paths if Path(p) == rel_prefix or rel_prefix in Path(p).parents or Path(p) in Path(rel_prefix).parents]
    if not scoped:
        return None
    subprocess.run(
        ["git", "submodule", "update", "--init", "--", *scoped],
        cwd=str(project_root), check=True,
    )
    return f"Synced {len(scoped)} submodule(s) under {rel_prefix}"


def dependency_installs(reports: list[SkillReport]) -> dict[str, tuple[Path, list[str]]]:
    """Skills that must be installed only because a passing suite requires
    them: name -> (skill dir, names of the skills that require it).

    Excludes anything that already installs on its own merits (a passing
    report), so what's left is exactly the set the old install would have
    dropped on the floor -- suite-less helper skills like hls-optimize that
    a chain-style suite invokes.
    """
    passing = {r.skill_name for r in reports if r.passed}
    out: dict[str, tuple[Path, list[str]]] = {}
    for report in reports:
        if not report.passed:
            continue
        for name, skill_dir in report.dependencies.items():
            if name in passing:
                continue
            entry = out.setdefault(name, (skill_dir, []))
            entry[1].append(report.skill_name)
    return out


def install_reports(
    reports: list[SkillReport],
    *,
    claude_skills_dir: Path,
    opencode_skills_dir: Path,
    workspace_root: Path,
) -> list[str]:
    """Copy every passing report's skill dir into both skill roots and its
    suite dir(s) into workspace_root, plus any suite-less skill a passing
    suite declares in ``invocation.skills`` (see dependency_installs) --
    without those the suite installs cleanly and then ERRORs at workspace
    setup. Only ever touches the specific <skill_name> subdirectory of each
    destination -- never wipes/rescans the rest of those trees, so
    hand-authored skills already there are untouched.
    Returns human-readable log lines, one per install action."""
    claude_skills_dir = Path(claude_skills_dir)
    opencode_skills_dir = Path(opencode_skills_dir)
    workspace_root = Path(workspace_root)
    claude_skills_dir.mkdir(parents=True, exist_ok=True)
    opencode_skills_dir.mkdir(parents=True, exist_ok=True)
    workspace_root.mkdir(parents=True, exist_ok=True)

    # Tracks names claimed *by this install run* only (not pre-existing disk
    # content) -- so collisions between two suites processed in the same run
    # get prefixed deterministically, and re-running install is idempotent
    # (the same reports always produce the same destination names, safely
    # overwritten in place via dirs_exist_ok=True) instead of accumulating
    # comp__-prefixed duplicates on every re-run.
    claimed_suite_names: set[str] = set()
    log: list[str] = []

    for report in reports:
        if not report.passed:
            continue

        for dest_root in (claude_skills_dir, opencode_skills_dir):
            dest = dest_root / report.skill_name
            shutil.copytree(report.skill_dir, dest, dirs_exist_ok=True)
        log.append(f"skill {report.skill_name} -> {claude_skills_dir}, {opencode_skills_dir}")

        for suite_dir in report.suites:
            name = suite_dir.name
            if name in claimed_suite_names:
                name = f"{report.skill_name}__{suite_dir.name}"
            dest = workspace_root / name
            shutil.copytree(suite_dir, dest, dirs_exist_ok=True)
            claimed_suite_names.add(name)
            log.append(f"suite {suite_dir} -> {dest}")

    # Dependencies last: a skill installed above on its own merits is already
    # excluded, so this never re-copies the same tree twice.
    for name, (skill_dir, required_by) in sorted(dependency_installs(reports).items()):
        for dest_root in (claude_skills_dir, opencode_skills_dir):
            shutil.copytree(skill_dir, dest_root / name, dirs_exist_ok=True)
        log.append(
            f"dep {name} -> {claude_skills_dir}, {opencode_skills_dir} "
            f"(required by {', '.join(sorted(required_by))})"
        )

    return log
