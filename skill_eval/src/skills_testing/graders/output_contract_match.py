"""
``output_contract_match`` grader -- compare the JSON result an agent emits
against a golden JSON from the test case, field by field, and report anomalies.

The contract
------------
Most suites instruct the agent (via ``runner_spec.yaml``'s
``shared_prompt_prefix``) to end its answer with a JSON object of a mandated
shape -- the *output contract*. This grader:

1. Recovers the agent's final answer text (not the raw transcript) and extracts
   the JSON from it, whether it was emitted raw or inside a ```json fenced
   block (``json ticks``).
2. Deep-compares it against the golden ``expected`` JSON from
   ``test_cases.yaml`` (substituted into ``grader_args`` as e.g.
   ``{expected_output}`` -- whole-value passthrough, like ``config_match``).
3. Reports every anomaly -- missing keys, value mismatches, and (optionally)
   unexpected extra keys -- so the dashboard's grader-score box shows exactly
   where the generated result diverged from golden. A precise match scores 1.0.

A golden value of ``null`` is a **don't-care wildcard**: that field is not
gated at all -- any agent value (or the field being absent) counts as a match.
Use it for fields whose value is run-specific execution telemetry rather than
part of the deterministic contract (e.g. ``tier2_success`` -- whether a second
config-apply tier was reached depends on the run's path, not the outcome).

Fields named in ``semantic_fields`` are compared by an **LLM judge** rather
than literal/tolerant equality -- for free text like ``notes`` where wording
varies but the substance must stay consistent. Each such field is scored 0-100
for consistency with the golden; ``semantic_threshold`` (default 70) is the
pass bar. When no judge is configured (offline / disabled) the field is not
gated, so a missing judge never spuriously fails the contract.

``semantic_fields`` accepts a bare list (generic judging) or -- preferred -- a
mapping of ``path -> intent``, where *intent* is a sentence telling the judge
exactly what to evaluate for THAT field (e.g. ignore how the note is framed,
fail only on a factual contradiction). A mapping value may also be
``{intent, threshold}`` for a per-field pass bar::

    output_contract:
      grader: output_contract_match
      grader_args:
        expected: "{expected_output}"
        semantic_threshold: 70            # default bar for semantic fields
        semantic_fields:
          notes: >
            Judge whether the agent's note is consistent with the golden's
            design rationale (same IP, width, direction, doc grounding).
            Ignore execution narration; fail only on a factual contradiction.

Spec (grader_spec.yaml ``output_schema`` entry)::

    output_contract:
      grader: output_contract_match
      mandatory: true
      grader_args:
        expected: "{expected_output}"   # golden dict from test_cases.yaml
        source: final_response          # final_response (default) | stdout | artifact
        # artifact: outputs/result.json  # when source: artifact
        # allow_extra: true              # extra keys in actual are not failures
"""
from __future__ import annotations

import json
import re
from typing import Any

from . import Grader, GraderContext, GraderResult, register_grader
from .config_match import _compare_value as _tolerant_value_eq
from .trace import final_response_text

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


# ------------------------------------------------------------ JSON extraction


def _try_json(text: str) -> Any:
    try:
        return json.loads(text.strip())
    except (json.JSONDecodeError, ValueError):
        return None


def _json_object_spans(text: str) -> list[str]:
    """Balanced ``{...}`` substrings that independently parse as JSON, in the
    order their closing brace appears.

    Candidate boundaries come from a dumb, quote-oblivious index scan for
    ``{``/``}`` characters, and each candidate is validated with the real
    JSON parser -- deliberately not a hand-rolled string/escape-aware
    tokenizer carrying state across the whole text. Some backends (Copilot's
    bullet-transcript text mode) interleave truncated tool-call command
    previews into the same text we parse: a Tcl ``if {$c eq "..."`` snippet
    or a ``"output":"...`` value cut off mid-string by the CLI's own preview
    truncation leaves a stray unclosed ``{`` or an unterminated quote. A
    single stateful scan over the whole text lets either one permanently
    desync (an unclosed brace never lets a depth counter return to 0; an
    unterminated string leaves "inside a string" latched for everything
    after it), silently hiding the agent's real, well-formed final JSON
    answer that follows. Re-validating each candidate slice with
    ``json.loads`` instead means earlier noise can't poison a later,
    self-contained object -- it either parses or it doesn't.
    """
    opens = [i for i, ch in enumerate(text) if ch == "{"]
    closes = [i for i, ch in enumerate(text) if ch == "}"]
    spans: list[str] = []
    for j in closes:
        for i in reversed([i for i in opens if i <= j]):
            span = text[i:j + 1]
            if _try_json(span) is not None:
                spans.append(span)
                break
    return spans


