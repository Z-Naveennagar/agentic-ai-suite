"""
Staggered Vivado MCP concurrent-session validator.

vivado-mcp-server 0.6.9 generates session IDs with second-resolution
timestamps. This validator submits all session launches concurrently, but
worker ``i`` waits ``i * launch_gap_seconds`` before calling ``vivado_start``.
The starts therefore overlap without landing in the same timestamp second.
After every launch finishes, all distinct sessions are probed concurrently and
then stopped.

Usage::

    python tools/vivado_session_validator.py \
        --sessions 18 --launch-gap-seconds 5 --settle-seconds 20

Exit code is 0 only when every requested session receives a distinct ID and
executes its sentinel successfully.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from skills_testing.verifiers.vivado_mcp import (  # noqa: E402
    MCPSession,
    extract_text,
    parse_session_id,
    server_url,
    vivado_path,
)


@dataclass
class Result:
    index: int
    launch_delay_s: float
    started: bool = False
    executed: bool = False
    stopped: bool = False
    session_id: str | None = None
    start_s: float | None = None
    error: str = ""
    cleanup_error: str = ""
    stage: str = "waiting"


_print_lock = threading.Lock()


def _log(message: str) -> None:
    with _print_lock:
        print(message, flush=True)


def _start_session(
    index: int,
    launch_delay: float,
    url: str,
    timeout: int,
    workdir: Path,
) -> tuple[Result, MCPSession | None]:
    result = Result(index=index, launch_delay_s=launch_delay)
    if launch_delay:
        _log(f"  [{index:03d}] waiting {launch_delay:.1f}s before vivado_start")
        time.sleep(launch_delay)

    started_at = time.time()
    sess = MCPSession(url, timeout)
    try:
        result.stage = "initialize"
        sess.initialize()
        result.stage = "vivado_start"
        session_dir = workdir / f"sess_{index:03d}"
        session_dir.mkdir(parents=True, exist_ok=True)
        response = sess.call("vivado_start", {
            "working_dir": str(session_dir),
            "session_type": "vivado",
            "vivado_path": vivado_path(),
            "display_mode": "none",
        })
        text = extract_text(response)
        session_id = parse_session_id(text)
        if not session_id:
            result.error = f"no session_id from vivado_start: {text[:200]}"
            sess.close()
            return result, None
        result.session_id = session_id
        result.started = True
        result.start_s = time.time() - started_at
        result.stage = "started"
        _log(
            f"  [{index:03d}] started sid={session_id} "
            f"after gap={launch_delay:.1f}s (call={result.start_s:.1f}s)"
        )
        return result, sess
    except Exception as exc:  # noqa: BLE001 - preserve every launch result
        result.error = f"{type(exc).__name__} at {result.stage}: {exc}"[:300]
        sess.close()
        return result, None


def _probe(result: Result, sess: MCPSession) -> tuple[bool, str]:
    result.stage = "vivado_execute"
    sentinel = f"VALIDATOR_OK_{result.index}_{time.time_ns()}"
    try:
        response = sess.call("vivado_execute", {
            "session_id": result.session_id,
            "command": f"puts {sentinel}",
        })
        output = extract_text(response)
        if sentinel not in output:
            error = f"execute did not echo sentinel: {output[:180]}"
            result.error = error
            return False, error
        result.executed = True
        result.stage = "ready"
        return True, ""
    except Exception as exc:  # noqa: BLE001 - preserve every probe result
        error = f"{type(exc).__name__} at vivado_execute: {exc}"[:240]
        result.error = error
        return False, error


def _stop(result: Result, sess: MCPSession) -> None:
    try:
        if result.session_id:
            sess.call("vivado_stop", {"session_id": result.session_id})
            result.stopped = True
            result.stage = "done"
    except Exception as exc:  # noqa: BLE001 - cleanup must continue
        result.cleanup_error = f"{type(exc).__name__} at vivado_stop: {exc}"[:300]
    finally:
        sess.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=int, default=18,
                        help="Concurrent launch tasks (default 18)")
    parser.add_argument("--launch-gap-seconds", type=float, default=5.0,
                        help="Gap between vivado_start calls (default 5)")
    parser.add_argument("--settle-seconds", type=float, default=20.0,
                        help="Wait once after all starts finish (default 20)")
    parser.add_argument("--url", default=None,
                        help="MCP URL (default: harness default)")
    parser.add_argument("--timeout", type=int, default=600,
                        help="Per-call timeout seconds")
    parser.add_argument("--workdir", default=None,
                        help="Scratch directory (default: temporary directory)")
    parser.add_argument("--json-out", default=None,
                        help="Write the result table as JSON")
    args = parser.parse_args(argv)

    if args.sessions < 1:
        parser.error("--sessions must be at least 1")
    if args.launch_gap_seconds < 0:
        parser.error("--launch-gap-seconds cannot be negative")
    if args.settle_seconds < 0:
        parser.error("--settle-seconds cannot be negative")

    url = args.url or server_url()
    workdir = Path(args.workdir or tempfile.mkdtemp(prefix="vivado-sess-val-"))
    result_handles: list[tuple[Result, MCPSession]] = []
    total_started_at = time.time()

    print(f"Validator: {args.sessions} staggered concurrent launches -> {url}")
    print(f"Launch gap: {args.launch_gap_seconds:.1f}s")
    print(f"Post-launch settle: {args.settle_seconds:.1f}s")
    print(f"Workdir: {workdir}\n")

    try:
        with ThreadPoolExecutor(max_workers=args.sessions) as executor:
            launches = list(executor.map(
                lambda index: _start_session(
                    index,
                    index * args.launch_gap_seconds,
                    url,
                    args.timeout,
                    workdir,
                ),
                range(args.sessions),
            ))

        results = [result for result, _ in launches]
        result_handles = [
            (result, sess) for result, sess in launches if sess is not None
        ]

        id_counts = Counter(
            result.session_id for result in results if result.session_id
        )
        duplicate_ids = sorted(
            session_id for session_id, count in id_counts.items() if count > 1
        )
        if duplicate_ids:
            for result in results:
                if result.session_id in duplicate_ids:
                    result.error = f"duplicate session_id {result.session_id}"
                    result.stage = "duplicate_id"

        if args.settle_seconds and result_handles:
            _log(
                f"All launches complete; settling {args.settle_seconds:.1f}s "
                "before concurrent probes"
            )
            time.sleep(args.settle_seconds)

        probeable = [
            (result, sess) for result, sess in result_handles
            if result.session_id not in duplicate_ids
        ]
        with ThreadPoolExecutor(max_workers=max(1, len(probeable))) as executor:
            probes = list(executor.map(lambda pair: _probe(*pair), probeable))
        probe_errors = [error for ok, error in probes if not ok]
    finally:
        # The server sustains concurrent execute calls, but a burst of 18 stop
        # calls can disconnect its HTTP process. Teardown sequentially; cleanup
        # throughput is not the capacity being measured.
        for result, sess in result_handles:
            _stop(result, sess)

    wall = time.time() - total_started_at
    started = sum(result.started for result in results)
    unique = len(id_counts)
    executed = sum(result.executed for result in results)
    stopped = sum(result.stopped for result in results)
    passed = (
        started == args.sessions
        and unique == args.sessions
        and executed == args.sessions
        and not duplicate_ids
    )

    print("\n idx  delay  started  exec  stopped  start_s  session_id / error")
    for result in results:
        detail = result.error or result.cleanup_error or result.session_id or ""
        start_s = f"{result.start_s:.1f}" if result.start_s is not None else "-"
        print(
            f"{result.index:>4} {result.launch_delay_s:>6.1f} "
            f"{str(result.started):>8} {str(result.executed):>5} "
            f"{str(result.stopped):>8} {start_s:>8}  {detail[:100]}"
        )
    print(f"\nRequested : {args.sessions}")
    print(f"Started   : {started}")
    print(f"Unique IDs: {unique}")
    print(f"Executed  : {executed}")
    print(f"Stopped   : {stopped}")
    print(f"Wall clock: {wall:.1f}s")

    summary = {
        "requested": args.sessions,
        "started": started,
        "unique_ids": unique,
        "duplicate_ids": duplicate_ids,
        "executed": executed,
        "stopped": stopped,
        "passed": passed,
        "wall_s": round(wall, 1),
        "launch_gap_seconds": args.launch_gap_seconds,
        "settle_seconds": args.settle_seconds,
        "url": url,
        "probe_errors": probe_errors,
        "sessions": [asdict(result) for result in results],
    }
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(summary, indent=2))
        print(f"JSON: {args.json_out}")

    github_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if github_summary:
        verdict = ":white_check_mark: PASS" if passed else ":warning: DEGRADED"
        with open(github_summary, "a") as output:
            output.write("### Vivado staggered concurrent-session validator\n\n")
            output.write("| Requested | Started | Unique IDs | Usable | Stopped | Verdict |\n")
            output.write("|---:|---:|---:|---:|---:|---|\n")
            output.write(
                f"| {args.sessions} | {started} | {unique} | **{executed}** | "
                f"{stopped} | {verdict} |\n\n"
            )
            output.write(
                f"Launches were submitted together and staggered by "
                f"{args.launch_gap_seconds:.1f}s; the final launch began after "
                f"{(args.sessions - 1) * args.launch_gap_seconds:.1f}s.\n\n"
            )
            for result in results:
                if result.error:
                    output.write(f"- `[{result.index:03d}]` {result.error[:180]}\n")
                if result.cleanup_error:
                    output.write(
                        f"- `[{result.index:03d}]` cleanup: "
                        f"{result.cleanup_error[:180]}\n"
                    )

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
