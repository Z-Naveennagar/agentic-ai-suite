"""
Per-test power measurement for self-hosted SLMs.

PowerMeter samples the AMD iGPU/APU "PPT" (Package Power Tracker) hwmon
sensor in a background thread while a test runs, then captures a short
"baseline" sample once the test is over so the dashboard can disclose
how much of the run-time draw was attributable to the workload itself.

The measurement is best-effort:
  - If no AMD PPT sensor is found (e.g. CI box, NVIDIA workstation),
    PowerMeter degrades to a no-op and ``metrics`` returns ``None``.
  - All sysfs reads are unprivileged (the PPT input is world-readable
    on Strix Halo / Phoenix).
  - The sampler runs at 5 Hz to balance accuracy vs CPU overhead.

Typical use::

    with PowerMeter(baseline_seconds=5) as pm:
        invocation = cli.invoke(...)
    # pm.metrics now has avg_active_w / peak_w / baseline_w / samples_n / ...

The returned dict is JSON-serializable and is persisted as the
``power_metrics`` column on ``skill_test_results``.  ``cost_model.annotate_with_cost``
reads it and bills the run at the *measured* average watts instead of
the static ``avg_power_watts`` from ``config.yaml``.
"""
from __future__ import annotations

import glob
import threading
import time
from pathlib import Path
from typing import Any


SAMPLE_HZ = 5.0
SAMPLE_PERIOD_S = 1.0 / SAMPLE_HZ


def _find_ppt_sensor() -> Path | None:
    """Locate the AMD APU package power sensor (label='PPT'), if present."""
    for path in sorted(glob.glob("/sys/class/drm/card*/device/hwmon/hwmon*")):
        label_files = sorted(glob.glob(f"{path}/power*_label"))
        for lf in label_files:
            try:
                with open(lf) as fh:
                    label = fh.read().strip()
            except OSError:
                continue
            if label == "PPT":
                # power1_label -> power1_input
                input_path = Path(lf.replace("_label", "_input"))
                if input_path.exists():
                    return input_path
    return None


def _read_uw(sensor: Path) -> int | None:
    try:
        with open(sensor) as fh:
            return int(fh.read().strip())
    except (OSError, ValueError):
        return None


class PowerMeter:
    """
    Background-sampling context manager for SoC package power.

    Parameters
    ----------
    baseline_seconds:
        After the active phase ends, sample the sensor for this many
        wall-seconds to characterize the post-test idle floor.  Set
        to 0 to skip baseline capture (faster, but cost rows lose the
        idle-vs-active disclosure).
    sensor:
        Optional explicit hwmon path.  Defaults to auto-detection.
    """

    def __init__(self, baseline_seconds: float = 5.0, sensor: Path | None = None):
        self.baseline_seconds = max(float(baseline_seconds), 0.0)
        self.sensor = sensor or _find_ppt_sensor()
        self._samples_uw: list[int] = []
        self._t0: float | None = None
        self._t1: float | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.metrics: dict[str, Any] | None = None

    # context manager ---------------------------------------------------

    def __enter__(self) -> "PowerMeter":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    # lifecycle ---------------------------------------------------------

    def start(self) -> None:
        if self.sensor is None:
            return
        self._t0 = time.monotonic()
        self._stop.clear()
        self._samples_uw.clear()
        self._thread = threading.Thread(
            target=self._sample_loop, name="power-meter", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        if self.sensor is None:
            self.metrics = None
            return
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._t1 = time.monotonic()

        active_samples = list(self._samples_uw)
        active_window = (self._t1 - self._t0) if (self._t0 and self._t1) else 0.0

        baseline_samples: list[int] = []
        baseline_window = 0.0
        if self.baseline_seconds > 0:
            b0 = time.monotonic()
            deadline = b0 + self.baseline_seconds
            while time.monotonic() < deadline:
                v = _read_uw(self.sensor)
                if v is not None:
                    baseline_samples.append(v)
                time.sleep(SAMPLE_PERIOD_S)
            baseline_window = time.monotonic() - b0

        self.metrics = self._summarize(
            active_samples, active_window,
            baseline_samples, baseline_window,
        )

    # internals ---------------------------------------------------------

    def _sample_loop(self) -> None:
        next_t = time.monotonic()
        while not self._stop.is_set():
            v = _read_uw(self.sensor)  # type: ignore[arg-type]
            if v is not None:
                self._samples_uw.append(v)
            next_t += SAMPLE_PERIOD_S
            sleep_for = next_t - time.monotonic()
            if sleep_for > 0:
                self._stop.wait(sleep_for)

    def _summarize(
        self,
        active: list[int], active_s: float,
        baseline: list[int], baseline_s: float,
    ) -> dict[str, Any] | None:
        if not active:
            return None
        avg_active_w = sum(active) / len(active) / 1e6
        peak_w = max(active) / 1e6
        baseline_w: float | None = None
        if baseline:
            baseline_w = sum(baseline) / len(baseline) / 1e6
        return {
            "sensor": str(self.sensor) if self.sensor else None,
            "sample_hz": SAMPLE_HZ,
            "samples_n": len(active),
            "active_window_s": round(active_s, 3),
            "avg_active_w": round(avg_active_w, 3),
            "peak_w": round(peak_w, 3),
            "baseline_samples_n": len(baseline),
            "baseline_window_s": round(baseline_s, 3),
            "baseline_w": round(baseline_w, 3) if baseline_w is not None else None,
            "active_overhead_w": (
                round(avg_active_w - baseline_w, 3)
                if baseline_w is not None else None
            ),
        }


def quick_idle_sample(seconds: float = 3.0) -> dict[str, Any] | None:
    """
    One-shot helper: sample PPT for *seconds* and return a baseline-only
    metrics dict (no active phase).  Useful for ad-hoc CLI tools.
    """
    pm = PowerMeter(baseline_seconds=0.0)
    if pm.sensor is None:
        return None
    samples: list[int] = []
    t0 = time.monotonic()
    deadline = t0 + seconds
    while time.monotonic() < deadline:
        v = _read_uw(pm.sensor)
        if v is not None:
            samples.append(v)
        time.sleep(SAMPLE_PERIOD_S)
    if not samples:
        return None
    return {
        "sensor": str(pm.sensor),
        "sample_hz": SAMPLE_HZ,
        "samples_n": len(samples),
        "window_s": round(time.monotonic() - t0, 3),
        "baseline_w": round(sum(samples) / len(samples) / 1e6, 3),
        "min_w": round(min(samples) / 1e6, 3),
        "max_w": round(max(samples) / 1e6, 3),
    }
