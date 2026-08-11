"""Shared-workspace grouping for suite setup/reset/teardown actions."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

GroupKey = tuple


def suite_key_for(case: Any) -> str:
    return case.suite_id or str(case.case_dir)


@dataclass
class GroupState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    remaining: int = 0
    workspace: Any | None = None
    session_ids: list[str] = field(default_factory=list)
    setup_error: str | None = None
    reset_error: str | None = None
    any_failed: bool = False

    def decrement(self) -> bool:
        self.remaining -= 1
        return self.remaining <= 0


def _normalize_key(key: GroupKey) -> tuple:
    return key if len(key) == 4 else (*key, 0)


class GroupRegistry:
    def __init__(self, session_cap: int | None = None) -> None:
        self._lock = threading.Lock()
        self._groups: dict[GroupKey, GroupState] = {}
        self._shard_of: dict[tuple, int] = {}
        self.session_semaphore = (
            threading.Semaphore(session_cap) if session_cap else None)

    def declare(self, key: GroupKey, count: int = 1) -> None:
        key = _normalize_key(key)
        with self._lock:
            self._groups.setdefault(key, GroupState()).remaining += count

    def get(self, key: GroupKey) -> GroupState | None:
        key = _normalize_key(key)
        with self._lock:
            return self._groups.get(key)

    def assign_shard(self, base_key: tuple, case_id: str, rep: int, shard_idx: int) -> None:
        with self._lock:
            self._shard_of[(*base_key, case_id, rep)] = shard_idx

    def shard_for(self, base_key: tuple, case_id: str, rep: int) -> int:
        with self._lock:
            return self._shard_of.get((*base_key, case_id, rep), 0)

    def sizes(self) -> dict[GroupKey, int]:
        with self._lock:
            return {key: state.remaining for key, state in self._groups.items()}

    def health(self) -> dict[GroupKey, dict]:
        with self._lock:
            return {
                key: {
                    "remaining": state.remaining,
                    "setup_error": state.setup_error,
                    "reset_error": state.reset_error,
                    "session_ids": list(state.session_ids),
                }
                for key, state in self._groups.items()
            }


def build_group_registry(
    cases: list[Any], *, repetitions: int = 1, parallel: int = 1,
    session_cap: int | None = None,
) -> GroupRegistry:
    """Create one group per suite/client/model and optional shard.

    Shards are assigned per (case, repetition) unit, not per case -- so
    repeated runs of the *same* case spread across distinct shards (and
    therefore distinct Vivado sessions) too, up to ``effective_cap``,
    instead of every repetition of a case being forced through the one
    session its case_id landed on.
    """
    effective_cap = max(1, min(parallel, session_cap) if session_cap else parallel)
    per_combo: dict[tuple, list] = {}
    for case in cases:
        if not any((case.setup_action, case.reset_action, case.teardown_action)):
            continue
        for entry in case.invocation.get("clients", []):
            key = (suite_key_for(case), entry["name"], entry["model"])
            per_combo.setdefault(key, []).append(case)

    registry = GroupRegistry(session_cap=effective_cap if session_cap else None)
    if not per_combo:
        return registry
    base_share, remainder = divmod(effective_cap, len(per_combo))
    for combo_idx, base_key in enumerate(sorted(per_combo)):
        combo_units = [
            (case, rep)
            for case in per_combo[base_key]
            for rep in range(repetitions)
        ]
        shards = max(1, min(base_share + (combo_idx < remainder), len(combo_units)))
        for index, (case, rep) in enumerate(combo_units):
            shard = index % shards
            registry.assign_shard(base_key, case.case_id, rep, shard)
            registry.declare((*base_key, shard))
    return registry
