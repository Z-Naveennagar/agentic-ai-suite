"""
Tests for the validator registry consumed by the artifact_valid grader.

We ship real implementations for:
    - tcl_syntax_check          (used by vivado-revision-control)
    - xclbin_magic_check        (used by vitis-vpp-link)
    - bootbin_check             (used by vitis-embedded-linux; minimal)
    - xsa_archive_check         (used by vivado-vitis-platform)
    - vivado_methodology_report_parser (used by rtl-assistant report_methodology)
    - vivado_timing_report_parser      (used by baselining + timing closure)

And stubs that simply assert non-empty file presence for the rest, so the
artifact_valid grader can be wired against any in-scope skill without
breaking the harness.
"""

from __future__ import annotations

import io
import struct
import zipfile

import pytest

from skills_testing.graders.validators import VALIDATOR_REGISTRY, get_validator


@pytest.mark.parametrize(
    "name",
    [
        "tcl_syntax_check",
        "xclbin_magic_check",
        "bootbin_check",
        "xsa_archive_check",
        "vivado_methodology_report_parser",
        "vivado_timing_report_parser",
        "vivado_cdc_report_parser",
        "non_empty_file",
    ],
)
def test_validator_registered(name):
    assert name in VALIDATOR_REGISTRY
    assert callable(get_validator(name))


# -- tcl_syntax_check -------------------------------------------------------


class TestTclSyntaxCheck:
    def test_balanced_braces_passes(self, tmp_path):
        p = tmp_path / "build.tcl"
        p.write_text("proc foo { x } { puts $x }\n")
        r = get_validator("tcl_syntax_check")(p, {})
        assert r["passed"] is True

    def test_unbalanced_braces_fails(self, tmp_path):
        p = tmp_path / "build.tcl"
        p.write_text("proc foo { x } { puts $x \n")
        r = get_validator("tcl_syntax_check")(p, {})
        assert r["passed"] is False
        assert "brace" in r["details"]["reason"].lower()

    def test_unbalanced_brackets_fails(self, tmp_path):
        p = tmp_path / "build.tcl"
        p.write_text("set x [expr 1 + 2\n")
        r = get_validator("tcl_syntax_check")(p, {})
        assert r["passed"] is False


# -- xclbin_magic_check -----------------------------------------------------


class TestXclbinMagicCheck:
    def test_recognizes_xclbin_magic(self, tmp_path):
        p = tmp_path / "kernels.xclbin"
        # Real xclbin starts with "xclbin2\0"; we accept that or "xclbin\0"
        p.write_bytes(b"xclbin2\x00" + b"\x00" * 256)
        r = get_validator("xclbin_magic_check")(p, {})
        assert r["passed"] is True

    def test_wrong_magic_fails(self, tmp_path):
        p = tmp_path / "kernels.xclbin"
        p.write_bytes(b"NOTXCLBIN" + b"\x00" * 256)
        r = get_validator("xclbin_magic_check")(p, {})
        assert r["passed"] is False


# -- bootbin_check ----------------------------------------------------------


class TestBootbinCheck:
    def test_minimum_size_and_nonempty(self, tmp_path):
        p = tmp_path / "BOOT.BIN"
        p.write_bytes(b"\x00" * 4096)
        r = get_validator("bootbin_check")(p, {"min_size_bytes": 1024})
        assert r["passed"] is True

    def test_too_small_fails(self, tmp_path):
        p = tmp_path / "BOOT.BIN"
        p.write_bytes(b"\x00" * 100)
        r = get_validator("bootbin_check")(p, {"min_size_bytes": 1024})
        assert r["passed"] is False


# -- xsa_archive_check ------------------------------------------------------


class TestXsaArchiveCheck:
    def test_zip_with_xsa_xml_passes(self, tmp_path):
        p = tmp_path / "design.xsa"
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("xsa.xml", "<root/>")
            z.writestr("design.bit", b"\x00" * 16)
        r = get_validator("xsa_archive_check")(p, {})
        assert r["passed"] is True
        assert "xsa.xml" in r["details"]["entries"]

    def test_non_zip_fails(self, tmp_path):
        p = tmp_path / "design.xsa"
        p.write_bytes(b"not a zip")
        r = get_validator("xsa_archive_check")(p, {})
        assert r["passed"] is False

    def test_zip_missing_xsa_xml_fails(self, tmp_path):
        p = tmp_path / "design.xsa"
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("readme.txt", "no manifest here")
        r = get_validator("xsa_archive_check")(p, {})
        assert r["passed"] is False


# -- vivado_methodology_report_parser --------------------------------------


_METHODOLOGY_RPT = """\
report_methodology
==================
Section 1 - Summary
-------------------
| Rule        | Severity     | Description                  | Violations |
+-------------+--------------+------------------------------+------------+
| TIMING-7    | Critical Wa.. | Bad async reset              | 3          |
| TIMING-9    | Warning      | Missing input delay          | 5          |
| LOGIC-1     | Advisory     | Bad use of latches           | 1          |
"""


class TestMethodologyParser:
    def test_extracts_violation_counts(self, tmp_path):
        p = tmp_path / "methodology.rpt"
        p.write_text(_METHODOLOGY_RPT)
        r = get_validator("vivado_methodology_report_parser")(p, {})
        assert r["passed"] is True
        d = r["details"]
        assert d["total_violations"] == 9
        assert d["critical_warnings"] == 3
        assert d["warnings"] == 5
        assert d["advisories"] == 1
        assert "by_rule" in d


# -- vivado_timing_report_parser -------------------------------------------


_TIMING_RPT = """\
Design Timing Summary
---------------------
| WNS(ns) | TNS(ns) | WHS(ns) | THS(ns) | TPWS(ns)|
| -0.123  | -1.456  |  0.045  |  0.000  |  0.000  |
"""


class TestTimingParser:
    def test_parses_wns_tns_whs(self, tmp_path):
        p = tmp_path / "timing.rpt"
        p.write_text(_TIMING_RPT)
        r = get_validator("vivado_timing_report_parser")(p, {})
        d = r["details"]
        assert d["wns_ns"] == pytest.approx(-0.123)
        assert d["tns_ns"] == pytest.approx(-1.456)
        assert d["whs_ns"] == pytest.approx(0.045)
        # negative WNS -> validator marks "passed=False" by default
        assert r["passed"] is False

    def test_positive_slack_passes(self, tmp_path):
        p = tmp_path / "timing.rpt"
        p.write_text(_TIMING_RPT.replace("-0.123", " 0.215").replace("-1.456", " 0.000"))
        r = get_validator("vivado_timing_report_parser")(p, {})
        assert r["passed"] is True


# -- non_empty_file (catch-all stub) ---------------------------------------


class TestNonEmptyFile:
    def test_passes_for_nonempty(self, tmp_path):
        p = tmp_path / "x"
        p.write_bytes(b"abc")
        r = get_validator("non_empty_file")(p, {})
        assert r["passed"] is True

    def test_fails_for_empty(self, tmp_path):
        p = tmp_path / "x"
        p.write_bytes(b"")
        r = get_validator("non_empty_file")(p, {})
        assert r["passed"] is False
