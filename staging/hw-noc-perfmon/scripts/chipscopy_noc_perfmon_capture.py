# Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
# Copyright Advanced Micro Devices, Inc. All rights reserved.
"""Capture bounded NoC performance-monitor samples through direct ChipScoPy."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import chipscopy
from chipscopy import create_session, delete_session
from chipscopy.api.noc import NoCPerfMonNodeListener, TC_BER, TC_BEW


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture finite NoC performance-monitor samples with ChipScoPy."
    )
    parser.add_argument("--hw-server-url", required=True)
    parser.add_argument("--cs-server-url", required=True)
    parser.add_argument("--ltx-path", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--node",
        action="append",
        dest="nodes",
        help="Discovered NoC element to monitor. Defaults to the first DDRMC, then NMU.",
    )
    parser.add_argument("--samples", type=int, default=2)
    parser.add_argument("--requested-period-ms", type=float, default=250.0)
    return parser.parse_args()


def choose_period(periods: list[float], requested_period_ms: float) -> float:
    for period in periods:
        if period >= requested_period_ms:
            return period
    return periods[-1]


def select_nodes(enabled: list[str], requested_nodes: list[str] | None) -> list[str]:
    if requested_nodes:
        invalid = sorted(set(requested_nodes) - set(enabled))
        if invalid:
            raise RuntimeError(f"Requested nodes are not enabled: {', '.join(invalid)}")
        return requested_nodes

    ddrmc_nodes = [node for node in enabled if node.upper().startswith("DDRMC")]
    if ddrmc_nodes:
        return [ddrmc_nodes[0]]

    nmu_nodes = [node for node in enabled if "NMU" in node.upper()]
    if nmu_nodes:
        return [nmu_nodes[0]]

    raise RuntimeError("No enabled DDRMC or NMU element is available for measurement")


def sample_tail(values: list[Any], sample_count: int) -> list[Any]:
    return values[-sample_count:] if values else []


def serialize_measurement(
    listener: NoCPerfMonNodeListener,
    selected_nodes: list[str],
    sample_count: int,
) -> list[dict[str, Any]]:
    measurements = []
    for node_name in selected_nodes:
        element = listener.unique_elements.get(node_name.lower())
        if element is None:
            raise RuntimeError(f"No listener data structure exists for {node_name}")
        samples = element.samples
        measurements.append(
            {
                "name": node_name,
                "type": samples["type"],
                "read_bandwidth_bytes_per_s": sample_tail(
                    samples["read_bandwidth"], sample_count
                ),
                "write_bandwidth_bytes_per_s": sample_tail(
                    samples["write_bandwidth"], sample_count
                ),
                "average_read_latency_counts": sample_tail(
                    samples["avg_read_latency"], sample_count
                ),
                "average_write_latency_counts": sample_tail(
                    samples["avg_write_latency"], sample_count
                ),
                "flags": sample_tail(samples["flags"], sample_count),
            }
        )
    return measurements


def main() -> None:
    args = parse_args()
    if args.samples < 1:
        raise ValueError("--samples must be at least 1")
    if not args.ltx_path.is_file():
        raise FileNotFoundError(f"LTX file does not exist: {args.ltx_path}")

    session = create_session(
        hw_server_url=args.hw_server_url,
        cs_server_url=args.cs_server_url,
    )
    try:
        device = session.devices[0]
        device.discover_and_setup_cores(noc_scan=True, ltx_file=str(args.ltx_path))
        if not device.noc_core:
            raise RuntimeError("No NoC performance-monitor core was discovered")

        noc = device.noc_core[0]
        noc.initialize()
        discovery = noc.discover_noc_elements()
        enabled = discovery.get("enabled", [])
        selected_nodes = select_nodes(enabled, args.nodes)
        enumeration = noc.enumerate_noc_elements(selected_nodes, raw_mode=True)
        monitored_nodes = enumeration.get("enabled", [])
        if monitored_nodes != selected_nodes:
            raise RuntimeError(
                "Selected nodes could not be enabled for measurement: "
                f"requested={selected_nodes}, enumerated={monitored_nodes}"
            )

        supported_periods = noc.get_supported_sampling_periods()
        sampling_intervals = {
            domain: choose_period(periods, args.requested_period_ms)
            for domain, periods in supported_periods.items()
            if periods
        }
        if {"NPI", "NoC"} - sampling_intervals.keys():
            raise RuntimeError(
                f"Missing NoC sampling periods: {sorted({'NPI', 'NoC'} - sampling_intervals.keys())}"
            )

        listener = NoCPerfMonNodeListener(
            sampling_intervals,
            args.samples,
            monitored_nodes,
            record_to_file=False,
        )
        session.chipscope_view.add_node_listener(listener)
        noc.configure_monitors(
            set(monitored_nodes),
            sampling_intervals,
            TC_BER | TC_BEW,
            args.samples,
        )

        timeout_seconds = max(sampling_intervals.values()) * args.samples / 1000 + 5
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            session.chipscope_view.run_events()
            if all(
                len(listener.unique_elements[node.lower()].samples["flags"]) >= args.samples
                for node in monitored_nodes
            ):
                break
            time.sleep(0.05)

        measurements = serialize_measurement(listener, monitored_nodes, args.samples)
        capture_complete = all(
            len(measurement["flags"]) == args.samples for measurement in measurements
        )
        result = {
            "method": "direct-chipscopy-nocperfmon",
            "chipscopy_version": chipscopy.__version__,
            "hw_server_url": args.hw_server_url,
            "cs_server_url": args.cs_server_url,
            "traffic_class": "best-effort-read-write",
            "sample_count": args.samples,
            "requested_period_ms": args.requested_period_ms,
            "sampling_intervals_ms": sampling_intervals,
            "enabled_elements": enabled,
            "selected_nodes": monitored_nodes,
            "capture_complete": capture_complete,
            "measurements": measurements,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        if not capture_complete:
            raise RuntimeError(
                f"Timed out before receiving {args.samples} samples for every monitored node"
            )
    finally:
        delete_session(session)


if __name__ == "__main__":
    main()
