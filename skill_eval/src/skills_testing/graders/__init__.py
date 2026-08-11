"""
Grader framework for skill testing.

A grader takes a *spec dict* (loaded from grading_spec.yaml) and a
GraderContext and returns a GraderResult. Each grader_type registered here
can be referenced in a case's grading_spec.yaml under the `type:` key.

Public API
----------
    Grader(ABC)                  - subclasses implement .grade(spec, ctx)
    GraderContext (dataclass)    - workspace_dir, stdout, stderr, lookups
    GraderResult  (dataclass)    - passed, score, details
    GRADER_REGISTRY              - {grader_type: Grader instance}
    get_grader(name)             - dict lookup with KeyError on miss
    register_grader(name, inst)  - for tests / extension points
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional


# -- core types -------------------------------------------------------------


@dataclass
class GraderResult:
    passed: bool
    score: float
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraderContext:
    """Everything a grader is allowed to look at."""

    workspace_dir: Path
    stdout: str = ""
    stderr: str = ""
    # Case directory on disk - lets graders resolve case-local schema /
    # oracle YAMLs without copying them into every workspace.
    case_dir: Optional[Path] = None
    # Per-case parameters (manifest.invocation.parameters) exposed to
    # template substitution in declarative schemas / oracles.
    parameters: dict[str, Any] = field(default_factory=dict)
    # baseline_lookup(skill_name, skill_version, case_id, metric_name) -> float | None
    baseline_lookup: Optional[Callable[[str, str, str, str], Optional[float]]] = None
    # llm_caller(prompt) -> {"score": float, "rationale": str}
    llm_caller: Optional[Callable[[str], dict]] = None
    # run_meta: {"skill_name", "skill_version", "case_id", "client", "model", ...}
    run_meta: dict[str, Any] = field(default_factory=dict)


class Grader(abc.ABC):
    grader_type: str = ""

    @abc.abstractmethod
    def grade(self, spec: dict, ctx: GraderContext) -> GraderResult: ...


# -- registry --------------------------------------------------------------


GRADER_REGISTRY: dict[str, Grader] = {}


def register_grader(name: str, instance: Grader) -> None:
    GRADER_REGISTRY[name] = instance


def get_grader(name: str) -> Grader:
    if name not in GRADER_REGISTRY:
        raise KeyError(f"unknown grader_type: {name!r}")
    return GRADER_REGISTRY[name]


# -- side-effect: register the built-in graders ----------------------------
# Imported here so that `from skills_testing.graders import GRADER_REGISTRY`
# is enough to populate the registry in test code.

from . import _builtins  # noqa: E402,F401  (import has registration side-effects)
from . import trigger  # noqa: E402,F401  (registers trigger)
from . import diff  # noqa: E402,F401  (registers diff)
from . import file_diff  # noqa: E402,F401  (registers file_diff)
from . import action_sequence  # noqa: E402,F401  (registers action_sequence)
from . import program  # noqa: E402,F401  (registers program)
from . import harness_script  # noqa: E402,F401  (registers harness_script)
from . import config_match  # noqa: E402,F401  (registers config_match)
from . import output_contract_match  # noqa: E402,F401  (registers output_contract_match)
from . import discovery_first  # noqa: E402,F401  (registers discovery_first)
from . import answer_leakage  # noqa: E402,F401  (registers answer_leakage)