def extract_json(text: str) -> tuple[Any, str | None]:
    """Return ``(obj, None)`` on success or ``(None, reason)``.

    Preference order: the LAST ```json fenced block, else the LAST balanced
    top-level ``{...}`` object, else the whole text. "Last" because the final
    answer's result object is what matters when earlier ones appear mid-run.
    """
    if not text or not text.strip():
        return None, "no output to parse"
    for block in reversed(_FENCE_RE.findall(text)):
        obj = _try_json(block)
        if isinstance(obj, (dict, list)):
            return obj, None
    for span in reversed(_json_object_spans(text)):
        obj = _try_json(span)
        if isinstance(obj, dict):
            return obj, None
    obj = _try_json(text)
    if isinstance(obj, (dict, list)):
        return obj, None
    return None, "no JSON object found in the agent's output"


# ------------------------------------------------------------ comparison


def _norm(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        f = float(v)
        return str(int(f)) if f == int(f) else str(f)
    # Case-insensitive, and treat whitespace/hyphens as underscores so an IP
    # name like "AXI GPIO" matches the golden "axi_gpio".
    return re.sub(r"[\s\-]+", "_", str(v).strip().lower())


def _vlnv_prefix_match(a: Any, b: Any) -> bool:
    """VLNV tolerance: a golden ``vendor:lib:name`` matches the agent's
    ``vendor:lib:name:version`` (the version suffix agents append). Gated to
    colon-segmented identifiers (>=2 colons) so it never fires on plain values."""
    sa, sb = str(a).strip(), str(b).strip()
    if sa.count(":") >= 2 and sb.startswith(sa + ":"):
        return True
    if sb.count(":") >= 2 and sa.startswith(sb + ":"):
        return True
    return False


def _eq(a: Any, b: Any) -> bool:
    if a == b:
        return True
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_eq(x, y) for x, y in zip(a, b))
    if isinstance(a, (dict, list)) or isinstance(b, (dict, list)):
        return False
    if _vlnv_prefix_match(a, b):
        return True
    # Tolerant scalar compare: numeric fuzz, true/false<->1/0, comma-list
    # element-wise (reused from config_match) then separator/case-insensitive.
    try:
        if _tolerant_value_eq(a, b):
            return True
    except Exception:
        pass
    return _norm(a) == _norm(b)


def _short(v: Any, limit: int = 160) -> Any:
    s = v if isinstance(v, (str, int, float, bool)) or v is None \
        else json.dumps(v, default=str)
    s = str(s)
    return s if len(s) <= limit else s[:limit] + "…"


# ------------------------------------------------------------ semantic compare

# Default judging intent when a semantic field declares none. A field's own
# ``intent`` (from the spec) replaces this, telling the judge exactly what to
# evaluate for THAT field (e.g. "ignore execution narration; fail only on a
# factual contradiction of the design").
_DEFAULT_INTENT = (
    "Judge whether the agent's value is semantically consistent with the "
    "golden: the same substantive facts and claims, with no contradictions. "
    "Different wording, extra detail, or a different order is fine; a factual "
    "contradiction, a missing key claim, or a materially different assertion "
    "is not."
)

_SEMANTIC_PROMPT = (
    "You are grading one field of an AI agent's structured result against a "
    "golden reference for the same field, on a 0-100 consistency scale.\n\n"
    "What to evaluate for this field:\n{intent}\n\n"
    "Field: {path}\n\n"
    "Golden value:\n{golden}\n\n"
    "Agent value:\n{actual}\n\n"
    'Reply with JSON {{"score": <0-100>, "rationale": <one short sentence>}}.'
)


def _as_text(v: Any) -> str:
    return v if isinstance(v, str) else json.dumps(v, default=str, ensure_ascii=False)


