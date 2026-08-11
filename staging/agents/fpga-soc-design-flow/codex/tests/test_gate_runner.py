# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import gate_runner  # noqa: E402
import v0_1_runner  # noqa: E402


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def create_intake_run(run_dir: Path, *, producer: str | None = None) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "user-request.md").write_text("Build a counter.\n")
    write_json(
        run_dir / "run.json",
        {
            "schema_version": 1,
            "request_id": run_dir.name,
            "expected_route": [
                "amd_soc_orchestrator",
                "amd_soc_intent_to_spec",
            ],
            "assurance": {
                "required": True,
                "mode": "exception_approval",
            },
        },
    )
    gate_runner.open_gate(run_dir, "intake", producer=producer)
    write_json(
        run_dir / "handoff-000-intake.json",
        {
            "schema_version": 1,
            "request_id": run_dir.name,
            "from_agent": "amd_soc_orchestrator",
            "to_agent": "amd_soc_intent_to_spec",
            "reason": "Translate the request into requirements.",
            "status": "READY",
            "iteration": 0,
            "input_artifacts": [
                {
                    "kind": "user-request",
                    "path": str(run_dir / "user-request.md"),
                    "revision": None,
                }
            ],
            "required_output": str(run_dir / "hardware-spec.json"),
            "evidence": [],
            "requires_user_approval": False,
        },
    )


