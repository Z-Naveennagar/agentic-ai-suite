# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARDWARE_FIXTURES = ROOT / "tests" / "fixtures" / "hardware_runs"
sys.path.insert(0, str(ROOT / "scripts"))

from contract_validation import validate_artifact_set  # noqa: E402


class HardwareReadyValidationTests(unittest.TestCase):
    DESIGN_ARTIFACTS = (
        "hardware-spec.json",
        "architecture-plan.json",
        "source-manifest.json",
        "verification-result.json",
        "implementation-result.json",
    )

    def test_hardware_test_without_result_is_valid_design_complete_state(self) -> None:
        source_run = HARDWARE_FIXTURES / "kv260-watchdog"
        hardware_test = source_run / "hardware-test.json"
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            for name in self.DESIGN_ARTIFACTS:
                shutil.copy2(source_run / name, run_dir / name)
            shutil.copy2(source_run / "debug-map.json", run_dir / "debug-map.json")
            shutil.copy2(hardware_test, run_dir / "hardware-test.json")

            errors = validate_artifact_set(
                run_dir,
                require_evidence_files=False,
                require_hardware=False,
            )

            self.assertEqual(errors, [])

    def test_hardware_test_target_is_checked_without_hardware_result(self) -> None:
        source_run = HARDWARE_FIXTURES / "kv260-watchdog"
        hardware_test_path = source_run / "hardware-test.json"
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            for name in self.DESIGN_ARTIFACTS:
                shutil.copy2(source_run / name, run_dir / name)
            shutil.copy2(source_run / "debug-map.json", run_dir / "debug-map.json")
            hardware_test = json.loads(hardware_test_path.read_text())
            hardware_test["target"]["part"] = "wrong-part"
            (run_dir / "hardware-test.json").write_text(
                json.dumps(hardware_test)
            )

            errors = validate_artifact_set(
                run_dir,
                require_evidence_files=False,
                require_hardware=False,
            )

            self.assertIn(
                "hardware-test target part does not match hardware specification",
                errors,
            )

    def test_require_hardware_rejects_non_pass_result(self) -> None:
        source_run = HARDWARE_FIXTURES / "kv260-watchdog"
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            for name in (
                *self.DESIGN_ARTIFACTS,
                "debug-map.json",
                "hardware-test.json",
                "hardware-validation-result.json",
            ):
                shutil.copy2(source_run / name, run_dir / name)
            result_path = run_dir / "hardware-validation-result.json"
            result = json.loads(result_path.read_text())
            result["status"] = "FAIL"
            result_path.write_text(json.dumps(result))

            errors = validate_artifact_set(
                run_dir,
                require_evidence_files=False,
                require_hardware=True,
            )

            self.assertIn(
                "hardware validation status is FAIL; expected PASS",
                errors,
            )

    def test_hardware_pass_must_use_implementation_owned_image(self) -> None:
        source_run = HARDWARE_FIXTURES / "kv260-watchdog"
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            for name in (
                *self.DESIGN_ARTIFACTS,
                "debug-map.json",
                "hardware-test.json",
                "hardware-validation-result.json",
            ):
                shutil.copy2(source_run / name, run_dir / name)
            result_path = run_dir / "hardware-validation-result.json"
            result = json.loads(result_path.read_text())
            result["programming"]["image_sha256"] = "0" * 64
            result_path.write_text(json.dumps(result))

            errors = validate_artifact_set(
                run_dir,
                require_evidence_files=False,
                require_hardware=True,
            )

            self.assertIn(
                "hardware programming image is not the hash-matched "
                "implementation programming image",
                errors,
            )

    def test_hardware_pass_measurements_must_satisfy_test_plan(self) -> None:
        source_run = HARDWARE_FIXTURES / "kv260-watchdog"
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            for name in (
                *self.DESIGN_ARTIFACTS,
                "debug-map.json",
                "hardware-test.json",
                "hardware-validation-result.json",
            ):
                shutil.copy2(source_run / name, run_dir / name)
            result_path = run_dir / "hardware-validation-result.json"
            result = json.loads(result_path.read_text())
            test = next(
                item
                for item in result["tests"]
                if item["id"] == "HW-CRIT-PASS"
            )
            test["measurements"]["vio.hw_test_pass"] = 0
            result_path.write_text(json.dumps(result))

            errors = validate_artifact_set(
                run_dir,
                require_evidence_files=False,
                require_hardware=True,
            )

            self.assertIn(
                "hardware test HW-CRIT-PASS measurements do not satisfy "
                "the test plan criterion",
                errors,
            )


if __name__ == "__main__":
    unittest.main()
