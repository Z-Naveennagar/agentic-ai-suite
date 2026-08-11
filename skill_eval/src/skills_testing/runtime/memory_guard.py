"""
Reactive memory backpressure for case invocations.

Sharded shared-workspace suites (see suite_lifecycle.py) can run several
concurrent Vivado sessions under a single ``--parallel`` value -- something
that never happened before sharding existed, when a shared-workspace suite
always ran exactly one session at a time regardless of ``--parallel``. A
suite whose cases vary widely in weight (e.g. ip-configurator's plain
AXI GPIO cells vs. its MIPI CSI-2 RX / VISP subsystem cases) can now line
up several of its *heaviest* cases running at once, spiking real memory
use well above anything a single-session run ever produced -- observed in
practice to be enough to trip the host's own resource limits and restart
the whole session, taking every process in it down together (this
harness's, and anything else running alongside it).

This is a reactive safety valve, not a static per-case cost model: rather
than trying to hand-classify which cases are "heavy" (fragile, and the
suite author already tried to avoid needing this -- see the multi-model
comment in ip-configurator's runner_spec.yaml), it checks real available
memory immediately before each case invocation and makes that case wait
for headroom to free up if another concurrent case is currently using it,
instead of piling on.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_CGROUP_CURRENT = Path("/sys/fs/cgroup/memory.current")
_CGROUP_MAX = Path("/sys/fs/cgroup/memory.max")
_MEMINFO = Path("/proc/meminfo")


def available_memory_gb() -> Optional[float]:
    """Best-effort real available memory, in GB.

    Prefers the cgroup v2 view (``memory.max - memory.current``) when the
    cgroup isn't unlimited, since that's the actual ceiling a container is
    bounded by -- ``/proc/meminfo``'s host-wide ``MemAvailable`` can read
    as having plenty of room while the *container's own* limit is already
    tight. Falls back to ``/proc/meminfo`` when cgroup limits aren't set
    or aren't readable. Returns ``None`` when neither is available, so
    callers can fail open rather than block forever on an unknown number.
    """
    try:
        if _CGROUP_MAX.exists() and _CGROUP_CURRENT.exists():
            max_raw = _CGROUP_MAX.read_text().strip()
            if max_raw != "max":
                limit = int(max_raw)
                current = int(_CGROUP_CURRENT.read_text().strip())
                return max(0.0, (limit - current) / 1e9)
    except (OSError, ValueError):
        pass

    try:
        for line in _MEMINFO.read_text().splitlines():
            if line.startswith("MemAvailable:"):
                kb = int(line.split()[1])
                return kb / 1e6
    except (OSError, ValueError, IndexError):
        pass

    return None


def wait_for_headroom(
    min_free_gb: float,
    *,
    poll_interval_s: float = 5.0,
    max_wait_s: float = 300.0,
    label: str = "",
) -> None:
    """Block the calling thread until at least *min_free_gb* is free, or
    give up and proceed anyway after *max_wait_s*.

    ``min_free_gb <= 0`` disables the check entirely (a no-op return) --
    this is how callers turn the guard off when it isn't configured.
    Fails open on an unreadable memory reading (``available_memory_gb()``
    returns ``None``): better to run without this safety net than to hang
    a case indefinitely on a number we can't determine.
    """
    if min_free_gb <= 0:
        return

    deadline = time.monotonic() + max_wait_s
    logged_wait = False
    while True:
        avail = available_memory_gb()
        if avail is None or avail >= min_free_gb:
            return
        if time.monotonic() >= deadline:
            logger.warning(
                "%s: proceeding after %.0fs without reaching the %.1fGB "
                "memory headroom target (last seen: %.1fGB free) -- "
                "another concurrent case may still be using it",
                label, max_wait_s, min_free_gb, avail,
            )
            return
        if not logged_wait:
            logger.info(
                "%s: waiting for %.1fGB free memory (currently %.1fGB) "
                "before starting -- another concurrent case is likely "
                "mid-elaboration",
                label, min_free_gb, avail,
            )
            logged_wait = True
        time.sleep(poll_interval_s)
