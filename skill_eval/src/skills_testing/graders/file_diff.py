"""
``file_diff`` grader -- generic two-file comparison.

Takes two file references and reports whether their contents match, which
line numbers differ, and a unified diff for human debugging. No
suite-specific assumptions: two files in, a diff out.

Spec (grader_spec.yaml)::

    - id: bd_tcl_consistency
      type: file_diff
      file_a: bd_dump.tcl                     # workspace-relative by default
      file_b: 'outputs/{case_id}/bd_dump.tcl'

*file_a*/*file_b* accept the same ``case://``/``workspace://`` prefixes as
the ``diff`` grader's ``context_dir`` (see ``diff._resolve_ref_dir``); a
bare path defaults to workspace-relative, since the common case is
comparing two files that both live in the same workspace.
"""

from __future__ import annotations

import difflib
from pathlib import Path

from . import Grader, GraderContext, GraderResult, register_grader
from .diff import _resolve_ref_dir


def _resolve(ctx: GraderContext, ref: str) -> Path:
    if ref.startswith("case://") or ref.startswith("workspace://"):
        return _resolve_ref_dir(ctx, ref)
    p = Path(ref)
    return p if p.is_absolute() else ctx.workspace_dir / ref


def _lines(text: str) -> list[str]:
    return text.replace("\r\n", "\n").split("\n")


def _changed_line_numbers(a: list[str], b: list[str]) -> list[int]:
    """1-indexed positions where a[i] != b[i] -- position-based, matching
    the `diff` grader's own _count_changed_lines semantics."""
    out: list[int] = []
    for i in range(max(len(a), len(b))):
        la = a[i] if i < len(a) else None
        lb = b[i] if i < len(b) else None
        if la != lb:
            out.append(i + 1)
    return out


class FileDiffGrader(Grader):
    grader_type = "file_diff"

    def grade(self, spec: dict, ctx: GraderContext) -> GraderResult:
        ref_a = spec.get("file_a")
        ref_b = spec.get("file_b")
        if not ref_a or not ref_b:
            raise ValueError("file_diff grader requires 'file_a' and 'file_b'")

        path_a = _resolve(ctx, ref_a)
        path_b = _resolve(ctx, ref_b)

        missing = [str(p) for p, ref in ((path_a, ref_a), (path_b, ref_b))
                   if not p.exists()]
        if missing:
            return GraderResult(
                passed=False, score=0.0,
                details={"file_a": str(path_a), "file_b": str(path_b),
                          "missing": missing,
                          "feedback": f"file(s) not found: {', '.join(missing)}"},
            )

        text_a = path_a.read_text(errors="replace")
        text_b = path_b.read_text(errors="replace")
        lines_a, lines_b = _lines(text_a), _lines(text_b)

        # Pass/fail and score are DERIVED from the line-number comparison,
        # not computed separately from it -- a raw `text_a == text_b`
        # shortcut would disagree with changed_line_numbers whenever line
        # endings differ (CRLF vs LF): _lines() normalizes those away, so
        # the two checks could otherwise report contradictory verdicts.
        changed = _changed_line_numbers(lines_a, lines_b)
        identical = not changed
        total = max(len(lines_a), len(lines_b), 1)
        score = 1.0 if identical else max(0.0, 1.0 - len(changed) / total)
        diff_text = "" if identical else "\n".join(difflib.unified_diff(
            lines_a, lines_b, fromfile=str(ref_a), tofile=str(ref_b), lineterm="",
        ))

        return GraderResult(
            passed=identical,
            score=score,
            details={
                "file_a": str(path_a), "file_b": str(path_b),
                "identical": identical,
                "changed_line_numbers": changed,
                "diff": diff_text,
                "feedback": (
                    "files are identical" if identical
                    else f"{len(changed)}/{total} line(s) differ"
                ),
            },
        )


register_grader(FileDiffGrader.grader_type, FileDiffGrader())
