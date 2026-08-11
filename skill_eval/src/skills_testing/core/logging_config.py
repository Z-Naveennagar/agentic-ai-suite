"""
Centralized logging setup for the harness.

The codebase has no structured logging today -- diagnostics are ad hoc
print()/sys.stderr.write() calls, which makes a long-running `skills-test
run` (real Vivado + a real coding agent, potentially hours) opaque: no way
to tell what's currently happening, whether a shared-workspace group's
setup/reset/teardown fired, or how long each step took.

Call configure_logging() once, early, from a CLI entrypoint
(customer_cli.py / integration_runner.main()) -- it's idempotent, so
either (or both) calling it is safe. Every module then gets its own
logger via ``logging.getLogger(__name__)``; this just wires format/level/
handlers once on the ``skills_testing`` package logger, and every child
logger propagates up to it.

Level guide used across the harness:
    DEBUG    - per-grader detail, lock wait/acquire, fine-grained state
    INFO     - normal progress a human watching a run wants to see:
               case start/end + status, group setup/reset/teardown firing,
               elapsed time for each (the "performance" signal)
    WARNING  - recoverable problems: a reset/teardown action failed but
               the run continues, a retry, a skipped optional step
    ERROR    - a case/group failed outright (setup failure, CLI invoke
               exception, etc.)

Set ``SKILL_TEST_LOG_LEVEL=DEBUG`` (or pass ``verbose=True``) for the
noisier tier.
"""

from __future__ import annotations

import logging
import os
import sys

_CONFIGURED = False


def configure_logging(*, level: str | None = None, verbose: bool = False) -> None:
    """Wire up the ``skills_testing`` package logger. Safe to call more
    than once (or from more than one entrypoint) -- only the first call
    does anything."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    lvl_name = level or os.environ.get("SKILL_TEST_LOG_LEVEL") or (
        "DEBUG" if verbose else "INFO")
    lvl = getattr(logging, lvl_name.upper(), logging.INFO)

    pkg_logger = logging.getLogger("skills_testing")
    pkg_logger.setLevel(lvl)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    ))
    pkg_logger.addHandler(handler)
    # Don't also hand records to the real root logger (avoids duplicate
    # lines if something else configures logging.basicConfig elsewhere).
    pkg_logger.propagate = False
