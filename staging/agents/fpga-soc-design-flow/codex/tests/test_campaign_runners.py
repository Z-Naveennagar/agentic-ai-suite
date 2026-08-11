# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import contextlib
import io
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
HARDWARE_FIXTURES = ROOT / "tests" / "fixtures" / "hardware_runs"
sys.path.insert(0, str(ROOT / "scripts"))

import campaign_runner  # noqa: E402
import chained_campaign  # noqa: E402
import hardware_campaign_runner  # noqa: E402
import v0_1_runner  # noqa: E402


class CampaignRunnerTests(unittest.TestCase):
    def test_chained_campaign_requires_hardware_authorization(self) -> None:
        arguments = [
            "--wait-state",
            "design.json",
            "--design-campaign-id",
            "design-campaign",
            "--hardware-campaign-id",
            "hardware-campaign",
            "--target-profile",
            "target.json",
        ]
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                chained_campaign.parser().parse_args(arguments)
        parsed = chained_campaign.parser().parse_args(
            [*arguments, "--authorize-hardware-actions"]
        )
        self.assertTrue(parsed.authorize_hardware_actions)

    def test_campaign_ids_cannot_escape_campaign_root(self) -> None:
        for module in (campaign_runner, hardware_campaign_runner):
            with self.assertRaises(ValueError):
                module.validate_campaign_id("../../outside")

    def test_campaign_lock_rejects_concurrent_writer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            campaign_dir = Path(temporary) / "campaign"
            first = campaign_runner.acquire_campaign_lock(campaign_dir)
            try:
                with self.assertRaises(RuntimeError):
                    campaign_runner.acquire_campaign_lock(campaign_dir)
            finally:
                first.close()

    def test_resume_adopts_existing_run_without_invoking_design(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            campaign_dir = root / "campaign"
            run_dir = root / "runs" / "resume-test--kv260_pl_counter"
            run_dir.mkdir(parents=True)
            (run_dir / "existing.json").write_text("{}")
            state = {
                "cases": {
                    "kv260_pl_counter": {
                        "case_id": "kv260_pl_counter",
                        "status": "RUNNING",
                    }
                }
            }
            with (
                mock.patch.object(campaign_runner, "ROOT", root),
                mock.patch.object(
                    campaign_runner,
                    "execute",
                    side_effect=[0, 0, 0],
                ) as execute,
            ):
                result = campaign_runner.run_case(
                    "kv260_pl_counter",
                    "resume-test",
                    campaign_dir,
                    None,
                    "workspace-write",
                    state,
                    threading.Lock(),
                    adopt_existing=True,
                )

            self.assertEqual(result["status"], "PASS")
            self.assertEqual(execute.call_count, 3)

    def test_request_ids_cannot_escape_runs_root(self) -> None:
        with self.assertRaises(ValueError):
            v0_1_runner.validate_request_id("../../outside")

    def test_hardware_ready_prompt_preserves_integration_owner_routing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            (run_dir / "hardware-test.json").write_text("{}")
            prompt = v0_1_runner.codex_prompt(
                run_dir,
                {
                    "id": "kv260_pl_counter",
                    "expected_route": ["amd_soc_orchestrator"],
                },
            )

        self.assertIn("use the RTL engineer for a PL-only design", prompt)
        self.assertIn("platform integrator when the architecture selects", prompt)
        self.assertIn("Do not program hardware or drive VIO", prompt)


class HardwareCampaignRunnerTests(unittest.TestCase):
    def test_hardware_authorization_flag_is_required(self) -> None:
        arguments = [
            "--design-campaign-state",
            "design.json",
            "--target-profile",
            "target.json",
        ]
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                hardware_campaign_runner.parser().parse_args(arguments)
        parsed = hardware_campaign_runner.parser().parse_args(
            [*arguments, "--authorize-hardware-actions"]
        )
        self.assertTrue(parsed.authorize_hardware_actions)

    def test_run_path_must_stay_beneath_runs(self) -> None:
        with self.assertRaises(ValueError):
            hardware_campaign_runner.resolve_run_dir("../outside")
        with self.assertRaises(ValueError):
            hardware_campaign_runner.resolve_run_dir("/tmp/outside")

    def test_implementation_artifact_must_stay_beneath_run(self) -> None:
        run_dir = ROOT / "runs" / "safe-run"
        with self.assertRaises(ValueError):
            hardware_campaign_runner.artifact_path(
                run_dir,
                "/tmp/other.bit",
            )

    def test_target_lock_rejects_concurrent_hardware_writer(self) -> None:
        target = ROOT / "hardware" / "targets" / "kv260-lab.example.json"
        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch.object(
                hardware_campaign_runner,
                "LOCK_ROOT",
                Path(temporary),
            ):
                with hardware_campaign_runner.exclusive_target_lock(target, 0):
                    with self.assertRaises(TimeoutError):
                        with hardware_campaign_runner.exclusive_target_lock(
                            target,
                            0,
                        ):
                            pass

    def test_readiness_checks_target_compatibility(self) -> None:
        source_run = HARDWARE_FIXTURES / "kv260-watchdog"
        source_target = (
            ROOT / "hardware" / "targets" / "kv260-lab.example.json"
        )
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            run_dir = temporary_path / "run"
            run_dir.mkdir()
            for name in ("hardware-test.json", "implementation-result.json"):
                shutil.copy2(source_run / name, run_dir / name)
            target_path = temporary_path / "target.json"
            target = source_target.read_text().replace(
                "xck26-sfvc784-2LV-c",
                "wrong-part",
            )
            target_path.write_text(target)

            errors = hardware_campaign_runner.readiness_errors(
                run_dir,
                target_path,
            )

            self.assertIn(
                "target part does not match hardware test plan",
                errors,
            )

    def test_result_must_bind_selected_target_profile(self) -> None:
        source_run = HARDWARE_FIXTURES / "kv260-watchdog"
        target = ROOT / "hardware" / "targets" / "kv260-lab.example.json"
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            shutil.copy2(
                source_run / "hardware-validation-result.json",
                run_dir / "hardware-validation-result.json",
            )

            errors = hardware_campaign_runner.result_binding_errors(
                run_dir,
                target,
            )

            self.assertEqual(
                errors,
                [
                    "hardware result target_profile_id does not match the "
                    "selected target profile"
                ],
            )


if __name__ == "__main__":
    unittest.main()
