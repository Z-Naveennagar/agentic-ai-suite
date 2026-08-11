"""
Smoke tests for every seed case shipped under skills_testing/test_cases/.

Each case must:
    * load through case_loader.load_case() (schema valid, all grader_types known)
    * declare at least one grader
    * if it has external_inputs pointing at SKILL_TEST_FIXTURES_ROOT, we
      additionally verify the file exists when that fixture root is configured.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from skills_testing.core.case_loader import discover_cases
from skills_testing.core.paths import DEFAULT_FIXTURES_ENV, TEST_CASES_ROOT, expand_path_template

pytestmark = pytest.mark.skip(
    reason="rtl-assistant/timing-closure-prototype/vivado-revision-control seed "
           "cases were removed from src/skills_testing/test_cases/ during the "
           "tests/ (formerly vivado_skills_repo) migration, with no replacement "
           "suite authored yet (legacy manifest.yaml format doesn't fit the "
           "3-file-only tests/ contract). Re-enable once real "
           "components exist."
)

EXPECTED_CASES = {
    ("rtl-assistant", "rtl-lint"),
    ("rtl-assistant", "report_methodology"),
    ("vivado-revision-control", "standard_export"),
    ("timing-closure-prototype", "post_route_dcp_analysis"),
    ("timing-closure-prototype", "timing_closure_iteration"),
}


def test_test_cases_root_exists():
    assert TEST_CASES_ROOT.is_dir()


def test_all_expected_seed_cases_present():
    cases = discover_cases(TEST_CASES_ROOT)
    found = {(c.skill_name, c.case_id) for c in cases}
    missing = EXPECTED_CASES - found
    assert not missing, f"missing seed cases: {missing}"


@pytest.mark.parametrize("skill_name,case_id", sorted(EXPECTED_CASES))
def test_each_case_loads_and_has_graders(skill_name, case_id):
    case_dir = TEST_CASES_ROOT / skill_name / case_id
    from skills_testing.core.case_loader import load_case
    spec = load_case(case_dir)
    assert spec.skill_name == skill_name
    assert spec.case_id == case_id
    assert spec.grading, f"{case_id} has no graders"
    assert spec.invocation.get("clients"), f"{case_id} has no clients"


def _external_input_paths(case_dir: Path) -> list[Path]:
    m = yaml.safe_load((case_dir / "manifest.yaml").read_text())
    out = []
    for ext in (m.get("invocation") or {}).get("external_inputs") or []:
        src = ext["src"] if isinstance(ext, dict) else ext
        out.append(expand_path_template(src))
    return out


@pytest.mark.parametrize(
    "case_id",
    ["post_route_dcp_analysis", "timing_closure_iteration"],
)
def test_timing_closure_external_inputs_present(case_id):
    """
    The FPGAHorizons lab cases reference DCPs under SKILL_TEST_FIXTURES_ROOT.
    Pull the fixture repository outside the source tree, then export:

        export SKILL_TEST_FIXTURES_ROOT=/path/to/demos

    If the fixture is missing on this host, this test is skipped (not
    failed) so the suite can run on machines without the demo cloned.
    """
    import os
    if DEFAULT_FIXTURES_ENV not in os.environ:
        pytest.skip(f"{DEFAULT_FIXTURES_ENV} is not set")
    case_dir = TEST_CASES_ROOT / "timing-closure-prototype" / case_id
    paths = _external_input_paths(case_dir)
    assert paths, f"{case_id} should declare external_inputs"
    missing = [p for p in paths if not p.exists()]
    if missing:
        pytest.skip(f"timing-closure fixture not pulled: {missing}")
    for p in paths:
        assert p.stat().st_size > 0
