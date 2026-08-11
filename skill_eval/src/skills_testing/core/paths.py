"""Path helpers for the skill-testing harness."""

from __future__ import annotations

import os
import re
from pathlib import Path


# NB: despite the name, REPO_ROOT is the *package* root (src/skills_testing/),
# not the git repository root -- it holds only source code and schemas now,
# nothing generated. PROJECT_ROOT is the harness root, one level above
# src/ (skill_eval/, not the true git top-level -- see paths.py's
# resolve_project_path and CLAUDE.md's "Repo layout" section) -- config.yaml,
# pricing.yaml, the installed-test-cases workspace (_workspace/), and
# _runtime/ (every generated artifact: results.db, the JSON results backup
# dir, logs/, reports/) all live there. staging/ and tests/ live one level
# further up, at the true git root, reached via explicit "../" config
# overrides (staging_root, test_suites).
# Grouping every run-generated thing under one _runtime/ directory (rather
# than as separate top-level results.db/logs/reports/results entries) keeps
# it clearly distinct from _workspace/ (installed test-case *definitions*,
# safe to wipe and reinstall any time) and from skill_testing.workspace_root
# (where an individual test actually *executes* -- ephemeral scratch space).
REPO_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = REPO_ROOT.parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "config.yaml"
# Model & hardware pricing, split out of config.yaml (see config.yaml's own
# header comment and core/cost_model.py) since it's externally-sourced vendor
# data maintained on a different cadence than harness behavior config.
DEFAULT_PRICING_CONFIG = PROJECT_ROOT / "pricing.yaml"
TEST_CASES_ROOT = REPO_ROOT / "test_cases"
RUNTIME_DIR = PROJECT_ROOT / "_runtime"
REPORTS_DIR = RUNTIME_DIR / "reports"
LOGS_DIR = RUNTIME_DIR / "logs"
DEFAULT_WORKSPACE_ENV = "SKILL_TEST_WORKSPACE_ROOT"
DEFAULT_FIXTURES_ENV = "SKILL_TEST_FIXTURES_ROOT"


_ENV_REF = re.compile(r"\$(?:\{(?P<braced>[A-Za-z_][A-Za-z0-9_]*)\}|(?P<bare>[A-Za-z_][A-Za-z0-9_]*))")


def default_workspace_root() -> Path:
    """Return the default scratch root without embedding user-specific paths."""
    return Path(os.environ.get(DEFAULT_WORKSPACE_ENV, REPO_ROOT / ".skill-tests")).expanduser()


def session_log_dir(name: str, base: str | os.PathLike | None = None) -> Path:
    """Directory holding the JSON monitoring logs for one test-run session.

    *base* may be a config-supplied path (absolute, or relative to
    PROJECT_ROOT, the repo root); defaults to ``LOGS_DIR``
    (``<repo-root>/_runtime/logs``). *name* is the per-session subdir name —
    callers pass ``<UTC-stamp>__<run_id>`` (see ``session_log.session_dir``)
    so sessions sort chronologically under logs/.
    """
    root = LOGS_DIR if base is None else resolve_project_path(base)
    return root / name


def resolve_repo_path(value: str | os.PathLike) -> Path:
    """Resolve *value* relative to the repository root when it is not absolute."""
    path = Path(value).expanduser()
    return path if path.is_absolute() else REPO_ROOT / path


def resolve_project_path(value: str | os.PathLike) -> Path:
    """Resolve *value* relative to PROJECT_ROOT (the git repo root) when not absolute.

    Use this instead of ``resolve_repo_path`` for the handful of things that
    live at the harness root rather than under the package (the
    installed-test-cases workspace, config.yaml) -- or one level further up
    at the true git root via an explicit "../" override (``staging_root``,
    ``test_suites``, whose directory value is ``../tests``).
    """
    path = Path(value).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def expand_path_template(value: str | os.PathLike) -> Path:
    """Expand `~` and environment variables in a customer-provided path.

    Raises a helpful error when a manifest references an unset variable such
    as `${SKILL_TEST_FIXTURES_ROOT}`.
    """
    raw = str(value)
    missing = [
        match.group("braced") or match.group("bare")
        for match in _ENV_REF.finditer(raw)
        if (match.group("braced") or match.group("bare")) not in os.environ
    ]
    if missing:
        names = ", ".join(sorted(set(missing)))
        raise FileNotFoundError(
            f"path {raw!r} references unset environment variable(s): {names}"
        )
    return Path(os.path.expandvars(raw)).expanduser()