def _semantic_compare(exp: Any, act: Any, path: str, judge,
                      threshold: float, intent: str | None = None) -> tuple[bool, dict]:
    """Judge free-text equivalence via the LLM caller, guided by the field's
    ``intent`` (what the judge should evaluate for this specific field). When
    no judge is available (offline / disabled) or the call errors, the field
    is *not* gated -- returns matched with a ``skipped`` note -- so a missing
    judge can never spuriously fail the contract."""
    if judge is None:
        return True, {"path": path, "score": None, "passed": True,
                      "skipped": True, "intent": intent,
                      "rationale": "not evaluated (no LLM judge configured)"}
    prompt = _SEMANTIC_PROMPT.format(
        path=path, golden=_as_text(exp), actual=_as_text(act),
        intent=(intent or _DEFAULT_INTENT))
    try:
        res = judge(prompt) or {}
        score = float(res.get("score", 0.0))
    except Exception as exc:  # judge infra failure -> don't gate on it
        return True, {"path": path, "score": None, "passed": True,
                      "skipped": True, "intent": intent,
                      "rationale": f"judge unavailable, not gated: {exc}"}
    passed = score >= threshold
    return passed, {"path": path, "score": score, "passed": passed,
                    "intent": intent, "rationale": str(res.get("rationale", ""))}


def _compare(exp: Any, act: Any, path: str, acc: dict,
             semantic: dict | None = None, judge=None,
             threshold: float = 70.0) -> None:
    """``semantic`` maps a field path -> {"intent": str|None, "threshold": float}
    for fields judged by the LLM rather than by literal/tolerant equality."""
    if isinstance(exp, dict):
        if not isinstance(act, dict):
            acc["total"] += 1
            acc["mismatches"].append(
                {"path": path or "(root)", "expected": _short(exp),
                 "got": _short(act)})
            return
        for k, v in exp.items():
            p = f"{path}.{k}" if path else k
            if k not in act:
                acc["total"] += 1
                # A golden ``null`` is a don't-care wildcard: it accepts any
                # agent value *and* the field being absent.
                if v is None:
                    acc["matched"] += 1
                else:
                    acc["missing"].append(p)
            else:
                _compare(v, act[k], p, acc, semantic, judge, threshold)
        for k in act:
            if k not in exp:
                acc["extra"].append(f"{path}.{k}" if path else k)
    else:
        acc["total"] += 1
        # Golden ``null`` = don't-care: it matches whatever the agent produced
        # (e.g. tier2_success: null in golden matches an agent's true/false).
        if exp is None:
            acc["matched"] += 1
            return
        # Semantic (LLM-judged) fields -- free text like ``notes`` where a
        # literal/tolerant compare is meaningless.
        if semantic and path in semantic:
            cfg = semantic[path] or {}
            ok, info = _semantic_compare(
                exp, act, path, judge,
                cfg.get("threshold", threshold), cfg.get("intent"))
            acc["semantic"].append(info)
            if ok:
                acc["matched"] += 1
            else:
                acc["mismatches"].append(
                    {"path": path or "(root)", "expected": _short(exp),
                     "got": _short(act), "semantic": True,
                     "rationale": info.get("rationale", "")})
            return
        if _eq(exp, act):
            acc["matched"] += 1
        else:
            acc["mismatches"].append(
                {"path": path or "(root)", "expected": _short(exp),
                 "got": _short(act)})


# ------------------------------------------------------------ grader


