"""Tests for shared-workspace group bookkeeping."""

from pathlib import Path

from skills_testing.core.case_loader import CaseSpec
from skills_testing.runtime.suite_lifecycle import (
    GroupRegistry, GroupState, build_group_registry, suite_key_for,
)

_SETUP = {"kind": "prompt", "prompt": "start", "timeout_seconds": 1800}


def _case(case_id, *, suite_id=None, case_dir="/suite", clients=None,
          setup_action=None, teardown_action=None, reset_action=None):
    return CaseSpec(
        skill_name="s", skill_version="1.0", case_id=case_id,
        case_dir=Path(case_dir), suite_id=suite_id,
        invocation={"clients": clients or [{"name": "opencode", "model": "m"}]},
        setup_action=setup_action, teardown_action=teardown_action,
        reset_action=reset_action,
    )


def test_suite_key_prefers_id_and_falls_back_to_path():
    assert suite_key_for(_case("c1", suite_id="id")) == "id"
    assert suite_key_for(_case("c1", case_dir="/some/dir")) == "/some/dir"


def test_group_state_decrement_reports_last_caller():
    state = GroupState(remaining=2)
    assert state.decrement() is False
    assert state.decrement() is True


def test_registry_normalizes_unsharded_key():
    registry = GroupRegistry()
    registry.declare(("s1", "opencode", "m"), 2)
    assert registry.get(("s1", "opencode", "m")).remaining == 2
    assert registry.get(("missing", "x", "y")) is None


def test_registry_omits_cases_without_lifecycle_actions():
    registry = build_group_registry([_case("c1", suite_id="s1")])
    assert registry.get(("s1", "opencode", "m")) is None


def test_registry_groups_by_suite_client_model():
    cases = [
        _case("c1", suite_id="s1", setup_action=_SETUP,
              clients=[{"name": "opencode", "model": "m"}]),
        _case("c2", suite_id="s1", reset_action=_SETUP,
              clients=[{"name": "opencode", "model": "m"}]),
        _case("c3", suite_id="s1", setup_action=_SETUP,
              clients=[{"name": "claude_code", "model": "sonnet"}]),
    ]
    registry = build_group_registry(cases)
    assert registry.get(("s1", "opencode", "m")).remaining == 2
    assert registry.get(("s1", "claude_code", "sonnet")).remaining == 1


def test_registry_sizes_membership_by_repetitions():
    registry = build_group_registry(
        [_case("c1", suite_id="s1", setup_action=_SETUP)], repetitions=3)
    assert registry.get(("s1", "opencode", "m")).remaining == 3


def test_registry_shards_cases_when_parallel():
    cases = [_case(f"c{i}", suite_id="s1", setup_action=_SETUP) for i in range(4)]
    registry = build_group_registry(cases, repetitions=2, parallel=2)
    sizes = registry.sizes()
    assert len(sizes) == 2
    assert sum(sizes.values()) == 8
