"""
``diff`` grader -- validate expected file edits.

Compares post-execution workspace files against a diff specification, ported
from waza's diff grader. Each expected file may declare:

  * ``snapshot`` -- a reference file whose contents must match exactly, and
  * ``contains`` -- a list of line fragments. A fragment prefixed with ``+``
    (or unprefixed) must appear; a fragment prefixed with ``-`` must NOT
    appear.

The score is ``passed_checks / total_checks`` where each file contributes one
existence check plus one check per snapshot and per contains-fragment.

Spec (grading_spec.yaml)::

    - id: edits_applied
      type: diff
      context_dir: case://snapshots      # base for relative snapshot paths
      update_snapshots: false            # write/refresh snapshots instead of failing
      expected_files:
        - path: src/main.py
          snapshot: main.py.snap
          contains:
            - "+def new_feature("       # must appear
            - "-TODO: remove this"      # must NOT appear
"""

from __future__ import annotations

import os
from pathlib import Path

from . import Grader, GraderContext, GraderResult, register_grader


def _resolve_ref_dir(ctx: GraderContext, ref: str) -> Path:
    """Resolve a ``context_dir`` reference to an absolute directory.

    Supports the same prefixes as the report_schema/oracle graders:
        case://...        -> relative to ctx.case_dir
        workspace://...   -> relative to ctx.workspace_dir
        <bare path>       -> absolute as-is, else relative to ctx.case_dir,
                             else relative to ctx.workspace_dir
    """
    if ref.startswith("case://"):
        base = ctx.case_dir or ctx.workspace_dir
        return (base / ref[len("case://"):])
    if ref.startswith("workspace://"):
        return ctx.workspace_dir / ref[len("workspace://"):]
    p = Path(ref)
    if p.is_absolute():
        return p
    if ctx.case_dir is not None:
        return ctx.case_dir / ref
    return ctx.workspace_dir / ref


def _validate_in_workspace(workspace_dir: Path, rel: str) -> None:
    """Raise ValueError if *rel* escapes *workspace_dir*."""
    ws = workspace_dir.resolve()
    target = (workspace_dir / rel).resolve()
    try:
        target.relative_to(ws)
    except ValueError:
        raise ValueError(f"diff grader: path {rel!r} escapes the workspace")


