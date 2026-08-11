# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from campaign_status import (  # noqa: E402
    build_report,
    infer_design_stage,
    junit_status,
    latest_gate,
    main,
    render_human,
    summarize_design_state,
    summarize_hardware_state,
    summarize_suite,
)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def passing_junit(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """<testsuites name="results">
  <testsuite name="all">
    <testcase name="smoke" classname="test_reference" />
  </testsuite>
</testsuites>
"""
    )


class CampaignStatusTests(unittest.TestCase):
    def test_design_counts_and_active_stage_come_from_run_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_dir = root / "runs" / "active"
            write_json(run_dir / "hardware-spec.json", {"status": "READY"})
            write_json(run_dir / "architecture-plan.json", {"status": "READY"})
            state_path = root / "campaign" / "state.json"
            write_json(
                state_path,
                {
                    "campaign_id": "design-test",
                    "cases": {
                        "active": {
                            "case_id": "active",
                            "status": "RUNNING",
                            "run_dir": "runs/active",
                        },
                        "queued": {"case_id": "queued", "status": "QUEUED"},
                        "passed": {"case_id": "passed", "status": "PASS"},
                    },
                },
            )

            summary = summarize_design_state(state_path, root)

            self.assertEqual(
                summary["counts"],
                {"PASS": 1, "QUEUED": 1, "RUNNING": 1},
            )
            self.assertEqual(summary["status"], "RUNNING")
            self.assertEqual(summary["active"][0]["stage"], "source/platform")
            self.assertEqual(
                summary["active"][0]["artifacts"],
                {
                    "hardware-spec.json": "READY",
                    "architecture-plan.json": "READY",
                },
            )

    def test_stage_inference_stops_at_first_missing_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            write_json(run_dir / "hardware-spec.json", {"status": "READY"})
            write_json(run_dir / "source-manifest.json", {"status": "READY"})

            self.assertEqual(infer_design_stage(run_dir), "architecture")

            write_json(run_dir / "architecture-plan.json", {"status": "READY"})
            self.assertEqual(infer_design_stage(run_dir), "verification")

    def test_stage_and_status_expose_latest_assurance_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            write_json(
                run_dir / "gates" / "g2-architecture-i001.json",
                {
                    "gate_id": "GATE-G2-ARCHITECTURE",
                    "stage": "architecture",
                    "iteration": 1,
                    "evaluated_at": "2026-08-02T12:00:00+00:00",
                    "verdict": "BLOCKED",
                    "producer": "amd_soc_architect",
                    "consumer": "vivado_rtl_engineer",
                    "next_action": "Obtain approval.",
                },
            )

            gate = latest_gate(run_dir)

            self.assertEqual(gate["verdict"], "BLOCKED")
            self.assertEqual(infer_design_stage(run_dir), "gate-architecture:blocked")

    def test_hardware_summary_shows_running_and_waiting_design_stages(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            active_run = root / "runs" / "active"
            waiting_run = root / "runs" / "waiting"
            for run_dir in (active_run, waiting_run):
                write_json(run_dir / "hardware-spec.json", {"status": "READY"})
            write_json(waiting_run / "architecture-plan.json", {"status": "READY"})
            design_state = root / "design" / "state.json"
            write_json(
                design_state,
                {
                    "campaign_id": "design",
                    "cases": {
                        "active": {
                            "status": "PASS",
                            "run_dir": "runs/active",
                        },
                        "waiting": {
                            "status": "RUNNING",
                            "run_dir": "runs/waiting",
                        },
                    },
                },
            )
            hardware_state = root / "hardware" / "state.json"
            write_json(
                hardware_state,
                {
                    "campaign_id": "hardware",
                    "design_campaign": str(design_state),
                    "cases": {
                        "active": {
                            "status": "RUNNING",
                            "run_dir": "runs/active",
                        },
                        "waiting": {"status": "WAITING_DESIGN"},
                    },
                },
            )

            summary = summarize_hardware_state(hardware_state, root)

            self.assertEqual(
                summary["counts"],
                {"RUNNING": 1, "WAITING_DESIGN": 1},
            )
            self.assertEqual(summary["active"][0]["stage"], "hardware-validation")
            self.assertEqual(
                summary["waiting"][0]["stage"],
                "waiting-design:source/platform",
            )

    def test_suite_materialization_and_reference_junit_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            suite_path = root / "evals" / "suite.json"
            write_json(
                suite_path,
                {
                    "id": "suite-test",
                    "cases": [{"case_id": "ready"}, {"case_id": "incomplete"}],
                },
            )
            case_root = root / "evals" / "designs" / "ready"
            write_json(
                case_root / "case.json",
                {
                    "candidate": {"rtl_sources": ["rtl/ready.sv"]},
                    "simulation": {"make_directory": "testbench"},
                },
            )
            (case_root / "prompt.md").write_text("Ready\n")
            write_json(case_root / "hardware-test.json", {})
            (case_root / "reference" / "rtl").mkdir(parents=True)
            (case_root / "reference" / "rtl" / "ready.sv").write_text(
                "module ready; endmodule\n"
            )
            (case_root / "testbench").mkdir()
            (case_root / "testbench" / "Makefile").write_text("all:\n\t@true\n")
            passing_junit(root / "runs" / "_selftest" / "ready" / "results.xml")

            summary = summarize_suite(suite_path, root)

            self.assertEqual(summary["materialized"], 1)
            self.assertEqual(summary["incomplete"][0]["case_id"], "incomplete")
            self.assertEqual(
                summary["reference_self_tests"]["counts"],
                {"MISSING": 1, "PASS": 1},
            )
            self.assertEqual(summary["reference_self_tests"]["passed"], 1)

    def test_junit_failure_and_invalid_xml_are_not_reported_as_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            failed = root / "failed.xml"
            failed.write_text(
                "<testsuites><testsuite><testcase name='x'>"
                "<failure /></testcase></testsuite></testsuites>"
            )
            invalid = root / "invalid.xml"
            invalid.write_text("<testsuites>")

            self.assertEqual(junit_status(failed)[0], "FAIL")
            self.assertEqual(junit_status(invalid)[0], "INVALID")

    def test_report_rendering_is_read_only_and_json_serializable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_path = root / "state.json"
            write_json(
                state_path,
                {
                    "campaign_id": "read-only",
                    "cases": {"one": {"status": "QUEUED"}},
                },
            )
            before = state_path.read_bytes()

            report = build_report([state_path], [], None, root)
            text = render_human(report)
            encoded = json.dumps(report, sort_keys=True)

            self.assertIn("Design campaign read-only", text)
            self.assertIn('"design_campaigns"', encoded)
            self.assertEqual(state_path.read_bytes(), before)

    def test_cli_accepts_repeatable_design_state_option_and_json_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_path = Path(temporary) / "state.json"
            write_json(
                state_path,
                {
                    "campaign_id": "cli-test",
                    "cases": {"one": {"status": "QUEUED"}},
                },
            )
            output = StringIO()

            with redirect_stdout(output):
                returncode = main(
                    ["--design-state", str(state_path), "--json"]
                )

            self.assertEqual(returncode, 0)
            report = json.loads(output.getvalue())
            self.assertEqual(
                report["design_campaigns"][0]["campaign_id"],
                "cli-test",
            )


if __name__ == "__main__":
    unittest.main()
