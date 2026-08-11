"""
``trigger`` grader -- detect whether the skill was activated by the agent.

Produces a *trigger probability* in ``[0.0, 1.0]`` from the run transcript
(see :mod:`skills_testing.graders.trace`) and decides pass/fail against a
threshold. Like waza's trigger grader it supports two modes:

    positive  (default)  pass when probability >= threshold
                         (the skill SHOULD have fired for this prompt)
    negative             pass when probability <  threshold
                         (a hard-negative case: the skill should NOT fire)

Spec (grading_spec.yaml)::

    - id: timing_skill_fired
      type: trigger
      skill: timing-closure-prototype   # optional; defaults to run_meta skill
      mode: positive                     # positive | negative (default positive)
      threshold: 0.5                     # default 0.5
"""

from __future__ import annotations

from . import Grader, GraderContext, GraderResult, register_grader
from .trace import detect_skill_activation

_DEFAULT_THRESHOLD = 0.5


def _is_unresolved(v) -> bool:
    """True for a leftover ``"{token}"`` placeholder that never substituted."""
    return isinstance(v, str) and v.strip().startswith("{") and v.strip().endswith("}")


def _candidate_skills(spec: dict) -> list[str]:
    """Collect the skill name(s) a trigger spec targets.

    Accepts a ``skills:`` list and/or a single ``skill:``; ignores unresolved
    ``"{token}"`` placeholders and non-string junk.
    """
    out: list[str] = []
    raw = spec.get("skills")
    if isinstance(raw, str) and not _is_unresolved(raw):
        out.append(raw)
    elif isinstance(raw, (list, tuple)):
        out.extend(s for s in raw if isinstance(s, str) and not _is_unresolved(s))
    one = spec.get("skill")
    if isinstance(one, str) and not _is_unresolved(one) and one not in out:
        out.append(one)
    return out


class TriggerGrader(Grader):
    grader_type = "trigger"

    def grade(self, spec: dict, ctx: GraderContext) -> GraderResult:
        # Arm-aware default: when `mode` is omitted, derive it from the A/B
        # arm so a single spec entry is correct on both. In the with-skill
        # arm the skill SHOULD fire (positive); in the no-skill arm it should
        # NOT (negative). An explicit `mode:` always wins.
        if spec.get("mode") is None:
            with_skill = ctx.run_meta.get("with_skill")
            mode = "negative" if with_skill is False else "positive"
        else:
            mode = str(spec.get("mode")).strip().lower()
        if mode not in ("positive", "negative"):
            raise ValueError(
                f"trigger grader: invalid mode {mode!r} "
                "(must be 'positive' or 'negative')"
            )

        threshold = float(spec.get("threshold", _DEFAULT_THRESHOLD))
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("trigger grader: threshold must be between 0 and 1")

        # Candidate skills: an explicit list (`skills:`, e.g. resolved from a
        # suite `grader_args: '{skills}'`) or a single `skill:`, falling back
        # to the case's own skill. Activation of ANY candidate counts (the
        # strongest signal across them wins). Unresolved "{...}" placeholders
        # are ignored.
        candidates = _candidate_skills(spec) or [ctx.run_meta.get("skill_name")]

        evidence = None
        probability = 0.0
        client = ctx.run_meta.get("client")
        for cand in candidates:
            ev = detect_skill_activation(
                ctx.stdout, ctx.stderr, skill_name=cand, client=client,
            )
            if evidence is None or ev.probability > probability:
                evidence, probability = ev, ev.probability
        skill_name = evidence.matched_skill or (
            candidates[0] if candidates else None
        )

        if mode == "positive":
            passed = probability >= threshold
            if passed:
                feedback = (
                    f"Skill activated (trigger probability {probability:.2f} "
                    f">= {threshold:.2f})"
                )
            else:
                feedback = (
                    f"Skill not activated (trigger probability {probability:.2f} "
                    f"< {threshold:.2f})"
                )
        else:  # negative
            passed = probability < threshold
            if passed:
                feedback = (
                    f"Skill correctly stayed dormant (trigger probability "
                    f"{probability:.2f} < {threshold:.2f})"
                )
            else:
                feedback = (
                    f"Skill activated unexpectedly (trigger probability "
                    f"{probability:.2f} >= {threshold:.2f})"
                )

        # Score is the trigger probability itself in positive mode, and its
        # complement in negative mode, so a higher score always means "more
        # aligned with the expectation".
        score = probability if mode == "positive" else (1.0 - probability)

        return GraderResult(
            passed=passed,
            score=score,
            details={
                "mode": mode,
                "threshold": threshold,
                "skill": skill_name,
                "trigger_probability": probability,
                "matched_skill": evidence.matched_skill,
                "signals": evidence.signals,
                "feedback": feedback,
            },
        )


register_grader(TriggerGrader.grader_type, TriggerGrader())
