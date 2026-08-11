#!/usr/bin/env python3
# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

"""Generate deterministic portable VIO/ILA plans for every KV260 evaluation case."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
CASES_ROOT = ROOT / "evals" / "designs"
SCHEMA_PATH = ROOT / "contracts" / "hardware-test.schema.json"

ADAPTERS = {
    "kv260_adaptive_threshold": "ps_dma",
    "kv260_alpha_overlay": "ps_dma",
    "kv260_async_fifo": "dual_clock_vio",
    "kv260_audio_channel_router": "vio_native",
    "kv260_audio_dc_blocker": "vio_native",
    "kv260_audio_fir_equalizer": "vio_native",
    "kv260_audio_gain": "vio_native",
    "kv260_audio_mute_ramp": "vio_native",
    "kv260_audio_peak_meter": "vio_native",
    "kv260_audio_tone_generator": "vio_native",
    "kv260_av_timestamp": "vio_native",
    "kv260_axi_lite_regs": "jtag_axi",
    "kv260_axi_traffic_monitor": "jtag_axi",
    "kv260_axis_packetizer": "ps_dma",
    "kv260_axis_register_slice": "ps_dma",
    "kv260_bayer_demosaic": "ps_dma",
    "kv260_bram_scratchpad": "vio_native",
    "kv260_camera_audio_synchronizer": "onchip_video_generator",
    "kv260_color_correction": "ps_dma",
    "kv260_crc32_stream": "ps_dma",
    "kv260_ddr_bandwidth_exerciser": "ps_dma",
    "kv260_debounce_counter": "vio_native",
    "kv260_dma_descriptor_queue": "ps_dma",
    "kv260_dma_loopback": "ps_dma",
    "kv260_fir_filter": "vio_native",
    "kv260_frame_buffer_path": "ps_dma",
    "kv260_frame_statistics": "onchip_video_generator",
    "kv260_gamma_lut": "ps_dma",
    "kv260_i2s_receiver": "vio_native",
    "kv260_i2s_transmitter": "vio_native",
    "kv260_image_histogram": "ps_dma",
    "kv260_interrupt_aggregator": "vio_native",
    "kv260_linux_gpio_mailbox": "jtag_axi",
    "kv260_mipi_capture_pipeline": "external_video_with_synthetic_fallback",
    "kv260_morphology_3x3": "ps_dma",
    "kv260_motion_detector": "onchip_video_generator",
    "kv260_multimedia_appliance": "ps_dma",
    "kv260_object_bounding_box": "ps_dma",
    "kv260_pl_counter": "vio_native",
    "kv260_pwm_generator": "vio_native",
    "kv260_raw10_unpacker": "ps_dma",
    "kv260_rgb_to_grayscale": "ps_dma",
    "kv260_sobel_filter": "ps_dma",
    "kv260_stereo_mixer": "vio_native",
    "kv260_sync_fifo": "vio_native",
    "kv260_video_cropper": "ps_dma",
    "kv260_video_scaler": "ps_dma",
    "kv260_video_test_pattern": "onchip_video_generator",
    "kv260_vision_pipeline": "external_video_with_synthetic_fallback",
    "kv260_watchdog_irq": "vio_native",
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def capabilities(adapter: str) -> list[str]:
    result = ["jtag", "vivado_hw_manager", "ila", "vio"]
    if adapter == "jtag_axi":
        result.append("jtag_axi")
    elif adapter == "ps_dma":
        result.extend(["ssh", "ps_software", "dma"])
    elif adapter in {"onchip_video_generator", "external_video_with_synthetic_fallback"}:
        result.append("onchip_generator")
    return result


def stimulus(adapter: str) -> dict:
    if adapter == "jtag_axi":
        control, data = "jtag_axi", "jtag_axi"
        description = "Use JTAG-to-AXI for deterministic register transactions; VIO controls the test shell and System ILA observes protocol activity."
    elif adapter == "ps_dma":
        control, data = "ssh", "dma"
        description = "Use PS software and DMA for deterministic high-rate traffic; VIO starts the test shell and System ILA observes the data path."
    elif adapter == "onchip_video_generator":
        control, data = "vio", "onchip_generator"
        description = "Use the on-chip video generator for board-independent stimulus; VIO configures and starts it while System ILA captures output."
    elif adapter == "external_video_with_synthetic_fallback":
        control, data = "vio", "onchip_generator"
        description = "Use a mandatory synthetic on-chip video path for portable self-test; an external camera/display path is an optional equipment-qualified extension."
    else:
        control, data = "vio", "vio"
        description = "Use VIO for low-rate deterministic native stimulus and status; ILA captures cycle-accurate DUT activity."
    return {
        "adapter": adapter,
        "control_plane": control,
        "data_plane": data,
        "seed": 1,
        "description": description,
    }


def clock_domains(case: dict, adapter: str) -> list[str]:
    ports = case["public_interface"]["modules"][0]["ports"]
    clocks = [port["name"] for port in ports if "clk" in port["name"].lower()]
    if adapter == "dual_clock_vio":
        return clocks or ["wr_clk", "rd_clk"]
    return [clocks[0] if clocks else "pl_clk0"]


def vio_core(index: int, clock: str) -> dict:
    suffix = str(index)
    return {
        "id": f"VIO-HW-TEST-{suffix}",
        "clock_domain": clock,
        "controls": [
            {
                "name": "hw_test_reset",
                "width": 1,
                "source": "hardware test shell",
                "purpose": "Hold the test shell in a known safe state.",
                "safe_initial_value": "0x1",
            },
            {
                "name": "hw_test_start",
                "width": 1,
                "source": "hardware test shell",
                "purpose": "Start one deterministic self-test transaction.",
                "safe_initial_value": "0x0",
            },
            {
                "name": "hw_test_enable",
                "width": 1,
                "source": "hardware test shell",
                "purpose": "Enable stimulus generation without changing the public DUT interface.",
                "safe_initial_value": "0x0",
            },
        ],
        "status": [
            {
                "name": "hw_test_busy",
                "width": 1,
                "source": "hardware test shell",
                "purpose": "Report an active hardware test.",
            },
            {
                "name": "hw_test_done",
                "width": 1,
                "source": "hardware test shell",
                "purpose": "Report bounded test completion.",
            },
            {
                "name": "hw_test_pass",
                "width": 1,
                "source": "hardware test shell",
                "purpose": "Report aggregate mandatory-criterion status.",
            },
            {
                "name": "hw_test_error_code",
                "width": 16,
                "source": "hardware test shell",
                "purpose": "Identify the first failed hardware criterion.",
            },
        ],
    }


def ila_core(index: int, clock: str, adapter: str, module: str) -> dict:
    kind = "system_ila" if adapter in {
        "jtag_axi",
        "ps_dma",
        "onchip_video_generator",
        "external_video_with_synthetic_fallback",
    } else "ila"
    return {
        "id": f"ILA-HW-TEST-{index}",
        "clock_domain": clock,
        "kind": kind,
        "depth": 1024,
        "probes": [
            {
                "name": "hw_test_start",
                "width": 1,
                "source": "hardware test shell",
                "purpose": "Trigger on the accepted test start.",
                "role": "trigger",
            },
            {
                "name": "hw_test_activity",
                "width": 1,
                "source": module,
                "purpose": "Show cycle-accurate DUT activity in this clock domain.",
                "role": "data",
            },
            {
                "name": "hw_test_done",
                "width": 1,
                "source": "hardware test shell",
                "purpose": "Correlate completion with observed activity.",
                "role": "status",
            },
            {
                "name": "hw_test_pass",
                "width": 1,
                "source": "hardware test shell",
                "purpose": "Capture the final self-check result.",
                "role": "status",
            },
            {
                "name": "hw_test_error_code",
                "width": 16,
                "source": "hardware test shell",
                "purpose": "Capture deterministic failure classification.",
                "role": "status",
            },
        ],
        "trigger": {
            "probe": "hw_test_start",
            "condition": "eq1'bR",
            "position": 128,
        },
    }


def actions() -> list[dict]:
    records = [
        ("PRECHECK", "precheck_target", 30, "Verify target identity, declared capabilities, and artifact hashes."),
        ("QUIESCE", "quiesce", 30, "Stop or isolate software and drivers that can access the PL."),
        ("PROGRAM", "program", 120, "Program the authorized image through the selected backend."),
        ("REFRESH", "refresh_debug", 30, "Associate the matching .ltx and inventory actual debug cores and probes."),
        ("RESET", "reset_vio", 10, "Synchronize and reset VIO outputs to safe initial values."),
        ("IMMEDIATE", "capture_immediate", 60, "Run a bounded immediate ILA capture as a debug-connectivity check."),
        ("CONFIGURE", "configure_stimulus", 30, "Configure the deterministic stimulus adapter and seed."),
        ("ARM", "arm_ila", 30, "Configure and arm the functional ILA trigger."),
        ("START", "start", 10, "Drive the VIO start transition in a separate Hardware Manager operation."),
        ("WAIT", "wait_done", 120, "Wait for bounded VIO or software completion."),
        ("STATUS", "read_status", 30, "Read busy, done, pass, and error-code status."),
        ("UPLOAD", "upload_ila", 60, "Upload and export ILA capture data."),
        ("EVALUATE", "evaluate", 30, "Evaluate every mandatory criterion independently."),
        ("CLEANUP", "cleanup", 30, "Restore safe VIO values and stop test software."),
    ]
    return [
        {
            "id": f"HW-ACT-{identifier}",
            "action": action,
            "timeout_seconds": timeout,
            "description": description,
        }
        for identifier, action, timeout, description in records
    ]


def criteria() -> list[dict]:
    return [
        {"id": "HW-CRIT-TARGET", "mandatory": True, "measurement": "target.part_matches", "operator": "equals", "expected": True},
        {"id": "HW-CRIT-DEBUG", "mandatory": True, "measurement": "debug.required_cores_present", "operator": "equals", "expected": True},
        {"id": "HW-CRIT-IMMEDIATE", "mandatory": True, "measurement": "ila.immediate_capture_samples", "operator": "greater_or_equal", "expected": 1},
        {"id": "HW-CRIT-DONE", "mandatory": True, "measurement": "vio.hw_test_done", "operator": "equals", "expected": 1},
        {"id": "HW-CRIT-PASS", "mandatory": True, "measurement": "vio.hw_test_pass", "operator": "equals", "expected": 1},
        {"id": "HW-CRIT-ERROR", "mandatory": True, "measurement": "vio.hw_test_error_code", "operator": "equals", "expected": 0},
        {"id": "HW-CRIT-CAPTURE", "mandatory": True, "measurement": "ila.functional_capture", "operator": "exists", "expected": True},
    ]


def equipment(case_id: str) -> list[dict]:
    if case_id == "kv260_mipi_capture_pipeline":
        return [
            {
                "kind": "MIPI camera module",
                "target_kind": "camera",
                "required": False,
                "required_capabilities": ["live_video", "v4l2_capture"],
                "purpose": "Optional physical-sensor qualification beyond the mandatory synthetic self-test.",
            }
        ]
    if case_id == "kv260_vision_pipeline":
        return [
            {
                "kind": "MIPI camera module",
                "target_kind": "camera",
                "required": False,
                "required_capabilities": ["live_video", "v4l2_capture"],
                "purpose": "Optional physical capture-path qualification.",
            },
            {
                "kind": "HDMI display or analyzer",
                "target_kind": "display",
                "required": False,
                "required_capabilities": ["video_output"],
                "purpose": "Optional physical display-path qualification.",
            },
        ]
    return []


def make_plan(case: dict) -> dict:
    case_id = case["id"]
    adapter = ADAPTERS[case_id]
    module = case["public_interface"]["modules"][0]["name"]
    clocks = clock_domains(case, adapter)
    return {
        "schema_version": 1,
        "case_id": case_id,
        "revision": 1,
        "status": "READY",
        "owner": "amd_soc_hardware_validator",
        "standard_profile": "portable-vio-ila-v1",
        "target": {
            "part": case["target"]["part"],
            "board_part": case["target"].get("board_part"),
        },
        "required_capabilities": capabilities(adapter),
        "programming": {
            "accepted_backends": ["vivado_hw_manager", "linux_fpga_manager"],
            "require_matching_ltx": True,
            "requires_xsa": True,
        },
        "stimulus": stimulus(adapter),
        "instrumentation": {
            "vio_cores": [vio_core(index, clock) for index, clock in enumerate(clocks)],
            "ila_cores": [ila_core(index, clock, adapter, module) for index, clock in enumerate(clocks)],
            "debug_map_required": True,
        },
        "test_sequence": actions(),
        "pass_criteria": criteria(),
        "cleanup": {
            "required": True,
            "actions": ["reset_vio_outputs", "stop_test_software", "restore_safe_state"],
        },
        "external_equipment": equipment(case_id),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate committed plans without rewriting them")
    args = parser.parse_args()
    schema = read_json(SCHEMA_PATH)
    validator = jsonschema.validators.validator_for(schema)(schema)
    failures = 0
    generated = 0
    for case_file in sorted(CASES_ROOT.glob("kv260_*/case.json")):
        case = read_json(case_file)
        if case["id"] not in ADAPTERS:
            print(f"ERROR: missing hardware adapter for {case['id']}", file=sys.stderr)
            failures += 1
            continue
        output = case_file.parent / "hardware-test.json"
        if args.check:
            if not output.is_file():
                print(f"ERROR: missing {output.relative_to(ROOT)}", file=sys.stderr)
                failures += 1
                continue
            try:
                plan = read_json(output)
            except (OSError, json.JSONDecodeError) as exc:
                print(f"ERROR: {output.relative_to(ROOT)}: {exc}", file=sys.stderr)
                failures += 1
                continue
            errors = list(validator.iter_errors(plan))
            semantic_errors = []
            if plan.get("case_id") != case["id"]:
                semantic_errors.append("case_id does not match case.json")
            if plan.get("target", {}).get("part") != case["target"]["part"]:
                semantic_errors.append("target part does not match case.json")
            if plan.get("target", {}).get("board_part") != case["target"].get("board_part"):
                semantic_errors.append("target board_part does not match case.json")
            if plan.get("stimulus", {}).get("adapter") != ADAPTERS[case["id"]]:
                semantic_errors.append("stimulus adapter does not match the adapter registry")
            for error in errors:
                semantic_errors.append(error.message)
            for message in semantic_errors:
                print(f"ERROR: {case['id']}: {message}", file=sys.stderr)
            if semantic_errors:
                failures += 1
        else:
            expected = make_plan(case)
            errors = list(validator.iter_errors(expected))
            if errors:
                for error in errors:
                    print(f"ERROR: {case['id']}: {error.message}", file=sys.stderr)
                failures += 1
                continue
            text = json.dumps(expected, indent=2, sort_keys=True) + "\n"
            output.write_text(text)
        generated += 1
    if set(ADAPTERS) != {
        path.parent.name for path in CASES_ROOT.glob("kv260_*/case.json")
    }:
        print("ERROR: hardware adapter map and KV260 case set differ", file=sys.stderr)
        failures += 1
    if failures:
        return 1
    print(f"PASS: {generated} KV260 hardware test plans {'checked' if args.check else 'generated'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