class GateRunnerTests(unittest.TestCase):
    def test_open_gate_context_is_not_a_closed_receipt(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "runs") as temporary:
            run_dir = Path(temporary)
            create_intake_run(run_dir)

            self.assertEqual(gate_runner.latest_receipts(run_dir), {})

    def test_verification_scope_rejects_cross_owner_mutation(self) -> None:
        baseline = {
            "platform/owned.xpr": {"size": 10, "sha256": "a" * 64},
            "verification/result.xml": {"size": 1, "sha256": "b" * 64},
        }
        current = {
            "platform/owned.xpr": {"size": 10, "sha256": "c" * 64},
            "verification/result.xml": {"size": 2, "sha256": "d" * 64},
        }

        self.assertEqual(
            gate_runner.stage_scope_violations("verification", baseline, current),
            ["platform/owned.xpr"],
        )

    def test_pass_receipt_is_schema_valid_and_opens_next_gate(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "runs") as temporary:
            run_dir = Path(temporary)
            create_intake_run(run_dir)

            receipt, path = gate_runner.close_gate(
                run_dir,
                "intake",
                auto_open_next=True,
            )

            self.assertEqual(receipt["verdict"], "PASS")
            self.assertTrue(path.is_file())
            self.assertTrue(path.with_suffix(".md").is_file())
            self.assertTrue(gate_runner.context_path(run_dir, "spec").is_file())
            self.assertEqual(receipt["inputs"][0]["integrity"], "PINNED")
            self.assertRegex(receipt["inputs"][0]["sha256"], r"^[a-f0-9]{64}$")
            self.assertIn("Why this work was done", path.with_suffix(".md").read_text())

    def test_producer_cannot_self_assign_another_agents_gate(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "runs") as temporary:
            run_dir = Path(temporary)
            create_intake_run(run_dir, producer="amd_soc_intent_to_spec")

            receipt, _ = gate_runner.close_gate(run_dir, "intake")

            self.assertEqual(receipt["verdict"], "FAIL")
            authority = next(
                item for item in receipt["checks"] if item["id"] == "gate-authority"
            )
            self.assertEqual(authority["status"], "FAIL")

    def test_pinned_artifact_tamper_is_detected(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "runs") as temporary:
            run_dir = Path(temporary)
            create_intake_run(run_dir)
            gate_runner.close_gate(run_dir, "intake")
            (run_dir / "user-request.md").write_text("Changed after the gate.\n")

            with mock.patch.object(
                gate_runner,
                "required_gate_stages",
                return_value=["intake"],
            ):
                errors = gate_runner.validate_gate_set(run_dir)

            self.assertTrue(
                any("pinned artifact hash mismatch" in error for error in errors),
                errors,
            )

    def test_framework_initializer_enables_assurance(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "runs") as temporary:
            temporary_root = Path(temporary)
            with mock.patch.object(v0_1_runner, "RUNS_ROOT", temporary_root):
                run_dir = v0_1_runner.initialize_run(
                    "basys3_pulse_counter",
                    "gate-initializer-test",
                )

            run = json.loads((run_dir / "run.json").read_text())
            receipts = gate_runner.latest_receipts(run_dir)
            self.assertTrue(run["assurance"]["required"])
            self.assertEqual(receipts["intake"][0]["verdict"], "PASS")
            self.assertTrue(gate_runner.context_path(run_dir, "spec").is_file())

    def test_approve_every_gate_mode_records_explicit_approval(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "runs") as temporary:
            temporary_root = Path(temporary)
            with mock.patch.object(v0_1_runner, "RUNS_ROOT", temporary_root):
                run_dir = v0_1_runner.initialize_run(
                    "basys3_pulse_counter",
                    "approve-every-gate-test",
                    "approve_every_gate",
                )

            intake = gate_runner.latest_receipts(run_dir)["intake"][0]
            self.assertEqual(intake["approval"]["status"], "GRANTED")
            context = gate_runner.approve_gate(
                run_dir,
                "spec",
                granted_by="test user",
                reasons=["reviewed specification work package"],
            )
            self.assertEqual(context["approval_granted_by"], "test user")

    def test_complete_direct_rtl_gate_chain_passes(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "runs") as temporary:
            run_dir = Path(temporary) / "example-direct-rtl"
            shutil.copytree(ROOT / "contracts" / "examples" / "direct-rtl", run_dir)
            (run_dir / "user-request.md").write_text(
                "Create an eight-bit event counter and a bitstream.\n"
            )
            write_json(
                run_dir / "run.json",
                {
                    "schema_version": 1,
                    "request_id": run_dir.name,
                    "expected_route": [
                        "amd_soc_orchestrator",
                        "amd_soc_intent_to_spec",
                        "amd_soc_architect",
                        "vivado_rtl_engineer",
                        "amd_soc_verifier",
                        "vivado_impl_closure",
                    ],
                    "assurance": {
                        "required": True,
                        "mode": "exception_approval",
                    },
                },
            )
            for relative in (
                "design/rtl/event_counter.sv",
                "reports/elaboration.rpt",
                "reports/elaboration.log",
                "verification/results.xml",
                "vivado/logs/synth_1.log",
                "vivado/logs/impl_1.log",
                "vivado/reports/synthesis.rpt",
                "vivado/reports/implementation.rpt",
                "vivado/reports/timing.rpt",
                "vivado/reports/drc.rpt",
                "vivado/reports/methodology.rpt",
                "vivado/reports/artifact.rpt",
                "vivado/event_counter.bit",
            ):
                path = run_dir / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"evidence for {relative}\n")

            gate_runner.open_gate(run_dir, "intake")
            write_json(
                run_dir / "handoff-000-intake.json",
                {
                    "schema_version": 1,
                    "request_id": run_dir.name,
                    "from_agent": "amd_soc_orchestrator",
                    "to_agent": "amd_soc_intent_to_spec",
                    "reason": "Create a measurable specification.",
                    "status": "READY",
                    "iteration": 0,
                    "input_artifacts": [
                        {
                            "kind": "user-request",
                            "path": str(run_dir / "user-request.md"),
                            "revision": None,
                        }
                    ],
                    "required_output": str(run_dir / "hardware-spec.json"),
                    "evidence": [],
                    "requires_user_approval": False,
                },
            )
            receipt, _ = gate_runner.close_gate(
                run_dir, "intake", auto_open_next=True
            )
            self.assertEqual(receipt["verdict"], "PASS")
            for stage in (
                "spec",
                "architecture",
                "source",
                "verification",
                "implementation",
            ):
                receipt, _ = gate_runner.close_gate(
                    run_dir, stage, auto_open_next=True
                )
                self.assertEqual(
                    receipt["verdict"],
                    "PASS",
                    receipt["verdict_reasons"],
                )

            self.assertEqual(gate_runner.validate_gate_set(run_dir), [])


if __name__ == "__main__":
    unittest.main()
