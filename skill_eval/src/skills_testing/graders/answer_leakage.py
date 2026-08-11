"""
Answer-leakage grader.

A suite's ``test_cases.yaml`` carries the golden ``expected`` values that
``grader_spec.yaml`` substitutes into ``{token}`` placeholders at grade
time. It is the answer key. An agent that reads it during a run can emit a
perfect output contract without doing any of the work the case is meant to
measure, and every downstream grader will happily score that as a PASS --
the run looks green and the measurement is worthless.

Nothing stages ``test_cases.yaml`` into the workspace (``runtime/workspace.py``
copies only ``inputs/``), but the suite tree is still on the same filesystem
as the agent's cwd -- for the installed layout, ``_workspace/<suite>/``. A
``bash`` / ``read`` / ``grep`` tool call with a path or a glob can reach it,
so "we don't copy it in" is not a containment guarantee.

This grader reads the transcript and fails the case when it sees the file
being accessed. It is deliberately a *detector over the transcript*, not a
sandbox: it cannot prevent the read, only refuse to credit a run that did
it. The complementary hardening (making the file unreadable for the
duration of a run) belongs in the workspace stager, not here.

Sibling answer-key files (``skill_spec.yaml`` -- the older name for the
same file -- and ``grader_spec.yaml``, which embeds the expected values via
its schema) are matched too, since reading either leaks the same answers.
"""

from __future__ import annotations

import re

from . import Grader, GraderContext, GraderResult, register_grader


# Filenames that carry, or resolve to, the golden answers. `skill_spec.yaml`
# is the legacy name for `test_cases.yaml` (still loadable -- see
# core/case_loader.py), so a suite using the old name must be caught too.
_ANSWER_KEY_FILES = ("test_cases.yaml", "skill_spec.yaml", "grader_spec.yaml")

# Match a bare mention of the filename. Deliberately broad: any appearance in
# the transcript is worth failing on, because the transcript records tool
# *calls* -- a `cat .../test_cases.yaml`, a Read tool arg, a grep glob that
# names it. A false positive is a case that merely *mentioned* the file
# without reading it; that is a far cheaper failure than silently crediting a
# run that read the answer key, so the bias is intentional.
_PATTERNS = {
    name: re.compile(re.escape(name), re.IGNORECASE)
    for name in _ANSWER_KEY_FILES
}


def _find_leaks(text: str) -> dict[str, int]:
    """Return {filename: occurrence count} for every answer-key file seen."""
    if not text:
        return {}
    return {
        name: len(pat.findall(text))
        for name, pat in _PATTERNS.items()
        if pat.search(text)
    }


def _excerpt(text: str, name: str, width: int = 160) -> str:
    """One short transcript excerpt around the first hit, for the report.

    Without this the failure reads as an unexplained FAIL; the operator
    needs to see *which* call touched the file to judge whether it was the
    agent or (say) a harness log line that happened to name the path.
    """
    pat = _PATTERNS[name]
    m = pat.search(text or "")
    if not m:
        return ""
    start = max(0, m.start() - width // 2)
    end = min(len(text), m.end() + width // 2)
    return " ".join(text[start:end].split())


class AnswerLeakage(Grader):
    """Fail a case whose transcript shows the suite's answer key being read.

    Spec::

        answer_key_not_read:
          grader: answer_leakage
          always: true
          mandatory: true

    ``mandatory: true`` is the point: a leaked answer must gate the case
    outright (hallucination contract in core/runner.py), not merely subtract
    a few points from a weighted score that could still clear threshold.
    """

    grader_type = "answer_leakage"

    def grade(self, spec: dict, ctx: GraderContext) -> GraderResult:
        args = spec.get("grader_args") or {}
        extra = args.get("extra_files") or []
        haystack = f"{ctx.stdout or ''}\n{ctx.stderr or ''}"

        leaks = _find_leaks(haystack)
        for name in extra:
            pat = re.compile(re.escape(str(name)), re.IGNORECASE)
            if pat.search(haystack):
                leaks[str(name)] = len(pat.findall(haystack))

        if not leaks:
            return GraderResult(
                passed=True, score=1.0,
                details={"reason": "no answer-key file referenced in transcript",
                         "checked": list(_ANSWER_KEY_FILES) + [str(e) for e in extra]},
            )

        first = sorted(leaks)[0]
        names = ", ".join(f"{n} (x{c})" for n, c in sorted(leaks.items()))
        return GraderResult(
            passed=False, score=0.0,
            details={
                "reason": (
                    f"answer-key leakage: the run referenced {names}. "
                    f"test_cases.yaml holds the golden `expected` values this "
                    f"case is graded against, so a run that reads it can "
                    f"reproduce the answer without doing the work -- the "
                    f"result is not a valid measurement and the case is "
                    f"failed regardless of its output."
                ),
                "leaked_files": leaks,
                "excerpt": _excerpt(haystack, first),
            },
        )


register_grader(AnswerLeakage.grader_type, AnswerLeakage())
