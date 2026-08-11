# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from artifact_finalize import (  # noqa: E402
    refresh_hardware,
    refresh_implementation,
    refresh_source,
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ArtifactFinalizeTests(unittest.TestCase):
    def test_source_rejects_volatile_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            source = run_dir / "top.sv"
            source.write_text("module top; endmodule\n")
            manifest = {
                "files": [
                    {"path": "top.sv", "sha256": None},
                    {"path": "final.xsa", "sha256": None},
                ],
                "compile_order": ["top.sv"],
                "elaboration": {"artifacts": [], "logs": []},
                "component_evidence": [],
            }

            changes, errors = refresh_source(manifest, run_dir, True)

            self.assertTrue(any("final.xsa" in error for error in errors))
            self.assertEqual(manifest["files"][0]["sha256"], digest(source))
            self.assertTrue(changes)

    def test_implementation_write_refreshes_existing_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            bitstream = run_dir / "design.bit"
            bitstream.write_bytes(b"bitstream")
            result = {
                "artifacts": [
                    {
                        "kind": "bitstream",
                        "path": "design.bit",
                        "exists": True,
                        "sha256": "0" * 64,
                    }
                ]
            }

            changes, errors = refresh_implementation(result, run_dir, True)

            self.assertEqual(errors, [])
            self.assertTrue(changes)
            self.assertEqual(result["artifacts"][0]["sha256"], digest(bitstream))

    def test_hardware_write_refreshes_programming_and_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            image = run_dir / "design.bit"
            probes = run_dir / "debug.ltx"
            capture = run_dir / "capture.csv"
            log = run_dir / "hardware.log"
            for path, value in (
                (image, b"image"),
                (probes, b"probes"),
                (capture, b"capture"),
                (log, b"log"),
            ):
                path.write_bytes(value)
            result = {
                "programming": {
                    "image": "design.bit",
                    "image_sha256": "0" * 64,
                    "probes_file": "debug.ltx",
                    "probes_sha256": "0" * 64,
                },
                "captures": [
                    {"path": "capture.csv", "sha256": "0" * 64}
                ],
                "artifacts": [
                    {
                        "path": "hardware.log",
                        "exists": True,
                        "sha256": "0" * 64,
                    }
                ],
            }

            changes, errors = refresh_hardware(result, run_dir, True)

            self.assertEqual(errors, [])
            self.assertEqual(len(changes), 4)
            self.assertEqual(result["programming"]["image_sha256"], digest(image))
            self.assertEqual(result["programming"]["probes_sha256"], digest(probes))
            self.assertEqual(result["captures"][0]["sha256"], digest(capture))
            self.assertEqual(result["artifacts"][0]["sha256"], digest(log))


if __name__ == "__main__":
    unittest.main()