class DiffGrader(Grader):
    grader_type = "diff"

    def grade(self, spec: dict, ctx: GraderContext) -> GraderResult:
        expected_files = spec.get("expected_files") or []
        if not expected_files:
            raise ValueError(
                "diff grader must have at least one 'expected_files' entry"
            )
        for i, ef in enumerate(expected_files):
            if not ef.get("path"):
                raise ValueError(
                    f"diff grader: expected_files[{i}] missing required 'path'"
                )
            if not ef.get("snapshot") and not ef.get("contains"):
                raise ValueError(
                    f"diff grader: expected_files[{i}] ('{ef['path']}') must "
                    "have 'snapshot' or 'contains'"
                )

        context_dir = spec.get("context_dir")
        update_snapshots = bool(spec.get("update_snapshots", False))
        ctx_dir = _resolve_ref_dir(ctx, context_dir) if context_dir else None

        # Path-containment guard before touching the filesystem.
        for ef in expected_files:
            _validate_in_workspace(ctx.workspace_dir, ef["path"])

        failures: list[str] = []
        snapshot_updates: list[dict] = []
        for ef in expected_files:
            f_failures, update = self._check_file(
                ctx, ef, ctx_dir, update_snapshots,
            )
            failures.extend(f_failures)
            if update is not None:
                snapshot_updates.append(update)

        return self._build_result(
            spec, expected_files, failures, snapshot_updates, update_snapshots, ctx,
        )

    # -- per-file ------------------------------------------------------------

    def _check_file(self, ctx, ef, ctx_dir, update_snapshots):
        path = ef["path"]
        full = ctx.workspace_dir / path
        failures: list[str] = []
        update = None

        if not full.exists():
            failures.append(f"Expected file not found in workspace: {path}")
            if ef.get("snapshot"):
                failures.append(
                    f"Snapshot comparison skipped (file not found): {path}"
                )
            for c in ef.get("contains") or []:
                failures.append(
                    f"Contains check skipped (file not found): {path} -> {c}"
                )
            return failures, update

        actual = full.read_text(errors="replace")

        if ef.get("snapshot"):
            snap_failures, update = self._check_snapshot(
                ef, actual, ctx_dir, update_snapshots,
            )
            failures.extend(snap_failures)

        if ef.get("contains"):
            failures.extend(self._check_contains(ef, actual))

        return failures, update

    def _check_snapshot(self, ef, actual, ctx_dir, update_snapshots):
        snapshot = ef["snapshot"]
        snap_path = Path(snapshot)
        if not snap_path.is_absolute() and ctx_dir is not None:
            snap_path = ctx_dir / snapshot

        if not snap_path.exists():
            if update_snapshots:
                self._write_snapshot(snap_path, actual)
                return [], {
                    "path": ef["path"], "snapshot": snapshot,
                    "status": "created",
                    "lines_changed": _count_changed_lines("", actual),
                }
            return (
                [f"Failed to read snapshot file {snapshot} for {ef['path']}: "
                 "no such file"],
                None,
            )

        expected = snap_path.read_text(errors="replace")
        if actual != expected:
            if update_snapshots:
                self._write_snapshot(snap_path, actual)
                return [], {
                    "path": ef["path"], "snapshot": snapshot,
                    "status": "updated",
                    "lines_changed": _count_changed_lines(expected, actual),
                }
            return (
                [f"File {ef['path']} does not match snapshot {snapshot}"],
                None,
            )

        if update_snapshots:
            return [], {
                "path": ef["path"], "snapshot": snapshot,
                "status": "unchanged", "lines_changed": 0,
            }
        return [], None

    def _check_contains(self, ef, actual):
        failures: list[str] = []
        for fragment in ef["contains"]:
            if not fragment:
                continue
            must_be_present = True
            check = fragment
            if fragment[0] == "+":
                check = fragment[1:]
            elif fragment[0] == "-":
                must_be_present = False
                check = fragment[1:]
            check = check.strip()
            if not check:
                continue
            found = check in actual
            if must_be_present and not found:
                failures.append(
                    f"File {ef['path']} missing expected fragment: {check}"
                )
            elif not must_be_present and found:
                failures.append(
                    f"File {ef['path']} contains fragment that should be "
                    f"absent: {check}"
                )
        return failures

    # -- aggregation ---------------------------------------------------------

    @staticmethod
    def _count_total_checks(expected_files) -> int:
        total = 0
        for ef in expected_files:
            total += 1  # implicit existence check
            if ef.get("snapshot"):
                total += 1
            total += len(ef.get("contains") or [])
        return total

    def _build_result(
        self, spec, expected_files, failures, snapshot_updates,
        update_snapshots, ctx,
    ) -> GraderResult:
        total = self._count_total_checks(expected_files)
        passed_checks = total - len(failures)
        score = (passed_checks / total) if total > 0 else 1.0
        passed = len(failures) == 0

        if failures:
            feedback = "; ".join(failures)
        elif update_snapshots:
            counts = {"updated": 0, "created": 0, "unchanged": 0}
            for su in snapshot_updates:
                counts[su["status"]] = counts.get(su["status"], 0) + 1
            feedback = (
                f"All diff checks passed (snapshots: {counts['updated']} "
                f"updated, {counts['created']} created, "
                f"{counts['unchanged']} unchanged)"
            )
        else:
            feedback = "All diff checks passed"

        return GraderResult(
            passed=passed,
            score=score,
            details={
                "expected_files": [
                    {k: ef[k] for k in ("path", "snapshot", "contains") if ef.get(k)}
                    for ef in expected_files
                ],
                "failures": failures,
                "passed_checks": passed_checks,
                "total_checks": total,
                "workspace_dir": str(ctx.workspace_dir),
                "snapshot_updates": snapshot_updates,
                "feedback": feedback,
            },
        )

    @staticmethod
    def _write_snapshot(snap_path: Path, content: str) -> None:
        snap_path.parent.mkdir(parents=True, exist_ok=True)
        snap_path.write_text(content)


def _count_changed_lines(before: str, after: str) -> int:
    """Position-based count of differing lines (matches waza semantics)."""
    def _norm(s: str) -> list[str]:
        return s.replace("\r\n", "\n").split("\n")

    before_lines = _norm(before)
    after_lines = _norm(after)
    n = max(len(before_lines), len(after_lines))
    changed = 0
    for i in range(n):
        b = before_lines[i] if i < len(before_lines) else None
        a = after_lines[i] if i < len(after_lines) else None
        if b != a:
            changed += 1
    return changed


register_grader(DiffGrader.grader_type, DiffGrader())
