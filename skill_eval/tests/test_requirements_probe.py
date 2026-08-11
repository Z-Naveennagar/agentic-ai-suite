"""
Tests for requirements_probe - decides whether a case can run on this host.

Contract:
    probe_host(probe_overrides=None) -> dict
        keys: vivado, vitis, xsdb, free_memory_gb, free_disk_gb_tmp
    case_can_run(requirements, host_caps) -> (bool, reason: str | None)
"""

from __future__ import annotations

import pytest

from skills_testing.runtime.requirements_probe import case_can_run, probe_host


def test_probe_host_returns_known_keys():
    info = probe_host()
    for k in ("vivado", "vitis", "xsdb", "free_memory_gb", "free_disk_gb_tmp"):
        assert k in info


def test_probe_host_overrides_take_precedence():
    info = probe_host(probe_overrides={"vivado": True, "vitis": True,
                                       "free_memory_gb": 999})
    assert info["vivado"] is True
    assert info["vitis"] is True
    assert info["free_memory_gb"] == 999


@pytest.fixture
def caps():
    return {
        "vivado": True,
        "vitis": False,
        "xsdb": False,
        "free_memory_gb": 32,
        "free_disk_gb_tmp": 100,
    }


def test_case_can_run_when_all_satisfied(caps):
    ok, reason = case_can_run(
        {"vivado": True, "vitis": False, "min_memory_gb": 8, "min_disk_gb": 4},
        caps,
    )
    assert ok is True
    assert reason is None


def test_case_skipped_when_vitis_missing(caps):
    ok, reason = case_can_run(
        {"vivado": True, "vitis": True, "min_memory_gb": 8, "min_disk_gb": 4},
        caps,
    )
    assert ok is False
    assert "vitis" in reason


def test_case_skipped_when_memory_short(caps):
    ok, reason = case_can_run(
        {"vivado": True, "min_memory_gb": 64},
        caps,
    )
    assert ok is False
    assert "memory" in reason.lower()


def test_case_skipped_when_disk_short(caps):
    ok, reason = case_can_run(
        {"vivado": True, "min_disk_gb": 200},
        caps,
    )
    assert ok is False
    assert "disk" in reason.lower()


def test_hardware_requirement_skipped_without_board(caps):
    ok, reason = case_can_run(
        {"vivado": True, "hardware": "vck190"},
        caps,
    )
    assert ok is False
    assert "hardware" in reason.lower()
