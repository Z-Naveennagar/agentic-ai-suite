"""
Resource-aware worker pool.

Each Task has an estimated memory cost. The scheduler runs tasks in
parallel up to *parallel* concurrency, and never has in-flight tasks whose
estimated memory sum exceeds *memory_budget_gb*.

A task that exceeds the whole budget on its own runs alone (otherwise
nothing would ever progress).
"""

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class Task:
    name: str
    run: Callable[[], Any]
    estimated_memory_gb: float = 1.0


@dataclass
class TaskResult:
    name: str
    value: Any = None
    error: Optional[BaseException] = None


class Scheduler:
    def __init__(self, parallel: int = 2, memory_budget_gb: float = 8.0) -> None:
        self.parallel = max(1, int(parallel))
        self.memory_budget_gb = float(memory_budget_gb)
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)
        self._in_flight_mem = 0.0
        self._in_flight_count = 0

    def _admit(self, mem: float) -> None:
        cap = self.memory_budget_gb
        with self._cv:
            while True:
                fits_count = self._in_flight_count < self.parallel
                fits_mem = (
                    self._in_flight_count == 0  # always allow first task in
                    or (self._in_flight_mem + mem) <= cap
                )
                if fits_count and fits_mem:
                    self._in_flight_count += 1
                    self._in_flight_mem += mem
                    return
                self._cv.wait()

    def _release(self, mem: float) -> None:
        with self._cv:
            self._in_flight_count -= 1
            self._in_flight_mem -= mem
            self._cv.notify_all()

    def run_all(self, tasks: list[Task]) -> list[TaskResult]:
        results: list[TaskResult] = [TaskResult(name=t.name) for t in tasks]

        def _wrap(idx: int, t: Task) -> None:
            mem = max(0.0, float(t.estimated_memory_gb))
            self._admit(mem)
            try:
                results[idx].value = t.run()
            except BaseException as exc:  # noqa: BLE001
                results[idx].error = exc
            finally:
                self._release(mem)

        with ThreadPoolExecutor(max_workers=self.parallel) as ex:
            futures: list[Future] = []
            for idx, t in enumerate(tasks):
                futures.append(ex.submit(_wrap, idx, t))
            for f in futures:
                f.result()
        return results
