"""
Tests for the resource-aware scheduler.

Contract:
    Scheduler(parallel=int, memory_budget_gb=float)
    .submit(task) where task has .run(), .estimated_memory_gb (default 1.0)
    .run_all(tasks) -> list[task results in input order]

The scheduler must:
    1. Run tasks in parallel up to *parallel*.
    2. Never have in-flight tasks whose estimated memory sums above the budget.
    3. Preserve input ordering of returned results.
    4. Surface task exceptions as exceptions in the returned slot
       (we use a TaskResult(value, error) wrapper).
"""

from __future__ import annotations

import threading
import time

import pytest

from skills_testing.core.scheduler import Scheduler, Task


class _Recorder:
    def __init__(self):
        self.in_flight = 0
        self.peak = 0
        self.lock = threading.Lock()

    def enter(self):
        with self.lock:
            self.in_flight += 1
            if self.in_flight > self.peak:
                self.peak = self.in_flight

    def leave(self):
        with self.lock:
            self.in_flight -= 1


def _task(rec, idx, mem=1.0, dur=0.05, fail=False):
    def run():
        rec.enter()
        try:
            time.sleep(dur)
            if fail:
                raise RuntimeError(f"boom-{idx}")
            return idx
        finally:
            rec.leave()
    return Task(name=f"t{idx}", run=run, estimated_memory_gb=mem)


def test_returns_results_in_input_order():
    rec = _Recorder()
    tasks = [_task(rec, i, dur=0.01) for i in range(5)]
    sched = Scheduler(parallel=2, memory_budget_gb=8.0)
    results = sched.run_all(tasks)
    assert [r.value for r in results] == [0, 1, 2, 3, 4]


def test_parallelism_capped():
    rec = _Recorder()
    tasks = [_task(rec, i, dur=0.05) for i in range(8)]
    sched = Scheduler(parallel=3, memory_budget_gb=64.0)
    sched.run_all(tasks)
    assert rec.peak <= 3


def test_memory_budget_capped():
    rec = _Recorder()
    # each task claims 4 GB; budget 6 GB; only one at a time should run.
    tasks = [_task(rec, i, mem=4.0, dur=0.05) for i in range(4)]
    sched = Scheduler(parallel=4, memory_budget_gb=6.0)
    sched.run_all(tasks)
    assert rec.peak == 1


def test_oversized_task_still_runs_alone():
    rec = _Recorder()
    tasks = [_task(rec, 0, mem=99.0, dur=0.01)]
    sched = Scheduler(parallel=4, memory_budget_gb=8.0)
    results = sched.run_all(tasks)
    assert results[0].value == 0
    assert results[0].error is None


def test_exception_surfaces_in_result():
    rec = _Recorder()
    tasks = [_task(rec, 0, dur=0.01),
             _task(rec, 1, dur=0.01, fail=True),
             _task(rec, 2, dur=0.01)]
    sched = Scheduler(parallel=2, memory_budget_gb=8.0)
    results = sched.run_all(tasks)
    assert results[0].value == 0
    assert results[1].value is None
    assert "boom-1" in str(results[1].error)
    assert results[2].value == 2
