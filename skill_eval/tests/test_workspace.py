"""
Tests for skills_testing.runtime.workspace - per-test scratch directories.

Contract:
    create_workspace(case_id, *, root=None, inputs_dir=None,
                     external_inputs=None) -> Workspace
    Workspace.dir          - Path to the scratch dir (under root)
    Workspace.populate()   - copies inputs_dir/* and external_inputs into dir
    Workspace.cleanup(keep_on_failure=False, failed=False)
    Workspace.size_bytes() - approx disk used
"""

from __future__ import annotations

from pathlib import Path

import pytest

from skills_testing.runtime.workspace import Workspace, create_workspace, probe_workspace_root


def test_create_workspace_under_root(tmp_path):
    ws = create_workspace("rtl-lint", root=tmp_path)
    assert ws.dir.parent == tmp_path
    assert ws.dir.is_dir()
    assert "rtl-lint" in ws.dir.name


def test_populate_copies_inputs_dir(tmp_path):
    inputs = tmp_path / "src_inputs"
    inputs.mkdir()
    (inputs / "top.sv").write_text("module top; endmodule")
    (inputs / "top.xdc").write_text("create_clock -name clk")
    ws = create_workspace("c1", root=tmp_path, inputs_dir=inputs)
    ws.populate()
    assert (ws.dir / "top.sv").read_text().startswith("module top")
    assert (ws.dir / "top.xdc").exists()


def test_populate_copies_external_inputs(tmp_path):
    src = tmp_path / "ext.dcp"
    src.write_bytes(b"\x00" * 4096)
    ws = create_workspace("c1", root=tmp_path, external_inputs=[src])
    ws.populate()
    assert (ws.dir / "ext.dcp").read_bytes() == src.read_bytes()


def test_populate_external_inputs_with_destination(tmp_path):
    src = tmp_path / "design.dcp"
    src.write_bytes(b"\x00" * 1024)
    ws = create_workspace(
        "c1", root=tmp_path,
        external_inputs=[{"src": str(src), "dest": "checkpoints/design.dcp"}],
    )
    ws.populate()
    assert (ws.dir / "checkpoints" / "design.dcp").exists()


def test_populate_expands_external_input_environment_variables(tmp_path, monkeypatch):
    fixture_root = tmp_path / "fixtures"
    fixture_root.mkdir()
    src = fixture_root / "design.dcp"
    src.write_bytes(b"\x00" * 1024)
    monkeypatch.setenv("CUSTOM_FIXTURE_ROOT", str(fixture_root))
    ws = create_workspace(
        "c1", root=tmp_path,
        external_inputs=[{"src": "${CUSTOM_FIXTURE_ROOT}/design.dcp",
                          "dest": "inputs/design.dcp"}],
    )
    ws.populate()
    assert (ws.dir / "inputs" / "design.dcp").exists()


def test_unset_external_input_environment_variable_raises(tmp_path):
    ws = create_workspace(
        "c1", root=tmp_path,
        external_inputs=[{"src": "${MISSING_FIXTURE_ROOT}/design.dcp",
                          "dest": "inputs/design.dcp"}],
    )
    with pytest.raises(FileNotFoundError, match="MISSING_FIXTURE_ROOT"):
        ws.populate()


def test_cleanup_removes_directory(tmp_path):
    ws = create_workspace("c1", root=tmp_path)
    (ws.dir / "noise.txt").write_text("x")
    p = ws.dir
    ws.cleanup()
    assert not p.exists()


def test_cleanup_preserves_on_failure_when_requested(tmp_path):
    ws = create_workspace("c1", root=tmp_path)
    (ws.dir / "outputs").mkdir()
    p = ws.dir
    ws.cleanup(keep_on_failure=True, failed=True)
    assert p.exists()
    assert (p / "outputs").exists()


def test_size_bytes_reports_total(tmp_path):
    ws = create_workspace("c1", root=tmp_path)
    (ws.dir / "a").write_bytes(b"\x00" * 100)
    (ws.dir / "b").write_bytes(b"\x00" * 250)
    assert ws.size_bytes() >= 350


def test_probe_workspace_root_returns_dict(tmp_path):
    info = probe_workspace_root(tmp_path)
    assert "free_bytes" in info
    assert "is_tmpfs" in info
    assert info["free_bytes"] > 0


def test_missing_external_input_raises(tmp_path):
    ws = create_workspace(
        "c1", root=tmp_path,
        external_inputs=[tmp_path / "does-not-exist.dcp"],
    )
    with pytest.raises(FileNotFoundError):
        ws.populate()