class OutputContractMatchGrader(Grader):
    grader_type = "output_contract_match"

    def grade(self, spec: dict, ctx: GraderContext) -> GraderResult:
        expected = spec.get("expected")
        if expected is None:
            expected = spec.get("golden")
        if isinstance(expected, str):
            parsed = _try_json(expected)
            expected = parsed if parsed is not None else expected
        if not isinstance(expected, dict):
            return GraderResult(
                passed=False, score=0.0,
                details={"feedback": "output_contract_match: 'expected' must "
                                     "resolve to a JSON object (golden result)",
                         "extracted": False})

        allow_extra = bool(spec.get("allow_extra", True))
        source = str(spec.get("source", "final_response"))
        try:
            threshold = float(spec.get("semantic_threshold", 70.0))
        except (TypeError, ValueError):
            threshold = 70.0
        # Fields compared semantically via the LLM judge (free text like
        # ``notes``) rather than by literal/tolerant equality. Accepts either a
        # bare list of field paths (generic judging) or a mapping of
        # ``path -> intent`` (a sentence telling the judge what to evaluate for
        # that field) or ``path -> {intent, threshold}`` for a per-field bar.
        semantic = self._parse_semantic_fields(
            spec.get("semantic_fields"), threshold)

        # Recover the actual JSON the agent produced.
        if source == "artifact":
            artifact = spec.get("artifact")
            actual, perr = self._from_artifact(ctx, artifact)
        else:
            text = final_response_text(ctx.stdout, ctx.stderr)
            if not (text and text.strip()):
                text = ctx.stdout or ""
            actual, perr = extract_json(text)

        if actual is None:
            return GraderResult(
                passed=False, score=0.0,
                details={"feedback": f"could not extract JSON result: {perr}",
                         "extracted": False, "source": source})

        acc = {"total": 0, "matched": 0, "mismatches": [],
               "missing": [], "extra": [], "semantic": []}
        _compare(expected, actual, "", acc,
                 semantic=semantic, judge=ctx.llm_caller, threshold=threshold)

        extra = acc["extra"]
        extra_fails = extra if not allow_extra else []
        anomalies = len(acc["mismatches"]) + len(acc["missing"]) + len(extra_fails)
        passed = anomalies == 0
        score = 1.0 if acc["total"] == 0 else acc["matched"] / acc["total"]
        # An extracted-but-diverging result should never score a clean 1.0.
        if not passed:
            score = min(score, 0.99)

        n_fields = acc["total"]
        # Allowed extras are informational, not anomalies -- keep them out of
        # the pass/fail summary (they're still listed in details["extra"] for
        # the report's footnote). Only extras that actually fail the verdict
        # (allow_extra: false) are surfaced here.
        if passed:
            feedback = f"all {n_fields} golden fields match"
        else:
            bits = [f"{acc['matched']}/{n_fields} fields match"]
            if acc["missing"]:
                bits.append(f"{len(acc['missing'])} missing")
            if acc["mismatches"]:
                bits.append(f"{len(acc['mismatches'])} mismatched")
            if extra_fails:
                bits.append(f"{len(extra_fails)} extra (not allowed)")
            feedback = "; ".join(bits)

        return GraderResult(
            passed=passed, score=score,
            details={
                "extracted": True,
                "source": source,
                "matched": acc["matched"],
                "total": n_fields,
                "missing": acc["missing"],
                "mismatches": acc["mismatches"],
                "extra": extra,
                "allow_extra": allow_extra,
                "semantic": acc["semantic"],
                "feedback": feedback,
            })

    @staticmethod
    def _parse_semantic_fields(raw: Any, default_threshold: float) -> dict:
        """Normalise ``semantic_fields`` into ``{path: {intent, threshold}}``.

        Accepts a bare list (``[notes]`` -> generic intent, default threshold),
        a mapping to an intent string (``{notes: "check ..."}``), or a mapping
        to ``{intent, threshold}`` for a per-field pass bar."""
        out: dict[str, dict] = {}
        if not raw:
            return out
        if isinstance(raw, dict):
            items = list(raw.items())
        elif isinstance(raw, list):
            items = [(p, None) for p in raw]
        else:
            return out
        for path, cfg in items:
            intent, th = None, default_threshold
            if isinstance(cfg, str):
                intent = cfg
            elif isinstance(cfg, dict):
                intent = cfg.get("intent")
                if cfg.get("threshold") is not None:
                    try:
                        th = float(cfg["threshold"])
                    except (TypeError, ValueError):
                        th = default_threshold
            out[str(path)] = {"intent": intent, "threshold": th}
        return out

    @staticmethod
    def _from_artifact(ctx: GraderContext, artifact: Any) -> tuple[Any, str | None]:
        if not artifact:
            return None, "source: artifact requires an 'artifact' path"
        path = ctx.workspace_dir / str(artifact)
        if not path.is_file():
            return None, f"artifact not found: {artifact}"
        text = path.read_text()
        obj = _try_json(text)
        if isinstance(obj, dict):
            return obj, None
        return extract_json(text)


register_grader(OutputContractMatchGrader.grader_type, OutputContractMatchGrader())
